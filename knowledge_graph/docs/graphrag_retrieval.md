# GraphRAG Multi-Hop Retrieval & Context Synthesis Architecture

This document specifies the GraphRAG (Graph-Augmented Retrieval-Augmented Generation) retrieval mechanism implemented in `knowledge_graph/graphrag/` for Jira task **RP-27**. It directly addresses the SE-P04 research panel feedback requiring algorithmic novelty and domain-specific knowledge graph traversal without relying on black-box LangChain or LlamaIndex wrappers.

---

## 1. Architectural Overview

The GraphRAG retrieval engine translates unstructured user queries into context-aware subgraphs by combining query intent classification, multi-tier seed anchor resolution, bounded multi-hop relational graph traversal, mathematical path scoring, and hub-suppressed provenance attachment.

```mermaid
flowchart TD
    Q[User Search Query / Prompt] --> INT[Rule/Keyword Intent Classifier: detect_query_intent]
    Q --> RES[Seed Anchor Resolver: resolve_seed_anchors]
    
    INT -->|Detected Intent: task_status, blocker_chain, ...| TRAV
    RES -->|Resolved Anchor Nodes [score >= 0.80]| ALIAS[Alias Transparency Expansion: ALIAS_OF]
    ALIAS --> TRAV[Constrained Multi-Hop Traversal: retrieve_subgraph]
    
    subgraph Neo4j [Neo4j 5 Graph Constraints]
        TRAV -->|Enforce 1..3 Hops| P[Extract Paths: (a)-[r*1..3]-(b)]
        P -->|Privacy Filter| PRIV[Drop n.sensitivity='private']
        P -->|Hub Suppression| HUB[Exclude :Conversation as Bridge Hops]
    end
    
    HUB --> SCORE[Mathematical Composite Scorer: score_path]
    SCORE -->|Rank by final_score DESC| TOP[Select Top-K Paths & Subgraph Nodes/Edges]
    TOP --> PROV[Hub-Suppressed Conversation Provenance Linking]
    
    PROV --> FMT[Context Builder: build_formatted_context]
    FMT --> OUT[Structured Markdown Context for Agentic Core / LLaMA 3]
    
    TRAV -.->|Side-by-side| COMP[Baseline Comparator: compare_retrieval]
    COMP -->|Evaluate Gain| GAIN[Multi-Hop Entity Gain Metrics]
```

---

## 2. Query Intent Classification & Relational Salience

Queries are classified into one of six distinct intents (`QueryIntent`):

| Intent | Description | Salience Boosted Relationships |
| :--- | :--- | :--- |
| `blocker_chain` | Inquiries regarding blockers, bugs, bottlenecks, or obstacles. | `BLOCKED_BY`, `HAS_ISSUE`, `RESOLVES`, `DEPENDS_ON`, `RAISED` |
| `task_status` | Inquiries on progress, assignments, work items, and deliverables. | `ASSIGNED_TO`, `WORKS_ON`, `PART_OF`, `REQUESTED_BY`, `SUPPORTS` |
| `deadline_schedule` | Inquiries on target milestones, schedules, or due dates. | `DUE_ON`, `SCHEDULED_ON`, `PLANS`, `PART_OF` |
| `meeting_summary` | Inquiries regarding discussions, participants, or agendas. | `ATTENDED`, `ABSENT_FROM`, `DISCUSSED`, `DECIDED`, `LOCATED_AT` |
| `person_context` | Inquiries regarding contacts, colleagues, kinship, or preferences. | `FAMILY_OF`, `FRIEND_OF`, `PARTNER_OF`, `WORKS_AT`, `LIVES_IN`, `MEMBER_OF` |
| `general` | Broad or unclassified associative search queries. | All Tier-1 edges (0.80), Tier-2 (0.55), `RELATED_TO` (0.30) |

The intent salience function `get_relationship_intent_salience(rel_type, intent)` assigns an edge weight $\in [0.0, 1.0]$. Tier-1 schema edges are preferred over Tier-2 edges, and generic `RELATED_TO` fallbacks receive a lower baseline weight (0.30).

---

## 3. Multi-Tier Seed Anchor Resolution

To initiate graph traversal without needing external dense vector embeddings during offline edge inference, `resolve_seed_anchors` resolves query terms against existing Neo4j graph nodes using a 3-tier hierarchy:

1. **Tier 1: Exact Normalized Key Match** (`score = 1.0`)
   - Candidate query phrases are normalized (`strip().lower()`) and matched against `n.key`.
2. **Tier 2: Exact Alias Match** (`score = 0.95`)
   - Candidate phrases are matched against alternate name variants stored in `n.aliases`.
3. **Tier 3: Substring & Fuzzy Matching** (`score = token_sort_ratio / 100.0`, threshold $\ge 80$)
   - RapidFuzz `token_sort_ratio` evaluates token permutations to handle speech-to-text typos and morphological variants.
   - Punctuation-tolerant substring matching captures named entities embedded within natural language questions (e.g. `"Sarah Chen"` within `"What is Sarah Chen working on?"`).

---

## 4. Constrained Multi-Hop Traversal Invariants

During path discovery from anchor nodes, the engine enforces four critical invariants:

### 4.1 Provenance Hub Suppression
Every conversation audio session creates a `:Conversation` node that connects to all entities mentioned within that session via `CREATED_IN` or `MENTIONS`. If `:Conversation` nodes were traversed as intermediate bridge hops, any two completely unrelated entities discussed in the same meeting would be artificially linked at hop distance 2 (hub explosion).
- **Invariant**: The Cypher query strictly forbids `:Conversation` nodes on intermediate hops:
  ```cypher
  ALL(n IN nodes(p)[1..-1] WHERE NOT n:Conversation) AND NOT b:Conversation
  ```
- **Provenance Attachment**: Instead, `:Conversation` nodes are queried independently for all retrieved subgraph nodes and attached as metadata (`ProvenanceRef`).

### 4.2 Alias Transparency
Entities with `ALIAS_OF` relationships are traversed transparently without penalty. Seed anchors pointing to alias variants automatically expand to include the canonical entity node.

### 4.3 Privacy Filtering
To ensure compliance with local on-device privacy requirements:
- When `include_private=False` (default), any node where `n.sensitivity = 'private'` is strictly excluded from seed anchors, path traversal, and returned subgraphs.
- When `include_private=True`, private entities are unlocked for authenticated, personal query contexts.

### 4.4 Bounded Depth
Traversal depth $d$ is strictly clamped to $1 \le d \le 3$. This guarantees sub-50ms execution on local hardware (e.g. Apple Silicon M2/M3) and prevents combinatorial path explosion.

---

## 5. Mathematical Composite Path Scoring Formula

Every traversed path $P$ of length $d$ ($1 \le d \le 3$) is evaluated using an explicit, normalized convex combination formula ($0.35 + 0.25 + 0.25 + 0.15 = 1.00$):

$$\text{final\_score} = 0.35 \times \left(0.75^{d - 1}\right) + 0.25 \times \overline{\text{confidence}} + 0.25 \times \overline{\text{intent\_salience}} + 0.15 \times \text{recency\_score}$$

Where:
1. **Hop Decay** $\left(0.75^{d - 1}\right)$: Penalizes distant multi-hop paths to favor direct relational evidence ($d=1 \implies 1.00$, $d=2 \implies 0.75$, $d=3 \implies 0.5625$).
2. **Mean Edge Confidence** $\left(\overline{\text{confidence}}\right)$: Average extraction certainty score of edges along the path (extracted from `r.confidence`, default 1.0).
3. **Mean Intent Salience** $\left(\overline{\text{intent\_salience}}\right)$: Average alignment of relationship types along the path with the user's detected query intent.
4. **Recency Score** $\left(\text{recency\_score}\right)$: Temporal decay computed from ISO timestamps (`updated_at`, `created_at`, `date`, `last_seen`):
   - $\le 7$ days: $1.00$
   - $\le 30$ days: $0.85$
   - $\le 90$ days: $0.70$
   - $\le 365$ days: $0.50$
   - $> 365$ days: $0.30$
   - Missing timestamp: $0.60$ default

---

## 6. Context Synthesizer & Downstream Consumers

### 6.1 Agentic Reasoning Core (Component 2 / LLaMA 3)
`build_formatted_context(result)` generates a structured Markdown prompt block containing:
- **`### [Seed Entities]`**: Resolved anchor nodes, types, match methods, and scores.
- **`### [Multi-Hop Relational Paths with Scores]`**: Human-readable relational chains with score breakdowns.
- **`### [Entity Details & Properties]`**: Property lists (status, priority, dates) for all retrieved nodes.
- **`### [Conversation Provenance]`**: Originating audio session sources.

### 6.2 Proactive Notification Engine (Component 4)
`get_pending_items_context(driver, include_private)` retrieves active tasks (`status IN ['open', 'in progress', 'blocked']`), their deadlines (`DUE_ON`), assignees (`ASSIGNED_TO`), and active blockers (`BLOCKED_BY`). It returns both structured JSON and a formatted markdown summary for proactive notification scheduling.

---

## 7. Flat Keyword Baseline Comparator

To demonstrate the algorithmic utility of GraphRAG over conventional search, `baseline_keyword.py` implements `compare_retrieval`:
- **Keyword Baseline**: Performs isolated property matching (`toLower(n.name) CONTAINS term`) without traversing relationships.
- **Multi-Hop Entity Gain**: Measures the set difference:
  $$\text{Gain} = \text{Entities}_{\text{GraphRAG}} \setminus \text{Entities}_{\text{Keyword}}$$
  This highlights entities (such as root blockers or assignees) that are structurally relevant to answering the query but whose textual descriptions do not contain the query keywords.

---

## 8. API Endpoints & CLI Usage

All endpoints are strictly bound to `127.0.0.1` for local on-device privacy.

### 8.1 REST Endpoints (`main.py`)
- `POST /retrieve`: Executes GraphRAG retrieval (`RetrievalRequest` $\to$ `RetrievalResult`).
- `POST /retrieve/compare`: Side-by-side comparison against flat keyword baseline.
- `GET /retrieve/pending`: Retrieves active pending tasks, deadlines, and blockers for proactive notifications.

### 8.2 Command Line Interface (`retrieve_cli.py`)
```bash
# Basic multi-hop query
python -m graphrag.retrieve_cli --query "What is blocking the benchmark task?"

# 3-hop traversal with markdown output
python -m graphrag.retrieve_cli --query "Sarah Chen" --hops 3 --format

# Side-by-side baseline comparison
python -m graphrag.retrieve_cli --query "Audio pipeline optimization" --compare-baseline

# Pending items for notifications
python -m graphrag.retrieve_cli --pending
```
