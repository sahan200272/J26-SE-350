"""Interactive Web Dashboard UI for Knowledge Graph & Multi-Hop GraphRAG Demo.

Provides:
  - get_graph_snapshot(): Fetches live Neo4j graph nodes, edges, and summary counts.
  - DEMO_HTML: Self-contained single-page application (HTML5 Canvas force-directed graph,
    live JSON ingestion, multi-hop GraphRAG query runner, LLaMA 3 8B answer display,
    mathematical path score breakdown table, and Keyword Baseline comparator).
"""

from typing import Any, Dict, List, Optional
from neo4j import Driver

from graph_schema.schema import get_driver
from graphrag.retriever import _sanitize_prop_value


def get_graph_snapshot(
    limit: int = 120,
    include_private: bool = False,
    keys: Optional[List[str]] = None,
    driver: Optional[Driver] = None,
) -> Dict[str, Any]:
    """Fetch a live snapshot of nodes, relationships, and label statistics from Neo4j."""
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    clean_keys = [k.strip() for k in (keys or []) if k and k.strip()]

    if clean_keys:
        nodes_query = """
        MATCH (n)
        WHERE NOT n:Conversation
          AND n.key IN $keys
          AND ($include_private OR coalesce(n['sensitivity'], 'normal') <> 'private')
        RETURN n.key AS key,
               coalesce(n.name, n.key) AS name,
               labels(n)[0] AS type,
               properties(n) AS props
        LIMIT $limit
        """
        edges_query = """
        MATCH (a)-[r]->(b)
        WHERE NOT a:Conversation AND NOT b:Conversation
          AND a.key IN $keys AND b.key IN $keys
          AND ($include_private OR (coalesce(a['sensitivity'], 'normal') <> 'private' AND coalesce(b['sensitivity'], 'normal') <> 'private'))
        RETURN a.key AS from_key,
               coalesce(a.name, a.key) AS from_name,
               labels(a)[0] AS from_type,
               type(r) AS rel_type,
               b.key AS to_key,
               coalesce(b.name, b.key) AS to_name,
               labels(b)[0] AS to_type,
               properties(r) AS props
        LIMIT $edge_limit
        """
    else:
        nodes_query = """
        MATCH (n)
        WHERE NOT n:Conversation
          AND n.key IS NOT NULL
          AND ($include_private OR coalesce(n['sensitivity'], 'normal') <> 'private')
        RETURN n.key AS key,
               coalesce(n.name, n.key) AS name,
               labels(n)[0] AS type,
               properties(n) AS props
        LIMIT $limit
        """
        edges_query = """
        MATCH (a)-[r]->(b)
        WHERE NOT a:Conversation AND NOT b:Conversation
          AND a.key IS NOT NULL AND b.key IS NOT NULL
          AND ($include_private OR (coalesce(a['sensitivity'], 'normal') <> 'private' AND coalesce(b['sensitivity'], 'normal') <> 'private'))
        RETURN a.key AS from_key,
               coalesce(a.name, a.key) AS from_name,
               labels(a)[0] AS from_type,
               type(r) AS rel_type,
               b.key AS to_key,
               coalesce(b.name, b.key) AS to_name,
               labels(b)[0] AS to_type,
               properties(r) AS props
        LIMIT $edge_limit
        """

    counts_query = """
    MATCH (n)
    WHERE n.key IS NOT NULL
    RETURN labels(n)[0] AS label, count(n) AS count
    ORDER BY count DESC
    """

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    label_counts: Dict[str, int] = {}

    try:
        with driver.session() as session:
            for rec in session.run(nodes_query, include_private=include_private, limit=limit, keys=clean_keys):
                raw_props = dict(rec["props"] or {})
                clean_props = {
                    str(k): _sanitize_prop_value(v)
                    for k, v in raw_props.items()
                    if k not in ("key", "name")
                }
                nodes.append({
                    "key": str(rec["key"]),
                    "name": str(rec["name"]),
                    "type": str(rec["type"] or "Concept"),
                    "props": clean_props,
                })

            for rec in session.run(edges_query, include_private=include_private, edge_limit=limit * 2, keys=clean_keys):
                raw_props = dict(rec["props"] or {})
                clean_props = {
                    str(k): _sanitize_prop_value(v)
                    for k, v in raw_props.items()
                }
                edges.append({
                    "from": str(rec["from_key"]),
                    "from_name": str(rec["from_name"]),
                    "from_type": str(rec["from_type"] or "Concept"),
                    "type": str(rec["rel_type"]),
                    "to": str(rec["to_key"]),
                    "to_name": str(rec["to_name"]),
                    "to_type": str(rec["to_type"] or "Concept"),
                    "confidence": float(raw_props.get("confidence", 1.0)),
                    "props": clean_props,
                })

            for rec in session.run(counts_query):
                lbl = str(rec["label"] or "Unknown")
                label_counts[lbl] = int(rec["count"])
    finally:
        if close_driver:
            driver.close()

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": sum(label_counts.values()),
        "total_edges": len(edges),
        "label_counts": label_counts,
    }


DEMO_HTML: str = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>J26-SE-350 | Graph-Based Knowledge Engine & Multi-Hop GraphRAG Demo</title>
<style>
  :root {
    --bg: #0b0f19;
    --panel: #131b2e;
    --panel-alt: #1a243d;
    --border: #2a395c;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --accent-hover: #0284c7;
    --success: #22c55e;
    --warn: #f59e0b;
    --danger: #ef4444;
    --purple: #a855f7;
    --gold: #facc15;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.45;
    padding-bottom: 32px;
  }
  header {
    background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
    border-bottom: 1px solid var(--border);
    padding: 14px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand h1 {
    font-size: 1.15rem;
    font-weight: 700;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .brand p {
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 2px;
  }
  .badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .badge {
    font-size: 0.75rem;
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--panel-alt);
    border: 1px solid var(--border);
    color: var(--text);
    font-weight: 600;
  }
  .badge.ok { border-color: #16a34a; color: #4ade80; background: rgba(34,197,94,0.12); }
  .badge.info { border-color: #0284c7; color: #38bdf8; background: rgba(56,189,248,0.12); }
  .badge.purple { border-color: #9333ea; color: #c084fc; background: rgba(168,85,247,0.12); }

  .layout {
    display: grid;
    grid-template-columns: 400px 1fr;
    gap: 16px;
    padding: 16px 24px;
    max-width: 1680px;
    margin: 0 auto;
  }
  @media (max-width: 1150px) {
    .layout { grid-template-columns: 1fr; }
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .panel-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #fff;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
  }
  .panel-title span.tag {
    font-size: 0.7rem;
    background: rgba(56,189,248,0.15);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
  }
  .preset-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  button {
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--panel-alt);
    color: var(--text);
    padding: 6px 11px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    transition: all 0.15s ease;
  }
  button:hover {
    border-color: var(--accent);
    background: #243252;
  }
  button.primary {
    background: var(--accent);
    color: #0f172a;
    border-color: var(--accent);
    font-weight: 700;
  }
  button.primary:hover {
    background: var(--accent-hover);
    color: #fff;
  }
  button.purple-btn {
    background: rgba(168,85,247,0.2);
    border-color: var(--purple);
    color: #e9d5ff;
  }
  button.purple-btn:hover {
    background: var(--purple);
    color: #fff;
  }
  textarea {
    width: 100%;
    height: 250px;
    background: #090d16;
    color: #a5f3fc;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.76rem;
    resize: vertical;
  }
  .controls-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  label.checkbox {
    font-size: 0.8rem;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
  }
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .stat-box {
    background: #090d16;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    text-align: center;
  }
  .stat-box .num {
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--accent);
  }
  .stat-box .lbl {
    font-size: 0.7rem;
    color: var(--muted);
  }
  .warning-box {
    background: rgba(245, 158, 11, 0.12);
    border: 1px solid var(--warn);
    color: #fcd34d;
    font-size: 0.75rem;
    padding: 8px;
    border-radius: 6px;
    display: none;
  }

  /* Right column layout */
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .query-bar {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .query-bar input[type="text"] {
    flex: 1;
    min-width: 260px;
    background: #090d16;
    border: 1px solid var(--border);
    color: #fff;
    padding: 9px 12px;
    border-radius: 6px;
    font-size: 0.88rem;
  }
  select {
    background: #090d16;
    color: var(--text);
    border: 1px solid var(--border);
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.8rem;
  }

  /* Canvas Graph */
  .canvas-wrap {
    position: relative;
    background: radial-gradient(circle at center, #111827 0%, #070a12 100%);
    border: 1px solid var(--border);
    border-radius: 8px;
    height: 390px;
    overflow: hidden;
  }
  canvas#graphCanvas {
    width: 100%;
    height: 100%;
    display: block;
    cursor: grab;
  }
  canvas#graphCanvas:active { cursor: grabbing; }
  .canvas-legend {
    position: absolute;
    top: 10px;
    left: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    background: rgba(15, 23, 42, 0.85);
    padding: 6px 10px;
    border-radius: 6px;
    border: 1px solid var(--border);
    font-size: 0.72rem;
    pointer-events: none;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }
  .node-inspector {
    position: absolute;
    bottom: 10px;
    right: 10px;
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 0.76rem;
    max-width: 320px;
    color: var(--text);
  }

  /* Answer box */
  .answer-card {
    background: linear-gradient(135deg, rgba(56,189,248,0.1) 0%, rgba(168,85,247,0.1) 100%);
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 12px 14px;
    display: none;
  }
  .answer-header {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
  }
  .answer-text {
    font-size: 0.9rem;
    color: #f8fafc;
  }

  /* Tabs */
  .tabs {
    display: flex;
    gap: 6px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
  }
  .tab-btn.active {
    background: var(--accent);
    color: #0f172a;
    border-color: var(--accent);
  }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
  }
  th, td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    text-align: left;
  }
  th {
    background: #090d16;
    color: var(--muted);
    font-weight: 600;
  }
  .score-pill {
    background: rgba(34,197,94,0.18);
    color: #4ade80;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 700;
  }
  .gain-chip {
    display: inline-block;
    background: rgba(34,197,94,0.15);
    border: 1px solid #16a34a;
    color: #86efac;
    padding: 4px 9px;
    border-radius: 999px;
    font-size: 0.76rem;
    margin: 3px;
  }
  pre.md-box {
    background: #090d16;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    font-size: 0.76rem;
    color: #cbd5e1;
    overflow-x: auto;
    max-height: 280px;
    white-space: pre-wrap;
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <h1>🕸️ Privacy-Preserving Knowledge Graph & Multi-Hop GraphRAG Engine</h1>
    <p>J26-SE-350 • Component 3 (Kumarage A.L.I — IT23264120) • 50% Progress Milestone Demo</p>
  </div>
  <div class="badges">
    <span class="badge ok" id="dbStatusBadge">● Neo4j 5 Connected</span>
    <span class="badge info">🔒 Localhost 127.0.0.1 Only</span>
    <span class="badge purple">🧠 Ollama LLaMA 3 (8B)</span>
    <span class="badge" id="graphCountBadge">Nodes: 0 | Edges: 0</span>
  </div>
</header>

<div class="layout">
  <!-- LEFT COLUMN: RP-25 & RP-26 INGESTION -->
  <div class="panel">
    <div class="panel-title">
      <span>1. Live JSON Payload Ingestion</span>
      <span class="tag">RP-25 & RP-26</span>
    </div>

    <div style="font-size:0.76rem; color:var(--muted);">Load a sample conversation payload or edit JSON below:</div>
    <div class="preset-row">
      <button onclick="loadPreset('whisperx')">⚡ WhisperX Blocker</button>
      <button onclick="loadPreset('office')">🏢 Office Sync</button>
      <button onclick="loadPreset('personal')">🎂 Personal & Aliases</button>
      <button onclick="loadPreset('correction')">🔄 Deadline Change</button>
      <button onclick="loadPreset('unknown')">🧩 Unknown Fallback</button>
    </div>

    <textarea id="jsonInput" spellcheck="false"></textarea>

    <div class="controls-row">
      <label class="checkbox">
        <input type="checkbox" id="dryRunCheck"> Dry-Run (Rollback Transaction)
      </label>
      <button class="primary" onclick="runIngest()">🚀 Ingest JSON to Neo4j</button>
    </div>

    <div class="panel-title" style="margin-top:4px;">
      <span>Ingestion Transaction Result</span>
      <span id="ingestModeBadge" style="font-size:0.72rem; color:var(--muted);">Ready</span>
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="num" id="stNodesCreated">0</div><div class="lbl">Nodes Created</div></div>
      <div class="stat-box"><div class="num" id="stNodesMerged">0</div><div class="lbl">Nodes Merged</div></div>
      <div class="stat-box"><div class="num" id="stAliasesAdded">0</div><div class="lbl">Aliases (Fuzzy)</div></div>
      <div class="stat-box"><div class="num" id="stEdgesCreated">0</div><div class="lbl">Edges Created</div></div>
      <div class="stat-box"><div class="num" id="stEdgesMerged">0</div><div class="lbl">Edges Merged</div></div>
      <div class="stat-box"><div class="num" id="stEdgesReplaced">0</div><div class="lbl">Edges Replaced</div></div>
    </div>

    <div class="warning-box" id="ingestWarnings"></div>
  </div>

  <!-- RIGHT COLUMN: RP-27 GRAPHRAG & VISUALIZATION -->
  <div class="right-col">
    <div class="panel">
      <div class="panel-title">
        <span>2. Constrained Multi-Hop GraphRAG Traversal & Live Subgraph</span>
        <span class="tag">RP-27</span>
      </div>

      <div class="preset-row">
        <span style="font-size:0.75rem; color:var(--muted); align-self:center;">Sample Queries:</span>
        <button onclick="setQuery('When is the Weekly sync meeting and who was absent?')">📅 Meeting Date & Attendance</button>
        <button onclick="setQuery('Who is friend of Kamal and where do they work?')">👥 Kamal's Friends & Workplace</button>
        <button onclick="setQuery('What is blocking Sarah Chen\\'s WhisperX task and how is that issue resolved?')">🔍 Sarah's WhisperX Blocker (3-Hop)</button>
        <button onclick="setQuery('Who is assigned to Test payment flow and what is blocking it?')">💳 Payment Flow Blocker</button>
      </div>

      <div class="query-bar">
        <input type="text" id="queryInput" value="What is blocking Sarah Chen's WhisperX task and how is that issue resolved?" placeholder="Ask a multi-hop relational question...">
        <select id="hopsSelect" title="Max Hops (d)">
          <option value="1">1 Hop</option>
          <option value="2" selected>2 Hops</option>
          <option value="3">3 Hops</option>
        </select>
        <label class="checkbox">
          <input type="checkbox" id="synthCheck" checked> 🧠 LLaMA 3 8B Answer
        </label>
        <label class="checkbox">
          <input type="checkbox" id="privateCheck"> Include Private
        </label>
        <button class="primary" onclick="runRetrieve()">🔍 Run GraphRAG</button>
        <button class="purple-btn" onclick="runCompare()">📊 Compare vs. Keyword Baseline</button>
        <button onclick="showLastIngestedGraph()" id="btnLastIngested" style="border-color:#22c55e; color:#4ade80;">✨ Ingested Graph</button>
        <button onclick="loadFullGraph()">🌐 Full DB Graph</button>
      </div>

      <!-- 2D Force-Directed Graph Canvas -->
      <div class="canvas-wrap">
        <canvas id="graphCanvas"></canvas>
        <div class="canvas-legend">
          <span id="graphViewModeLabel" style="color:#4ade80; font-weight:700; margin-right:6px;">[Mode: Full DB Graph]</span>
          <span class="legend-item"><span class="dot" style="background:#facc15; box-shadow:0 0 6px #facc15;"></span>Seed Anchor</span>
          <span class="legend-item"><span class="dot" style="background:#38bdf8;"></span>Person</span>
          <span class="legend-item"><span class="dot" style="background:#22c55e;"></span>Task</span>
          <span class="legend-item"><span class="dot" style="background:#ef4444;"></span>Issue</span>
          <span class="legend-item"><span class="dot" style="background:#a855f7;"></span>Decision</span>
          <span class="legend-item"><span class="dot" style="background:#f97316;"></span>Deadline / Meeting</span>
          <span class="legend-item"><span class="dot" style="background:#94a3b8;"></span>Other</span>
        </div>
        <div class="node-inspector" id="nodeInspector">
          Click or drag any node to inspect properties & relationships.
        </div>
      </div>

      <!-- LLaMA 3 8B Synthesized Answer Box -->
      <div class="answer-card" id="answerCard">
        <div class="answer-header">
          <span id="answerModelLabel">🧠 LLaMA 3 (8B) Graph-Grounded Answer</span>
          <span id="answerLatencyLabel"></span>
        </div>
        <div class="answer-text" id="answerText"></div>
      </div>

      <!-- Evaluation & Mathematical Scoring Tabs -->
      <div class="tabs">
        <button class="tab-btn active" id="tabBtnStored" onclick="switchTab('tabStored', this)">🗄️ Stored Graph (Nodes & Edges)</button>
        <button class="tab-btn" id="tabBtnPaths" onclick="switchTab('tabPaths', this)">📐 Mathematical Scored Paths</button>
        <button class="tab-btn" id="tabBtnCompare" onclick="switchTab('tabCompare', this)">📊 Baseline Comparison (SE-P04 Proof)</button>
        <button class="tab-btn" id="tabBtnPending" onclick="switchTab('tabPending', this)">🔔 Pending Tasks & Blockers (C4)</button>
        <button class="tab-btn" id="tabBtnContext" onclick="switchTab('tabContext', this)">📄 Raw LLM Prompt Context</button>
      </div>

      <!-- TAB 0: STORED GRAPH EXPLORER (BEFORE GRAPHRAG) -->
      <div class="tab-content active" id="tabStored">
        <div style="font-size:0.76rem; color:var(--muted); margin-bottom:8px; display:flex; justify-content:space-between;">
          <span id="storedSubgraphTitle">Showing currently displayed nodes & relationships stored in Neo4j:</span>
          <span id="storedSubgraphCounts" style="color:var(--accent); font-weight:700;"></span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
          <div style="overflow-x:auto; max-height:240px;">
            <table>
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Entity Name</th>
                  <th>Normalized Key & Properties</th>
                </tr>
              </thead>
              <tbody id="storedNodesTableBody">
                <tr><td colspan="3" style="color:var(--muted);">Loading stored nodes...</td></tr>
              </tbody>
            </table>
          </div>
          <div style="overflow-x:auto; max-height:240px;">
            <table>
              <thead>
                <tr>
                  <th>Source Entity</th>
                  <th>Relationship</th>
                  <th>Target Entity</th>
                </tr>
              </thead>
              <tbody id="storedEdgesTableBody">
                <tr><td colspan="3" style="color:var(--muted);">Loading stored relationships...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- TAB 1: SCORED PATHS -->
      <div class="tab-content" id="tabPaths">
        <div style="font-size:0.75rem; color:var(--muted); margin-bottom:8px;">
          Composite Formula: <code>S(P) = 0.35 * (0.75^(d-1)) + 0.25 * Confidence + 0.25 * IntentSalience + 0.15 * Recency</code>
          <span id="intentBadge" style="margin-left:10px; color:var(--accent); font-weight:700;"></span>
        </div>
        <div style="overflow-x:auto; max-height:250px;">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Multi-Hop Relational Path</th>
                <th>Hops (d)</th>
                <th>Decay</th>
                <th>Conf</th>
                <th>Intent</th>
                <th>Recency</th>
                <th>Final Score</th>
              </tr>
            </thead>
            <tbody id="pathsTableBody">
              <tr><td colspan="8" style="color:var(--muted);">Run a GraphRAG query above to view ranked multi-hop paths.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- TAB 2: BASELINE COMPARISON -->
      <div class="tab-content" id="tabCompare">
        <div class="stat-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:10px;">
          <div class="stat-box"><div class="num" id="cmpGraphCount">-</div><div class="lbl">GraphRAG Entities</div></div>
          <div class="stat-box"><div class="num" id="cmpKeyCount">-</div><div class="lbl">Flat Keyword Entities</div></div>
          <div class="stat-box"><div class="num" style="color:var(--success);" id="cmpGainCount">-</div><div class="lbl">Multi-Hop Entity Gain</div></div>
          <div class="stat-box"><div class="num" id="cmpLatency">-</div><div class="lbl">GraphRAG Latency</div></div>
        </div>
        <div id="cmpSummary" style="font-size:0.82rem; margin-bottom:8px; color:var(--text);">
          Click "📊 Compare vs. Keyword Baseline" to evaluate multi-hop entity recall gain.
        </div>
        <div id="cmpGainList"></div>
      </div>

      <!-- TAB 3: PENDING ITEMS -->
      <div class="tab-content" id="tabPending">
        <pre class="md-box" id="pendingBox">Loading pending tasks...</pre>
      </div>

      <!-- TAB 4: FORMATTED CONTEXT -->
      <div class="tab-content" id="tabContext">
        <pre class="md-box" id="contextBox">Run a GraphRAG query to inspect the formatted Markdown context sent to Component 2.</pre>
      </div>
    </div>
  </div>
</div>

<script>
let lastTouchedKeys = [];

const PRESETS = {
  whisperx: {
    source: "demo_convo_20261019_whisperx",
    schema_version: "1.0",
    timestamp: "2026-10-19T10:00:00Z",
    entities: [
      { type: "Person", name: "Sarah Chen", op: "add", props: { title: "Staff AI Engineer", aliases: ["Sarah"] } },
      { type: "Task", name: "Optimize WhisperX GPU memory", op: "add", props: { priority: "urgent", status: "blocked", confidence: 0.95 } },
      { type: "Issue", name: "CUDA Out of Memory on 8GB VRAM", op: "add", props: { severity: "critical", status: "open" } },
      { type: "Decision", name: "Enable INT8 Quantization for WhisperX", op: "add", props: { status: "agreed", rationale: "Cuts VRAM usage by 50%" } },
      { type: "Deadline", name: "2026-10-25", op: "add", props: { date: "2026-10-25" } }
    ],
    relationships: [
      { from: { type: "Task", name: "Optimize WhisperX GPU memory" }, type: "ASSIGNED_TO", to: { type: "Person", name: "Sarah Chen" }, props: { confidence: 0.95 } },
      { from: { type: "Task", name: "Optimize WhisperX GPU memory" }, type: "DUE_ON", to: { type: "Deadline", name: "2026-10-25" } },
      { from: { type: "Task", name: "Optimize WhisperX GPU memory" }, type: "BLOCKED_BY", to: { type: "Issue", name: "CUDA Out of Memory on 8GB VRAM" } },
      { from: { type: "Decision", name: "Enable INT8 Quantization for WhisperX" }, type: "RESOLVES", to: { type: "Issue", name: "CUDA Out of Memory on 8GB VRAM" } }
    ]
  },
  office: {
    source: "voice_convo_20261018_sprint_sync",
    schema_version: "1.0",
    timestamp: "2026-10-18T10:30:00Z",
    entities: [
      { type: "Meeting", name: "Sprint 15 Architecture Sync", props: { date: "2026-10-18", duration: "45m" } },
      { type: "Person", name: "David Miller", props: { title: "Senior Backend Engineer" } },
      { type: "Task", name: "Benchmark Ollama 8B inference latency", props: { priority: "high", status: "in progress" } },
      { type: "Issue", name: "Whisper memory limit exceeded", props: { severity: "high", status: "open" } },
      { type: "Decision", name: "Adopt Ollama 8B with 4-bit Quantization", props: { status: "agreed", rationale: "Reduces resident memory to 3.8GB" } },
      { type: "Deadline", name: "2026-10-21", props: { date: "2026-10-21" } }
    ],
    relationships: [
      { from: { type: "Person", name: "David Miller" }, type: "ATTENDED", to: { type: "Meeting", name: "Sprint 15 Architecture Sync" } },
      { from: { type: "Task", name: "Benchmark Ollama 8B inference latency" }, type: "ASSIGNED_TO", to: { type: "Person", name: "David Miller" } },
      { from: { type: "Task", name: "Benchmark Ollama 8B inference latency" }, type: "DUE_ON", to: { type: "Deadline", name: "2026-10-21" } },
      { from: { type: "Person", name: "David Miller" }, type: "RAISED", to: { type: "Issue", name: "Whisper memory limit exceeded" } },
      { from: { type: "Decision", name: "Adopt Ollama 8B with 4-bit Quantization" }, type: "RESOLVES", to: { type: "Issue", name: "Whisper memory limit exceeded" } }
    ]
  },
  personal: {
    source: "voice_convo_20261018_personal",
    schema_version: "1.0",
    timestamp: "2026-10-18T19:00:00Z",
    entities: [
      { type: "Person", name: "Ruwan Fernando", props: { aliases: ["Ruwan"] } },
      { type: "Person", name: "Kamal Perera", props: { sensitivity: "normal" } },
      { type: "Event", name: "Dilini surprise party", props: { date: "2026-11-15", status: "planned" } },
      { type: "Location", name: "Kandy", props: { description: "Hill country venue" } },
      { type: "Task", name: "Buy cake and balloons", props: { priority: "medium", status: "open" } }
    ],
    relationships: [
      { from: { type: "Person", name: "Ruwan Fernando" }, type: "FRIEND_OF", to: { type: "Person", name: "Kamal Perera" } },
      { from: { type: "Event", name: "Dilini surprise party" }, type: "LOCATED_AT", to: { type: "Location", name: "Kandy" } },
      { from: { type: "Task", name: "Buy cake and balloons" }, type: "ASSIGNED_TO", to: { type: "Person", name: "Ruwan Fernando" } }
    ]
  },
  correction: {
    source: "voice_convo_20261019_reschedule",
    schema_version: "1.0",
    timestamp: "2026-10-19T11:00:00Z",
    entities: [
      { type: "Task", name: "Optimize WhisperX GPU memory", op: "update", props: { priority: "urgent", status: "in progress" } },
      { type: "Deadline", name: "2026-10-28", op: "add", props: { date: "2026-10-28" } }
    ],
    relationships: [
      { from: { type: "Task", name: "Optimize WhisperX GPU memory" }, type: "DUE_ON", to: { type: "Deadline", name: "2026-10-28" }, op: "update" }
    ]
  },
  unknown: {
    source: "voice_convo_20261019_open_fallback",
    schema_version: "1.0",
    timestamp: "2026-10-19T12:00:00Z",
    entities: [
      { type: "Person", name: "Sarah Chen", op: "add" },
      { type: "Payment", name: "Cloud GPU Invoice #402", op: "add", props: { value: 150, unit: "USD" } }
    ],
    relationships: [
      { from: { type: "Person", name: "Sarah Chen" }, type: "APPROVED_PAYMENT", to: { type: "Payment", name: "Cloud GPU Invoice #402" } }
    ]
  }
};

function loadPreset(name) {
  const data = PRESETS[name];
  if (data) {
    document.getElementById("jsonInput").value = JSON.stringify(data, null, 2);
  }
}

function setQuery(q) {
  document.getElementById("queryInput").value = q;
  runRetrieve();
}

function switchTab(tabId, btn) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById(tabId).classList.add("active");
  btn.classList.add("active");
  if (tabId === "tabPending") {
    loadPending();
  }
}

function updateStoredTables(nodes, edges, titleText) {
  document.getElementById("storedSubgraphTitle").textContent = titleText;
  document.getElementById("storedSubgraphCounts").textContent = `${nodes.length} Nodes | ${edges.length} Relationships`;

  const nBody = document.getElementById("storedNodesTableBody");
  nBody.innerHTML = "";
  if (!nodes || nodes.length === 0) {
    nBody.innerHTML = `<tr><td colspan="3" style="color:var(--muted);">No nodes to display.</td></tr>`;
  } else {
    nodes.forEach(n => {
      const propStr = Object.entries(n.props || {})
        .filter(([k, v]) => v !== null && v !== "" && k !== "created_at" && k !== "updated_at")
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(", ");
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge">${n.type}</span></td>
        <td><strong>${n.name}</strong></td>
        <td style="color:var(--muted); font-size:0.73rem;"><code>${n.key}</code>${propStr ? ' • ' + propStr : ''}</td>
      `;
      nBody.appendChild(tr);
    });
  }

  const eBody = document.getElementById("storedEdgesTableBody");
  eBody.innerHTML = "";
  if (!edges || edges.length === 0) {
    eBody.innerHTML = `<tr><td colspan="3" style="color:var(--muted);">No relationships to display.</td></tr>`;
  } else {
    edges.forEach(e => {
      const orig = e.props && e.props.label ? ` (${e.props.label})` : "";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${e.from_name || e.from}</strong> <span style="color:var(--muted);">(${e.from_type || ''})</span></td>
        <td><span style="color:var(--accent); font-weight:700;">—[${e.type}${orig}]→</span></td>
        <td><strong>${e.to_name || e.to}</strong> <span style="color:var(--muted);">(${e.to_type || ''})</span></td>
      `;
      eBody.appendChild(tr);
    });
  }
}

async function showLastIngestedGraph() {
  if (!lastTouchedKeys || lastTouchedKeys.length === 0) {
    await loadFullGraph();
    return;
  }
  const incPriv = document.getElementById("privateCheck").checked;
  const qs = encodeURIComponent(lastTouchedKeys.join(","));
  const res = await fetch(`/graph/snapshot?include_private=${incPriv}&keys=${qs}`);
  const data = await res.json();
  document.getElementById("graphCountBadge").textContent = `Nodes: ${data.total_nodes} | Edges: ${data.total_edges}`;
  document.getElementById("graphViewModeLabel").textContent = `[Mode: ✨ Ingested Payload Graph (${data.nodes.length} nodes)]`;
  document.getElementById("answerCard").style.display = "none";
  setGraphData(data.nodes || [], data.edges || [], new Set());
  updateStoredTables(data.nodes || [], data.edges || [], "✨ Newly Ingested / Updated Graph Stored in Neo4j (Before GraphRAG):");
  switchTab("tabStored", document.getElementById("tabBtnStored"));
}

async function runIngest() {
  const raw = document.getElementById("jsonInput").value;
  const dryRun = document.getElementById("dryRunCheck").checked;
  const warnBox = document.getElementById("ingestWarnings");
  warnBox.style.display = "none";

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (e) {
    warnBox.style.display = "block";
    warnBox.textContent = "Invalid JSON syntax: " + e.message;
    return;
  }

  document.getElementById("ingestModeBadge").textContent = dryRun ? "Simulating (Dry-Run)..." : "Ingesting...";
  try {
    const res = await fetch(`/ingest?dry_run=${dryRun}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ingestion failed");

    document.getElementById("stNodesCreated").textContent = data.nodes_created;
    document.getElementById("stNodesMerged").textContent = data.nodes_merged;
    document.getElementById("stAliasesAdded").textContent = data.aliases_added;
    document.getElementById("stEdgesCreated").textContent = data.edges_created;
    document.getElementById("stEdgesMerged").textContent = data.edges_merged;
    document.getElementById("stEdgesReplaced").textContent = data.edges_replaced;
    document.getElementById("ingestModeBadge").textContent = dryRun ? "Dry-Run Rolled Back" : "✅ Committed to Neo4j";

    if (data.warnings && data.warnings.length > 0) {
      warnBox.style.display = "block";
      warnBox.innerHTML = "<strong>Audit / Conflict Warnings:</strong><br>" + data.warnings.map(w => "• " + w).join("<br>");
    }

    // Extract touched entity keys (excluding Conversation node) and immediately display the stored subgraph!
    if (data.touched && data.touched.length > 0 && !dryRun) {
      lastTouchedKeys = data.touched
        .filter(pair => pair[0] !== "Conversation")
        .map(pair => pair[1]);
      await showLastIngestedGraph();
    } else {
      await loadFullGraph();
    }
    await loadPending();
  } catch (err) {
    warnBox.style.display = "block";
    warnBox.textContent = "Error: " + err.message;
  }
}

async function runRetrieve() {
  const query = document.getElementById("queryInput").value.trim();
  if (!query) return;
  const maxHops = parseInt(document.getElementById("hopsSelect").value, 10);
  const synth = document.getElementById("synthCheck").checked;
  const incPriv = document.getElementById("privateCheck").checked;

  switchTab("tabPaths", document.getElementById("tabBtnPaths"));

  const ansCard = document.getElementById("answerCard");
  if (synth) {
    ansCard.style.display = "block";
    document.getElementById("answerText").textContent = "⏳ Traversing Neo4j subgraph and synthesizing grounded answer with local LLaMA 3 (8B)...";
  } else {
    ansCard.style.display = "none";
  }

  try {
    const res = await fetch("/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        max_hops: maxHops,
        top_k: 15,
        include_private: incPriv,
        synthesize_answer: synth,
        llm_model: "llama3:8b"
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Retrieval failed");

    // Render subgraph on canvas
    const seedKeys = new Set((data.anchors || []).map(a => a.key));
    document.getElementById("graphViewModeLabel").textContent = `[Mode: 🔍 GraphRAG ${maxHops}-Hop Subgraph]`;
    setGraphData(data.nodes || [], data.edges || [], seedKeys);
    updateStoredTables(data.nodes || [], data.edges || [], `🔍 Retrieved GraphRAG Subgraph for Query: "${query}"`);

    // Update Answer Card
    if (synth && data.synthesized_answer) {
      ansCard.style.display = "block";
      document.getElementById("answerModelLabel").textContent = `🧠 LLaMA 3 8B Grounded Answer (${data.llm_model_used || 'llama3:8b'})`;
      document.getElementById("answerLatencyLabel").textContent = `Retrieval: ${data.latency_ms} ms | Synthesis: ${data.synthesis_latency_ms || 0} ms`;
      document.getElementById("answerText").textContent = data.synthesized_answer;
    }

    // Update Scored Paths Table
    document.getElementById("intentBadge").textContent = `Detected Intent: ${data.detected_intent} (${data.latency_ms} ms)`;
    const tbody = document.getElementById("pathsTableBody");
    tbody.innerHTML = "";
    if (!data.ranked_paths || data.ranked_paths.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="color:var(--muted);">No paths found for query.</td></tr>`;
    } else {
      data.ranked_paths.forEach((p, idx) => {
        const parts = [];
        if (p.hops && p.hops.length > 0) {
          parts.push(`<strong>${p.hops[0].from_node.name}</strong> <span style="color:var(--muted);">(${p.hops[0].from_node.type})</span>`);
          p.hops.forEach(h => {
            const orig = h.props && h.props.label ? ` (${h.props.label})` : "";
            parts.push(`<span style="color:var(--accent);">—[${h.relationship_type}${orig}]→</span> <strong>${h.to_node.name}</strong> <span style="color:var(--muted);">(${h.to_node.type})</span>`);
          });
        }
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${idx + 1}</td>
          <td>${parts.join(" ")}</td>
          <td>${p.length}</td>
          <td>${p.hop_decay.toFixed(3)}</td>
          <td>${p.confidence_score.toFixed(2)}</td>
          <td>${p.intent_salience.toFixed(2)}</td>
          <td>${p.recency_score.toFixed(2)}</td>
          <td><span class="score-pill">${p.final_score.toFixed(4)}</span></td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Update Raw Context Box
    document.getElementById("contextBox").textContent = data.formatted_context || "";
  } catch (err) {
    ansCard.style.display = "block";
    document.getElementById("answerText").textContent = "Error: " + err.message;
  }
}

async function runCompare() {
  const query = document.getElementById("queryInput").value.trim();
  if (!query) return;
  const maxHops = parseInt(document.getElementById("hopsSelect").value, 10);
  const incPriv = document.getElementById("privateCheck").checked;

  // Switch to Compare tab
  switchTab("tabCompare", document.getElementById("tabBtnCompare"));

  try {
    const res = await fetch("/retrieve/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        max_hops: maxHops,
        top_k: 15,
        include_private: incPriv
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Comparison failed");

    const m = data.metrics;
    document.getElementById("cmpGraphCount").textContent = m.graphrag_entity_count;
    document.getElementById("cmpKeyCount").textContent = m.keyword_entity_count;
    document.getElementById("cmpGainCount").textContent = "+" + m.multi_hop_gain_count;
    document.getElementById("cmpLatency").textContent = m.graphrag_latency_ms + " ms";
    document.getElementById("cmpSummary").textContent = data.summary;

    const gainDiv = document.getElementById("cmpGainList");
    if (data.multi_hop_entity_gain && data.multi_hop_entity_gain.length > 0) {
      gainDiv.innerHTML = `<div style="font-size:0.76rem; color:var(--muted); margin-bottom:4px;">Entities Uncovered Exclusively via Multi-Hop Graph Traversal:</div>` +
        data.multi_hop_entity_gain.map(g => `<span class="gain-chip">+ [${g.type}] ${g.name}</span>`).join("");
    } else {
      gainDiv.innerHTML = "";
    }

    if (data.graphrag_result) {
      const seedKeys = new Set((data.graphrag_result.anchors || []).map(a => a.key));
      document.getElementById("graphViewModeLabel").textContent = `[Mode: 📊 Baseline Comparison Subgraph]`;
      setGraphData(data.graphrag_result.nodes || [], data.graphrag_result.edges || [], seedKeys);
    }
  } catch (err) {
    document.getElementById("cmpSummary").textContent = "Error: " + err.message;
  }
}

async function loadPending() {
  try {
    const incPriv = document.getElementById("privateCheck").checked;
    const res = await fetch(`/retrieve/pending?include_private=${incPriv}`);
    const data = await res.json();
    document.getElementById("pendingBox").textContent = data.formatted_context || "No pending tasks.";
  } catch (e) {
    document.getElementById("pendingBox").textContent = "Error loading pending tasks.";
  }
}

async function loadFullGraph() {
  try {
    const incPriv = document.getElementById("privateCheck").checked;
    const res = await fetch(`/graph/snapshot?include_private=${incPriv}`);
    const data = await res.json();
    document.getElementById("graphCountBadge").textContent = `Nodes: ${data.total_nodes} | Edges: ${data.total_edges}`;
    document.getElementById("graphViewModeLabel").textContent = `[Mode: 🌐 Full DB Graph (${data.nodes.length} nodes)]`;
    setGraphData(data.nodes || [], data.edges || [], new Set());
    updateStoredTables(data.nodes || [], data.edges || [], `🌐 Full Database Graph Stored in Neo4j (${data.nodes.length} Nodes, ${data.edges.length} Edges):`);
    switchTab("tabStored", document.getElementById("tabBtnStored"));
  } catch (e) {
    console.error(e);
  }
}

/* =====================================================================
   Interactive 2D Force-Directed Graph Canvas (Zero External CDN Needed)
   ===================================================================== */
const canvas = document.getElementById("graphCanvas");
const ctx = canvas.getContext("2d");
let gNodes = [];
let gEdges = [];
let dragNode = null;
let hoverNode = null;
let simAlpha = 0.0;

const TYPE_COLORS = {
  Person: "#38bdf8",
  Task: "#22c55e",
  Issue: "#ef4444",
  Decision: "#a855f7",
  Deadline: "#f97316",
  Meeting: "#f97316",
  Project: "#eab308",
  Event: "#ec4899",
  Location: "#14b8a6",
  Concept: "#94a3b8"
};

function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;
}
window.addEventListener("resize", resizeCanvas);

function setGraphData(nodes, edges, seedKeys) {
  resizeCanvas();
  const w = canvas.width || 800;
  const h = canvas.height || 390;
  const nodeMap = new Map();
  const count = Math.max(1, nodes.length);

  gNodes = nodes.map((n, i) => {
    // Golden-angle spiral initial placement for uniform distribution without corner clumping
    const goldenAngle = i * 2.399963229728653;
    const rRatio = Math.sqrt((i + 0.5) / count);
    const rx = (w * 0.38) * rRatio;
    const ry = (h * 0.36) * rRatio;
    const obj = {
      key: n.key,
      name: n.name,
      type: n.type,
      props: n.props || {},
      isSeed: seedKeys.has(n.key),
      x: w / 2 + rx * Math.cos(goldenAngle),
      y: h / 2 + ry * Math.sin(goldenAngle),
      vx: 0,
      vy: 0
    };
    nodeMap.set(n.key, obj);
    return obj;
  });

  gEdges = [];
  edges.forEach(e => {
    const src = nodeMap.get(e.from);
    const dst = nodeMap.get(e.to);
    if (src && dst && src !== dst) {
      gEdges.push({
        source: src,
        target: dst,
        type: e.type,
        props: e.props || {}
      });
    }
  });

  // Pre-compute 140 layout ticks synchronously so graph appears settled immediately
  for (let tick = 0; tick < 140; tick++) {
    const alpha = Math.max(0.05, 1.0 - tick / 140);
    stepPhysics(alpha);
  }
  // Cool down gently over a few frames and then stop moving completely
  simAlpha = 0.15;
}

function stepPhysics(alphaOverride) {
  const alpha = alphaOverride !== undefined ? alphaOverride : simAlpha;
  if (alpha <= 0.002 && !dragNode) return;

  const w = canvas.width || 800;
  const h = canvas.height || 390;
  const isLarge = gNodes.length > 30;
  const repulseStrength = isLarge ? 650 : 2200;
  const targetDist = isLarge ? 68 : 115;
  const gravityStrength = isLarge ? 0.012 : 0.006;

  // Repulsion between nodes
  for (let i = 0; i < gNodes.length; i++) {
    for (let j = i + 1; j < gNodes.length; j++) {
      const a = gNodes[i];
      const b = gNodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let distSq = dx * dx + dy * dy + 1.0;
      if (isLarge && distSq > 18000) continue; // Local cutoff for large graph clarity
      let dist = Math.sqrt(distSq);
      let force = (repulseStrength / distSq) * alpha;
      let fx = (dx / dist) * force;
      let fy = (dy / dist) * force;
      a.vx -= fx; a.vy -= fy;
      b.vx += fx; b.vy += fy;
    }
  }
  // Spring attraction along edges
  for (const e of gEdges) {
    let dx = e.target.x - e.source.x;
    let dy = e.target.y - e.source.y;
    let dist = Math.sqrt(dx * dx + dy * dy) + 0.1;
    let force = (dist - targetDist) * 0.04 * alpha;
    let fx = (dx / dist) * force;
    let fy = (dy / dist) * force;
    e.source.vx += fx; e.source.vy += fy;
    e.target.vx -= fx; e.target.vy -= fy;
  }
  // Center gravity & velocity damping
  const padX = 55;
  const padY = 38;
  for (const n of gNodes) {
    if (n === dragNode) continue;
    n.vx += (w / 2 - n.x) * gravityStrength * alpha;
    n.vy += (h / 2 - n.y) * gravityStrength * alpha;
    n.vx *= 0.72;
    n.vy *= 0.72;
    n.x = Math.max(padX, Math.min(w - padX, n.x + n.vx));
    n.y = Math.max(padY, Math.min(h - padY, n.y + n.vy));
  }

  if (alphaOverride === undefined && !dragNode) {
    simAlpha *= 0.92;
    if (simAlpha < 0.002) simAlpha = 0;
  }
}

function drawGraph() {
  stepPhysics();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const isLarge = gNodes.length > 30;

  // Draw edges
  for (const e of gEdges) {
    const x1 = e.source.x, y1 = e.source.y;
    const x2 = e.target.x, y2 = e.target.y;
    const isHighlighted = hoverNode && (e.source === hoverNode || e.target === hoverNode);
    ctx.strokeStyle = isHighlighted ? "#38bdf8" : (isLarge ? "rgba(71, 85, 105, 0.55)" : "#334155");
    ctx.lineWidth = isHighlighted ? 2.2 : (isLarge ? 1.1 : 1.5);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Arrowhead
    const angle = Math.atan2(y2 - y1, x2 - x1);
    const arrowDist = isLarge ? 11 : 16;
    const ax = x2 - arrowDist * Math.cos(angle);
    const ay = y2 - arrowDist * Math.sin(angle);
    ctx.fillStyle = isHighlighted ? "#38bdf8" : "#64748b";
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(ax - 6 * Math.cos(angle - Math.PI / 6), ay - 6 * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(ax - 6 * Math.cos(angle + Math.PI / 6), ay - 6 * Math.sin(angle + Math.PI / 6));
    ctx.closePath();
    ctx.fill();

    // Edge label (show always on subgraphs, or on hover in Full DB mode to prevent clutter)
    if (!isLarge || isHighlighted) {
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      ctx.fillStyle = isHighlighted ? "#bae6fd" : "#94a3b8";
      ctx.font = isHighlighted ? "bold 10px -apple-system, sans-serif" : "10px -apple-system, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(e.type, mx, my - 4);
    }
  }

  // Draw nodes
  for (const n of gNodes) {
    const r = n.isSeed ? 15 : (isLarge ? 8 : 12);
    const color = TYPE_COLORS[n.type] || "#94a3b8";

    if (n.isSeed) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 5, 0, 2 * Math.PI);
      ctx.strokeStyle = "#facc15";
      ctx.lineWidth = 2.5;
      ctx.shadowColor = "#facc15";
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = n === hoverNode ? "#ffffff" : "#0f172a";
    ctx.lineWidth = n === hoverNode ? 2.5 : 1.8;
    ctx.stroke();

    // Node name
    ctx.fillStyle = n === hoverNode ? "#ffffff" : "#f8fafc";
    ctx.font = (n.isSeed || n === hoverNode) ? "bold 11px -apple-system, sans-serif" : (isLarge ? "9.5px -apple-system, sans-serif" : "11px -apple-system, sans-serif");
    ctx.textAlign = "center";
    const maxLen = isLarge && n !== hoverNode ? 18 : 26;
    const label = n.name.length > maxLen ? n.name.slice(0, maxLen - 2) + "…" : n.name;
    ctx.fillText(label, n.x, n.y + r + (isLarge ? 10 : 13));
  }

  requestAnimationFrame(drawGraph);
}

canvas.addEventListener("mousedown", e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  for (const n of gNodes) {
    if (Math.hypot(n.x - mx, n.y - my) <= 18) {
      dragNode = n;
      simAlpha = 0.25;
      showNodeInspector(n);
      break;
    }
  }
});
canvas.addEventListener("mousemove", e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  if (dragNode) {
    dragNode.x = mx;
    dragNode.y = my;
    dragNode.vx = 0;
    dragNode.vy = 0;
    simAlpha = 0.2;
    return;
  }
  hoverNode = null;
  for (const n of gNodes) {
    if (Math.hypot(n.x - mx, n.y - my) <= 18) {
      hoverNode = n;
      break;
    }
  }
});
window.addEventListener("mouseup", () => {
  if (dragNode) {
    dragNode = null;
    simAlpha = 0.12;
  }
});

function showNodeInspector(n) {
  const propEntries = Object.entries(n.props || {})
    .filter(([k, v]) => v !== null && v !== "" && k !== "created_at" && k !== "updated_at")
    .map(([k, v]) => `<code>${k}</code>: ${JSON.stringify(v)}`)
    .join(" • ");
  document.getElementById("nodeInspector").innerHTML = `
    <strong>[${n.type}] ${n.name}</strong> ${n.isSeed ? '<span style="color:#facc15;">★ Seed Anchor</span>' : ''}<br>
    <span style="color:var(--muted);">${propEntries || 'key: ' + n.key}</span>
  `;
}

// Initialize on load
window.addEventListener("DOMContentLoaded", () => {
  loadPreset("whisperx");
  loadFullGraph();
  loadPending();
  requestAnimationFrame(drawGraph);
});
</script>
</body>
</html>
"""
