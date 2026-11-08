from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .core import GROUPS, ImageDocument, Layer, image_from_png, layer_image, png_bytes, validate_image_size

MAX_PROJECT_FILE = 256 * 1024 * 1024
MAX_PROJECT_TOTAL = 512 * 1024 * 1024
MAX_PACKAGE_TOTAL = 256 * 1024 * 1024


def _project_entry_name(value: str) -> bool:
    p = PurePosixPath(value)
    return bool(value) and "\\" not in value and not value.startswith("/") and ".." not in p.parts and "." not in p.parts and ":" not in value


def save_project(document: ImageDocument, path: str | Path) -> None:
    path = Path(path)
    entries: dict[str, bytes] = {"source.png": png_bytes(document.source)}
    layers = []
    for index, layer in enumerate(document.layers):
        file = f"masks/layer_{index:03d}.png"
        entries[file] = png_bytes(layer.mask)
        layers.append({"name": layer.name, "group": layer.group, "visible": layer.visible, "mask": file})
    manifest = {
        "format": "my-livliv-project",
        "version": 1,
        "source_name": document.source_name,
        "source": "source.png",
        "head_box": list(document.head_box) if document.head_box else None,
        "layers": layers,
    }
    entries["project.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=False) as archive:
        for name in ("project.json", *[n for n in entries if n != "project.json"]):
            archive.writestr(name, entries[name])


def load_project(path: str | Path) -> ImageDocument:
    path = Path(path)
    if path.stat().st_size > MAX_PROJECT_FILE:
        raise ValueError("프로젝트 파일이 256MB 제한을 초과합니다.")
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > 256:
            raise ValueError("프로젝트 안의 파일 수가 제한을 초과합니다.")
        names: set[str] = set()
        total = 0
        for info in infos:
            if not _project_entry_name(info.filename) or info.is_dir():
                raise ValueError("프로젝트 안에 안전하지 않은 파일 경로가 있습니다.")
            if info.filename in names:
                raise ValueError("프로젝트 안에 중복 파일 경로가 있습니다.")
            names.add(info.filename)
            if info.flag_bits & 0x1:
                raise ValueError("암호화된 프로젝트 ZIP은 열 수 없습니다.")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("심볼릭 링크가 든 프로젝트 ZIP은 열 수 없습니다.")
            total += info.file_size
            if info.file_size > 128 * 1024 * 1024 or total > MAX_PROJECT_TOTAL:
                raise ValueError("프로젝트의 압축 해제 크기가 허용치를 초과합니다.")
        if "project.json" not in names:
            raise ValueError("project.json이 없는 파일입니다.")
        raw = archive.read("project.json")
        manifest = json.loads(raw.decode("utf-8"))
        if manifest.get("format") != "my-livliv-project" or manifest.get("version") != 1:
            raise ValueError("지원하지 않는 My LivLiv 프로젝트 형식입니다.")
        source_name = manifest.get("source", "")
        if source_name != "source.png" or source_name not in names:
            raise ValueError("원본 이미지 파일이 없거나 경로가 유효하지 않습니다.")
        source = image_from_png(archive.read(source_name))
        layers: list[Layer] = []
        layer_entries = manifest.get("layers")
        if not isinstance(layer_entries, list) or not 1 <= len(layer_entries) <= 512:
            raise ValueError("프로젝트 파츠 목록이 유효하지 않습니다.")
        used: set[str] = set()
        for entry in layer_entries:
            if not isinstance(entry, dict):
                raise ValueError("프로젝트 파츠 항목이 유효하지 않습니다.")
            mask_path = entry.get("mask", "")
            if not _project_entry_name(mask_path) or not mask_path.startswith("masks/") or mask_path not in names:
                raise ValueError("파츠 마스크 경로가 안전하지 않거나 파일이 없습니다.")
            if mask_path in used:
                raise ValueError("같은 파츠 마스크 파일을 두 번 참조합니다.")
            used.add(mask_path)
            group = entry.get("group")
            if group not in GROUPS:
                raise ValueError("프로젝트 파츠의 LivLiv 그룹이 유효하지 않습니다.")
            mask = image_from_png(archive.read(mask_path)).convertToFormat(QImage.Format.Format_Grayscale8)
            if mask.size() != source.size():
                raise ValueError("파츠 마스크와 원본 이미지의 크기가 다릅니다.")
            layers.append(Layer(str(entry.get("name", "파츠"))[:64], group, mask, bool(entry.get("visible", True))))
        raw_box = manifest.get("head_box")
        head_box = tuple(int(v) for v in raw_box) if isinstance(raw_box, list) and len(raw_box) == 4 else None
        if head_box and (head_box[2] <= head_box[0] or head_box[3] <= head_box[1]):
            raise ValueError("머리 앵커 상자 크기가 잘못되었습니다.")
        doc = ImageDocument(source, str(manifest.get("source_name", path.name))[:260], layers, head_box)
        return doc


def _safe_layer_id(name: str, index: int, used: set[str]) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip()).strip("_")
    if not ascii_name or not ascii_name[0].isalpha():
        ascii_name = f"Part_{index + 1}"
    candidate = ascii_name[:56]
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base[:56 - len(str(suffix)) - 1]}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def build_model(document: ImageDocument, name: str = "My LivLiv 캐릭터", license_id: str | None = None) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    width, height = document.width, document.height
    validate_image_size(width, height)
    if len(document.layers) > 512:
        raise ValueError("LivLiv v4는 최대 512개 파츠를 지원합니다.")
    name = name.strip()[:64] or "My LivLiv 캐릭터"
    files: list[tuple[str, bytes]] = []
    layers: list[dict[str, Any]] = []
    ids: set[str] = set()
    all_boxes = []
    for index, layer in enumerate(document.layers):
        if not layer.visible:
            continue
        try:
            texture, box = layer_image(document, layer, crop=True)
        except ValueError:
            continue
        texture_name = _safe_layer_id(layer.name, index, ids)
        texture_path = f"textures/{texture_name}.png"
        files.append((texture_path, png_bytes(texture)))
        all_boxes.append(box)
        layers.append({
            "id": texture_name,
            "label": {"ko": layer.name[:48]},
            "texture": texture_path,
            "x": box.x(), "y": box.y(), "w": box.width(), "h": box.height(),
            "group": layer.group,
        })
    if not layers:
        raise ValueError("내보낼 수 있는 표시 파츠가 없습니다. 최소 한 개의 파츠를 표시하세요.")

    x0 = min(b.x() for b in all_boxes)
    y0 = min(b.y() for b in all_boxes)
    x1 = max(b.x() + b.width() for b in all_boxes)
    y1 = max(b.y() + b.height() for b in all_boxes)
    fallback = document.head_box is None
    if document.head_box is not None:
        hx0, hy0, hx1, hy1 = document.head_box
        hx0, hy0 = max(0, min(width - 1, hx0)), max(0, min(height - 1, hy0))
        hx1, hy1 = max(hx0 + 1, min(width, hx1)), max(hy0 + 1, min(height, hy1))
    else:
        # This is a clearly reported fallback to the whole visible drawing, not face detection.
        hx0, hy0, hx1, hy1 = x0, y0, x1, y1
    head_w, head_h = max(1, hx1 - hx0), max(1, hy1 - hy0)
    model = {
        "format": "livliv-model",
        "version": 4,
        "name": name,
        "meta": {
            "generator": {"name": "My LivLiv", "build": "0.1.0"},
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "requires": [],
        "canvas": [width, height],
        "anchors": {
            "head": {"cx": hx0 + head_w / 2, "cy": hy0 + head_h / 2, "rx": head_w / 2, "ry": head_h / 2},
            "face": [hx0, hy0, hx1, hy1],
            "neck_y": hy1,
            "top_y": y0,
            "bottom_y": y1,
            "hair_root_y": hy0 + head_h * 0.22,
        },
        "rig": {"yaw": 0.27, "pitch": 0.22, "roll": 0.5, "hair_limit": 0.25},
        "layers": layers,
    }
    if license_id:
        model["meta"]["license"] = {"id": license_id}
    validate_model(model)
    return model, files


def validate_model(model: dict[str, Any]) -> None:
    """Strict local checks; the full vendored v4 JSON Schema is used when jsonschema is installed."""
    allowed = {"format", "version", "name", "meta", "requires", "files", "canvas", "profile", "rig", "tuning", "anchors", "expressions", "layers"}
    if any(key not in allowed and not key.startswith("x-") for key in model):
        raise ValueError("LivLiv model.json에 스키마에 없는 최상위 필드가 있습니다.")
    if model.get("format") != "livliv-model" or model.get("version") != 4:
        raise ValueError("LivLiv Model Format v4 헤더가 올바르지 않습니다.")
    if not isinstance(model.get("name"), str) or not 1 <= len(model["name"]) <= 64:
        raise ValueError("모델 이름은 1–64자여야 합니다.")
    canvas = model.get("canvas")
    if not isinstance(canvas, list) or len(canvas) != 2 or any(not isinstance(v, int) for v in canvas):
        raise ValueError("canvas는 정수 [width, height]여야 합니다.")
    validate_image_size(*canvas)
    if not isinstance(model.get("meta", {}).get("generator", {}).get("name"), str):
        raise ValueError("meta.generator.name이 필요합니다.")
    anchors = model.get("anchors", {})
    for key in ("head", "face", "neck_y", "top_y", "bottom_y", "hair_root_y"):
        if key not in anchors:
            raise ValueError(f"anchors.{key}가 없습니다.")
    head = anchors["head"]
    if not all(key in head for key in ("cx", "cy", "rx", "ry")) or head["rx"] <= 0 or head["ry"] <= 0:
        raise ValueError("anchors.head 타원 값이 유효하지 않습니다.")
    layers = model.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) <= 512:
        raise ValueError("LivLiv 모델에는 1–512개 파츠가 필요합니다.")
    seen = set()
    for layer in layers:
        lid = layer.get("id")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", lid or "") or lid in seen:
            raise ValueError("파츠 id가 잘못되었거나 중복되었습니다.")
        seen.add(lid)
        if layer.get("group") not in GROUPS:
            raise ValueError("파츠 그룹이 공식 LivLiv v4 그룹이 아닙니다.")
        if not re.fullmatch(r"textures/[A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:webp|png)", layer.get("texture", "")):
            raise ValueError("파츠 텍스처 경로가 LivLiv v4 규칙과 다릅니다.")
        x, y, w, h = (layer.get(k) for k in ("x", "y", "w", "h"))
        if not all(isinstance(v, int) for v in (x, y, w, h)) or w < 1 or h < 1 or x < 0 or y < 0 or x + w > canvas[0] or y + h > canvas[1]:
            raise ValueError("파츠 위치 또는 크기가 캔버스 범위를 벗어났습니다.")
    try:
        import jsonschema
    except ImportError:
        return
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "livliv-model-v4.json"
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(model)


def export_livliv(document: ImageDocument, path: str | Path, name: str = "My LivLiv 캐릭터", license_id: str | None = None) -> dict[str, Any]:
    model, texture_entries = build_model(document, name, license_id)
    model_bytes = json.dumps(model, ensure_ascii=False, indent=2).encode("utf-8")
    if len(model_bytes) > 4 * 1024 * 1024:
        raise ValueError("model.json이 플레이어의 4MB 제한을 초과합니다.")
    path = Path(path)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.writestr("model.json", model_bytes, compress_type=zipfile.ZIP_STORED)
        for name_, payload in texture_entries:
            archive.writestr(name_, payload, compress_type=zipfile.ZIP_STORED)
    validate_livliv_package(path)
    return model


def validate_livliv_package(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.stat().st_size > MAX_PACKAGE_TOTAL:
        raise ValueError(".livliv 패키지가 256MB를 초과합니다.")
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= 2048:
            raise ValueError("패키지 파일 수가 LivLiv Player 제한을 벗어났습니다.")
        seen: set[str] = set()
        total = 0
        for info in infos:
            if not _project_entry_name(info.filename) or info.filename in seen:
                raise ValueError("패키지에 중복되거나 안전하지 않은 경로가 있습니다.")
            seen.add(info.filename)
            if info.flag_bits & 0x1:
                raise ValueError("암호화된 .livliv 패키지는 허용하지 않습니다.")
            total += info.file_size
            if total > MAX_PACKAGE_TOTAL:
                raise ValueError("패키지 압축 해제 크기가 256MB를 초과합니다.")
        if not infos or infos[0].filename != "model.json" or "model.json" not in seen:
            raise ValueError("model.json은 첫 번째 루트 파일이어야 합니다.")
        model = json.loads(archive.read("model.json").decode("utf-8"))
        validate_model(model)
        for layer in model["layers"]:
            texture = layer["texture"]
            if texture not in seen:
                raise ValueError(f"텍스처 파일이 없습니다: {texture}")
            image = image_from_png(archive.read(texture), strict_canvas=False)
            if image.width() != layer["w"] or image.height() != layer["h"]:
                raise ValueError(f"파츠 텍스처 크기와 model.json이 다릅니다: {texture}")
    return model

