"""Word error rate (stdlib only).

Normalisation (applied to reference and hypothesis alike): lowercase; every character that is
not a letter, digit, apostrophe or whitespace becomes a space; apostrophes at word edges are
dropped; words are split on whitespace. In the **raw** WER nothing else is normalised: "ten"
and "10" are different words, and so are "ms" and "miss".

The **number-normalised** WER additionally maps each single spoken number or ordinal word to
digits with :data:`NUMBER_WORDS`, identically in reference and hypothesis ("twentieth" ->
"20th", "ten" -> "10"). Only single words are mapped: "twenty one" becomes "20 1", not "21".
Because the mapping is applied to both sides, a non-numeric use ("the one who", "a second")
can only hide an error where the recogniser wrote digits for it.

Named entities: reference words written with a capital letter that do not start a sentence
(and are not "I") - e.g. names, places, days, months, titles such as "Ms.". An edit counts as a
named-entity error when its reference word is one of them (insertions have no reference word
and count as other errors).

    WER = (S + D + I) / N    (N = number of reference words)

    python -m hub_speech_pipeline.asr.wer --reference ref.txt --hypothesis hyp.txt
    python -m hub_speech_pipeline.asr.wer --reference ref.txt --transcript session_transcript.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

_NOT_WORD = re.compile(r"[^\w\s']|_", re.UNICODE)

_CARDINALS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
              "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
              "nineteen"]
_ORDINALS = ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
             "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth",
             "seventeenth", "eighteenth", "nineteenth"]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_TENS_ORDINAL = {"twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "sixtieth": 60,
                 "seventieth": 70, "eightieth": 80, "ninetieth": 90}


def _suffix(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


#: Spoken number word -> digits, for the number-normalised WER (single words only).
NUMBER_WORDS: dict[str, str] = (
    {w: str(i) for i, w in enumerate(_CARDINALS)}
    | {w: f"{i}{_suffix(i)}" for i, w in enumerate(_ORDINALS)}
    | {w: str(n) for w, n in _TENS.items()}
    | {w: f"{n}th" for w, n in _TENS_ORDINAL.items()}
    | {"hundred": "100", "hundredth": "100th", "thousand": "1000", "thousandth": "1000th"}
)


def normalise(text: str, numbers: bool = False) -> list[str]:
    words = _NOT_WORD.sub(" ", text.lower()).split()
    words = [w.strip("'") for w in words if w.strip("'")]
    return [NUMBER_WORDS.get(w, w) for w in words] if numbers else words


_TITLES = re.compile(r"\b(Mr|Ms|Mrs|Dr|Prof)\.\s")


def reference_entities(text: str) -> set[str]:
    """Normalised words written capitalised mid-sentence in ``text`` (not "I").

    A heuristic: it cannot recognise a name that starts a sentence. Pass an explicit list
    (``--entities``) when that matters."""
    entities = set()
    protected = _TITLES.sub(lambda m: m.group(1) + "․ ", text)  # "Ms. Perera" is not a sentence end
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", protected):
        tokens = sentence.split()
        for i, token in enumerate(tokens):
            word = token.strip(".,;:!?\"'()[]․")
            if i > 0 and word and word[0].isupper() and word != "I":
                entities.update(normalise(word))
    return entities


@dataclasses.dataclass
class WerResult:
    reference_words: int
    hypothesis_words: int
    substitutions: int
    deletions: int
    insertions: int
    alignment: list[tuple[str, str | None, str | None]]  # (op, reference word, hypothesis word)

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def wer(self) -> float:
        if self.reference_words == 0:
            return 0.0 if self.hypothesis_words == 0 else float("inf")
        return self.errors / self.reference_words

    def edits(self, entities: set[str] = frozenset()) -> list[dict]:
        """The non-matching alignment steps, each flagged as a named-entity error or not."""
        return [{"op": op, "reference": r, "hypothesis": h, "entity": r is not None and r in entities}
                for op, r, h in self.alignment if op != "ok"]

    def to_json(self, entities: set[str] = frozenset()) -> dict:
        edits = self.edits(entities)
        return {
            "wer": self.wer, "reference_words": self.reference_words,
            "hypothesis_words": self.hypothesis_words, "substitutions": self.substitutions,
            "deletions": self.deletions, "insertions": self.insertions, "errors": self.errors,
            "entity_errors": sum(e["entity"] for e in edits),
            "other_errors": sum(not e["entity"] for e in edits),
            "edits": edits,
        }


def word_error_rate(reference: str, hypothesis: str, numbers: bool = False) -> WerResult:
    """Levenshtein alignment of normalised words; ties prefer substitution, then deletion.
    ``numbers`` applies :data:`NUMBER_WORDS` to both sides."""
    ref, hyp = normalise(reference, numbers), normalise(hypothesis, numbers)
    n, m = len(ref), len(hyp)
    # cost[i][j] = edits to turn ref[:i] into hyp[:j]
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = ref[i - 1] == hyp[j - 1]
            cost[i][j] = min(cost[i - 1][j - 1] + (0 if same else 1), cost[i - 1][j] + 1, cost[i][j - 1] + 1)
    i, j, ops = n, m, []
    s = d = ins = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            if ref[i - 1] == hyp[j - 1]:
                ops.append(("ok", ref[i - 1], hyp[j - 1]))
            else:
                ops.append(("sub", ref[i - 1], hyp[j - 1]))
                s += 1
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            ops.append(("del", ref[i - 1], None))
            d += 1
            i -= 1
        else:
            ops.append(("ins", None, hyp[j - 1]))
            ins += 1
            j -= 1
    ops.reverse()
    return WerResult(n, m, s, d, ins, ops)


def transcript_text(path: Path) -> str:
    """The text of a session transcript JSON (chunks in order)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return " ".join(seg["text"].strip() for chunk in data["chunks"] for seg in chunk["segments"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Word error rate")
    parser.add_argument("--reference", type=Path, required=True)
    hyp = parser.add_mutually_exclusive_group(required=True)
    hyp.add_argument("--hypothesis", type=Path, help="plain-text hypothesis")
    hyp.add_argument("--transcript", type=Path, help="session transcript JSON from the hub")
    parser.add_argument("--entities", help="comma-separated named entities of the reference "
                                           "(default: capitalised mid-sentence words)")
    parser.add_argument("--json", type=Path, help="write the result as JSON")
    args = parser.parse_args(argv)
    reference = args.reference.read_text(encoding="utf-8")
    hypothesis = (args.hypothesis.read_text(encoding="utf-8") if args.hypothesis
                  else transcript_text(args.transcript))
    if args.entities:
        entities = {w for item in args.entities.split(",") for w in normalise(item)}
        source = "explicit list (--entities)"
    else:
        entities = reference_entities(reference)
        source = "heuristic: capitalised mid-sentence words of the reference"
    out = {"reference_file": str(args.reference), "hypothesis_file": str(args.hypothesis or args.transcript),
           "hypothesis_text": hypothesis.strip(),
           "normalisation": "lowercase; punctuation -> space; edge apostrophes dropped",
           "named_entities": sorted(entities), "named_entities_source": source, "number_words": NUMBER_WORDS}
    for label, numbers in (("raw", False), ("number_normalised", True)):
        result = word_error_rate(reference, hypothesis, numbers)
        doc = result.to_json(entities)
        out[label] = doc
        print(f"{label} WER {result.wer:.4f} = ({result.substitutions} S + {result.deletions} D + "
              f"{result.insertions} I) / {result.reference_words} reference words; named-entity errors "
              f"{doc['entity_errors']}, other errors {doc['other_errors']}")
        for e in doc["edits"]:
            print(f"   {'NE ' if e['entity'] else '   '}{e['op']}: {e['reference']!r} -> {e['hypothesis']!r}")
    print(f"named entities (reference): {', '.join(sorted(entities))}")
    if args.json:
        args.json.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
