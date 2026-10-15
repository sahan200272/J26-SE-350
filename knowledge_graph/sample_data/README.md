# Sample Payloads & Synthetic Test Fixtures

> [!IMPORTANT]
> **Data Provenance & Metric Integrity**:
> All fixtures in `sample_data/payloads/` are **hand-written synthetic data** authored strictly to conform to the `contracts/graph_payload.schema.json` contract and exercise edge cases in the Knowledge Graph ingestion engine.
> They are **NOT real extractor outputs** from the Agentic Core LLM pipeline and **MUST NOT be used for reported evaluation metrics or pipeline accuracy benchmarks**.

---

## 1. Fixture Descriptions & Behaviors Exercised

| Fixture File | Domain Layer | Key Behaviors Exercised |
|:---|:---|:---|
| `01_office_meeting.json` | Layer A (Work & Office) | • Meeting key resolution: `normalize_key(name + " " + date)`<br>• Meeting attendance: `ATTENDED` and `ABSENT_FROM`<br>• Task assignments: `ASSIGNED_TO` and `DUE_ON`<br>• Problem resolution: `HAS_ISSUE`<br>• Discussion provenance: `DECIDED`, `RAISED`, and `USES` |
| `02_personal_party.json` | Layer B (Personal & Social) | • Kinship & social networks: `FAMILY_OF` and `FRIEND_OF`<br>• Location & employer: `LIVES_IN` and `WORKS_AT`<br>• Personal plans: `PLANS` with event node<br>• Sentiment: `LIKES` and `DISLIKES`<br>• Ownership: `OWNS` an `Item`<br>• Uncertainty tracking: `confidence: 0.5` |
| `03_correction.json` | Layer C (Signals & Mutations) | • Operation `op: "update"` property overwriting<br>• Single-valued relationship replacement: updates task deadline, deletes old `DUE_ON` edge, creates new edge, increments `edges_replaced`, logs warning |
| `04_cancellation.json` | Layer C (Signals & Mutations) | • Cancellation operation `op: "retract"` on entity and relationship<br>• Safe non-destructive behavior: logs warning without deleting historical nodes (`TODO(RP-29)`) |
| `05_alias_duplicates.json` | Layer C & Resolution | • Manual alias linking: `ALIAS_OF` keeps entities separate<br>• Fuzzy duplicate resolution: RapidFuzz `token_sort_ratio >= 90` merges typo task duplicate into existing node and appends typo to `aliases`<br>• Symmetric canonicalization: `FRIEND_OF` ingested in both directions produces exactly 1 edge |
| `06_unknown_types.json` | Schema Fallback | • Unrecognized entity label (`Hobby`) normalized to `Concept` with `props["original_type"] = "Hobby"`<br>• Unknown relationship type (`CUSTOM_UNKNOWN_RELATION`) normalized to `RELATED_TO` with `props["label"]`<br>• Inverted relationship direction (`Person -> Task` for `ASSIGNED_TO`) normalized to `RELATED_TO` |
| `triples_example.json` | Ingestion Adapters | • Raw untyped `[Subject, Predicate, Object]` triples format<br>• Label inference via `ALLOWED_DIRECTIONS` for unambiguous relations (`ASSIGNED_TO`, `FRIEND_OF`, `WORKS_AT`)<br>• Fallback to `Concept` and `RELATED_TO` for ambiguous (`DUE_ON`) or unknown predicates |

---

## 2. Real Extractor Samples (`real_samples/`)

The `sample_data/real_samples/` directory is reserved for genuine extraction outputs produced by the Agentic Reasoning Core extractor once the teammate's component is completed and integrated.

When available:
1. Real speech extraction payloads will be placed into `sample_data/real_samples/`.
2. They will be used for automated regression benchmarks and end-to-end extraction accuracy measurements.
3. The `scripts/mock_extractor.py` CLI can be repointed from `sample_data/payloads/` to `sample_data/real_samples/` to evaluate realistic conversation batches.
