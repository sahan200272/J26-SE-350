# RP-17 results: intent extraction F1

Story: RP-17, "Evaluate reasoning accuracy and action execution correctness
against defined benchmarks". Target: intent F1 >= 90% on the 200-case
Synthetic Multi-Intent Evaluation Suite.

## How it was measured
- Definition: `docs/evaluation/intent_f1_definition.md`, agreed on 2026-11-18
  before any scoring. The threshold (0.5 title-word overlap) and the stop
  words are untuned guesses fixed in that definition.
- Source: the frozen official schema-compliance run of 20 Oct 2026
  (`schema_compliance_official.json`): llama3:8b, grammar mode, prefilter off,
  temperature 0, RTX 2050 laptop (56% CPU / 44% GPU). Dataset fingerprint
  a03126ad... was checked before scoring.
- Offline scoring: no new LLM calls. Each case's saved `raw_output` and its
  expected plan go through the same `DraftPlan` check and `resolve_plan`, then
  notes and events are matched one to one.
- Command: `python -m scripts.score_intent_f1 --out docs/evaluation/intent_f1_official.json`.
  Checked in sandbox and tested on Laptop 1 (same output).
- Scored once. Reported as is. No tuning on the 200 eval cases.

## Result: NOT MET

Micro F1 = **52.1%** (95% bootstrap CI 46.2% to 57.7%), target >= 90%.

| Category | Cases | TP | FP | FN | Precision | Recall | F1 | Exact cases |
|---|---|---|---|---|---|---|---|---|
| single_intent | 50 | 36 | 34 | 14 | 51.4% | 72.0% | 60.0% | 21 |
| multi_intent | 75 | 105 | 86 | 71 | 55.0% | 59.7% | 57.2% | 17 |
| ambiguous | 25 | 11 | 9 | 14 | 55.0% | 44.0% | 48.9% | 11 |
| noise | 50 | 0 | 52 | 0 | - | - | - | 3 |
| **Total** | **200** | **152** | **181** | **99** | **45.6%** | **60.6%** | **52.1%** | **52** |

- Noise: only 3 of 50 chit-chat cases gave an empty plan (6.0%).
- Notes-only F1 33.8%; events-only F1 78.0%.
- The 7 schema-failed cases cause only 8 of the 99 misses.
- On matched items: folder correct 42/58 notes, attendees correct 87/94 events.

## Error analysis (NOT the result)
Command: `python -m scripts.intent_f1_error_analysis --out docs/evaluation/intent_f1_error_analysis.json`.
Each miss and extra is put into one cause (first rule that fits).

Extras (FP, 181):

| Cause | Count | Example (synthetic case) |
|---|---|---|
| Note title words differ from the expected note | 55 | SC-052: "Idea" for "Survey progress bar" |
| Item written in a noise case | 52 | SC-126: note "Lunch" about the canteen |
| Note that repeats a predicted event | 39 | SC-008: note "Security Training" next to the event |
| Event at the right date and time, title differs | 21 | SC-056: "Meeting" for "Guided tour discussion" |
| Other | 14 | |

Misses (FN, 99):

| Cause | Count |
|---|---|
| Note title words differ (a note was written, but with other words) | 61 |
| Event at the right date and time, title differs | 21 |
| Case failed the schema (empty plan) | 8 |
| Not found at all | 5 |
| Note answered as an event, or the other way | 4 |

Lenient upper bound: if note titles are ignored (notes paired by count) and
events are matched by date and time only, F1 would be **79.1%**
(precision 69.4%, recall 92.0%). So the matching rule explains part of the
gap, but even the most lenient rule stays below 90%: the main problem is
extra items (low precision), not missed items.

## What this means
The model finds most of the real intents (lenient recall 92%), but it
over-produces: it saves a note for chit-chat, copies each event into a note,
and uses vague titles such as "Meeting" or "Idea". Grammar-constrained
decoding fixes the JSON shape (RP-14), but it cannot fix what the model
chooses to write. This is the quantization-induced reasoning gap named in the
blueprint, now measured.

## Limits of this result
- The run had the prefilter OFF (it measured the model, as the schema
  definition required). The real pipeline runs a rules-only prefilter first,
  which can keep some chit-chat away from the LLM. Its effect is not in this
  number.
- One model (llama3:8b), one run, temperature 0, synthetic English cases.
- Title matching is rule-based word overlap; it cannot see synonyms.
- Cloud GPT-4 / Claude 3.5 baseline: not run yet (needs an API key and a
  decision to send the synthetic cases to the cloud).

## Next steps (each needs a decision first)
1. Cloud baseline on the same 200 cases with the same scorer.
2. Prefilter effect, scored offline (rules only, no new LLM calls), shown as
   a separate number next to this one.
3. Precision fixes (prompt rules against chit-chat notes and event copies, or
   a rules-only post-filter), tuned ONLY on `dev_cases.json`. Any change to
   SYSTEM_PROMPT, schema or config means a new frozen setup and a new official
   run; this 52.1% stays the first official result.
