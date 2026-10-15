# Knowledge Graph Ingestion Pipeline

This document specifies the automated ingestion architecture for ingesting entity and relationship data from spoken voice conversation payloads and triple extractors into the local Neo4j 5 graph database.

---

## 1. Ingestion Architecture & Flow

The ingestion pipeline handles payload normalization, entity resolution, single-valued conflict management, relationship canonicalization, and provenance linking within a single ACID transaction per payload.

```mermaid
flowchart TD
    A[Voice Conversation / Extractor] -->|Triples [S, P, O] or Typed Dicts| B[Adapter: triples_to_payload]
    A -->|Payload JSON| C[Payload Validator & Normalizer]
    B --> C
    C --> D[Ingestion Engine: ingest_payload]
    
    subgraph Transaction [Single Transaction Execution: session.execute_write]
        D --> E[Entity Resolution & MERGE]
        E -->|Exact key match| F[Reuse Node]
        E -->|Rapidfuzz ratio >= 90| G[Merge Node & Add Alias]
        E -->|No match| H[Create New Node]
        
        D --> I[Relationship Processing]
        I -->|Symmetric: FRIEND_OF, ...| J[canonical_pair sort]
        I -->|Single-valued: DUE_ON, ...| K[Detect & Replace Old Edge]
        I -->|Missing Endpoints| L[Create from EntityRef]
        
        D --> M[Provenance Linking]
        M --> N[MERGE :Conversation Node]
        N -->|Task, Decision, Issue, Question, Idea, Note, Doc| O[(Entity)-[:CREATED_IN]->(:Conversation)]
        N -->|Other Entities| P[(:Conversation)-[:MENTIONS]->(Entity)]
    end
    
    Transaction -->|dry_run=True| Q[Rollback Transaction & Return Counts]
    Transaction -->|dry_run=False| R[Commit & Return IngestResult]
```

---

## 2. Ingestion Rules & Invariants

### 2.1 Entity Resolution & Deduplication
1. **Scope**: Entity resolution is scoped strictly to the **same node label**.
2. **Exact Key Matching**: If the computed normalized key exists in the database for that label, the existing node is reused.
3. **Fuzzy Alias Matching**:
   - If no exact match is found, existing keys for that label (queried once per label per transaction) are compared against the candidate key using RapidFuzz `token_sort_ratio`.
   - If the highest match ratio is $\ge 90$ (`ALIAS_THRESHOLD = 90`), the incoming entity is resolved to the existing node.
   - The incoming entity's display name is appended to the existing node's `aliases` property list (avoiding duplicate entries).
   - `aliases_added` count is incremented.
4. **Calendar Exception**: `Deadline` entities represent discrete dates (`YYYY-MM-DD`). To prevent different dates from collapsing into aliases (e.g. `2026-10-22` vs `2026-10-23`), fuzzy matching is skipped for `Deadline` nodes.

### 2.2 Meeting Key Normalization Rule
Meeting nodes represent specific meeting sessions. Their unique `key` is generated according to:
- If `props["date"]` is provided and non-empty: `normalize_key(name + " " + date)`
- Else if the payload contains an ISO timestamp (`payload.timestamp`): `normalize_key(name + " " + timestamp[:10])`
- Otherwise: `normalize_key(name)`
- The human-readable display name `name` remains untouched.

### 2.3 Relationship Handling

#### Whitelisted Cypher Literals
To prevent Cypher injection and enforce graph invariants, all node labels and relationship types are strictly asserted against `ALLOWED_NODE_LABELS` and `ALLOWED_RELATIONSHIP_TYPES` before constructing any Cypher query.

#### Symmetric Relationships
Symmetric relationships (`FRIEND_OF`, `PARTNER_OF`, `COLLABORATES_WITH`) represent bidirectional undirected connections.
- The endpoints are sorted alphabetically using `canonical_pair(rel_type, key_a, key_b)`.
- Regardless of whether `Ruwan FRIEND_OF Kamal` or `Kamal FRIEND_OF Ruwan` is ingested, exactly one edge is created/merged in the graph.

#### Single-Valued Relationships
Single-valued relationship types (`DUE_ON`, `SCHEDULED_ON`, `LIVES_IN`) permit at most one outgoing edge from a source entity.
- If a source entity already has an outgoing edge of this type pointing to a different target node, the old edge is deleted.
- The new edge is created and merged.
- `edges_replaced` is incremented.
- A warning is recorded: `<type>: <old_target> -> <new_target>`.
- *(TODO(RP-29): Full change history tracking using `:Change` nodes).*

#### Missing Endpoints
If a relationship references an endpoint that was omitted from `payload.entities`, the endpoint is automatically merged into the graph from its `EntityRef` definition before creating the relationship.

### 2.4 Provenance Rule
Every ingested payload automatically maintains origin tracking:
1. A `:Conversation` node is merged using `key = normalize_key(payload.source)` and `name = payload.source`.
2. For each touched entity in the transaction:
   - If `label in {"Task", "Decision", "Issue", "Question", "Idea", "Note", "Document"}`:
     An edge `(entity)-[:CREATED_IN]->(Conversation)` is merged.
   - For all other entity types (e.g. `Person`, `Team`, `Tool`, `Organization`):
     An edge `(Conversation)-[:MENTIONS]->(entity)` is merged.
   - The `:Conversation` node is never linked to itself.

### 2.5 Operation (Op) Handling Status
- **`add` & `update`**: Both operations merge the node/relationship and overwrite/update property values.
- **`retract`**: In RP-26, deletions are deferred to prevent accidental loss of spoken history. A warning is logged and added to `result.warnings`. Full retraction logic with conflict policies and tombstone tracking is planned for RP-29.

### 2.6 Idempotency & Dry Run
- **Idempotency**: Ingesting the same payload multiple times is completely idempotent. Total node and edge counts in the graph remain unchanged, with subsequent runs recording `nodes_created=0` and `edges_created=0`.
- **Dry Run**: When `dry_run=True`, the entire ingestion logic executes within an explicit transaction that is rolled back upon completion. The returned `IngestResult` reports all counts and warnings that would have occurred without mutating the graph.

---

## 3. Running the Services

### 3.1 Local FastAPI Service (Strict Localhost Binding)

> [!IMPORTANT]
> **Privacy Invariant**: The ingestion listener processes personal conversation transcripts and entity graphs. It MUST ALWAYS be bound to `127.0.0.1` (localhost) and NEVER to `0.0.0.0` or public network adapters.

Start the FastAPI ingestion listener:
```bash
cd knowledge_graph
./venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

#### API Endpoints
- **`GET /health`**: Health check and Neo4j connectivity verification.
- **`POST /ingest[?dry_run=true]`**: Ingest a validated JSON `Payload`.
- **`POST /ingest/triples[?dry_run=true]`**: Ingest untyped or typed `[Subject, Predicate, Object]` triples.

#### Example Triples Ingestion via cURL
```bash
curl -X POST "http://127.0.0.1:8000/ingest/triples?dry_run=false" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "standup_convo_20261018",
    "timestamp": "2026-10-18T09:30:00Z",
    "triples": [
      ["Benchmark latency", "ASSIGNED_TO", "David Miller"],
      ["David Miller", "FRIEND_OF", "Sarah Chen"]
    ]
  }'
```

---

### 3.2 CLI Tool (`graph_schema.ingest_cli`)

The CLI allows batch ingesting payload JSON files or triple files directly from the command line:

```bash
# Ingest payload files in live mode
python -m graph_schema.ingest_cli sample_data/payloads/01_office_meeting.json sample_data/payloads/02_personal_party.json

# Simulate ingestion in dry-run mode
python -m graph_schema.ingest_cli sample_data/payloads/01_office_meeting.json --dry-run

# Ingest untyped triple files
python -m graph_schema.ingest_cli sample_data/payloads/triples_example.json --triples
```
