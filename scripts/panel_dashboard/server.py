"""Tiny local web server: GET / serves the page, GET /api/status reads the result files."""

from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from scripts.panel_dashboard.objectives import OBJECTIVES
from scripts.panel_dashboard.status import evaluate_all

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_DIR = REPO_ROOT / "docs" / "evaluation"
PAGE = Path(__file__).with_name("index.html")


def build_status(eval_dir: Path) -> dict[str, Any]:
    """Read every result file now (no caching) and return the panel data."""
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds").replace("T", " "),
        "eval_dir": str(eval_dir.relative_to(REPO_ROOT)) if eval_dir.is_relative_to(REPO_ROOT) else str(eval_dir),
        "rows": evaluate_all(OBJECTIVES, eval_dir),
    }


def make_handler(eval_dir: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/status":
                body = json.dumps(build_status(eval_dir), indent=2).encode("utf-8")
                self._send(body, "application/json; charset=utf-8")
            else:
                self._send(b"Not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

        def _send(self, body: bytes, content_type: str, code: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # keep the console quiet
            pass

    return Handler


def make_server(host: str, port: int, eval_dir: Path) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(eval_dir))
