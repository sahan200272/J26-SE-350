"""WER utility."""

from __future__ import annotations

import functools
import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path

from hub_speech_pipeline.asr.normalizer import SPELLING_FILE, provenance
from hub_speech_pipeline.asr.wer import (NUMBER_WORDS, align_words, main, normalise, reference_entities, tokens,
                                         transcript_text, word_error_rate)

REFERENCE_01 = (
    "This is a test recording for Echo Vault. On Tuesday the twentieth of October I will present the "
    "progress of component one. Kasun will review the slides at the SLIIT Malabe campus before ten in the "
    "morning.\n\nAfter the presentation I need to send the evaluation report to Ms. Perera by Monday. Next "
    "week we will test the pipeline in the computing lab with four participants.\n")


class NumberNormalisation(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(NUMBER_WORDS["ten"], "10")
        self.assertEqual(NUMBER_WORDS["one"], "1")
        self.assertEqual(NUMBER_WORDS["twentieth"], "20th")
        self.assertEqual(NUMBER_WORDS["first"], "1st")
        self.assertEqual(NUMBER_WORDS["second"], "2nd")
        self.assertEqual(NUMBER_WORDS["third"], "3rd")
        self.assertEqual(NUMBER_WORDS["eleventh"], "11th")
        self.assertEqual(NUMBER_WORDS["twelfth"], "12th")
        self.assertEqual(NUMBER_WORDS["ninety"], "90")

    def test_applied_identically_to_both_sides(self):
        r = word_error_rate("before ten in the morning on the twentieth", "before 10 in the morning on the 20th",
                            "numbers")
        self.assertEqual(r.wer, 0.0)
        raw = word_error_rate("before ten in the morning on the twentieth", "before 10 in the morning on the 20th", "raw")
        self.assertEqual(raw.substitutions, 2)
        # Both sides spelled out: still a match after mapping.
        self.assertEqual(word_error_rate("four participants", "four participants", "numbers").wer, 0.0)

    def test_compound_numbers_are_not_combined(self):
        self.assertEqual(normalise("twenty one", "numbers"), ["20", "1"])


class Entities(unittest.TestCase):
    def test_capitalised_mid_sentence_words_of_the_reference(self):
        # "Ms. Perera" is not split as a sentence end; "Kasun" starts a sentence, so the heuristic
        # cannot see it (hence the explicit --entities list).
        self.assertEqual(reference_entities(REFERENCE_01),
                         {"echo", "vault", "tuesday", "october", "sliit", "malabe", "ms", "perera", "monday"})

    def test_errors_are_split_into_entity_and_other(self):
        hyp = "This is the test recording for Echo World. On Tuesday the twentieth of October"
        ref = "This is a test recording for Echo Vault. On Tuesday the twentieth of October"
        result = word_error_rate(ref, hyp, "raw").to_json(reference_entities(ref))
        self.assertEqual((result["entity_errors"], result["other_errors"]), (1, 1))
        flagged = {(e["reference"], e["entity"]) for e in result["edits"]}
        self.assertEqual(flagged, {("vault", True), ("a", False)})


class Normalise(unittest.TestCase):
    def test_lowercase_and_punctuation(self):
        self.assertEqual(normalise("This is a test, for Echo Vault."), ["this", "is", "a", "test", "for", "echo", "vault"])
        self.assertEqual(normalise("Ms. Perera's report!"), ["ms", "perera's", "report"])
        self.assertEqual(normalise("'quoted' -- well-known"), ["quoted", "well", "known"])

    def test_numbers_are_not_rewritten(self):
        self.assertEqual(normalise("ten 10 twentieth 20th"), ["ten", "10", "twentieth", "20th"])


class WordErrorRate(unittest.TestCase):
    def test_identical_after_normalisation_is_zero(self):
        r = word_error_rate("Kasun will review the slides.", "kasun will review the slides", "raw")
        self.assertEqual((r.wer, r.errors, r.reference_words), (0.0, 0, 5))

    def test_counts_substitutions_deletions_insertions(self):
        sub = word_error_rate("a b c", "a x c", "raw")
        self.assertEqual((sub.substitutions, sub.deletions, sub.insertions), (1, 0, 0))
        dele = word_error_rate("a b c", "a c", "raw")
        self.assertEqual((dele.substitutions, dele.deletions, dele.insertions), (0, 1, 0))
        ins = word_error_rate("a b", "a x b", "raw")
        self.assertEqual((ins.substitutions, ins.deletions, ins.insertions), (0, 0, 1))
        self.assertIn(("ins", None, "x"), ins.alignment)
        # Several minimal alignments exist (3 S, or 1 S + 1 D + 1 I); the count is what matters.
        mixed = word_error_rate("the cat sat on the mat", "the bat sat on mat today", "raw")
        self.assertEqual(mixed.errors, 3)
        self.assertAlmostEqual(mixed.wer, 3 / 6)

    def test_minimum_edit_distance(self):
        # Shifting by one word costs 2 (one deletion + one insertion), not 4 substitutions.
        r = word_error_rate("a b c d", "b c d e", "raw")
        self.assertEqual(r.errors, 2)

    def test_empty_hypothesis_and_reference(self):
        self.assertEqual(word_error_rate("one two three", "", "raw").wer, 1.0)
        self.assertEqual(word_error_rate("", "", "raw").wer, 0.0)
        self.assertEqual(word_error_rate("", "extra", "raw").wer, float("inf"))

    def test_number_format_counts_as_an_error(self):
        r = word_error_rate("before ten in the morning", "before 10 in the morning", "raw")
        self.assertEqual((r.substitutions, r.wer), (1, 0.2))


class WhisperStandard(unittest.TestCase):
    def test_numbers_fillers_spelling_and_punctuation(self):
        self.assertEqual(tokens("On Tuesday the twentieth, before ten in the morning!"),
                         ["on", "tuesday", "the", "20th", "before", "10", "in", "the", "morning"])
        self.assertEqual(tokens("Um, uh, hmm... yeah."), ["yeah"])
        # The standard normaliser expands "'s" to " is" (also for possessives) - applied to both sides.
        self.assertEqual(tokens("The colour of Mr. Perera's car"), ["the", "color", "of", "mister", "perera", "is", "car"])

    def test_whisper_is_the_default(self):
        self.assertEqual(word_error_rate("before ten in the morning", "Before 10 in the morning.").wer, 0.0)
        self.assertEqual(word_error_rate("before ten in the morning", "before 10 in the morning", "raw").wer, 0.2)

    def test_spelling_table_is_the_pinned_file(self):
        p = provenance()
        self.assertEqual(p["spelling_table_commit"], "ea1c266709125f68a89acdc0c6ddbde6773eb0ed")
        self.assertEqual(hashlib.sha256(SPELLING_FILE.read_bytes()).hexdigest(), p["spelling_table_sha256"])

    def test_unknown_normaliser(self):
        with self.assertRaises(ValueError):
            tokens("x", "lowercase-only")


class Alignment(unittest.TestCase):
    @staticmethod
    def brute_force(a: list[str], b: list[str]) -> int:
        @functools.lru_cache(maxsize=None)
        def d(i: int, j: int) -> int:
            if i == 0 or j == 0:
                return i + j
            return min(d(i - 1, j - 1) + (a[i - 1] != b[j - 1]), d(i - 1, j) + 1, d(i, j - 1) + 1)
        return d(len(a), len(b))

    def test_edit_counts_match_brute_force_and_alignment_is_consistent(self):
        rng = random.Random(7)
        for _ in range(200):
            a = [rng.choice("abcd") for _ in range(rng.randint(0, 9))]
            b = [rng.choice("abcd") for _ in range(rng.randint(0, 9))]
            r = align_words(a, b)
            self.assertEqual(r.errors, self.brute_force(a, b), (a, b))
            self.assertEqual([x for op, x, _ in r.alignment if x is not None], a)
            self.assertEqual([y for op, _, y in r.alignment if y is not None], b)

    def test_long_sequences(self):
        ref = [f"w{i % 50}" for i in range(3000)]
        hyp = ref[:1000] + ref[1010:2500] + ["x"] * 5 + ref[2500:]
        r = align_words(ref, hyp)
        self.assertEqual(r.errors, 10 + 5)


class Cli(unittest.TestCase):
    def test_transcript_json_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp, "ref.txt")
            ref.write_text("Hello world. Good morning.", encoding="utf-8")
            session = Path(tmp, "s.json")
            session.write_text(json.dumps({"chunks": [
                {"segments": [{"text": " Hello world."}]},
                {"segments": [{"text": " Good evening."}]}]}), encoding="utf-8")
            self.assertEqual(transcript_text(session), "Hello world. Good evening.")
            out = Path(tmp, "wer.json")
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--reference", str(ref), "--transcript", str(session), "--json", str(out)]), 0)
            result = json.loads(out.read_text())
            self.assertEqual(result["whisper"]["wer"], 0.25)
            self.assertEqual(result["normalisers"]["whisper"]["spelling_table_sha256"][:8], "6607f948")
            self.assertEqual(result["raw"]["wer"], 0.25)
            self.assertEqual(result["number_normalised"]["wer"], 0.25)
            self.assertEqual(result["raw"]["edits"],
                             [{"op": "sub", "reference": "morning", "hypothesis": "evening", "entity": False}])
            self.assertEqual(result["named_entities"], [])  # "Hello" and "Good" start sentences


if __name__ == "__main__":
    unittest.main()
