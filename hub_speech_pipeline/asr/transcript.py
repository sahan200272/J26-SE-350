"""Transcript documents: per chunk and per session (pure Python, no model imports).

Times:
* chunk-relative: seconds from the start of the chunk's audio (WhisperX output);
* session-relative: chunk-relative + the chunk's ``start_ms`` from its sidecar (the phone's
  monotonic offset from session start; pauses are gaps on this timeline).

Timing per chunk (milliseconds):
* ``queue_wait_ms``  - from the poll that found the chunk ready to the start of processing;
* ``decode_ms``      - Opus -> 16 kHz float PCM (ffmpeg, via whisperx.load_audio);
* ``transcribe_ms``  - WhisperX transcription (VAD + faster-whisper);
* ``align_ms``       - WhisperX forced alignment (wav2vec2) for word timestamps;
* ``total_ms``       - from the start of processing until the transcript is ready to write;
* ``rtf``            - total_ms / audio duration (sidecar samples / sample rate).

Latency per chunk: transcript write time (PC clock) minus the chunk's ``end_wallclock`` (phone
clock) converted to PC time with the measured phone - PC offset::

    latency = t_write_pc - (end_wallclock_phone - offset)

with uncertainty = offset uncertainty + 0.5 ms (``end_wallclock`` has millisecond precision).
"""

from __future__ import annotations

import statistics

from hub_speech_pipeline.tools.verify_session import ns_to_iso, wallclock_ns

CHUNK_SCHEMA = "c1-transcript-chunk/0.1"
SESSION_SCHEMA = "c1-transcript-session/0.1"


def _r(seconds: float | None) -> float | None:
    return None if seconds is None else round(seconds, 3)


def with_session_times(segments: list[dict], chunk_start_ms: float) -> list[dict]:
    """Copies of WhisperX segments with session-relative times added (seconds, 1 ms)."""
    offset = chunk_start_ms / 1000.0
    out = []
    for seg in segments:
        words = []
        for w in seg.get("words", []):
            start, end = w.get("start"), w.get("end")
            words.append({
                "word": w.get("word"),
                "start": _r(start), "end": _r(end),
                "session_start": _r(None if start is None else offset + start),
                "session_end": _r(None if end is None else offset + end),
                "score": None if w.get("score") is None else round(float(w["score"]), 3),
            })
        out.append({
            "text": seg.get("text", "").strip(),
            "start": _r(seg.get("start")), "end": _r(seg.get("end")),
            "session_start": _r(offset + seg["start"]) if seg.get("start") is not None else None,
            "session_end": _r(offset + seg["end"]) if seg.get("end") is not None else None,
            "words": words,
        })
    return out


def latency(written_ns: int, end_wallclock: str, clock: dict | None) -> dict:
    """End-to-end latency of one chunk; ``clock`` = {"offset_ms", "uncertainty_ms"} or None."""
    end_ns = wallclock_ns(end_wallclock)
    if clock is None:
        return {"latency_ms": round((written_ns - end_ns) / 1e6, 1), "clock_corrected": False,
                "clock_offset_ms": None, "uncertainty_ms": None,
                "transcript_written_pc": ns_to_iso(written_ns)}
    end_pc_ns = end_ns - clock["offset_ms"] * 1e6
    return {"latency_ms": round((written_ns - end_pc_ns) / 1e6, 1), "clock_corrected": True,
            "clock_offset_ms": round(clock["offset_ms"], 2),
            "uncertainty_ms": round(clock["uncertainty_ms"] + 0.5, 1),
            "transcript_written_pc": ns_to_iso(written_ns)}


def chunk_document(sidecar: dict, segments: list[dict], model: dict, timing: dict,
                   latency_info: dict, arrival: dict | None = None) -> dict:
    audio_s = sidecar["samples"] / sidecar["sample_rate"]
    return {
        "schema_version": CHUNK_SCHEMA,
        "session_id": sidecar["session_id"],
        "seq": sidecar["seq"],
        "audio_file": sidecar["audio_file"],
        "audio_sha256": sidecar["sha256"],
        "chunk_start_ms": sidecar["start_ms"],
        "chunk_end_ms": sidecar["end_ms"],
        "start_wallclock": sidecar["start_wallclock"],
        "end_wallclock": sidecar["end_wallclock"],
        "audio_duration_s": round(audio_s, 4),
        "model": model,
        "text": " ".join(s["text"] for s in segments).strip(),
        "segments": segments,
        "timing": timing | {"rtf": round(timing["total_ms"] / (audio_s * 1000), 4) if audio_s else None},
        "latency": latency_info,
        "arrival": arrival,
    }


def summarise(values: list[float]) -> dict | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"count": len(values), "median": round(statistics.median(values), 3),
            "max": round(max(values), 3), "min": round(min(values), 3)}


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    minutes, s = divmod(seconds, 60)
    return f"{int(minutes):02d}:{s:06.3f}"


def session_documents(manifest: dict, chunks: list[dict], model: dict, notes: list[str] | None = None) -> tuple[dict, str]:
    """(JSON, Markdown) transcript of a complete session, chunks in seq order."""
    chunks = sorted(chunks, key=lambda c: c["seq"])
    keys = ["queue_wait_ms", "decode_ms", "transcribe_ms", "align_ms", "total_ms", "rtf"]
    summary = {k: summarise([c["timing"].get(k) for c in chunks]) for k in keys}
    summary["latency_ms"] = summarise([c["latency"]["latency_ms"] for c in chunks])
    audio = sum(c["audio_duration_s"] for c in chunks)
    processing = sum(c["timing"]["total_ms"] for c in chunks) / 1000
    summary["session_audio_s"] = round(audio, 3)
    summary["session_processing_s"] = round(processing, 3)
    summary["session_rtf"] = round(processing / audio, 4) if audio else None
    doc = {
        "schema_version": SESSION_SCHEMA,
        "session_id": manifest["session_id"],
        "session_start_wallclock": manifest.get("session_start_wallclock"),
        "session_end_wallclock": manifest.get("session_end_wallclock"),
        "pause_intervals": manifest.get("pause_intervals"),
        "chunk_count": len(chunks),
        "model": model,
        "text": " ".join(c["text"] for c in chunks if c["text"]).strip(),
        "timing_summary": summary,
        "notes": notes or [],
        "chunks": chunks,
    }
    pauses = ", ".join(
        "%.1f-%.1f s (%s)" % (p["start_ms"] / 1000, p["end_ms"] / 1000, p["reason"])
        for p in manifest.get("pause_intervals") or []) or "none"
    lines = [
        f"# Transcript {manifest['session_id']}",
        "",
        f"- Session: {manifest.get('session_start_wallclock')} to {manifest.get('session_end_wallclock')}"
        f" (phone clock); {len(chunks)} chunks, {audio:.1f} s of speech",
        f"- Model: WhisperX {model.get('whisper_model')} ({model.get('compute_type')}, {model.get('device')}),"
        f" language {model.get('language')}, alignment {model.get('align_model')}",
        f"- Pauses: {pauses}",
    ] + [f"- Note: {n}" for n in notes or []] + ["", "## Transcript", ""]
    for c in chunks:
        for seg in c["segments"]:
            lines.append(f"**[{_clock(seg['session_start'])} - {_clock(seg['session_end'])}]** {seg['text']}")
            lines.append("")
        if not c["segments"]:
            lines.append(f"*(chunk {c['seq']}: no speech recognised)*")
            lines.append("")
    lines += ["## Timing per chunk", "",
              "| seq | audio s | queue ms | decode ms | transcribe ms | align ms | total ms | RTF | latency ms |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c in chunks:
        t, lat = c["timing"], c["latency"]
        lines.append(f"| {c['seq']} | {c['audio_duration_s']:.2f} | {t['queue_wait_ms']:.0f} | {t['decode_ms']:.0f}"
                     f" | {t['transcribe_ms']:.0f} | {t['align_ms']:.0f} | {t['total_ms']:.0f} | {t['rtf']:.3f}"
                     f" | {lat['latency_ms']:.0f} |")
    lines += ["", "## Summary", "", "| measure | median | max |", "|---|---:|---:|"]
    for k in keys + ["latency_ms"]:
        if summary[k]:
            lines.append(f"| {k} | {summary[k]['median']} | {summary[k]['max']} |")
    lines += ["", f"Session: {audio:.2f} s of audio processed in {processing:.2f} s (RTF {summary['session_rtf']}).",
              "Latency = transcript write time - chunk end_wallclock, corrected for the phone/PC clock offset"
              + (f" ({chunks[0]['latency']['clock_offset_ms']} ms +/- {chunks[0]['latency']['uncertainty_ms']} ms)."
                 if chunks and chunks[0]["latency"].get("clock_corrected") else " (not corrected: no clock offset)."),
              ""]
    return doc, "\n".join(lines)
