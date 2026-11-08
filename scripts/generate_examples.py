from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(ROOT))

from mlliv.core import ImageDocument, Layer, remove_border_background
from mlliv.package_io import export_livliv, save_project


def draw_character(path: Path, palette: dict[str, str], shift: int = 0) -> QImage:
    width, height = 512, 768
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(palette["background"]))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    # Back hair and shoulders.
    painter.setBrush(QColor(palette["hair"]))
    painter.drawEllipse(120 + shift, 70, 272, 330)
    painter.setBrush(QColor(palette["shirt"]))
    painter.drawRoundedRect(90, 420, 332, 330, 88, 88)
    # Neck and face.
    painter.setBrush(QColor(palette["skin"]))
    painter.drawRoundedRect(220 + shift, 333, 72, 126, 25, 25)
    painter.drawEllipse(164 + shift, 106, 184, 248)
    # Bangs.
    painter.setBrush(QColor(palette["hair"]))
    painter.drawEllipse(142 + shift, 62, 226, 160)
    painter.drawEllipse(153 + shift, 123, 90, 115)
    painter.drawEllipse(210 + shift, 119, 100, 130)
    painter.drawEllipse(271 + shift, 125, 83, 117)
    # Eyes, brows and mouth.
    painter.setBrush(QColor(palette["ink"]))
    painter.drawRoundedRect(205 + shift, 230, 22, 28, 9, 9)
    painter.drawRoundedRect(285 + shift, 230, 22, 28, 9, 9)
    painter.setPen(QPen(QColor(palette["ink"]), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(196 + shift, 207, 232 + shift, 205)
    painter.drawLine(278 + shift, 205, 314 + shift, 207)
    painter.setPen(QPen(QColor(palette["mouth"]), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(244 + shift, 300, 268 + shift, 302)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(palette["cheek"]))
    painter.drawEllipse(186 + shift, 269, 32, 13)
    painter.drawEllipse(296 + shift, 269, 32, 13)
    # Collar detail.
    painter.setBrush(QColor(palette["accent"]))
    painter.drawRoundedRect(193, 435, 126, 18, 8, 8)
    painter.end()
    image.save(str(path), "PNG")
    return image


def region_mask(foreground: QImage, head: bool) -> QImage:
    width, height = foreground.width(), foreground.height()
    mask = QImage(width, height, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    painter = QPainter(mask)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("white"))
    if head:
        painter.drawEllipse(122, 55, 276, 414)
    else:
        painter.drawRoundedRect(72, 400, 368, 368, 100, 100)
    painter.end()
    foreground_data = memoryview(foreground.bits())
    mask_data = memoryview(mask.bits())
    for y in range(height):
        frow, mrow = y * foreground.bytesPerLine(), y * mask.bytesPerLine()
        for x in range(width):
            mask_data[mrow + x] = foreground_data[frow + x] * mask_data[mrow + x] // 255
    return mask


def create_example(filename: str, palette: dict[str, str], shift: int, package_name: str) -> None:
    source_path = EXAMPLES / filename
    source = draw_character(source_path, palette, shift)
    foreground, _ = remove_border_background(source, 44)
    head_mask = region_mask(foreground, True)
    body_mask = region_mask(foreground, False)
    document = ImageDocument(source, filename, [
        Layer("몸과 의상", "body", body_mask),
        Layer("머리와 앞머리", "head", head_mask),
    ], (148 + shift, 62, 368 + shift, 363))
    export_livliv(document, EXAMPLES / package_name, Path(filename).stem.replace("-", " "), "CC0-1.0")
    save_project(document, EXAMPLES / (Path(filename).stem + ".mlliv"))


def main() -> None:
    EXAMPLES.mkdir(exist_ok=True)
    create_example("character-a.png", {
        "background": "#e7eef8", "hair": "#54437b", "shirt": "#64a9a5", "skin": "#f2c8aa",
        "ink": "#302d46", "mouth": "#984d5b", "cheek": "#df8b91", "accent": "#d6b260",
    }, 0, "character-a.livliv")
    create_example("character-b.png", {
        "background": "#f1eadf", "hair": "#715044", "shirt": "#d77f64", "skin": "#efc5a5",
        "ink": "#3d3331", "mouth": "#8e4450", "cheek": "#e58d8c", "accent": "#7cb1aa",
    }, -12, "character-b.livliv")
    (EXAMPLES / "LICENSE.md").write_text(
        "# Example artwork license\n\nThe two synthetic vector test illustrations and their exported sample packages in this directory were created for My LivLiv and are dedicated to the public domain under CC0 1.0. They contain no third-party character art or player sample assets.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
