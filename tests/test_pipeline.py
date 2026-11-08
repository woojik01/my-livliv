from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from mlliv.core import ImageDocument, Layer, alpha_mask, remove_border_background
from mlliv.package_io import build_livliv_bytes, export_livliv, load_project, save_project, validate_livliv_package
from mlliv.player_preview import LocalPreviewServer


def synthetic_character() -> QImage:
    image = QImage(192, 256, QImage.Format.Format_ARGB32)
    image.fill(QColor("#edf3fa"))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#7b5cb8"))
    p.drawEllipse(35, 28, 122, 132)
    p.setBrush(QColor("#f1c7a9"))
    p.drawEllipse(54, 45, 86, 100)
    p.setBrush(QColor("#4c365f"))
    p.drawEllipse(73, 83, 9, 12)
    p.drawEllipse(111, 83, 9, 12)
    p.setPen(QPen(QColor("#934d55"), 3))
    p.drawLine(86, 119, 105, 119)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#54a9a1"))
    p.drawRoundedRect(24, 158, 145, 100, 34, 34)
    p.end()
    return image


class PipelineTests(unittest.TestCase):
    def test_border_background_cutout_keeps_subject(self):
        image = synthetic_character()
        mask, report = remove_border_background(image, 26)
        self.assertGreater(report["removed_pixels"], image.width() * image.height() // 4)
        self.assertEqual(mask.pixel(2, 2) & 0xFF, 0)
        self.assertGreater(mask.pixel(96, 99) & 0xFF, 180)

    def test_project_save_and_restore_preserves_masks_and_groups(self):
        source = synthetic_character()
        mask, _ = remove_border_background(source, 26)
        doc = ImageDocument(source, "synthetic.png", [Layer("body", "body", mask)])
        doc.head_box = (54, 45, 140, 145)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.mlliv"
            save_project(doc, path)
            restored = load_project(path)
        self.assertEqual(restored.source.size(), source.size())
        self.assertEqual(restored.layers[0].name, "body")
        self.assertEqual(restored.layers[0].group, "body")
        self.assertEqual(restored.head_box, doc.head_box)
        self.assertEqual(restored.layers[0].mask.pixel(2, 2) & 0xFF, 0)

    def test_export_is_valid_v4_package_and_roundtrips_textures(self):
        source = synthetic_character()
        mask, _ = remove_border_background(source, 26)
        doc = ImageDocument(source, "synthetic.png", [Layer("Body", "body", mask)])
        doc.head_box = (54, 45, 140, 145)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.livliv"
            model = export_livliv(doc, path, "Synthetic")
            checked = validate_livliv_package(path)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist()[0], "model.json")
                on_disk = json.loads(archive.read("model.json"))
                layer = on_disk["layers"][0]
                image = QImage.fromData(archive.read(layer["texture"]), "PNG")
        self.assertEqual(model["version"], 4)
        self.assertEqual(checked["canvas"], [192, 256])
        self.assertEqual([image.width(), image.height()], [layer["w"], layer["h"]])
        self.assertEqual(model["anchors"]["face"], [54, 45, 140, 145])

    def test_in_memory_package_build_uses_official_schema_validation(self):
        source = synthetic_character()
        mask, _ = remove_border_background(source, 26)
        doc = ImageDocument(source, "synthetic.png", [Layer("Body", "body", mask)])
        doc.head_box = (54, 45, 140, 145)
        model, package = build_livliv_bytes(doc, "Synthetic Preview")
        checked = validate_livliv_package(package)
        self.assertEqual(model["version"], 4)
        self.assertEqual(checked["name"], "Synthetic Preview")
        self.assertGreater(len(package), 0)

    def test_preview_server_serves_package_at_token_url_with_restrictive_headers(self):
        source = synthetic_character()
        mask, _ = remove_border_background(source, 26)
        doc = ImageDocument(source, "synthetic.png", [Layer("Body", "body", mask)])
        _model, package = build_livliv_bytes(doc, "Synthetic Preview")
        server = LocalPreviewServer()
        server.set_package(package)
        server.start()
        try:
            with urllib.request.urlopen(server.url + "api/model.livliv", timeout=3) as response:
                self.assertEqual(response.read(), package)
                self.assertEqual(response.headers.get_content_type(), "application/zip")
                self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            try:
                urllib.request.urlopen(server.url.rsplit("/", 2)[0] + "/wrong/api/model.livliv", timeout=3)
                self.fail("A request without the per-run token should not be served.")
            except urllib.error.HTTPError as error:
                self.assertEqual(error.code, 404)
                error.close()
        finally:
            server.close()

    def test_empty_mask_is_not_exported(self):
        source = synthetic_character()
        empty = QImage(source.width(), source.height(), QImage.Format.Format_Grayscale8)
        empty.fill(0)
        doc = ImageDocument(source, "empty.png", [Layer("empty", "head", empty)])
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "표시 파츠"):
                export_livliv(doc, Path(folder) / "bad.livliv")

    def test_unsafe_project_archive_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evil.mlliv"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../outside.txt", "no")
                archive.writestr("project.json", "{}")
            with self.assertRaisesRegex(ValueError, "안전하지 않은"):
                load_project(path)


if __name__ == "__main__":
    unittest.main()
