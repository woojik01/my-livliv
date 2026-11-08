from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

MAX_SIDE = 8192
MAX_PIXELS = 64_000_000
GROUPS = ("head", "body", "hair_back", "hair_side", "hair_front", "hair_inner")


def _rgba_bytes(image: QImage) -> tuple[QImage, memoryview]:
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return rgba, memoryview(rgba.bits())


def png_bytes(image: QImage) -> bytes:
    buffer = QByteArray()
    device = QBuffer(buffer)
    if not device.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(device, "PNG"):
        raise ValueError("이미지를 PNG로 인코딩하지 못했습니다.")
    return bytes(buffer)


def image_from_png(data: bytes, strict_canvas: bool = True) -> QImage:
    image = QImage.fromData(data, "PNG")
    if image.isNull():
        raise ValueError("손상되었거나 지원하지 않는 PNG 이미지입니다.")
    if strict_canvas:
        validate_image_size(image.width(), image.height())
    elif image.width() < 1 or image.height() < 1 or image.width() > MAX_SIDE or image.height() > MAX_SIDE:
        raise ValueError("파츠 이미지 크기가 허용 범위를 벗어났습니다.")
    return image


def validate_image_size(width: int, height: int) -> None:
    if width < 16 or height < 16 or width > MAX_SIDE or height > MAX_SIDE:
        raise ValueError(f"이미지 크기는 각 변 16–{MAX_SIDE}px여야 합니다.")
    if width * height > MAX_PIXELS:
        raise ValueError("이미지 총 픽셀 수가 64MP 제한을 초과합니다.")


def alpha_mask(image: QImage) -> QImage:
    rgba, pixels = _rgba_bytes(image)
    mask = QImage(image.width(), image.height(), QImage.Format.Format_Grayscale8)
    mask.fill(0)
    target = memoryview(mask.bits())
    for y in range(image.height()):
        src_row = y * rgba.bytesPerLine()
        dst_row = y * mask.bytesPerLine()
        for x in range(image.width()):
            target[dst_row + x] = pixels[src_row + x * 4 + 3]
    return mask


def remove_border_background(image: QImage, tolerance: int = 32) -> tuple[QImage, dict[str, object]]:
    """Remove a nearly uniform, border-connected background; this is CV, not an AI model."""
    if not 0 <= tolerance <= 180:
        raise ValueError("배경 허용치는 0–180이어야 합니다.")
    width, height = image.width(), image.height()
    validate_image_size(width, height)
    rgba, pixels = _rgba_bytes(image)
    stride = rgba.bytesPerLine()

    samples: list[tuple[int, int, int]] = []
    step = max(1, min(width, height) // 128)
    for x in range(0, width, step):
        for y in (0, height - 1):
            i = y * stride + x * 4
            samples.append((pixels[i], pixels[i + 1], pixels[i + 2]))
    for y in range(0, height, step):
        for x in (0, width - 1):
            i = y * stride + x * 4
            samples.append((pixels[i], pixels[i + 1], pixels[i + 2]))
    background = tuple(int(median([c[channel] for c in samples])) for channel in range(3))
    threshold = tolerance * tolerance * 3

    def is_background(index: int) -> bool:
        i = (index // width) * stride + (index % width) * 4
        dr = pixels[i] - background[0]
        dg = pixels[i + 1] - background[1]
        db = pixels[i + 2] - background[2]
        return dr * dr + dg * dg + db * db <= threshold

    count = width * height
    removed = bytearray(count)
    queue: deque[int] = deque()
    for x in range(width):
        for idx in (x, (height - 1) * width + x):
            if not removed[idx] and is_background(idx):
                removed[idx] = 1
                queue.append(idx)
    for y in range(height):
        for idx in (y * width, y * width + width - 1):
            if not removed[idx] and is_background(idx):
                removed[idx] = 1
                queue.append(idx)
    while queue:
        idx = queue.popleft()
        x, y = idx % width, idx // width
        if x and not removed[idx - 1] and is_background(idx - 1):
            removed[idx - 1] = 1
            queue.append(idx - 1)
        if x + 1 < width and not removed[idx + 1] and is_background(idx + 1):
            removed[idx + 1] = 1
            queue.append(idx + 1)
        if y and not removed[idx - width] and is_background(idx - width):
            removed[idx - width] = 1
            queue.append(idx - width)
        if y + 1 < height and not removed[idx + width] and is_background(idx + width):
            removed[idx + width] = 1
            queue.append(idx + width)

    mask = QImage(width, height, QImage.Format.Format_Grayscale8)
    mask.fill(255)
    target = memoryview(mask.bits())
    feathered = 0
    for y in range(height):
        row = y * mask.bytesPerLine()
        for x in range(width):
            if not removed[y * width + x]:
                continue
            target[row + x] = 0
            # One-pixel antialias fringe for the foreground side of the cut.
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height and not removed[ny * width + nx]:
                    at = ny * mask.bytesPerLine() + nx
                    if target[at] > 192:
                        target[at] = 192
                        feathered += 1

    removed_count = sum(removed)
    if removed_count == count:
        # A solid-color image is not silently converted into an empty character.
        return alpha_mask(image), {
            "removed_pixels": 0,
            "foreground_pixels": count,
            "background_rgb": list(background),
            "warning": "배경색과 이미지가 거의 같아 제거를 적용하지 않았습니다.",
        }
    return mask, {
        "removed_pixels": removed_count,
        "foreground_pixels": count - removed_count,
        "background_rgb": list(background),
        "feathered_pixels": feathered,
        "warning": "단색에 가까운 테두리 배경만 제거합니다. 머리카락 경계는 브러시로 확인하세요.",
    }


@dataclass
class Layer:
    name: str
    group: str = "body"
    mask: QImage | None = None
    visible: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("파츠 이름은 비어 있을 수 없습니다.")
        if self.group not in GROUPS:
            raise ValueError(f"지원하지 않는 LivLiv 파츠 그룹: {self.group}")


@dataclass
class ImageDocument:
    source: QImage
    source_name: str = "image.png"
    layers: list[Layer] = field(default_factory=list)
    head_box: tuple[int, int, int, int] | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        if self.source.isNull():
            raise ValueError("원본 이미지가 비어 있습니다.")
        validate_image_size(self.source.width(), self.source.height())
        self.source = self.source.convertToFormat(QImage.Format.Format_ARGB32)
        if not self.layers:
            self.layers.append(Layer("원본 파츠", "body", alpha_mask(self.source)))
        for layer in self.layers:
            if layer.mask is None or layer.mask.size() != self.source.size():
                raise ValueError("파츠 마스크 크기가 원본 이미지와 다릅니다.")
            layer.mask = layer.mask.convertToFormat(QImage.Format.Format_Grayscale8)

    @property
    def width(self) -> int:
        return self.source.width()

    @property
    def height(self) -> int:
        return self.source.height()

    def add_layer(self, name: str, group: str = "head") -> int:
        mask = QImage(self.width, self.height, QImage.Format.Format_Grayscale8)
        mask.fill(0)
        self.layers.append(Layer(name, group, mask))
        self.revision += 1
        return len(self.layers) - 1

    def touch(self) -> None:
        self.revision += 1


def layer_image(document: ImageDocument, layer: Layer, crop: bool = False) -> tuple[QImage, QRect]:
    """Apply a grayscale mask to source alpha and optionally crop to nontransparent bounds."""
    rgba, pixels = _rgba_bytes(document.source)
    mask = layer.mask.convertToFormat(QImage.Format.Format_Grayscale8)
    mask_bytes = memoryview(mask.bits())
    width, height = document.width, document.height
    rects: list[int] = [width, height, -1, -1]
    for y in range(height):
        src_row = y * rgba.bytesPerLine()
        mask_row = y * mask.bytesPerLine()
        for x in range(width):
            offset = src_row + x * 4
            alpha = (pixels[offset + 3] * mask_bytes[mask_row + x]) // 255
            pixels[offset + 3] = alpha
            if alpha:
                rects[0] = min(rects[0], x)
                rects[1] = min(rects[1], y)
                rects[2] = max(rects[2], x)
                rects[3] = max(rects[3], y)
    if rects[2] < rects[0] or rects[3] < rects[1]:
        raise ValueError(f"'{layer.name}' 파츠에 내보낼 픽셀이 없습니다.")
    bounds = QRect(rects[0], rects[1], rects[2] - rects[0] + 1, rects[3] - rects[1] + 1)
    return (rgba.copy(bounds) if crop else rgba, bounds)


def composite_image(document: ImageDocument, turn_degrees: float = 0.0) -> QImage:
    result = QImage(document.width, document.height, QImage.Format.Format_ARGB32)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for layer in document.layers:
        if not layer.visible:
            continue
        try:
            image, box = layer_image(document, layer, crop=True)
        except ValueError:
            continue
        x, y = box.x(), box.y()
        if turn_degrees and layer.group in {"head", "hair_back", "hair_side", "hair_front", "hair_inner"}:
            pivot = QPointF(document.head_box[0] + (document.head_box[2] - document.head_box[0]) / 2,
                            document.head_box[1] + (document.head_box[3] - document.head_box[1]) / 2) if document.head_box else QPointF(document.width / 2, document.height / 3)
            painter.save()
            painter.translate(pivot)
            painter.rotate(turn_degrees * (0.6 if layer.group.startswith("hair_") else 1.0))
            painter.translate(-pivot)
            painter.drawImage(x, y, image)
            painter.restore()
        else:
            painter.drawImage(x, y, image)
    painter.end()
    return result

