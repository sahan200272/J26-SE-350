"""Tiny local web server.

GET  /            the page
GET  /api/status  reads the result files (the official targets)
GET  /api/sample  the sample transcript, for the "Load sample" button
POST /api/run     runs Stage 1 and Stage 2 on a pasted transcript (demo only)

The server listens on 127.0.0.1 only. A pasted transcript stays on this
computer: it goes to the local LLM and the local MCP servers, nowhere else.
A demo run never changes the target rows; those come only from result files.
"""

from __future__ import annotations

import json
import tempfile
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from scripts.panel_dashboard.objectives import OBJECTIVES
from scripts.panel_dashboard.status import evaluate_all

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_DIR = REPO_ROOT / "docs" / "evaluation"
DEFAULT_VAULT = Path(tempfile.gettempdir()) / "j26_pp1_demo_vault"
SAMPLE = REPO_ROOT / "agentic_core" / "datasets" / "segmentation" / "sample_standup.md"
PAGE = Path(__file__).with_name("index.html")
MAX_TRANSCRIPT_CHARS = 50_000  # untuned guess; a long meeting is about 10,000 words


def build_status(eval_dir: Path) -> dict[str, Any]:
    """Read every result file now (no caching) and return the panel data."""
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds").replace("T", " "),
        "eval_dir": str(eval_dir.relative_to(REPO_ROOT)) if eval_dir.is_relative_to(REPO_ROOT) else str(eval_dir),
        "rows": evaluate_all(OBJECTIVES, eval_dir),
    }


def _default_client():
    from agentic_core.llm.client import LLMClient

    return LLMClient()


def make_handler(
    eval_dir: Path,
    vault_root: Path = DEFAULT_VAULT,
    client_factory: Callable[[], Any] = _default_client,
) -> type[BaseHTTPRequestHandler]:
    run_lock = threading.Lock()  # one pipeline run at a time

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/status":
                self._json(build_status(eval_dir))
            elif path == "/api/sample":
                try:
                    text = SAMPLE.read_text(encoding="utf-8-sig")
                except OSError:
                    self._json({"error": "Sample transcript not found."}, HTTPStatus.NOT_FOUND)
                    return
                self._json({"name": SAMPLE.name, "text": text})
            else:
                self._send(b"Not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != "/api/run":
                self._send(b"Not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_TRANSCRIPT_CHARS * 4 + 1000:
                self._json({"error": "Transcript is too large."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                text = body["transcript"]
                date_text = body.get("date") or None
                attack = body.get("attack") is True
                if not isinstance(text, str) or (date_text is not None and not isinstance(date_text, str)):
                    raise TypeError
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
                self._json({"error": "Send JSON with a 'transcript' text."}, HTTPStatus.BAD_REQUEST)
                return
            if not text.strip():
                self._json({"error": "Paste a transcript first."}, HTTPStatus.BAD_REQUEST)
                return
            if len(text) > MAX_TRANSCRIPT_CHARS:
                self._json({"error": f"Transcript is too large (over {MAX_TRANSCRIPT_CHARS} characters)."},
                           HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            if not run_lock.acquire(blocking=False):
                self._json({"error": "A run is already in progress. Wait for it to finish."},
                           HTTPStatus.CONFLICT)
                return
            try:
                self._run(text, date_text, attack)
            finally:
                run_lock.release()

        def _run(self, text: str, date_text: str | None, attack: bool) -> None:
            from scripts.demo_pipeline import run_pipeline

            client = client_factory()
            if not client.is_ready():
                self._json({"error": "Ollama is not running or the model is missing. Start Ollama first."},
                           HTTPStatus.SERVICE_UNAVAILABLE)
                return
            vault = vault_root / datetime.now().strftime("run_%Y%m%d_%H%M%S")
            try:
                result = run_pipeline(text, "pasted transcript", vault, client,
                                      date_text=date_text, attack=attack, say=lambda _line: None)
            except ValueError as error:  # bad transcript format or bad date
                self._json({"error": f"Transcript problem: {error}"}, HTTPStatus.BAD_REQUEST)
                return
            self._json(result)

        def _json(self, data: Any, code: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(data, indent=2).encode("utf-8")
            self._send(body, "application/json; charset=utf-8", code)

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


def make_server(
    host: str,
    port: int,
    eval_dir: Path,
    vault_root: Path = DEFAULT_VAULT,
    client_factory: Callable[[], Any] = _default_client,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(eval_dir, vault_root, client_factory))
