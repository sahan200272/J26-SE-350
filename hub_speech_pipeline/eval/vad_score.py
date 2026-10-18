"""Frame-level VAD scoring against reference speech regions (stdlib only).

The timeline is cut into frames of ``frame_s`` (10 ms). A frame is speech in a reference or a
system output when its **midpoint** lies inside one of its regions; frame decisions of a
coarser VAD (e.g. 32 ms frames) are looked up at each 10 ms frame's midpoint.

With a ``collar``, frames whose midpoint lies at most ``collar`` seconds (inclusive) from a
reference region boundary (a start or an end) are not scored, as in NIST md-eval's no-score
collar; the score then measures the regions away from their exact edges.
"""

from __future__ import annotations

import math


def n_frames(duration_s: float, frame_s: float = 0.01) -> int:
    return int(math.floor(duration_s / frame_s + 1e-9))


def frames_from_regions(regions: list[tuple[float, float]], count: int, frame_s: float = 0.01) -> bytearray:
    """1 where the frame midpoint is inside a region (regions sorted, non-overlapping or not)."""
    out = bytearray(count)
    for start, end in regions:
        first = max(0, math.ceil(start / frame_s - 0.5 - 1e-9))  # first frame with midpoint >= start
        last = min(count, math.ceil(end / frame_s - 0.5 - 1e-9))  # frames with midpoint < end
        for k in range(first, last):
            out[k] = 1
    return out


def frames_from_decisions(decisions: list[bool], decision_frame_s: float, count: int,
                          frame_s: float = 0.01) -> bytearray:
    out = bytearray(count)
    for k in range(count):
        i = int(((k + 0.5) * frame_s) / decision_frame_s)
        if i < len(decisions) and decisions[i]:
            out[k] = 1
    return out


def collar_mask(regions: list[tuple[float, float]], count: int, collar_s: float, frame_s: float = 0.01) -> bytearray:
    """1 = scored; 0 = within ``collar_s`` of a reference boundary."""
    mask = bytearray([1]) * count
    if collar_s <= 0:
        return mask
    for boundary in sorted({t for region in regions for t in region}):
        first = max(0, math.ceil((boundary - collar_s) / frame_s - 0.5 - 1e-9))
        last = min(count, math.floor((boundary + collar_s) / frame_s - 0.5 + 1e-9) + 1)
        for k in range(first, last):
            mask[k] = 0
    return mask


def score(reference: bytearray, hypothesis: bytearray, mask: bytearray | None = None,
          frame_s: float = 0.01) -> dict:
    if len(reference) != len(hypothesis):
        raise ValueError("reference and hypothesis have different frame counts")
    tp = fp = fn = tn = 0
    for k in range(len(reference)):
        if mask is not None and not mask[k]:
            continue
        r, h = reference[k], hypothesis[k]
        if r and h:
            tp += 1
        elif h:
            fp += 1
        elif r:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    scored = tp + fp + fn + tn
    return {
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "accuracy": round((tp + tn) / scored, 4) if scored else 0.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "scored_frames": scored, "excluded_frames": len(reference) - scored,
        "reference_speech_fraction": round((tp + fn) / scored, 4) if scored else 0.0,
        "system_speech_fraction": round((tp + fp) / scored, 4) if scored else 0.0,
        "frame_s": frame_s,
    }

