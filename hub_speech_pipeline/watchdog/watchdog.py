"""Inbox watchdog: finds ready chunks, processes them in order, completes sessions.

Rules (H1):
* The inbox is **read-only**: the watchdog only lists, stats and reads files there.
* A chunk ``<sid>_<seq:05d>`` is **ready** only when its ``.opus`` and ``.json`` both exist,
  both have the same size and mtime in two consecutive polls (stable), the sidecar parses and
  names this session, seq and audio file, and the SHA-256 of the ``.opus`` equals the sidecar's
  ``sha256``. Syncthing's temporary files are ignored.
* Chunks are processed **in seq order per session**: seq n+1 waits for seq n. The only seqs
  passed over are those the session manifest lists in ``failed_chunks`` (never delivered).
* **Persistent state** (``<outputs>/state.json``, written atomically after every chunk) holds
  the next seq per session, so after a restart nothing is reprocessed or skipped. If the hub
  stopped after writing a transcript but before saving state, the transcript (same audio
  SHA-256) is adopted instead of being redone.
* A session is **complete** only when its manifest has arrived (stable, parses) and every file
  it lists is present and processed - the manifest can arrive before the last ``.opus``. Then
  the session transcript (Markdown + JSON) is written once.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, Protocol

from hub_speech_pipeline.asr import transcript
from hub_speech_pipeline.tools.verify_session import TEMP_FILE, creation_time_ns, ns_to_iso

STATE_SCHEMA = "c1-hub-state/0.1"
CHUNK_SCHEMA = "c1-chunk/0.1"
MANIFEST_SCHEMA = "c1-manifest/0.1"
BACKLOG_THRESHOLD_S = 60  # processed this long after arrival: latency is not a live measurement


class Engine(Protocol):
    info: dict

    def transcribe(self, audio_path: Path) -> tuple[list[dict], dict]: ...


@dataclasses.dataclass
class ReadyChunk:
    session_id: str
    seq: int
    opus: Path
    sidecar_path: Path
    sidecar: dict
    first_seen_ns: int
    ready_ns: int


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class State:
    """Per-session progress, persisted as JSON."""

    def __init__(self, path: Path):
        self.path = path
        if path.is_file():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = {"schema_version": STATE_SCHEMA, "sessions": {}}

    def session(self, sid: str) -> dict:
        return self.data["sessions"].setdefault(
            sid, {"next_seq": 0, "processed": {}, "skipped_failed": [], "completed": False})

    def save(self) -> None:
        write_atomic(self.path, json.dumps(self.data, indent=2) + "\n")


class Watchdog:
    def __init__(self, inbox: Path, outputs: Path, engine: Engine,
                 clock: Callable[[], dict | None] = lambda: None, log: Callable[[str], None] = print,
                 now_ns: Callable[[], int] = time.time_ns, sessions: set[str] | None = None):
        inbox, outputs = Path(inbox).resolve(), Path(outputs).resolve()
        if outputs == inbox or inbox in outputs.parents:
            raise ValueError("outputs must not be inside the read-only inbox")
        self.inbox, self.outputs, self.engine = inbox, outputs, engine
        self.clock, self.log, self.now_ns, self.only = clock, log, now_ns, sessions
        self.state = State(outputs / "state.json")
        self._previous: dict[str, tuple[int, int]] = {}  # rel path -> (size, mtime_ns), last poll
        self._first_seen: dict[tuple[str, int], int] = {}
        self._ready_since: dict[tuple[str, int], int] = {}
        self._sha_ok: dict[str, tuple[int, int]] = {}  # rel path -> (size, mtime) verified
        self._warned: set[str] = set()
        self.processed_count = 0

    # --- polling -------------------------------------------------------------------------

    def _scan(self) -> dict[str, dict[str, tuple[int, int]]]:
        sessions: dict[str, dict[str, tuple[int, int]]] = {}
        if not self.inbox.is_dir():
            return sessions
        for entry in os.scandir(self.inbox):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if self.only is not None and entry.name not in self.only:
                continue
            files = {}
            for f in os.scandir(entry.path):
                if f.is_file() and not TEMP_FILE.match(f.name):
                    st = f.stat()
                    files[f.name] = (st.st_size, st.st_mtime_ns)
            sessions[entry.name] = files
        return sessions

    def poll_once(self) -> int:
        """One pass over the inbox; returns the number of chunks processed."""
        snapshot = self._scan()
        current = {f"{sid}/{name}": meta for sid, files in snapshot.items() for name, meta in files.items()}
        stable = {rel for rel, meta in current.items() if self._previous.get(rel) == meta}
        before = self.processed_count
        for sid in sorted(snapshot):
            self._advance(sid, snapshot[sid], stable)
        self._previous = current
        return self.processed_count - before

    def run(self, interval_s: float = 0.2, until_idle: bool = False, idle_polls: int = 10,
            stop: Callable[[], bool] | None = None) -> None:
        """Polls forever, or with ``until_idle`` until every session is complete or nothing
        has changed for ``idle_polls`` polls, or until ``stop()`` returns True."""
        quiet = 0
        while True:
            processed = self.poll_once()
            if stop is not None and stop():
                return
            if until_idle:
                pending = self.incomplete_sessions()
                quiet = 0 if processed else quiet + 1
                if not pending and quiet >= 2:
                    return
                if pending and quiet >= idle_polls:
                    self.log(f"[watchdog] idle with incomplete sessions: {pending}")
                    return
            time.sleep(interval_s)

    def incomplete_sessions(self) -> list[str]:
        return sorted(sid for sid in self._scan() if not self.state.session(sid)["completed"])

    def completed_sessions(self) -> set[str]:
        return {sid for sid, st in self.state.data["sessions"].items() if st.get("completed")}

    # --- per session ---------------------------------------------------------------------

    def _advance(self, sid: str, files: dict[str, tuple[int, int]], stable: set[str]) -> None:
        st = self.state.session(sid)
        if st["completed"]:
            return
        manifest = self._manifest(sid, files, stable)
        failed = {f["seq"] for f in manifest.get("failed_chunks", [])} if manifest else set()
        while True:
            n = st["next_seq"]
            if n in failed:
                st["skipped_failed"].append(n)
                st["next_seq"] = n + 1
                self.state.save()
                self.log(f"[watchdog] {sid} #{n}: listed as failed in the manifest, passed over")
                continue
            chunk = self._ready(sid, n, files, stable)
            if chunk is None:
                break
            self._process(chunk, st)
        if manifest and self._complete(sid, manifest, files, st):
            self._finish_session(sid, manifest, st)

    def _manifest(self, sid: str, files, stable) -> dict | None:
        name = f"{sid}_manifest.json"
        if name not in files or f"{sid}/{name}" not in stable:
            return None
        try:
            manifest = json.loads((self.inbox / sid / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._warn_once(f"{sid}/{name}", f"[watchdog] {sid}: manifest unreadable ({e}), waiting")
            return None
        if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("session_id") != sid:
            self._warn_once(f"{sid}/{name}#schema", f"[watchdog] {sid}: manifest schema/session mismatch, waiting")
            return None
        return manifest

    def _ready(self, sid: str, seq: int, files, stable) -> ReadyChunk | None:
        base = f"{sid}_{seq:05d}"
        opus_name, json_name = f"{base}.opus", f"{base}.json"
        if opus_name not in files or json_name not in files:
            return None
        key = (sid, seq)
        now = self.now_ns()
        self._first_seen.setdefault(key, now)
        opus_rel, json_rel = f"{sid}/{opus_name}", f"{sid}/{json_name}"
        if opus_rel not in stable or json_rel not in stable or files[opus_name][0] == 0:
            return None  # just appeared or still changing
        opus, side = self.inbox / sid / opus_name, self.inbox / sid / json_name
        try:
            sidecar = json.loads(side.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self._warn_once(json_rel, f"[watchdog] {json_rel}: sidecar unreadable ({e}), waiting")
            return None
        if (sidecar.get("schema_version") != CHUNK_SCHEMA or sidecar.get("session_id") != sid
                or sidecar.get("seq") != seq or sidecar.get("audio_file") != opus_name):
            self._warn_once(json_rel + "#fields", f"[watchdog] {json_rel}: sidecar does not describe this chunk, waiting")
            return None
        if self._sha_ok.get(opus_rel) != files[opus_name]:
            digest = sha256_file(opus)
            if digest != sidecar.get("sha256"):
                self._warn_once(opus_rel + "#" + digest, f"[watchdog] {opus_rel}: SHA-256 {digest[:12]} != sidecar "
                                f"{str(sidecar.get('sha256'))[:12]}, waiting")
                return None
            self._sha_ok[opus_rel] = files[opus_name]
        ready = self._ready_since.setdefault(key, now)
        return ReadyChunk(sid, seq, opus, side, sidecar, self._first_seen[key], ready)

    def _output_path(self, sid: str, seq: int) -> Path:
        return self.outputs / sid / f"{sid}_{seq:05d}.transcript.json"

    def _process(self, chunk: ReadyChunk, st: dict) -> None:
        out = self._output_path(chunk.session_id, chunk.seq)
        if out.is_file():  # written before a crash, state not saved: adopt, do not redo
            try:
                existing = json.loads(out.read_text(encoding="utf-8"))
            except ValueError:
                existing = {}
            if existing.get("audio_sha256") == chunk.sidecar["sha256"]:
                self._mark(chunk, st, out, recovered=True)
                self.log(f"[watchdog] {chunk.session_id} #{chunk.seq}: transcript already written, adopted")
                return
        start_ns = self.now_ns()
        t0 = time.perf_counter()
        segments, stages = self.engine.transcribe(chunk.opus)
        timed = transcript.with_session_times(segments, chunk.sidecar["start_ms"])
        total_ms = (time.perf_counter() - t0) * 1000
        timing = {"queue_wait_ms": round((start_ns - chunk.ready_ns) / 1e6, 1)} | stages | {"total_ms": round(total_ms, 1)}
        arrival = self._arrival(chunk, start_ns)
        written_ns = self.now_ns()
        doc = transcript.chunk_document(chunk.sidecar, timed, self.engine.info, timing,
                                        transcript.latency(written_ns, chunk.sidecar["end_wallclock"], self.clock()),
                                        arrival)
        write_atomic(out, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        self._mark(chunk, st, out, recovered=False)
        self.processed_count += 1
        self.log(f"[watchdog] {chunk.session_id} #{chunk.seq}: {doc['audio_duration_s']:.2f} s audio, "
                 f"total {timing['total_ms']:.0f} ms (decode {timing['decode_ms']:.0f}, transcribe "
                 f"{timing['transcribe_ms']:.0f}, align {timing['align_ms']:.0f}), RTF {doc['timing']['rtf']:.3f}, "
                 f"latency {doc['latency']['latency_ms']:.0f} ms: {doc['text'][:80]!r}")

    def _arrival(self, chunk: ReadyChunk, start_ns: int) -> dict:
        info = {"first_seen_pc": ns_to_iso(chunk.first_seen_ns), "ready_pc": ns_to_iso(chunk.ready_ns),
                "processing_started_pc": ns_to_iso(start_ns)}
        try:
            created = max(creation_time_ns(chunk.opus), creation_time_ns(chunk.sidecar_path))
            waited = (start_ns - created) / 1e9
            info |= {"created_pc": ns_to_iso(created),
                     "created_note": "file creation time = start of the Syncthing download",
                     "waited_since_arrival_s": round(waited, 3),
                     "backlog": waited > BACKLOG_THRESHOLD_S}
        except (OSError, RuntimeError):
            info["created_pc"] = None
        return info

    def _mark(self, chunk: ReadyChunk, st: dict, out: Path, recovered: bool) -> None:
        st["processed"][str(chunk.seq)] = {
            "audio_sha256": chunk.sidecar["sha256"], "output": out.relative_to(self.outputs).as_posix(),
            "at": ns_to_iso(self.now_ns()), "recovered": recovered}
        st["next_seq"] = chunk.seq + 1
        self.state.save()

    def _complete(self, sid: str, manifest: dict, files, st: dict) -> bool:
        listed = [name for c in manifest.get("chunks", []) for name in (c["audio_file"], c["sidecar_file"])]
        if any(name not in files for name in listed):
            return False
        done = set(st["processed"]) | {str(n) for n in st["skipped_failed"]}
        return all(str(c["seq"]) in done for c in manifest.get("chunks", []))

    def _finish_session(self, sid: str, manifest: dict, st: dict) -> None:
        docs = [json.loads((self.outputs / st["processed"][str(c["seq"])]["output"]).read_text(encoding="utf-8"))
                for c in sorted(manifest.get("chunks", []), key=lambda c: c["seq"])]
        notes = []
        if any((d.get("arrival") or {}).get("backlog") for d in docs):
            notes.append(f"Processed from backlog (more than {BACKLOG_THRESHOLD_S} s after arrival): the latency "
                         "values include the time the chunks waited before the hub ran; they are not live latencies.")
        if st["skipped_failed"]:
            notes.append(f"Chunks listed as failed by the phone (never delivered): {st['skipped_failed']}")
        doc, markdown = transcript.session_documents(manifest, docs, self.engine.info, notes)
        write_atomic(self.outputs / sid / f"{sid}_transcript.json", json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        write_atomic(self.outputs / sid / f"{sid}_transcript.md", markdown)
        st["completed"] = True
        st["completed_at"] = ns_to_iso(self.now_ns())
        self.state.save()
        self.log(f"[watchdog] {sid}: session complete, {len(docs)} chunks -> {sid}_transcript.md/.json")

    def _warn_once(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self.log(message)
