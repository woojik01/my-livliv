from __future__ import annotations

import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .core import ImageDocument, Layer
from .package_io import build_livliv_bytes


def project_runtime_dir() -> Path:
    """Find packaged player assets both in source checkouts and PyInstaller bundles."""
    import sys

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "runtime"
    return Path(__file__).resolve().parents[1] / "runtime"


class LocalPreviewServer:
    """Serve the pinned Player bundle and the current package on loopback only."""

    _CSP = (
        "default-src 'self' data: blob:; "
        "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "connect-src 'self'; font-src 'self'; media-src 'none'; worker-src 'none'; "
        "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )

    def __init__(self, asset_root: str | Path | None = None):
        self.asset_root = Path(asset_root or project_runtime_dir()).resolve()
        if not self.asset_root.is_dir():
            raise FileNotFoundError(f"LivLiv Player 자산 폴더가 없습니다: {self.asset_root}")
        self.token = secrets.token_urlsafe(32)
        self._package: bytes | None = None
        self._package_lock = threading.Lock()

        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "MyLivLivLocal/1"
            sys_version = ""

            def log_message(self, _format: str, *args) -> None:
                return

            def _reply(self, status: int, payload: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.send_header("Content-Security-Policy", owner._CSP)
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                request_path = unquote(urlsplit(self.path).path)
                prefix = f"/{owner.token}/"
                if not request_path.startswith(prefix):
                    self._reply(404, b"Not found")
                    return
                relative = request_path[len(prefix):]
                if relative == "api/model.livliv":
                    with owner._package_lock:
                        package = owner._package
                    if package is None:
                        self._reply(404, b"No preview package")
                    else:
                        self._reply(200, package, "application/zip")
                    return
                if "\\" in relative or "\x00" in relative:
                    self._reply(404, b"Not found")
                    return
                parts = PurePosixPath(relative).parts if relative else ()
                if any(part in {".", ".."} for part in parts):
                    self._reply(404, b"Not found")
                    return
                if not parts:
                    candidate = owner.asset_root / "preview.html"
                else:
                    candidate = owner.asset_root.joinpath(*parts)
                try:
                    resolved = candidate.resolve(strict=True)
                    if not resolved.is_relative_to(owner.asset_root) or not resolved.is_file():
                        raise ValueError("outside asset root")
                    payload = resolved.read_bytes()
                except (OSError, ValueError):
                    self._reply(404, b"Not found")
                    return
                content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
                if resolved.suffix.lower() == ".js":
                    content_type = "text/javascript; charset=utf-8"
                self._reply(200, payload, content_type)

            def do_POST(self) -> None:
                self._reply(405, b"Method not allowed")

            def do_OPTIONS(self) -> None:
                self._reply(405, b"Method not allowed")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._server.owner = self
        self._thread = threading.Thread(target=self._server.serve_forever, name="MyLivLivPlayerHost", daemon=True)
        self._started = False

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/{self.token}/"

    def start(self) -> None:
        if not self._started:
            self._thread.start()
            self._started = True

    def set_package(self, package: bytes) -> None:
        with self._package_lock:
            self._package = bytes(package)

    def close(self) -> None:
        if self._started:
            self._server.shutdown()
            self._thread.join(timeout=2)
            self._started = False
        self._server.server_close()


def snapshot_document(document: ImageDocument) -> ImageDocument:
    """Create separate QImage values so the preview worker cannot see in-flight edits."""
    layers = [
        Layer(layer.name, layer.group, QImage(layer.mask), layer.visible)
        for layer in document.layers
    ]
    return ImageDocument(
        QImage(document.source),
        document.source_name,
        layers,
        tuple(document.head_box) if document.head_box else None,
    )


class PreviewBuildWorker(QThread):
    package_ready = Signal(bytes)
    failed = Signal(str)

    def __init__(self, document: ImageDocument, model_name: str, parent=None):
        super().__init__(parent)
        self._document = document
        self._model_name = model_name

    def run(self) -> None:
        try:
            _model, package = build_livliv_bytes(self._document, self._model_name)
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.package_ready.emit(package)
