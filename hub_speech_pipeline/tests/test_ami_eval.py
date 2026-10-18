"""E0: AMI NXT reference parsing, speech regions, frame-level VAD scoring, entity matching."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hub_speech_pipeline.eval import ami, vad_score
from hub_speech_pipeline.eval.e0 import count_ngram, entity_matches

NS = 'xmlns:nite="http://nite.sourceforge.net/"'

WORDS_A = f"""<?xml version="1.0" encoding="ISO-8859-1" standalone="yes"?>
<nite:root nite:id="M.A.words" {NS}>
   <w nite:id="M.A.words0" starttime="0.50" endtime="0.80">Hello</w>
   <w nite:id="M.A.words1" starttime="0.80" endtime="1.20">everybody</w>
   <w nite:id="M.A.words2" starttime="1.20" endtime="1.20" punc="true">.</w>
   <vocalsound nite:id="M.A.words3" starttime="1.20" endtime="1.50" type="laugh"/>
   <w nite:id="M.A.words4" starttime="1.40" endtime="1.60" trunc="true">Beauti</w>
   <w nite:id="M.A.words5" starttime="1.60" endtime="2.00">the</w>
   <w nite:id="M.A.words6" starttime="2.00" endtime="2.40">L_C_D_</w>
   <w nite:id="M.A.words7" starttime="2.40" endtime="2.90">costs</w>
   <w nite:id="M.A.words8" starttime="2.90" endtime="3.10">twenty</w>
   <w nite:id="M.A.words9" starttime="3.10" endtime="3.30">five</w>
   <w nite:id="M.A.words10" starttime="3.30" endtime="3.60">Euros</w>
   <w nite:id="M.A.words11" starttime="3.60" endtime="3.60" punc="true">,</w>
   <disfmarker nite:id="M.A.words12" starttime="3.60" endtime="3.60"/>
   <w nite:id="M.A.words13" starttime="3.80" endtime="4.00">okay</w>
   <w nite:id="M.A.words14" starttime="6.00" endtime="6.50">Sarah</w>
</nite:root>
"""

WORDS_B = f"""<?xml version="1.0" encoding="ISO-8859-1" standalone="yes"?>
<nite:root nite:id="M.B.words" {NS}>
   <w nite:id="M.B.words0" starttime="1.00" endtime="1.30">Hi</w>
   <w nite:id="M.B.words1" starttime="9.00" endtime="9.40">Yeah</w>
</nite:root>
"""

NE_TYPES = f"""<?xml version="1.0" encoding="ISO-8859-1" standalone="yes"?>
<ne-type nite:id="ne_0" name="ne-root" {NS}>
  <ne-type nite:id="ne_1" name="ENAMEX">
    <ne-type nite:id="ne_11" name="PERSON">
      <ne-type nite:id="ne_1111" name="PROJECT_MANAGER"/>
    </ne-type>
  </ne-type>
  <ne-type nite:id="ne_3" name="NUMEX">
    <ne-type nite:id="ne_31" name="MONEY"/>
  </ne-type>
  <ne-type nite:id="ne_40" name="ARTEFACT">
    <ne-type nite:id="ne_47" name="DRAWING"/>
  </ne-type>
</ne-type>
"""

NE_A = f"""<?xml version="1.0" encoding="ISO-8859-1" standalone="yes"?>
<nite:root nite:id="M.A.ne" {NS}>
   <named-entity nite:id="M.A.ne.1">
      <nite:pointer role="type" href="ne-types.xml#id(ne_31)"/>
      <nite:child href="M.A.words.xml#id(M.A.words8)..id(M.A.words11)"/>
   </named-entity>
   <named-entity nite:id="M.A.ne.2">
      <nite:pointer role="type" href="ne-types.xml#id(ne_1111)"/>
      <nite:child href="M.A.words.xml#id(M.A.words14)"/>
   </named-entity>
</nite:root>
"""


class Corpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        for sub, name, text in [("words", "M.A.words.xml", WORDS_A), ("words", "M.B.words.xml", WORDS_B),
                                ("ontologies", "ne-types.xml", NE_TYPES), ("namedEntities", "M.A.ne.xml", NE_A)]:
            (root / sub).mkdir(exist_ok=True)
            (root / sub / name).write_text(text, encoding="iso-8859-1")
        self.root = root
        self.words = ami.load_words(root, "M")

    def tearDown(self):
        self.tmp.cleanup()

    def test_words_parsed_without_non_word_elements(self):
        self.assertEqual(sorted(self.words), ["A", "B"])
        a = self.words["A"]
        self.assertEqual(len(a), 13)  # the 13 <w> elements; <vocalsound>/<disfmarker> are not words
        self.assertTrue(a[2].punc)
        self.assertTrue(a[3].trunc)
        self.assertEqual((a[0].start, a[0].end, a[0].text), (0.5, 0.8, "Hello"))

    def test_reference_transcript_excludes_punctuation_and_fragments_and_is_time_ordered(self):
        ref = ami.reference_words(self.words)
        self.assertEqual([w.text for w in ref][:4], ["Hello", "everybody", "Hi", "the"])
        self.assertNotIn("Beauti", [w.text for w in ref])
        self.assertEqual(ami.reference_text(self.words),
                         "Hello everybody Hi the LCD costs twenty five Euros okay Sarah Yeah")

    def test_acronym_joining(self):
        self.assertEqual(ami.join_acronym("L_C_D_"), "LCD")
        self.assertEqual(ami.join_acronym("T_V_"), "TV")
        self.assertEqual(ami.join_acronym("well_known"), "well_known")
        self.assertEqual(ami.join_acronym("hello"), "hello")

    def test_speech_regions_merge_short_gaps_per_speaker_then_union(self):
        # A: 0.5-1.2, (fragment 1.4-1.6 joins: gap 0.2 < 0.3), 1.6-3.6, 3.8-4.0 (gap 0.2) -> 0.5-4.0; 6.0-6.5
        # B: 1.0-1.3 inside A's region; 9.0-9.4
        self.assertEqual(ami.speech_regions(self.words), [(0.5, 4.0), (6.0, 6.5), (9.0, 9.4)])
        unmerged = ami.speech_regions(self.words, merge_gap=0.0)
        self.assertEqual(unmerged[:3], [(0.5, 1.3), (1.4, 3.6), (3.8, 4.0)])

    def test_merge_intervals(self):
        self.assertEqual(ami.merge_intervals([(0, 1), (1, 2), (2.5, 3)]), [(0, 2), (2.5, 3)])
        self.assertEqual(ami.merge_intervals([(2.5, 3), (0, 1), (1.2, 2)], gap=0.3), [(0, 2), (2.5, 3)])
        self.assertEqual(ami.merge_intervals([(0, 5), (1, 2)]), [(0, 5)])

    def test_named_entities_with_types_ranges_and_categories(self):
        entities = ami.load_entities(self.root, "M", self.words)
        self.assertEqual([(e.text, e.type, e.category) for e in entities],
                         [("twenty five Euros", "MONEY", "NUMEX"), ("Sarah", "PROJECT_MANAGER", "ENAMEX")])
        self.assertEqual(entities[0].word_ids, ("M.A.words8", "M.A.words9", "M.A.words10"))  # comma excluded
        self.assertEqual((entities[0].start, entities[0].end), (2.9, 3.6))

    def test_ne_type_ontology(self):
        types = ami.parse_ne_types(self.root / "ontologies" / "ne-types.xml")
        self.assertEqual(types["ne_1111"], ("PROJECT_MANAGER", "ENAMEX"))
        self.assertEqual(types["ne_47"], ("DRAWING", "ARTEFACT"))
        self.assertEqual(types["ne_3"], ("NUMEX", "NUMEX"))


class FrameScoring(unittest.TestCase):
    def test_midpoint_rule(self):
        frames = vad_score.frames_from_regions([(0.02, 0.05)], 8)
        # midpoints 0.005, 0.015, 0.025, 0.035, 0.045, 0.055 ...: 0.025-0.045 inside [0.02, 0.05)
        self.assertEqual(list(frames), [0, 0, 1, 1, 1, 0, 0, 0])

    def test_coarse_decisions_are_looked_up_at_each_midpoint(self):
        frames = vad_score.frames_from_decisions([False, True, False], 0.032, 10)
        # 32 ms frame 1 covers 0.032-0.064: 10 ms midpoints 0.035, 0.045, 0.055 -> frames 3, 4, 5
        self.assertEqual(list(frames), [0, 0, 0, 1, 1, 1, 0, 0, 0, 0])

    def test_precision_recall_f1(self):
        ref = bytearray([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
        hyp = bytearray([0, 1, 1, 1, 1, 1, 0, 0, 0, 0])
        s = vad_score.score(ref, hyp)
        self.assertEqual((s["tp"], s["fp"], s["fn"], s["tn"]), (3, 2, 1, 4))
        self.assertEqual((s["precision"], s["recall"]), (0.6, 0.75))
        self.assertAlmostEqual(s["f1"], 2 * 0.6 * 0.75 / 1.35, places=4)

    def test_collar_excludes_frames_near_reference_boundaries(self):
        mask = vad_score.collar_mask([(0.10, 0.30)], 50, 0.025)
        excluded = [k for k in range(50) if not mask[k]]
        # midpoints at most 25 ms from 0.10 (0.075-0.125, inclusive) and from 0.30 (0.275-0.325)
        self.assertEqual(excluded, [7, 8, 9, 10, 11, 12, 27, 28, 29, 30, 31, 32])
        ref = vad_score.frames_from_regions([(0.10, 0.30)], 50)
        hyp = vad_score.frames_from_regions([(0.08, 0.32)], 50)  # 20 ms too wide on both sides
        self.assertLess(vad_score.score(ref, hyp)["precision"], 1.0)
        self.assertEqual(vad_score.score(ref, hyp, mask)["precision"], 1.0)

    def test_frame_count(self):
        self.assertEqual(vad_score.n_frames(1049.3546875), 104935)


class EntityMatching(unittest.TestCase):
    def test_ngram_counting(self):
        self.assertEqual(count_ngram("a b a b a".split(), ("a", "b")), 2)
        self.assertEqual(count_ngram("a b".split(), ()), 0)

    def test_correct_is_capped_by_mentions_and_normalised(self):
        entities = [{"text": "twenty five Euros", "type": "MONEY", "category": "NUMEX"},
                    {"text": "crocodile", "type": "DRAWING", "category": "ARTEFACT"},
                    {"text": "crocodile", "type": "DRAWING", "category": "ARTEFACT"},
                    {"text": "Sarah", "type": "PROJECT_MANAGER", "category": "ENAMEX"}]
        from hub_speech_pipeline.asr.wer import tokens
        ref = tokens("It costs twenty five Euros. A crocodile, another crocodile. I'm Sarah.")
        hyp = tokens("It costs €25. A crocodile, a crocodile and a crocodile. I'm Sara.")
        m = entity_matches(entities, ref, hyp)
        self.assertEqual(m["mentions"], 4)
        rows = {r["surface"]: r for r in m["entities"]}
        self.assertEqual(rows["crocodile"]["correct"], 2)  # 3 in the hypothesis, capped at 2 mentions
        self.assertEqual(rows["twenty five Euros"]["correct"], 1)  # both normalise to the same form
        self.assertEqual(rows["Sarah"]["correct"], 0)
        self.assertEqual(m["correct"], 3)
        self.assertEqual(m["by_category"]["ARTEFACT"], {"correct": 2, "mentions": 2})


if __name__ == "__main__":
    unittest.main()
