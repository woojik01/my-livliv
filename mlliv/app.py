from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDockWidget, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QSlider, QSplitter, QStatusBar, QTabWidget, QToolBar, QVBoxLayout, QWidget,
)

from .core import GROUPS, ImageDocument, Layer, composite_image, remove_border_background, validate_image_size
from .package_io import export_livliv, load_project, save_project
from .player_preview import LocalPreviewServer, PreviewBuildWorker, snapshot_document


GROUP_LABELS = {
    "head": "머리 (head)",
    "body": "몸 (body)",
    "hair_back": "뒷머리 (hair_back)",
    "hair_side": "옆머리 (hair_side)",
    "hair_front": "앞머리 (hair_front)",
    "hair_inner": "안쪽 머리 (hair_inner)",
}


class ImageCanvas(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(480, 400)
        self.setMouseTracking(True)
        self.document: ImageDocument | None = None
        self.selected_index = 0
        self.mode = "paint"
        self.brush_size = 28
        self.turn = 0
        self.on_edit_start = None
        self.on_head_box = None
        self.on_status = None
        self._last: QPointF | None = None
        self._head_start: QPointF | None = None
        self._head_end: QPointF | None = None
        self._drawing = False
        self._cache_revision = -1
        self._cache_turn = 999
        self._cache = QImage()

    def set_document(self, document: ImageDocument | None) -> None:
        self.document = document
        self._cache_revision = -1
        self.update()

    def set_turn(self, value: int) -> None:
        if self.turn != value:
            self.turn = value
            self._cache_revision = -1
            self.update()

    def invalidate(self) -> None:
        self._cache_revision = -1
        self.update()

    def _canvas_rect(self) -> QRectF:
        if not self.document:
            return QRectF()
        margin = 28
        scale = min((self.width() - margin * 2) / self.document.width,
                    (self.height() - margin * 2) / self.document.height)
        w = self.document.width * scale
        h = self.document.height * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _image_point(self, point: QPointF) -> QPointF:
        rect = self._canvas_rect()
        if rect.isEmpty():
            return QPointF()
        x = (point.x() - rect.x()) * self.document.width / rect.width()
        y = (point.y() - rect.y()) * self.document.height / rect.height()
        return QPointF(max(0, min(self.document.width - 1, x)), max(0, min(self.document.height - 1, y)))

    def _preview(self) -> QImage:
        if not self.document:
            return QImage()
        if self._cache_revision != self.document.revision or self._cache_turn != self.turn:
            self._cache = composite_image(self.document, self.turn)
            self._cache_revision = self.document.revision
            self._cache_turn = self.turn
        return self._cache

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#121a24"))
        if not self.document:
            painter.setPen(QColor("#c8d2df"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "이미지를 열어 시작하세요\n단색 배경 추출과 마스크 브러시를 지원합니다.")
            painter.end()
            return
        rect = self._canvas_rect()
        tile = QImage(16, 16, QImage.Format.Format_RGB32)
        tile.fill(QColor("#e8ebef"))
        tp = QPainter(tile)
        tp.fillRect(QRect(0, 0, 8, 8), QColor("#cfd5dd"))
        tp.fillRect(QRect(8, 8, 8, 8), QColor("#cfd5dd"))
        tp.end()
        painter.fillRect(rect, QColor("#e8ebef"))
        painter.save()
        painter.setClipRect(rect)
        painter.fillRect(rect, QBrush(QPixmap.fromImage(tile)))
        painter.drawImage(rect, self._preview())
        if self.document.head_box:
            x0, y0, x1, y1 = self.document.head_box
            head_rect = QRectF(rect.x() + x0 * rect.width() / self.document.width,
                               rect.y() + y0 * rect.height() / self.document.height,
                               (x1 - x0) * rect.width() / self.document.width,
                               (y1 - y0) * rect.height() / self.document.height)
            painter.setPen(QPen(QColor("#ffd166"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(head_rect)
        if self._head_start and self._head_end:
            a, b = self._view_point(self._head_start), self._view_point(self._head_end)
            painter.setPen(QPen(QColor("#46e6b2"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(a, b).normalized())
        painter.restore()
        if self.turn:
            painter.setPen(QColor("#d4dce7"))
            painter.drawText(16, 24, f"임시 2D 회전 미리보기 {self.turn:+d}°")
        painter.end()

    def _view_point(self, image_point: QPointF) -> QPointF:
        rect = self._canvas_rect()
        return QPointF(rect.x() + image_point.x() * rect.width() / self.document.width,
                       rect.y() + image_point.y() * rect.height() / self.document.height)

    def mousePressEvent(self, event) -> None:
        if not self.document or event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._image_point(event.position())
        if self.mode == "head":
            self._head_start = point
            self._head_end = point
            self._drawing = True
            self.update()
            return
        if not 0 <= self.selected_index < len(self.document.layers):
            return
        if self.on_edit_start:
            self.on_edit_start()
        self._drawing = True
        self._last = point
        self._paint_segment(point, point)

    def mouseMoveEvent(self, event) -> None:
        if not self.document or not self._drawing:
            return
        point = self._image_point(event.position())
        if self.mode == "head":
            self._head_end = point
            self.update()
            return
        if self._last is not None:
            self._paint_segment(self._last, point)
            self._last = point

    def mouseReleaseEvent(self, event) -> None:
        if not self._drawing or event.button() != Qt.MouseButton.LeftButton:
            return
        self._drawing = False
        if self.mode == "head" and self._head_start and self._head_end:
            a, b = self._head_start, self._head_end
            box = (int(min(a.x(), b.x())), int(min(a.y(), b.y())),
                   int(max(a.x(), b.x())) + 1, int(max(a.y(), b.y())) + 1)
            if box[2] - box[0] >= 8 and box[3] - box[1] >= 8:
                self.document.head_box = box
                self.document.touch()
                if self.on_head_box:
                    self.on_head_box(box)
            else:
                if self.on_status:
                    self.on_status("머리 앵커를 지정하려면 가로·세로 8px 이상으로 드래그하세요.")
            self._head_start = self._head_end = None
        self.invalidate()
        self.changed.emit()

    def _paint_segment(self, start: QPointF, end: QPointF) -> None:
        layer = self.document.layers[self.selected_index]
        painter = QPainter(layer.mask)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        value = 0 if self.mode == "erase" else 255
        pen = QPen(QColor(value, value, value), self.brush_size,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()
        self.document.touch()
        self._cache_revision = -1
        self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My LivLiv v0.1.0 — 로컬 2.5D 제작기")
        self.resize(1440, 900)
        self.document: ImageDocument | None = None
        self.project_path: Path | None = None
        self.dirty = False
        self.selected_index = 0
        self.undo_stack: list[list[tuple[str, str, QImage, bool]]] = []
        self.redo_stack: list[list[tuple[str, str, QImage, bool]]] = []

        self.canvas = ImageCanvas()
        self.preview_server = LocalPreviewServer()
        self.preview_server.start()
        self._preview_worker: PreviewBuildWorker | None = None
        self._player_page_ready = False
        self._player_package_ready = False
        self._pending_player_load = False
        self.preview_tabs = QTabWidget()
        self.preview_tabs.addTab(self.canvas, "파츠 편집")
        self.player_view = QWebEngineView()
        self.player_view.loadFinished.connect(self._player_page_loaded)
        self.preview_tabs.addTab(self.player_view, "공식 Player 미리보기")
        self.player_view.load(QUrl(self.preview_server.url))

        self.canvas.changed.connect(self._mark_dirty)
        self.canvas.on_edit_start = self._push_undo
        self.canvas.on_head_box = self._head_box_updated
        self.canvas.on_status = self._status
        self.layer_list = QListWidget()
        self.layer_list.currentRowChanged.connect(self._select_layer)
        self.layer_list.itemChanged.connect(self._layer_item_changed)
        self._refreshing_list = False

        self._build_ui()
        self._set_enabled(False)

    def _build_ui(self) -> None:
        toolbar = QToolBar("작업 도구")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        actions = [
            ("이미지 열기", self.open_image), ("프로젝트 열기", self.open_project),
            ("저장", self.save_project), ("실행 취소", self.undo), ("다시 실행", self.redo),
            ("내보내기", self.export_model),
        ]
        for label, slot in actions:
            action = QAction(label, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)
        toolbar.addSeparator()
        cut_action = QAction("테두리 배경 제거", self)
        cut_action.triggered.connect(self.remove_background)
        toolbar.addAction(cut_action)
        self.add_part_action = QAction("파츠 추가", self)
        self.add_part_action.triggered.connect(self.add_part)
        toolbar.addAction(self.add_part_action)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("파츠 계층 · 아래쪽이 먼저 그려집니다"))
        self.layer_list.setMinimumWidth(210)
        left_layout.addWidget(self.layer_list, 1)
        row = QHBoxLayout()
        for label, slot in (("위로", lambda: self.move_layer(-1)), ("아래로", lambda: self.move_layer(1)), ("삭제", self.delete_layer)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            row.addWidget(button)
        left_layout.addLayout(row)

        right = QWidget()
        right.setMinimumWidth(260)
        right.setMaximumWidth(340)
        form = QFormLayout(right)
        form.setContentsMargins(12, 10, 12, 10)
        form.addRow(QLabel("<b>선택한 파츠</b>"))
        self.layer_name = QLineEdit()
        self.layer_name.editingFinished.connect(self._rename_layer)
        form.addRow("이름", self.layer_name)
        self.group_combo = QComboBox()
        for group in GROUPS:
            self.group_combo.addItem(GROUP_LABELS[group], group)
        self.group_combo.currentIndexChanged.connect(self._change_group)
        form.addRow("움직임 그룹", self.group_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("마스크 칠하기", "paint")
        self.mode_combo.addItem("마스크 지우기", "erase")
        self.mode_combo.addItem("머리 앵커 그리기", "head")
        self.mode_combo.currentIndexChanged.connect(self._change_mode)
        form.addRow("캔버스 도구", self.mode_combo)
        self.brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setRange(2, 160)
        self.brush_slider.setValue(28)
        self.brush_slider.valueChanged.connect(self._brush_size)
        form.addRow("브러시 크기", self.brush_slider)

        form.addRow(QLabel("<b>단색 배경 제거</b>"))
        self.tolerance = QSlider(Qt.Orientation.Horizontal)
        self.tolerance.setRange(0, 120)
        self.tolerance.setValue(32)
        form.addRow("색 허용치", self.tolerance)
        remove_button = QPushButton("선택 파츠의 배경 제거")
        remove_button.clicked.connect(self.remove_background)
        form.addRow(remove_button)

        form.addRow(QLabel("<b>임시 회전 보기</b>"))
        self.turn_slider = QSlider(Qt.Orientation.Horizontal)
        self.turn_slider.setRange(-30, 30)
        self.turn_slider.valueChanged.connect(self.canvas.set_turn)
        form.addRow("고개 회전", self.turn_slider)
        note = QLabel(
            "이 미리보기는 편집 마스크의 2D 회전 확인용입니다.\n"
            "오른쪽의 공식 Player 탭에서는 내보낼 모델을 실제 렌더링할 수 있습니다.\n"
            "머리 영역은 드래그로 직접 지정하고, 파츠는 브러시로 나누세요."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9fb0c3; padding:8px; background:#1c2632; border-radius:6px;")
        form.addRow(note)

        form.addRow(QLabel("<b>LivLiv Player 미리보기</b>"))
        self.preview_build_button = QPushButton("Player 미리보기 생성 / 갱신")
        self.preview_build_button.clicked.connect(self.build_player_preview)
        form.addRow(self.preview_build_button)
        self.player_sliders: dict[str, QSlider] = {}
        for key, label, low, high, initial in (
            ("angleX", "좌우 회전", -30, 30, 0),
            ("angleY", "위아래 회전", -30, 30, 0),
            ("angleZ", "기울이기", -30, 30, 0),
            ("eyeLOpen", "눈 뜨기", 0, 100, 100),
            ("mouthOpen", "입 열기", 0, 100, 0),
            ("smile", "미소", 0, 100, 0),
        ):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setValue(initial)
            slider.valueChanged.connect(self._player_params_changed)
            self.player_sliders[key] = slider
            form.addRow(label, slider)
        player_buttons = QWidget()
        player_buttons_row = QHBoxLayout(player_buttons)
        player_buttons_row.setContentsMargins(0, 0, 0, 0)
        for label, callback in (("깜빡임", self._player_blink),
                                ("끄덕임", lambda: self._player_action("nod")),
                                ("초기화", self._reset_player_params)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            player_buttons_row.addWidget(button)
        form.addRow(player_buttons)
        self.player_controls_note = QLabel("Player 파라미터는 모델에 해당 파츠가 있을 때 반영됩니다.")
        self.player_controls_note.setWordWrap(True)
        self.player_controls_note.setStyleSheet("color:#9fb0c3; padding:4px;")
        form.addRow(self.player_controls_note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.preview_tabs)
        splitter.addWidget(right)
        splitter.setSizes([250, 920, 300])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self._status("이미지를 열거나 프로젝트를 불러오세요. 모든 이미지는 이 PC에서 처리됩니다.")

        file_menu = self.menuBar().addMenu("파일")
        for label, slot in (("이미지 열기", self.open_image), ("프로젝트 열기", self.open_project),
                            ("프로젝트 저장", self.save_project), ("LivLiv 모델 내보내기", self.export_model)):
            action = QAction(label, self)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        edit_menu = self.menuBar().addMenu("편집")
        for label, slot, shortcut in (("실행 취소", self.undo, "Ctrl+Z"), ("다시 실행", self.redo, "Ctrl+Y")):
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            edit_menu.addAction(action)

    def _set_enabled(self, enabled: bool) -> None:
        self.layer_list.setEnabled(enabled)
        self.add_part_action.setEnabled(enabled)
        self.layer_name.setEnabled(enabled)
        self.group_combo.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        self.brush_slider.setEnabled(enabled)
        self.turn_slider.setEnabled(enabled)
        self.preview_build_button.setEnabled(enabled and self._preview_worker is None)
        for slider in self.player_sliders.values():
            slider.setEnabled(enabled)

    def _status(self, text: str) -> None:
        self.statusBar().showMessage(text, 12_000)

    def _player_page_loaded(self, ok: bool) -> None:
        self._player_page_ready = ok
        if not ok:
            self._status("LivLiv Player 페이지를 열지 못했습니다. Player 자산 폴더를 확인하세요.")
            return
        if self._pending_player_load and self._player_package_ready:
            self._load_latest_player_package()

    def _load_latest_player_package(self) -> None:
        if not self._player_page_ready or not self._player_package_ready:
            return
        self._pending_player_load = False
        self.player_view.page().runJavaScript("window.MyLivLivPreview?.loadLatest();")
        self.preview_tabs.setCurrentWidget(self.player_view)

    def build_player_preview(self) -> None:
        if not self.document:
            return
        if self._preview_worker is not None:
            self._status("Player 미리보기를 만들고 있습니다. 잠시 기다려 주세요.")
            return
        self.preview_build_button.setEnabled(False)
        self._status("LivLiv v4 패키지를 만들고 공식 Player 미리보기를 준비합니다…")
        snapshot = snapshot_document(self.document)
        model_name = Path(self.document.source_name).stem[:64]
        worker = PreviewBuildWorker(snapshot, model_name, self)
        self._preview_worker = worker
        worker.package_ready.connect(self._player_package_built)
        worker.failed.connect(self._player_package_failed)
        worker.finished.connect(lambda worker=worker: self._preview_worker_finished(worker))
        worker.start()

    def _player_package_built(self, package: bytes) -> None:
        self.preview_server.set_package(package)
        self._player_package_ready = True
        self._pending_player_load = True
        self._status("미리보기 패키지를 만들었습니다. 공식 Player에서 렌더링합니다.")
        self._load_latest_player_package()

    def _player_package_failed(self, message: str) -> None:
        self._status(f"Player 미리보기 생성 실패: {message}")

    def _preview_worker_finished(self, worker: PreviewBuildWorker) -> None:
        if self._preview_worker is worker:
            self._preview_worker = None
        worker.deleteLater()
        self.preview_build_button.setEnabled(self.document is not None)

    def _run_player_javascript(self, source: str) -> None:
        if self._player_page_ready:
            self.player_view.page().runJavaScript(source)

    def _player_params_changed(self, _value: int = 0) -> None:
        values: dict[str, float] = {}
        for key, slider in self.player_sliders.items():
            value = slider.value()
            if key in {"eyeLOpen", "mouthOpen", "smile"}:
                value /= 100
            values[key] = value
        values["eyeROpen"] = values["eyeLOpen"]
        self._run_player_javascript(f"window.MyLivLivPreview?.setParams({values!r});")

    def _player_blink(self) -> None:
        self._run_player_javascript("window.MyLivLivPreview?.blink();")

    def _player_action(self, name: str) -> None:
        if name in {"nod", "shake", "tilt", "hop", "shy"}:
            self._run_player_javascript(f"window.MyLivLivPreview?.action({name!r});")

    def _reset_player_params(self) -> None:
        for key, value in (("angleX", 0), ("angleY", 0), ("angleZ", 0),
                           ("eyeLOpen", 100), ("mouthOpen", 0), ("smile", 0)):
            self.player_sliders[key].setValue(value)

    def _push_undo(self) -> None:
        if not self.document:
            return
        snapshot = [(layer.name, layer.group, layer.mask, layer.visible) for layer in self.document.layers]
        self.undo_stack.append(snapshot)
        del self.undo_stack[:-8]
        self.redo_stack.clear()

    def _restore_snapshot(self, snapshot) -> None:
        if not self.document:
            return
        self.document.layers = [Layer(name, group, mask, visible) for name, group, mask, visible in snapshot]
        self.selected_index = min(self.selected_index, max(0, len(self.document.layers) - 1))
        self.document.touch()
        self._refresh_layers()

    def undo(self) -> None:
        if not self.document or not self.undo_stack:
            return
        self.redo_stack.append([(x.name, x.group, x.mask, x.visible) for x in self.document.layers])
        self._restore_snapshot(self.undo_stack.pop())
        self.canvas.invalidate()
        self._mark_dirty()
        self._status("편집을 실행 취소했습니다.")

    def redo(self) -> None:
        if not self.document or not self.redo_stack:
            return
        self.undo_stack.append([(x.name, x.group, x.mask, x.visible) for x in self.document.layers])
        self._restore_snapshot(self.redo_stack.pop())
        self.canvas.invalidate()
        self._mark_dirty()
        self._status("편집을 다시 적용했습니다.")

    def _mark_dirty(self) -> None:
        if self.document:
            self.dirty = True
            marker = " *" if self.dirty else ""
            self.setWindowTitle(f"My LivLiv v0.1.0 — {self.document.source_name}{marker}")

    def _replace_document(self, document: ImageDocument, path: Path | None = None) -> None:
        self.document = document
        self.project_path = path
        self.selected_index = 0
        self.dirty = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.canvas.set_document(document)
        self._refresh_layers()
        self._set_enabled(True)
        self._status(f"불러옴: {document.width} × {document.height}px · {len(document.layers)}개 파츠 · 로컬 처리")

    def _refresh_layers(self) -> None:
        if not self.document:
            self.layer_list.clear()
            return
        self._refreshing_list = True
        self.layer_list.clear()
        for layer in self.document.layers:
            item = QListWidgetItem(layer.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
            item.setToolTip(GROUP_LABELS[layer.group])
            self.layer_list.addItem(item)
        self.selected_index = max(0, min(self.selected_index, len(self.document.layers) - 1))
        self.layer_list.setCurrentRow(self.selected_index)
        self._refreshing_list = False
        self._select_layer(self.selected_index)

    def _select_layer(self, index: int) -> None:
        if not self.document or not 0 <= index < len(self.document.layers):
            return
        self.selected_index = index
        self.canvas.selected_index = index
        layer = self.document.layers[index]
        self.layer_name.blockSignals(True)
        self.layer_name.setText(layer.name)
        self.layer_name.blockSignals(False)
        self.group_combo.blockSignals(True)
        self.group_combo.setCurrentIndex(self.group_combo.findData(layer.group))
        self.group_combo.blockSignals(False)
        self.canvas.invalidate()

    def _layer_item_changed(self, item: QListWidgetItem) -> None:
        if not self.document or self._refreshing_list:
            return
        index = self.layer_list.row(item)
        if not 0 <= index < len(self.document.layers):
            return
        layer = self.document.layers[index]
        if item.checkState() != (Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked):
            self._push_undo()
            layer.visible = item.checkState() == Qt.CheckState.Checked
            self.document.touch()
            self.canvas.invalidate()
            self._mark_dirty()
        if item.text() != layer.name:
            layer.name = item.text()[:64]
            self._select_layer(index)
            self._mark_dirty()

    def _rename_layer(self) -> None:
        if self.document and 0 <= self.selected_index < len(self.document.layers):
            name = self.layer_name.text().strip()[:64]
            if name:
                self._push_undo()
                self.document.layers[self.selected_index].name = name
                self.layer_list.item(self.selected_index).setText(name)
                self.document.touch()
                self._mark_dirty()

    def _change_group(self, _index: int) -> None:
        if self.document and 0 <= self.selected_index < len(self.document.layers):
            group = self.group_combo.currentData()
            layer = self.document.layers[self.selected_index]
            if group != layer.group:
                self._push_undo()
                layer.group = group
                self.layer_list.item(self.selected_index).setToolTip(GROUP_LABELS[group])
                self.document.touch()
                self._mark_dirty()

    def _change_mode(self, _index: int) -> None:
        self.canvas.mode = self.mode_combo.currentData()
        labels = {"paint": "브러시로 칠할 파츠를 선택하세요.", "erase": "선택 파츠에서 지울 영역을 칠하세요.",
                  "head": "캔버스에서 머리 영역을 드래그하세요."}
        self._status(labels[self.canvas.mode])

    def _brush_size(self, size: int) -> None:
        self.canvas.brush_size = size

    def _head_box_updated(self, box: tuple[int, int, int, int]) -> None:
        self._mark_dirty()
        self._status(f"수동 머리 앵커 설정: x={box[0]}–{box[2]}, y={box[1]}–{box[3]}")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        choice = QMessageBox.question(self, "저장하지 않은 편집", "변경 사항을 저장할까요?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self.save_project()
        return True

    def open_image(self) -> None:
        if not self._confirm_discard():
            return
        file, _ = QFileDialog.getOpenFileName(self, "캐릭터 이미지 열기", "", "이미지 (*.png *.jpg *.jpeg)")
        if not file:
            return
        try:
            reader = QImageReader(file)
            reader.setAutoTransform(True)
            dims = reader.size()
            if not dims.isValid():
                raise ValueError("이미지 헤더를 읽지 못했습니다.")
            validate_image_size(dims.width(), dims.height())
            image = reader.read()
            if image.isNull():
                raise ValueError(reader.errorString() or "이미지 읽기 실패")
            doc = ImageDocument(image, Path(file).name)
            self._replace_document(doc)
            if image.hasAlphaChannel():
                self._status(f"투명도 채널을 불러왔습니다: {image.width()} × {image.height()}px")
        except Exception as error:
            QMessageBox.critical(self, "이미지 열기 실패", str(error))

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        file, _ = QFileDialog.getOpenFileName(self, "My LivLiv 프로젝트 열기", "", "My LivLiv 프로젝트 (*.mlliv)")
        if not file:
            return
        try:
            self._replace_document(load_project(file), Path(file))
        except Exception as error:
            QMessageBox.critical(self, "프로젝트 열기 실패", str(error))

    def save_project(self) -> bool:
        if not self.document:
            return False
        path = self.project_path
        if path is None:
            file, _ = QFileDialog.getSaveFileName(self, "프로젝트 저장", "My LivLiv 프로젝트.mlliv", "My LivLiv 프로젝트 (*.mlliv)")
            if not file:
                return False
            path = Path(file).with_suffix(".mlliv")
        try:
            save_project(self.document, path)
            self.project_path = path
            self.dirty = False
            self.setWindowTitle(f"My LivLiv v0.1.0 — {self.document.source_name}")
            self._status(f"프로젝트 저장 완료: {path.name}")
            return True
        except Exception as error:
            QMessageBox.critical(self, "프로젝트 저장 실패", str(error))
            return False

    def export_model(self) -> None:
        if not self.document:
            return
        file, _ = QFileDialog.getSaveFileName(self, "LivLiv v4 모델 내보내기", "캐릭터.livliv", "LivLiv 모델 (*.livliv)")
        if not file:
            return
        path = Path(file).with_suffix(".livliv")
        try:
            model_name = Path(self.document.source_name).stem[:64]
            model = export_livliv(self.document, path, model_name)
            self.preview_server.set_package(path.read_bytes())
            self._player_package_ready = True
            self._pending_player_load = True
            message = f"v4 패키지를 생성하고 내부 구조를 확인했습니다.\n\n{path}\n파츠: {len(model['layers'])}개\n캔버스: {model['canvas'][0]} × {model['canvas'][1]}px"
            if not self.document.head_box:
                message += "\n\n머리 앵커를 지정하지 않아 전체 캐릭터 경계를 임시 앵커로 사용했습니다. 정확한 움직임을 위해 머리 앵커를 지정한 뒤 다시 내보내세요."
            QMessageBox.information(self, "내보내기 완료", message)
            self._status(f"LivLiv 모델 내보내기 완료: {path.name}")
            self._load_latest_player_package()
        except Exception as error:
            QMessageBox.critical(self, "모델 내보내기 실패", str(error))

    def remove_background(self) -> None:
        if not self.document or not 0 <= self.selected_index < len(self.document.layers):
            return
        self._push_undo()
        layer = self.document.layers[self.selected_index]
        try:
            mask, report = remove_border_background(self.document.source, self.tolerance.value())
            layer.mask = mask
            self.document.touch()
            self.canvas.invalidate()
            self._mark_dirty()
            self._status(f"테두리 색 추출 완료 · 배경 픽셀 {report['removed_pixels']:,}개 · {report['warning']}")
            if report["removed_pixels"] == 0:
                QMessageBox.information(self, "배경 제거", str(report["warning"]))
        except Exception as error:
            QMessageBox.critical(self, "배경 제거 실패", str(error))

    def add_part(self) -> None:
        if not self.document:
            return
        self._push_undo()
        index = self.document.add_layer(f"새 파츠 {len(self.document.layers) + 1}", "head")
        self.selected_index = index
        self._refresh_layers()
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("paint"))
        self._mark_dirty()
        self._status("새 마스크에 칠해 파츠를 지정하세요. 기존 파츠의 겹치는 영역은 지우개로 정리할 수 있습니다.")

    def delete_layer(self) -> None:
        if not self.document or len(self.document.layers) <= 1:
            QMessageBox.information(self, "파츠 삭제", "최소 한 개의 파츠는 남아 있어야 합니다.")
            return
        self._push_undo()
        del self.document.layers[self.selected_index]
        self.selected_index = max(0, self.selected_index - 1)
        self.document.touch()
        self._refresh_layers()
        self.canvas.invalidate()
        self._mark_dirty()

    def move_layer(self, direction: int) -> None:
        if not self.document:
            return
        destination = self.selected_index + direction
        if not 0 <= destination < len(self.document.layers):
            return
        self._push_undo()
        layers = self.document.layers
        layers[self.selected_index], layers[destination] = layers[destination], layers[self.selected_index]
        self.selected_index = destination
        self.document.touch()
        self._refresh_layers()
        self.canvas.invalidate()
        self._mark_dirty()

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            if self._preview_worker is not None and not self._preview_worker.wait(10_000):
                self._status("Player 미리보기를 만드는 중입니다. 잠시 후 다시 닫아 주세요.")
                event.ignore()
                return
            self.preview_server.close()
            event.accept()
        else:
            event.ignore()


def run() -> int:
    app = QApplication([])
    app.setApplicationName("My LivLiv")
    app.setOrganizationName("My LivLiv community project")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()

