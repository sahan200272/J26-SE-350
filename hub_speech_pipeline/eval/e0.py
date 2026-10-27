"""E0 dataset pilot on one AMI meeting: references, VAD scoring, ASR on oracle vs VAD segments.

    python -m hub_speech_pipeline.eval.e0 refs            # NXT words -> transcript, speech regions, entities
    python -m hub_speech_pipeline.eval.e0 vad             # score vad_offline.dart outputs (10 ms frames)
    python -m hub_speech_pipeline.eval.e0 asr --model base --segments oracle   # or --segments vad
    python -m hub_speech_pipeline.eval.e0 score           # WER (Whisper normaliser) + named entities

Inputs: ``D:\\SLIIT\\Research\\datasets\\AMI`` (annotations, audio, derived references) and
``c1_outputs/E0/vad/<meeting>.{vad_segmenter,fixed_chunk}.json`` from
``mobile_client/tool/vad_offline.dart``. Outputs go to ``c1_outputs/E0``.

ASR runs offline (see common/offline.py); each segment is cut from the meeting audio and
transcribed on its own, as the hub transcribes each chunk. Alignment is skipped (WER does not
need word times), so the RTF here is transcription only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

from hub_speech_pipeline.eval import ami, vad_score

AMI_ROOT = Path(r"D:\SLIIT\Research\datasets\AMI")
OUTPUTS = Path(r"D:\SLIIT\Research\05 - Implementation\c1_outputs\E0")
VAD_FRAME_S = 512 / 16000  # EnergyVad frame: 512 samples at 16 kHz
MIN_SEGMENT_S = 0.1


def paths(meeting: str, root: Path = AMI_ROOT) -> dict[str, Path]:
    derived = root / "derived"
    return {
        "annotations": root / "annotations",
        "wav": root / "amicorpus" / meeting / "audio" / f"{meeting}.Mix-Headset.wav",
        "derived": derived,
        "words_tsv": derived / f"{meeting}.words.tsv",
        "reference": derived / f"{meeting}.reference.txt",
        "regions": derived / f"{meeting}.speech_regions.json",
        "entities": derived / f"{meeting}.entities.json",
    }


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            raise ValueError(f"{path}: expected 16 kHz mono 16-bit")
        return w.getnframes() / w.getframerate()


# --- refs ----------------------------------------------------------------------------------

def build_references(meeting: str, root: Path = AMI_ROOT) -> dict:
    p = paths(meeting, root)
    words = ami.load_words(p["annotations"], meeting)
    ref_words = ami.reference_words(words)
    regions = ami.speech_regions(words)
    word_regions = ami.speech_regions(words, merge_gap=0.0)
    entities = ami.load_entities(p["annotations"], meeting, words)
    p["derived"].mkdir(parents=True, exist_ok=True)
    with open(p["words_tsv"], "w", encoding="utf-8") as f:
        f.write("start\tend\tspeaker\tword\tpunc\ttrunc\n")
        for w in sorted((w for ws in words.values() for w in ws), key=lambda w: (w.start, w.end, w.speaker)):
            f.write(f"{w.start:.3f}\t{w.end:.3f}\t{w.speaker}\t{w.text}\t{int(w.punc)}\t{int(w.trunc)}\n")
    p["reference"].write_text(ami.reference_text(words) + "\n", encoding="utf-8")
    duration = wav_duration(p["wav"])
    summary = {
        "meeting": meeting, "duration_s": round(duration, 3), "speakers": list(words),
        "w_elements": sum(len(ws) for ws in words.values()),
        "punctuation_tokens": sum(w.punc for ws in words.values() for w in ws),
        "fragments": sum(w.trunc for ws in words.values() for w in ws),
        "reference_words": len(ref_words),
        "merge_gap_s": ami.NIST_MERGE_GAP_S,
        "regions": len(regions), "speech_s": round(sum(e - s for s, e in regions), 3),
        "speech_fraction": round(sum(e - s for s, e in regions) / duration, 4),
        "unmerged_regions": len(word_regions),
        "unmerged_speech_s": round(sum(e - s for s, e in word_regions), 3),
        "entities": len(entities),
    }
    p["regions"].write_text(json.dumps(summary | {
        "regions": [[round(s, 3), round(e, 3)] for s, e in regions],
        "unmerged_regions_list": [[round(s, 3), round(e, 3)] for s, e in word_regions]}, indent=1) + "\n",
        encoding="utf-8")
    p["entities"].write_text(json.dumps([e.__dict__ | {"word_ids": list(e.word_ids)} for e in entities],
                                        indent=1) + "\n", encoding="utf-8")
    return summary


# --- vad -----------------------------------------------------------------------------------

def score_vad(meeting: str, root: Path = AMI_ROOT, outputs: Path = OUTPUTS) -> dict:
    p = paths(meeting, root)
    refs = json.loads(p["regions"].read_text(encoding="utf-8"))
    count = vad_score.n_frames(refs["duration_s"])
    reference = {"merged_0.3s": vad_score.frames_from_regions([tuple(r) for r in refs["regions"]], count),
                 "words_unmerged": vad_score.frames_from_regions([tuple(r) for r in refs["unmerged_regions_list"]], count)}
    masks = {name: {"no_collar": None,
                    "collar_0.25s": vad_score.collar_mask(
                        [tuple(r) for r in refs["regions" if name == "merged_0.3s" else "unmerged_regions_list"]],
                        count, 0.25)}
             for name in reference}
    vad = json.loads((outputs / "vad" / f"{meeting}.vad_segmenter.json").read_text(encoding="utf-8"))
    fixed = json.loads((outputs / "vad" / f"{meeting}.fixed_chunk.json").read_text(encoding="utf-8"))
    systems = {
        "energy_vad_frames": vad_score.frames_from_decisions([f["speech"] for f in vad["frames"]], VAD_FRAME_S, count),
        "vad_segmenter": vad_score.frames_from_regions([(s["start_s"], s["end_s"]) for s in vad["segments"]], count),
        "fixed_chunk_5s": vad_score.frames_from_regions([(s["start_s"], s["end_s"]) for s in fixed["segments"]], count),
    }
    result = {"meeting": meeting, "frame_s": 0.01, "frames": count,
              "configs": {"vad_segmenter": {"vad": vad["vad"], "segmenter": vad["segmenter"]},
                          "fixed_chunk_5s": {"vad": fixed["vad"], "segmenter": fixed["segmenter"]}},
              "segments": {"vad_segmenter": len(vad["segments"]), "fixed_chunk_5s": len(fixed["segments"])},
              "scores": {}}
    for ref_name, ref in reference.items():
        for collar_name, mask in masks[ref_name].items():
            for sys_name, hyp in systems.items():
                result["scores"][f"{sys_name} | {ref_name} | {collar_name}"] = vad_score.score(ref, hyp, mask)
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / f"{meeting}.vad_scores.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


# --- asr -----------------------------------------------------------------------------------

def run_asr(meeting: str, model: str, segmentation: str, root: Path = AMI_ROOT, outputs: Path = OUTPUTS,
            threads: int = 4) -> dict:
    from hub_speech_pipeline.common.offline import blocked_attempts, enforce_offline

    enforce_offline()
    from hub_speech_pipeline.asr.engine import WhisperXEngine

    p = paths(meeting, root)
    if segmentation == "oracle":
        regions = [tuple(r) for r in json.loads(p["regions"].read_text(encoding="utf-8"))["regions"]]
    elif segmentation == "vad":
        vad = json.loads((outputs / "vad" / f"{meeting}.vad_segmenter.json").read_text(encoding="utf-8"))
        regions = [(s["start_s"], s["end_s"]) for s in vad["segments"]]
    else:
        raise ValueError(segmentation)
    engine = WhisperXEngine(model, "int8", "en", threads=threads)
    t0 = time.perf_counter()
    audio = engine.load_audio(p["wav"])
    decode_ms = (time.perf_counter() - t0) * 1000
    rows, total_ms, skipped = [], 0.0, []
    for i, (start, end) in enumerate(sorted(regions)):
        if end - start < MIN_SEGMENT_S:
            skipped.append([start, end])
            continue
        segments, ms = engine.transcribe_array(audio[int(round(start * 16000)):int(round(end * 16000))])
        total_ms += ms
        text = " ".join(s["text"].strip() for s in segments).strip()
        rows.append({"start": round(start, 3), "end": round(end, 3), "ms": round(ms, 1), "text": text})
        print(f"[{model}/{segmentation}] {i + 1}/{len(regions)} {start:8.2f}-{end:8.2f} s {ms:7.0f} ms {text[:70]!r}", flush=True)
    audio_s = sum(r["end"] - r["start"] for r in rows)
    result = {"meeting": meeting, "model": engine.info, "segmentation": segmentation,
              "segments": rows, "skipped_short_segments": skipped, "min_segment_s": MIN_SEGMENT_S,
              "decode_ms": round(decode_ms, 1), "model_load_s": round(engine.load_s, 2),
              "audio_s": round(audio_s, 3), "transcribe_ms": round(total_ms, 1),
              "rtf": round(total_ms / 1000 / audio_s, 4) if audio_s else None,
              "network_attempts_blocked": blocked_attempts()}
    out = outputs / "asr" / f"{meeting}.{model}.{segmentation}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


# --- score ---------------------------------------------------------------------------------

def count_ngram(tokens: list[str], gram: tuple[str, ...]) -> int:
    n = len(gram)
    return sum(1 for i in range(len(tokens) - n + 1) if tuple(tokens[i:i + n]) == gram) if n else 0


def entity_matches(entities: list[dict], ref_tokens: list[str], hyp_tokens: list[str]) -> dict:
    """Per distinct normalised entity: mentions, found in the normalised reference, and
    correct in the hypothesis = min(mentions, exact n-gram occurrences in the hypothesis)."""
    from hub_speech_pipeline.asr.wer import tokens

    groups: dict[tuple[str, ...], dict] = {}
    for e in entities:
        gram = tuple(tokens(e["text"], "whisper"))
        g = groups.setdefault(gram, {"text": " ".join(gram), "surface": e["text"], "type": e["type"],
                                     "category": e["category"], "mentions": 0})
        g["mentions"] += 1
    rows = []
    for gram, g in groups.items():
        found_ref = count_ngram(ref_tokens, gram)
        found_hyp = count_ngram(hyp_tokens, gram)
        rows.append(g | {"in_reference": found_ref, "in_hypothesis": found_hyp,
                         "correct": min(g["mentions"], found_hyp) if gram else 0, "empty_after_normalisation": not gram})
    rows.sort(key=lambda r: (-r["mentions"], r["text"]))
    mentions = sum(r["mentions"] for r in rows)
    correct = sum(r["correct"] for r in rows)
    by_category: dict[str, list[int]] = {}
    for r in rows:
        c = by_category.setdefault(r["category"], [0, 0])
        c[0] += r["correct"]
        c[1] += r["mentions"]
    return {"mentions": mentions, "correct": correct, "distinct": len(rows),
            "by_category": {k: {"correct": v[0], "mentions": v[1]} for k, v in sorted(by_category.items())},
            "entities": rows}


def score_asr(meeting: str, root: Path = AMI_ROOT, outputs: Path = OUTPUTS) -> dict:
    from hub_speech_pipeline.asr.normalizer import provenance
    from hub_speech_pipeline.asr.wer import align_words, tokens

    p = paths(meeting, root)
    reference = p["reference"].read_text(encoding="utf-8")
    ref_tokens = tokens(reference, "whisper")
    entities = json.loads(p["entities"].read_text(encoding="utf-8"))
    result = {"meeting": meeting, "normaliser": provenance(), "reference_tokens": len(ref_tokens), "runs": {}}
    for path in sorted((outputs / "asr").glob(f"{meeting}.*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        hyp = " ".join(s["text"] for s in sorted(run["segments"], key=lambda s: s["start"]))
        hyp_tokens = tokens(hyp, "whisper")
        w = align_words(ref_tokens, hyp_tokens)
        key = f"{run['model']['whisper_model']}.{run['segmentation']}"
        result["runs"][key] = {
            "wer": round(w.wer, 4), "substitutions": w.substitutions, "deletions": w.deletions,
            "insertions": w.insertions, "reference_words": w.reference_words, "hypothesis_words": w.hypothesis_words,
            "segments": len(run["segments"]), "audio_s": run["audio_s"], "transcribe_ms": run["transcribe_ms"],
            "rtf": run["rtf"], "rtf_vs_meeting": round(run["transcribe_ms"] / 1000 / json.loads(
                p["regions"].read_text(encoding="utf-8"))["duration_s"], 4),
            "skipped_short_segments": len(run["skipped_short_segments"]),
            "network_attempts_blocked": len(run["network_attempts_blocked"]),
            "named_entities": entity_matches(entities, ref_tokens, hyp_tokens),
        }
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / f"{meeting}.asr_scores.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                                                         encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["refs", "vad", "asr", "score"])
    parser.add_argument("--meeting", default="ES2004a")
    parser.add_argument("--model", choices=["base", "small"])
    parser.add_argument("--segments", choices=["oracle", "vad"])
    args = parser.parse_args(argv)
    if args.command == "refs":
        print(json.dumps(build_references(args.meeting), indent=1))
    elif args.command == "vad":
        r = score_vad(args.meeting)
        for k, v in r["scores"].items():
            print(f"{k:55s} P {v['precision']:.3f} R {v['recall']:.3f} F1 {v['f1']:.3f} "
                  f"(sys speech {v['system_speech_fraction']:.3f}, ref speech {v['reference_speech_fraction']:.3f}, "
                  f"scored {v['scored_frames']})")
    elif args.command == "asr":
        if not args.model or not args.segments:
            parser.error("asr needs --model and --segments")
        r = run_asr(args.meeting, args.model, args.segments)
        print(f"{args.model}/{args.segments}: {len(r['segments'])} segments, {r['audio_s']:.1f} s audio, "
              f"transcribe {r['transcribe_ms'] / 1000:.1f} s, RTF {r['rtf']}, blocked {len(r['network_attempts_blocked'])}")
    else:
        r = score_asr(args.meeting)
        for k, v in r["runs"].items():
            ne = v["named_entities"]
            print(f"{k:14s} WER {v['wer']:.4f} (S {v['substitutions']} D {v['deletions']} I {v['insertions']} / "
                  f"{v['reference_words']}), RTF {v['rtf']}, NE {ne['correct']}/{ne['mentions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
