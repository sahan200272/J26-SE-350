# Schema compliance: definition (agreed 2026-10-20, before any data or runs)

Target: NFR-04, JSON schema compliance >= 98% on 200 synthetic test cases.

## What is measured
The LLM's own output: a DraftPlan JSON object. The JSON-RPC 2.0 envelope is
built later by the FastMCP client, not by the LLM, so it is NOT measured here.

## Unit
One case = one synthetic transcript (Component 1 Markdown format) that the
default segmenter turns into exactly one segment. Recording date = `started_at`.

## Compliant
The model's FIRST answer, called through `extract_plan(..., use_prefilter=False)`:
  (a) parses as JSON, AND
  (b) passes DraftPlan validation (Pydantic).
No retry, no repair. The prefilter is off so we measure the model, not the gate.

Compliance rate = compliant cases / cases that ran.

## Reported per case and per category
JSON syntax valid, schema valid, cut off at num_predict (tokens_out >= 512),
all Pydantic error types, raw output text, tokens, time.

## Not measured here
Correctness. An empty plan counts as compliant even if a task was missed.
That is Intent F1, measured later on the same dataset.

## When a run is NOT valid (panel shows NOT MEASURED)
- not "official" (frozen dataset not used, or fingerprint mismatch),
- not all 200 cases ran (any Ollama/connection error = infra_error),
- SYSTEM_PROMPT, DraftPlan schema or LLM config hash differs from the frozen ones.

## Baseline (comparison only, no target)
The same 200 cases with the grammar OFF (Ollama `format=None`), same prompt
and config. Shown next to the main result, never as MET or NOT MET.

## Rules
- The first full official run is the result. Below 98% is reported as is.
- Never tune on the 200 cases. Prompt/schema fixes only on the separate dev set.
- After freezing: no change to SYSTEM_PROMPT, schema, or config.
- 95% confidence interval: Wilson score interval.
