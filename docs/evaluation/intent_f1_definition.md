# Intent F1: definition (agreed 2026-11-18, before any scoring)

Target: intent extraction F1 >= 90% on the 200-case Synthetic Multi-Intent
Evaluation Suite (Jira RP-17). Cloud GPT-4 / Claude 3.5 baseline: later, same
scorer, separate decision.

## What is measured
Whether the plan the system would act on contains the right items: the right
notes and the right events, no missing ones and no extra ones.
Schema compliance (NFR-04) is a separate number and is not changed by this.

## Source of predictions (offline, no new LLM calls)
The frozen official run `docs/evaluation/schema_compliance_official.json`
(grammar mode, 20 Oct, Laptop 2). For each case we take its `raw_output`.
The run is used only if:
- `official` is true, all 200 cases ran, and no case had an infra error,
- `dataset_fingerprint` equals the SHA-256 of today's `eval_cases.json`
  (a03126ad...),
- the 200 record ids are exactly the 200 case ids.
Otherwise the scorer prints NOT MEASURED and gives no F1.

## From raw output to predicted plan
Predicted plan = what the system would really do:
1. Parse `raw_output` with `DraftPlan` (the same strict check as RP-14).
2. If it fails (bad JSON or schema error): predicted plan = EMPTY. The
   system acts on nothing, so every expected item in that case is a miss.
3. If it passes: run the existing `resolve_plan(draft, reference_date)`
   (reference_date = the `started_at` date of the case). This turns day words
   into real dates, removes exact duplicates and drops fake attendees such as
   "Speaker 1" and blank names.
The expected plan goes through the same steps, so both sides are compared in
the same form. (The scorer first checks that all 200 expected plans pass
`DraftPlan`; if one does not, the run stops with an error.)

## Items and matching
An item is one note or one event. A note can only match a note, an event can
only match an event. An expected note answered by an event (or the other way)
counts as 1 miss + 1 extra.

### Title words (used for notes and events)
1. Lower-case. Split on anything that is not a letter or digit.
2. Remove stop words (fixed list, not tuned):
   a, an, the, to, of, for, and, or, with, about, on, in, at, by, from,
   our, my, your, we, us, i, you, this, that, it, is, be, will.
3. Title overlap = Jaccard = |A and B| / |A or B| of the two word sets.
   If either set is empty, overlap = 0.
No stemming and no synonyms ("cleanup" and "clean" are different words).

THRESHOLD = 0.5 (untuned guess, fixed now, never changed after scoring).

### Note match
Title overlap >= 0.5. The body and the folder are NOT part of the match.

### Event match
Same start (resolved date AND HH:MM time, both exact) AND title overlap >= 0.5.
Attendees are NOT part of the match.

### Pairing
Inside one case, for each item type: list all pairs that match, sort by
overlap (highest first; ties by order in the expected list, then in the
predicted list), and take pairs greedily so each item is used at most once.

- True positive (TP): a pair that matched.
- False negative (FN): an expected item with no pair (a miss).
- False positive (FP): a predicted item with no pair (an extra).

## Numbers reported
Main number (the one compared with the 90% target):
- Micro F1 over all 200 cases, notes and events together:
  precision = TP / (TP + FP), recall = TP / (TP + FN),
  F1 = 2PR / (P + R). Noise cases are included: they have no expected items,
  so they can only add FPs.

Also reported (no target, for the write-up):
- Micro F1, precision and recall per category: single_intent, multi_intent,
  ambiguous. For noise F1 cannot be calculated (there is nothing to find), so
  noise shows: FP count and clean-case rate (cases with an empty plan).
- Notes-only F1 and events-only F1.
- Exact-case rate: cases where every item matched with no miss and no extra.
- Cost of non-compliance: how many FNs come from the 7 schema-failed cases.
- Attribute accuracy on matched pairs only (not part of F1):
  note folder correct, event attendees correct (same set after lower-casing).
- 95% confidence interval for the main F1: bootstrap over cases,
  10,000 resamples, fixed seed 17 (Wilson cannot be used for F1).
- The list of every FN and FP per case, so each one can be checked by hand.

MET if main micro F1 >= 0.90, otherwise NOT MET. The point value decides;
the interval is shown next to it.

## Code
- Scorer (rules only, no LLM): `agentic_core/tests/intent_f1/scorer.py`.
- Unit tests on small hand-made examples, never on the eval cases:
  `agentic_core/tests/intent_f1/`.
- Runner: `scripts/score_intent_f1.py`. Writes
  `docs/evaluation/intent_f1_official.json`.

## Rules
- This definition is agreed before any scoring. The first official score is
  the result, reported as is, even below 90%.
- No change to the threshold, the stop words, the matching rules, the prompt,
  the schema or the config after seeing results.
- Never tune on the 200 eval cases; dev_cases.json is the dev set.
- The cloud baseline (if approved) uses this same scorer on the same 200 cases.
- TPOT and VRAM are not part of RP-17 scoring (deferred to GPU machine).
