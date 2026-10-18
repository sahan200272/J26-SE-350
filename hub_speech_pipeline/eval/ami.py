"""AMI corpus references from the NXT manual annotations (stdlib only).

* **Words:** ``words/<meeting>.<speaker>.words.xml``. ``<w>`` elements carry ``starttime``,
  ``endtime`` (seconds) and the word; ``punc="true"`` marks punctuation tokens and
  ``trunc="true"`` word fragments. ``<vocalsound>``, ``<disfmarker>``, ``<gap>`` and other
  elements are not words.
* **Reference transcript for WER:** every non-punctuation, non-fragment word of all speakers,
  ordered by start time (then end time, then speaker). Fragments are left out (NIST scoring
  treats them as optionally deletable). AMI writes letter-by-letter acronyms as ``L_C_D_``;
  these are joined (``LCD``) so they match how a recogniser writes them.
* **Reference speech regions:** for each speaker, the intervals of their non-punctuation words
  (fragments included), joined when the gap between two is shorter than ``merge_gap`` (0.3 s,
  the NIST Rich Transcription convention for speaker segments); then the union over speakers.
* **Named entities:** ``namedEntities/<meeting>.<speaker>.ne.xml``; each ``<named-entity>``
  points to a type in ``ontologies/ne-types.xml`` and to a word range
  (``…words.xml#id(first)..id(last)``) in that speaker's words file.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NITE = "{http://nite.sourceforge.net/}"
NIST_MERGE_GAP_S = 0.3
_ACRONYM = re.compile(r"^(?:[A-Za-z]_)+[A-Za-z]?_?$")


@dataclasses.dataclass(frozen=True)
class Word:
    speaker: str
    id: str
    start: float
    end: float
    text: str
    punc: bool = False
    trunc: bool = False


@dataclasses.dataclass(frozen=True)
class Entity:
    id: str
    speaker: str
    type: str  # e.g. "CARDINAL"
    category: str  # e.g. "NUMEX"
    word_ids: tuple[str, ...]
    text: str
    start: float
    end: float


def join_acronym(text: str) -> str:
    """AMI letter-by-letter spelling ``L_C_D_`` -> ``LCD``; other words unchanged."""
    return text.replace("_", "") if _ACRONYM.match(text) else text


def parse_words(path: Path, speaker: str) -> list[Word]:
    """The ``<w>`` elements of one speaker's words file, in document order."""
    words = []
    for e in ET.parse(path).getroot():
        if e.tag != "w":
            continue
        start, end = e.get("starttime"), e.get("endtime")
        if start is None or end is None:
            continue
        words.append(Word(speaker, e.get(NITE + "id"), float(start), float(end), (e.text or "").strip(),
                          e.get("punc") == "true", e.get("trunc") == "true"))
    return words


def meeting_speakers(annotations: Path, meeting: str) -> list[str]:
    return sorted(p.name.split(".")[1] for p in (annotations / "words").glob(f"{meeting}.*.words.xml"))


def load_words(annotations: Path, meeting: str) -> dict[str, list[Word]]:
    """speaker -> words (document order)."""
    return {spk: parse_words(annotations / "words" / f"{meeting}.{spk}.words.xml", spk)
            for spk in meeting_speakers(annotations, meeting)}


def reference_words(words: dict[str, list[Word]]) -> list[Word]:
    """Words scored by WER: no punctuation, no fragments, ordered by time."""
    out = [w for ws in words.values() for w in ws if not w.punc and not w.trunc and w.text]
    return sorted(out, key=lambda w: (w.start, w.end, w.speaker))


def reference_text(words: dict[str, list[Word]]) -> str:
    return " ".join(join_acronym(w.text) for w in reference_words(words))


def merge_intervals(intervals: list[tuple[float, float]], gap: float = 0.0) -> list[tuple[float, float]]:
    """Sorted union of intervals; intervals closer than ``gap`` are joined."""
    out: list[list[float]] = []
    for start, end in sorted(intervals):
        if out and (start <= out[-1][1] or start - out[-1][1] < gap):
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [(a, b) for a, b in out]


def speech_regions(words: dict[str, list[Word]], merge_gap: float = NIST_MERGE_GAP_S) -> list[tuple[float, float]]:
    """Reference speech regions: per-speaker word intervals joined across gaps < merge_gap,
    then the union over speakers."""
    per_speaker = []
    for ws in words.values():
        intervals = [(w.start, w.end) for w in ws if not w.punc and w.end > w.start]
        per_speaker += merge_intervals(intervals, merge_gap)
    return merge_intervals(per_speaker)


def parse_ne_types(path: Path) -> dict[str, tuple[str, str]]:
    """type id -> (name, top-level category), from ontologies/ne-types.xml."""
    types: dict[str, tuple[str, str]] = {}

    def walk(node: ET.Element, category: str | None) -> None:
        for child in node:
            if child.tag != "ne-type":
                continue
            if child.get("name") == "ne-root":
                walk(child, None)
                continue
            cat = category or child.get("name")  # children of the root are the categories
            types[child.get(NITE + "id")] = (child.get("name"), cat)
            walk(child, cat)

    # The file's root is the "ne-root" type itself (or a wrapper around it): its children are
    # the categories either way.
    walk(ET.parse(path).getroot(), None)
    return types


_HREF = re.compile(r"#id\(([^)]+)\)(?:\.\.id\(([^)]+)\))?")


def parse_entities(path: Path, speaker: str, words: list[Word], types: dict[str, tuple[str, str]]) -> list[Entity]:
    index = {w.id: i for i, w in enumerate(words)}
    out = []
    for e in ET.parse(path).getroot():
        if e.tag != "named-entity":
            continue
        type_id = None
        span: list[Word] = []
        for child in e:
            href = child.get("href", "")
            if child.tag == NITE + "pointer" and child.get("role") == "type":
                type_id = href.split("#id(")[-1].rstrip(")")
            elif child.tag == NITE + "child":
                m = _HREF.search(href)
                if m:
                    first, last = m.group(1), m.group(2) or m.group(1)
                    span += words[index[first]:index[last] + 1]
        span_words = [w for w in span if not w.punc]
        if not span_words:
            continue
        name, category = types.get(type_id, (type_id or "?", "?"))
        out.append(Entity(e.get(NITE + "id"), speaker, name, category, tuple(w.id for w in span_words),
                          " ".join(join_acronym(w.text) for w in span_words),
                          span_words[0].start, span_words[-1].end))
    return out


def load_entities(annotations: Path, meeting: str, words: dict[str, list[Word]] | None = None) -> list[Entity]:
    words = words or load_words(annotations, meeting)
    types = parse_ne_types(annotations / "ontologies" / "ne-types.xml")
    out = []
    for spk, ws in words.items():
        path = annotations / "namedEntities" / f"{meeting}.{spk}.ne.xml"
        if path.is_file():
            out += parse_entities(path, spk, ws, types)
    return sorted(out, key=lambda e: e.start)
