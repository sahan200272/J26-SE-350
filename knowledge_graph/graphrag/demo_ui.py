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
        WHERE n.key IN $keys
          AND ($include_private OR coalesce(n['sensitivity'], 'normal') <> 'private')
        RETURN n.key AS key,
               coalesce(n.name, n.key) AS name,
               labels(n)[0] AS type,
               properties(n) AS props
        LIMIT $limit
        """
        edges_query = """
        MATCH (a)-[r]->(b)
        WHERE a.key IN $keys AND b.key IN $keys
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


DEMO_HTML: str = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>J26-SE-350 | Knowledge Graph & Multi-Hop GraphRAG Console</title>
<style>
  :root {
    --bg: #f8fafc;
    --panel: #ffffff;
    --panel-alt: #f1f5f9;
    --border: #e2e8f0;
    --border-hover: #cbd5e1;
    --text: #0f172a;
    --muted: #64748b;
    --accent: #2563eb;
    --accent-hover: #1d4ed8;
    --accent-subtle: #eff6ff;
    --success: #16a34a;
    --success-subtle: #f0fdf4;
    --warn: #d97706;
    --danger: #dc2626;
    --purple: #7c3aed;
    --purple-subtle: #faf5ff;
    --card-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.03);
    --card-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.06), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.45;
    padding-bottom: 40px;
    -webkit-font-smoothing: antialiased;
  }
  header {
    background: #ffffff;
    border-bottom: 1px solid var(--border);
    padding: 14px 28px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
  }
  .brand-wrap {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand-icon {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    background: #0f172a;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    font-weight: 700;
    font-size: 0.82rem;
    letter-spacing: 0.05em;
  }
  .brand h1 {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.01em;
  }
  .brand p {
    font-size: 0.77rem;
    color: var(--muted);
    margin-top: 1px;
  }
  .badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .badge {
    font-size: 0.74rem;
    padding: 4px 10px;
    border-radius: 6px;
    background: var(--panel-alt);
    border: 1px solid var(--border);
    color: #334155;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .badge .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .badge.ok { border-color: #bbf7d0; color: #15803d; background: var(--success-subtle); }
  .badge.ok .dot { background: #16a34a; }
  .badge.info { border-color: #bfdbfe; color: #1d4ed8; background: var(--accent-subtle); }
  .badge.info .dot { background: #2563eb; }
  .badge.purple { border-color: #e9d5ff; color: #7e22ce; background: var(--purple-subtle); }
  .badge.purple .dot { background: #9333ea; }
  .badge.emerald { border-color: #a7f3d0; color: #047857; background: #ecfdf5; }
  .badge.emerald .dot { background: #059669; }

  .layout {
    display: grid;
    grid-template-columns: 410px 1fr;
    gap: 16px;
    padding: 18px 28px;
    max-width: 1720px;
    margin: 0 auto;
  }
  @media (max-width: 1150px) {
    .layout { grid-template-columns: 1fr; padding: 14px 16px; }
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    box-shadow: var(--card-shadow);
  }
  .panel-title {
    font-size: 0.88rem;
    font-weight: 600;
    color: #0f172a;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
    letter-spacing: -0.01em;
  }
  .panel-title span.tag {
    font-size: 0.7rem;
    background: var(--accent-subtle);
    color: var(--accent);
    border: 1px solid #bfdbfe;
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
    background: #ffffff;
    color: #334155;
    padding: 6px 11px;
    border-radius: 6px;
    font-size: 0.77rem;
    font-weight: 500;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  button:hover {
    border-color: var(--border-hover);
    background: var(--panel-alt);
    color: #0f172a;
  }
  button.primary {
    background: #0f172a;
    color: #ffffff;
    border-color: #0f172a;
    font-weight: 600;
  }
  button.primary:hover {
    background: #1e293b;
    border-color: #1e293b;
    color: #ffffff;
  }
  button.purple-btn {
    background: var(--purple-subtle);
    border-color: #ddd6fe;
    color: #6d28d9;
    font-weight: 500;
  }
  button.purple-btn:hover {
    background: #ede9fe;
    border-color: #c4b5fd;
    color: #5b21b6;
  }
  button.outline-accent {
    background: #ffffff;
    border-color: #cbd5e1;
    color: #0f172a;
  }
  button.outline-accent:hover {
    background: var(--panel-alt);
    border-color: #94a3b8;
  }
  textarea {
    width: 100%;
    height: 250px;
    background: #ffffff;
    color: #0f172a;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.76rem;
    resize: vertical;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }
  .controls-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  label.checkbox {
    font-size: 0.78rem;
    color: #475569;
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-weight: 500;
  }
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .stat-box {
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    text-align: center;
  }
  .stat-box .num {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.02em;
  }
  .stat-box .lbl {
    font-size: 0.69rem;
    color: var(--muted);
    font-weight: 500;
    margin-top: 2px;
  }
  .warning-box {
    background: #fffbeb;
    border: 1px solid #fde68a;
    color: #92400e;
    font-size: 0.75rem;
    padding: 8px 12px;
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
    background: #ffffff;
    border: 1px solid var(--border);
    color: #0f172a;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.85rem;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .query-bar input[type="text"]:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }
  select {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid var(--border);
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.8rem;
    outline: none;
  }
  select:focus {
    border-color: var(--accent);
  }

  /* Canvas Graph */
  .canvas-wrap {
    position: relative;
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 8px;
    height: 390px;
    overflow: hidden;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.03);
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
    gap: 10px;
    background: rgba(255, 255, 255, 0.95);
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid var(--border);
    font-size: 0.72rem;
    color: #334155;
    box-shadow: var(--card-shadow);
    pointer-events: none;
    backdrop-filter: blur(4px);
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 5px;
    font-weight: 500;
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    display: inline-block;
  }
  .node-inspector {
    position: absolute;
    bottom: 10px;
    right: 10px;
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 0.75rem;
    max-width: 340px;
    color: #0f172a;
    box-shadow: var(--card-shadow-md);
    backdrop-filter: blur(4px);
  }

  /* Answer box */
  .answer-card {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 12px 14px;
    display: none;
    box-shadow: var(--card-shadow);
  }
  .answer-header {
    font-size: 0.76rem;
    font-weight: 600;
    color: #15803d;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
  }
  .answer-text {
    font-size: 0.88rem;
    color: #0f172a;
    line-height: 1.5;
  }

  /* Tabs */
  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0px;
    overflow-x: auto;
  }
  .tab-btn {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--muted);
    font-weight: 500;
    font-size: 0.79rem;
    padding: 8px 12px;
    border-radius: 0;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }
  .tab-btn:hover {
    color: #0f172a;
    background: transparent;
    border-color: transparent;
  }
  .tab-btn.active {
    background: transparent;
    color: #0f172a;
    border-bottom: 2px solid #0f172a;
    font-weight: 600;
  }
  .tab-content { display: none; padding-top: 12px; }
  .tab-content.active { display: block; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.77rem;
    background: #ffffff;
  }
  th, td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    text-align: left;
  }
  th {
    background: #f8fafc;
    color: #475569;
    font-weight: 600;
    font-size: 0.71rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  tr:hover td {
    background: #f8fafc;
  }
  .score-pill {
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.74rem;
  }
  .gain-chip {
    display: inline-block;
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
    color: #047857;
    padding: 3px 8px;
    border-radius: 999px;
    font-size: 0.74rem;
    margin: 3px;
    font-weight: 500;
  }
  pre.md-box {
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    font-size: 0.76rem;
    color: #334155;
    overflow-x: auto;
    max-height: 280px;
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }
</style>
</head>
<body>

<header>
  <div class="brand-wrap">
    <div class="brand-icon">KG</div>
    <div class="brand">
      <h1>Knowledge Graph & Contextual Linking Engine</h1>
      <p>J26-SE-350 &bull; Component 3 (Kumarage A.L.I &mdash; IT23264120) &bull; Evaluation Console</p>
    </div>
  </div>
  <div class="badges">
    <span class="badge ok" id="dbStatusBadge"><span class="dot"></span>Neo4j Connected</span>
    <span class="badge info"><span class="dot"></span>127.0.0.1 (Local)</span>
    <span class="badge purple"><span class="dot"></span>LLaMA 3 (8B)</span>
    <span class="badge emerald" id="mlBadge"><span class="dot"></span>ML Intent Model (96.9% CV)</span>
    <span class="badge" id="graphCountBadge">Nodes: 0 | Edges: 0</span>
  </div>
</header>

<div class="layout">
  <!-- LEFT COLUMN: INGESTION -->
  <div class="panel">
    <div class="panel-title">
      <span>1. Live JSON Payload Ingestion</span>
      <span class="tag">RP-25 & RP-26</span>
    </div>

    <div style="font-size:0.76rem; color:var(--muted);">Load sample conversation payload or edit JSON directly:</div>
    <div class="preset-row">
      <button onclick="loadPreset('whisperx')">WhisperX Blocker</button>
      <button onclick="loadPreset('office')">Office Sync</button>
      <button onclick="loadPreset('personal')">Personal & Aliases</button>
      <button onclick="loadPreset('correction')">Deadline Reschedule</button>
      <button onclick="loadPreset('unknown')">Unknown Intent</button>
    </div>

    <textarea id="jsonInput" spellcheck="false"></textarea>

    <div class="controls-row">
      <label class="checkbox">
        <input type="checkbox" id="dryRunCheck"> Dry-Run (Rollback Transaction)
      </label>
      <button class="primary" onclick="runIngest()">Ingest Payload to Neo4j</button>
    </div>

    <div class="panel-title" style="margin-top:4px;">
      <span>Transaction Results</span>
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

  <!-- RIGHT COLUMN: GRAPHRAG & VISUALIZATION -->
  <div class="right-col">
    <div class="panel">
      <div class="panel-title">
        <span>2. Constrained Multi-Hop GraphRAG Traversal</span>
        <span class="tag">RP-27</span>
      </div>

      <div class="preset-row">
        <span style="font-size:0.75rem; color:var(--muted); align-self:center;">Presets:</span>
        <button onclick="setQuery('When is the Weekly sync meeting and who was absent?')">Meeting Attendance</button>
        <button onclick="setQuery('Who is friend of Kamal and where do they work?')">Personal Relationships</button>
        <button onclick="setQuery('What is blocking Sarah Chen\'s WhisperX task and how is that issue resolved?')">Multi-Hop Blocker Chain</button>
        <button onclick="setQuery('Who is assigned to Test payment flow and what is blocking it?')">Task Dependency</button>
      </div>

      <div class="query-bar">
        <input type="text" id="queryInput" value="What is blocking Sarah Chen's WhisperX task and how is that issue resolved?" placeholder="Enter multi-hop relational search query...">
        <select id="hopsSelect" title="Max Traversal Depth">
          <option value="1">1 Hop</option>
          <option value="2" selected>2 Hops</option>
          <option value="3">3 Hops</option>
        </select>
        <label class="checkbox">
          <input type="checkbox" id="synthCheck" checked> LLaMA 3 Synthesis
        </label>
        <label class="checkbox">
          <input type="checkbox" id="privateCheck"> Include Private
        </label>
        <button class="primary" onclick="runRetrieve()">Execute GraphRAG</button>
        <button class="purple-btn" onclick="runCompare()">Compare Baseline</button>
        <button onclick="showLastIngestedGraph()" id="btnLastIngested" style="border-color:#bbf7d0; color:#15803d; background:#f0fdf4;">View Ingested</button>
        <button onclick="loadFullGraph()" class="outline-accent">View Complete Graph</button>
      </div>

      <!-- 2D Force-Directed Graph Canvas -->
      <div class="canvas-wrap">
        <canvas id="graphCanvas"></canvas>
        <div class="canvas-legend">
          <span id="graphViewModeLabel" style="color:#0f172a; font-weight:700; margin-right:6px;">[Mode: Complete Graph]</span>
          <span class="legend-item"><span class="dot" style="background:#f59e0b;"></span>Seed Anchor</span>
          <span class="legend-item"><span class="dot" style="background:#0284c7;"></span>Person</span>
          <span class="legend-item"><span class="dot" style="background:#16a34a;"></span>Task</span>
          <span class="legend-item"><span class="dot" style="background:#dc2626;"></span>Issue</span>
          <span class="legend-item"><span class="dot" style="background:#7c3aed;"></span>Decision</span>
          <span class="legend-item"><span class="dot" style="background:#ea580c;"></span>Deadline / Meeting</span>
          <span class="legend-item"><span class="dot" style="background:#64748b;"></span>Other</span>
        </div>
        <div class="node-inspector" id="nodeInspector">
          Click or drag nodes to inspect relational properties.
        </div>
      </div>

      <!-- LLaMA 3 8B Synthesized Answer Box -->
      <div class="answer-card" id="answerCard">
        <div class="answer-header">
          <span id="answerModelLabel">LLaMA 3 (8B) Grounded Answer</span>
          <span id="answerLatencyLabel"></span>
        </div>
        <div class="answer-text" id="answerText"></div>
      </div>

      <!-- Evaluation & Mathematical Scoring Tabs -->
      <div class="tabs">
        <button class="tab-btn active" id="tabBtnStored" onclick="switchTab('tabStored', this)">Stored Graph Entities</button>
        <button class="tab-btn" id="tabBtnPaths" onclick="switchTab('tabPaths', this)">Ranked Traversal Paths</button>
        <button class="tab-btn" id="tabBtnModel" onclick="switchTab('tabModel', this)">ML Intent Evaluation</button>
        <button class="tab-btn" id="tabBtnCompare" onclick="switchTab('tabCompare', this)">Keyword Baseline Comparison</button>
        <button class="tab-btn" id="tabBtnContext" onclick="switchTab('tabContext', this)">Retrieved Context</button>
      </div>

      <!-- TAB 0: STORED GRAPH EXPLORER (BEFORE GRAPHRAG) -->
      <div class="tab-content active" id="tabStored">
        <div style="font-size:0.76rem; color:var(--muted); margin-bottom:8px; display:flex; justify-content:space-between;">
          <span id="storedSubgraphTitle">Currently displayed nodes and relationships in Neo4j:</span>
          <span id="storedSubgraphCounts" style="color:var(--accent); font-weight:700;"></span>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
          <div style="overflow-x:auto; max-height:240px; border:1px solid var(--border); border-radius:6px;">
            <table>
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Entity Name</th>
                  <th>Key & Properties</th>
                </tr>
              </thead>
              <tbody id="storedNodesTableBody">
                <tr><td colspan="3" style="color:var(--muted);">Loading stored nodes...</td></tr>
              </tbody>
            </table>
          </div>
          <div style="overflow-x:auto; max-height:240px; border:1px solid var(--border); border-radius:6px;">
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
        <div id="liveIntentProbsBar" style="display:none; font-size:0.72rem; margin-bottom:8px; padding:6px 10px; background:var(--panel-alt); border:1px solid var(--border); border-radius:6px;"></div>
        <div style="overflow-x:auto; max-height:250px; border:1px solid var(--border); border-radius:6px;">
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
              <tr><td colspan="8" style="color:var(--muted);">Execute a GraphRAG query above to view ranked multi-hop paths.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- TAB 1B: TRAINED ML INTENT CLASSIFIER METRICS -->
      <div class="tab-content" id="tabModel">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <div style="font-size:0.78rem; color:var(--text);">
            <strong>Architecture:</strong> <span id="mlModelName" style="color:var(--accent);">Hybrid TF-IDF N-Gram + L2 Softmax Logistic Regression & Multinomial NB Ensemble</span>
          </div>
          <button onclick="retrainModel()" id="btnRetrainModel" class="outline-accent" style="border-color:var(--accent); color:var(--accent);">Re-Train Classifier (5-Fold CV)</button>
        </div>
        <div class="stat-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:10px;">
          <div class="stat-box"><div class="num" style="color:var(--success);" id="mlCvAcc">96.9%</div><div class="lbl">5-Fold CV Accuracy</div></div>
          <div class="stat-box"><div class="num" style="color:var(--success);" id="mlCvF1">0.9694</div><div class="lbl">5-Fold Macro F1</div></div>
          <div class="stat-box"><div class="num" id="mlTestAcc">94.4%</div><div class="lbl">80/20 Holdout Test Acc</div></div>
          <div class="stat-box"><div class="num" id="mlDatasetInfo">360 / 4,220</div><div class="lbl">Samples / Vocab Features</div></div>
        </div>
        <div style="display:grid; grid-template-columns: 1.05fr 1fr; gap:12px;">
          <div style="overflow-x:auto; max-height:230px; border:1px solid var(--border); border-radius:6px;">
            <div style="font-size:0.73rem; color:var(--muted); padding:6px 10px; background:#f8fafc; border-bottom:1px solid var(--border); font-weight:600;">Per-Class Evaluation Metrics (5-Fold Stratified CV):</div>
            <table>
              <thead>
                <tr>
                  <th>Intent Class</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>F1-Score</th>
                  <th>Support</th>
                </tr>
              </thead>
              <tbody id="mlPerClassBody">
                <tr><td colspan="5" style="color:var(--muted);">Loading model metrics...</td></tr>
              </tbody>
            </table>
          </div>
          <div style="overflow-x:auto; max-height:230px; border:1px solid var(--border); border-radius:6px;">
            <div style="font-size:0.73rem; color:var(--muted); padding:6px 10px; background:#f8fafc; border-bottom:1px solid var(--border); font-weight:600;">6x6 Confusion Matrix (Rows = True, Cols = Predicted):</div>
            <table id="mlConfusionTable">
              <tbody id="mlConfusionBody">
                <tr><td style="color:var(--muted);">Loading confusion matrix...</td></tr>
              </tbody>
            </table>
          </div>
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
          Click "Compare Baseline" to evaluate multi-hop entity recall gain against flat search.
        </div>
        <div id="cmpGainList"></div>
      </div>

      <!-- TAB 4: FORMATTED CONTEXT -->
      <div class="tab-content" id="tabContext">
        <pre class="md-box" id="contextBox">Execute a GraphRAG query to inspect the formatted Markdown context block sent to LLaMA 3.</pre>
      </div>
    </div>
  </div>
</div>

<script>
let lastTouchedKeys = [];

const PRESETS = {
  security: {
    source: "voice_memo_20261020_security_review",
    schema_version: "1.0",
    timestamp: "2026-10-20T09:30:00Z",
    entities: [
      { type: "Person", name: "Kavindu Jayasinghe", op: "add", props: { title: "Mobile Security Engineer", aliases: ["Kavindu"] } },
      { type: "Task", name: "Encrypt local SQLite voice cache", op: "add", props: { status: "blocked", priority: "urgent", description: "Add AES-256 encryption to offline voice transcript cache" } },
      { type: "Deadline", name: "2026-10-24", op: "add", props: { date: "2026-10-24" } },
      { type: "Issue", name: "Android Keystore biometric timeout crash", op: "add", props: { severity: "critical", status: "open" } },
      { type: "Decision", name: "Use background session key caching", op: "add", props: { status: "agreed" } },
      { type: "Meeting", name: "Security Architecture Standup", op: "add", props: { date: "2026-10-20", time: "09:30" } }
    ],
    relationships: [
      { from: { type: "Task", name: "Encrypt local SQLite voice cache" }, type: "ASSIGNED_TO", to: { type: "Person", name: "Kavindu Jayasinghe" }, props: { confidence: 0.98 } },
      { from: { type: "Task", name: "Encrypt local SQLite voice cache" }, type: "DUE_ON", to: { type: "Deadline", name: "2026-10-24" }, props: { confidence: 0.95 } },
      { from: { type: "Task", name: "Encrypt local SQLite voice cache" }, type: "BLOCKED_BY", to: { type: "Issue", name: "Android Keystore biometric timeout crash" }, props: { confidence: 0.96 } },
      { from: { type: "Decision", name: "Use background session key caching" }, type: "RESOLVES", to: { type: "Issue", name: "Android Keystore biometric timeout crash" }, props: { confidence: 0.94 } },
      { from: { type: "Decision", name: "Use background session key caching" }, type: "CREATED_IN", to: { type: "Meeting", name: "Security Architecture Standup" }, props: { confidence: 0.95 } },
      { from: { type: "Person", name: "Kavindu Jayasinghe" }, type: "ATTENDED", to: { type: "Meeting", name: "Security Architecture Standup" }, props: { confidence: 0.99 } }
    ]
  },
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
}

function updateStoredTables(nodes, edges, titleText) {
  document.getElementById("storedSubgraphTitle").textContent = titleText;
  document.getElementById("storedSubgraphCounts").textContent = `${nodes.length} Nodes | ${edges.length} Relationships`;

  const nBody = document.getElementById("storedNodesTableBody");
  nBody.innerHTML = "";
  if (!nodes || nodes.length === 0) {
    nBody.innerHTML = `<tr><td colspan="3" style="color:var(--muted); text-align:center; padding:16px;">No nodes to display.</td></tr>`;
  } else {
    nodes.forEach(n => {
      const propStr = Object.entries(n.props || {})
        .filter(([k, v]) => v !== null && v !== "" && k !== "created_at" && k !== "updated_at")
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(", ");
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge" style="display:inline-block; font-size:0.71rem; padding:2px 7px;">${n.type}</span></td>
        <td><strong>${n.name}</strong></td>
        <td style="color:var(--muted); font-size:0.73rem;"><code>${n.key}</code>${propStr ? ' • ' + propStr : ''}</td>
      `;
      nBody.appendChild(tr);
    });
  }

  const eBody = document.getElementById("storedEdgesTableBody");
  eBody.innerHTML = "";
  if (!edges || edges.length === 0) {
    eBody.innerHTML = `<tr><td colspan="3" style="color:var(--muted); text-align:center; padding:16px;">No relationships to display.</td></tr>`;
  } else {
    edges.forEach(e => {
      const orig = e.props && e.props.label ? ` (${e.props.label})` : "";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${e.from_name || e.from}</strong> <span style="color:var(--muted); font-size:0.72rem;">(${e.from_type || ''})</span></td>
        <td><span style="color:var(--accent); font-weight:600;">—[${e.type}${orig}]→</span></td>
        <td><strong>${e.to_name || e.to}</strong> <span style="color:var(--muted); font-size:0.72rem;">(${e.to_type || ''})</span></td>
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
  document.getElementById("graphViewModeLabel").textContent = `[Mode: Ingested Subgraph (${data.nodes.length} nodes)]`;
  document.getElementById("answerCard").style.display = "none";
  setGraphData(data.nodes || [], data.edges || [], new Set());
  updateStoredTables(data.nodes || [], data.edges || [], "Ingested / Updated Subgraph Stored in Neo4j (Pre-Retrieval):");
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
    if (!res.ok) {
      const errDetail = Array.isArray(data.detail)
        ? data.detail.map(d => (d.msg || JSON.stringify(d))).join(" | ")
        : (typeof data.detail === "object" ? JSON.stringify(data.detail) : (data.detail || "Ingestion failed"));
      throw new Error(errDetail);
    }

    document.getElementById("stNodesCreated").textContent = data.nodes_created;
    document.getElementById("stNodesMerged").textContent = data.nodes_merged;
    document.getElementById("stAliasesAdded").textContent = data.aliases_added;
    document.getElementById("stEdgesCreated").textContent = data.edges_created;
    document.getElementById("stEdgesMerged").textContent = data.edges_merged;
    document.getElementById("stEdgesReplaced").textContent = data.edges_replaced;
    document.getElementById("ingestModeBadge").textContent = dryRun ? "Dry-Run Rolled Back" : "Committed to Neo4j";

    if (data.warnings && data.warnings.length > 0) {
      warnBox.style.display = "block";
      warnBox.innerHTML = "<strong>Audit / Conflict Warnings:</strong><br>" + data.warnings.map(w => "• " + w).join("<br>");
    }

    if (data.touched && data.touched.length > 0 && !dryRun) {
      lastTouchedKeys = data.touched
        .filter(pair => pair[0] !== "Conversation")
        .map(pair => pair[1]);
      await showLastIngestedGraph();
    } else {
      await loadFullGraph();
    }
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
    document.getElementById("answerText").textContent = "Traversing Neo4j subgraph and synthesizing grounded answer with local LLaMA 3 (8B)...";
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
    document.getElementById("graphViewModeLabel").textContent = `[Mode: GraphRAG ${maxHops}-Hop Subgraph]`;
    setGraphData(data.nodes || [], data.edges || [], seedKeys);
    updateStoredTables(data.nodes || [], data.edges || [], `Retrieved Subgraph for Query: "${query}"`);

    // Update Answer Card
    if (synth && data.synthesized_answer) {
      ansCard.style.display = "block";
      document.getElementById("answerModelLabel").textContent = `LLaMA 3 (8B) Grounded Answer (${data.llm_model_used || 'llama3:8b'})`;
      document.getElementById("answerLatencyLabel").textContent = `Retrieval: ${data.latency_ms} ms | Synthesis: ${data.synthesis_latency_ms || 0} ms`;
      document.getElementById("answerText").textContent = data.synthesized_answer;
    }

    // Update Scored Paths Table & ML Intent Confidence
    const confPct = ((data.intent_confidence || 1.0) * 100).toFixed(1);
    document.getElementById("intentBadge").innerHTML = `Detected Intent: <strong>${data.detected_intent}</strong> <span style="color:var(--success); font-weight:600;">[ML Confidence: ${confPct}%]</span> (${data.latency_ms} ms)`;

    const probsBar = document.getElementById("liveIntentProbsBar");
    if (data.intent_probabilities && Object.keys(data.intent_probabilities).length > 0) {
      probsBar.style.display = "block";
      const chips = Object.entries(data.intent_probabilities)
        .sort((a,b) => b[1] - a[1])
        .map(([c, p]) => `<span style="margin-right:12px; ${c === data.detected_intent ? 'color:var(--accent); font-weight:600;' : 'color:var(--muted);'}">${c}: ${(p*100).toFixed(1)}%</span>`)
        .join("");
      probsBar.innerHTML = `<strong>ML Intent Probabilities:</strong> ` + chips;
    } else {
      probsBar.style.display = "none";
    }

    const tbody = document.getElementById("pathsTableBody");
    tbody.innerHTML = "";
    if (!data.ranked_paths || data.ranked_paths.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="color:var(--muted); text-align:center; padding:16px;">No connected paths found for query.</td></tr>`;
    } else {
      data.ranked_paths.forEach((p, idx) => {
        const parts = [];
        if (p.hops && p.hops.length > 0) {
          parts.push(`<strong>${p.hops[0].from_node.name}</strong> <span style="color:var(--muted); font-size:0.72rem;">(${p.hops[0].from_node.type})</span>`);
          p.hops.forEach(h => {
            const orig = h.props && h.props.label ? ` (${h.props.label})` : "";
            parts.push(`<span style="color:var(--accent); font-weight:600;">—[${h.relationship_type}${orig}]→</span> <strong>${h.to_node.name}</strong> <span style="color:var(--muted); font-size:0.72rem;">(${h.to_node.type})</span>`);
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
      gainDiv.innerHTML = `<div style="font-size:0.76rem; color:var(--muted); margin-bottom:6px; font-weight:500;">Entities Uncovered Exclusively via Multi-Hop Graph Traversal:</div>` +
        data.multi_hop_entity_gain.map(g => `<span class="gain-chip">+ [${g.type}] ${g.name}</span>`).join("");
    } else {
      gainDiv.innerHTML = "";
    }

    if (data.graphrag_result) {
      const seedKeys = new Set((data.graphrag_result.anchors || []).map(a => a.key));
      document.getElementById("graphViewModeLabel").textContent = `[Mode: Baseline Comparison Subgraph]`;
      setGraphData(data.graphrag_result.nodes || [], data.graphrag_result.edges || [], seedKeys);
    }
  } catch (err) {
    document.getElementById("cmpSummary").textContent = "Error: " + err.message;
  }
}

async function loadFullGraph() {
  try {
    const incPriv = document.getElementById("privateCheck").checked;
    const res = await fetch(`/graph/snapshot?include_private=${incPriv}`);
    const data = await res.json();
    document.getElementById("graphCountBadge").textContent = `Nodes: ${data.total_nodes} | Edges: ${data.total_edges}`;
    document.getElementById("graphViewModeLabel").textContent = `[Mode: Complete Database Graph (${data.nodes.length} nodes)]`;
    setGraphData(data.nodes || [], data.edges || [], new Set());
    updateStoredTables(data.nodes || [], data.edges || [], `Complete Database Graph Stored in Neo4j (${data.nodes.length} Nodes, ${data.edges.length} Edges):`);
    switchTab("tabStored", document.getElementById("tabBtnStored"));
  } catch (e) {
    console.error(e);
  }
}

/* =====================================================================
   Interactive 2D Force-Directed Graph Canvas (Clean Light Theme)
   ===================================================================== */
const canvas = document.getElementById("graphCanvas");
const ctx = canvas.getContext("2d");
let gNodes = [];
let gEdges = [];
let dragNode = null;
let hoverNode = null;
let simAlpha = 0.0;

const TYPE_COLORS = {
  Person: "#0284c7",    // sky blue
  Task: "#16a34a",      // green
  Issue: "#dc2626",     // crimson red
  Decision: "#7c3aed",  // violet purple
  Deadline: "#ea580c",  // warm orange
  Meeting: "#d97706",   // amber
  Project: "#2563eb",   // royal blue
  Event: "#db2777",     // pink
  Location: "#0d9488",  // teal
  Concept: "#64748b"    // slate
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

  gEdges = edges.map(e => ({
    source: nodeMap.get(e.from) || { x: w / 2, y: h / 2, vx: 0, vy: 0 },
    target: nodeMap.get(e.to) || { x: w / 2, y: h / 2, vx: 0, vy: 0 },
    type: e.type,
    props: e.props || {}
  })).filter(e => e.source.key && e.target.key);

  simAlpha = 1.0;
}

function stepPhysics(alphaOverride) {
  const alpha = alphaOverride !== undefined ? alphaOverride : simAlpha;
  if (alpha <= 0.0001) return;

  const w = canvas.width;
  const h = canvas.height;
  const count = gNodes.length;
  const isLarge = count > 30;

  const repulseStrength = isLarge ? 550 : 1200;
  const targetDist = isLarge ? 48 : 85;
  const gravityStrength = isLarge ? 0.045 : 0.035;

  for (let i = 0; i < count; i++) {
    for (let j = i + 1; j < count; j++) {
      const a = gNodes[i];
      const b = gNodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let distSq = dx * dx + dy * dy + 1.0;
      if (isLarge && distSq > 18000) continue;
      let dist = Math.sqrt(distSq);
      let force = (repulseStrength / distSq) * alpha;
      let fx = (dx / dist) * force;
      let fy = (dy / dist) * force;
      a.vx -= fx; a.vy -= fy;
      b.vx += fx; b.vy += fy;
    }
  }

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
    ctx.strokeStyle = isHighlighted ? "#2563eb" : (isLarge ? "rgba(148, 163, 184, 0.6)" : "#cbd5e1");
    ctx.lineWidth = isHighlighted ? 2.0 : (isLarge ? 1.0 : 1.3);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Arrowhead
    const angle = Math.atan2(y2 - y1, x2 - x1);
    const arrowDist = isLarge ? 11 : 16;
    const ax = x2 - arrowDist * Math.cos(angle);
    const ay = y2 - arrowDist * Math.sin(angle);
    ctx.fillStyle = isHighlighted ? "#2563eb" : "#94a3b8";
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(ax - 6 * Math.cos(angle - Math.PI / 6), ay - 6 * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(ax - 6 * Math.cos(angle + Math.PI / 6), ay - 6 * Math.sin(angle + Math.PI / 6));
    ctx.closePath();
    ctx.fill();

    // Edge label
    if (!isLarge || isHighlighted) {
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      ctx.fillStyle = isHighlighted ? "#1e40af" : "#64748b";
      ctx.font = isHighlighted ? "600 10px -apple-system, sans-serif" : "10px -apple-system, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(e.type, mx, my - 4);
    }
  }

  // Draw nodes
  for (const n of gNodes) {
    const r = n.isSeed ? 14 : (isLarge ? 8 : 11);
    const color = TYPE_COLORS[n.type] || "#64748b";

    if (n.isSeed) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 4, 0, 2 * Math.PI);
      ctx.strokeStyle = "#d97706";
      ctx.lineWidth = 2.5;
      ctx.stroke();
      ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = n === hoverNode ? "#0f172a" : "#ffffff";
    ctx.lineWidth = n === hoverNode ? 2.5 : 2.0;
    ctx.stroke();

    // Node name
    ctx.fillStyle = n === hoverNode ? "#0f172a" : "#1e293b";
    ctx.font = (n.isSeed || n === hoverNode) ? "600 11px -apple-system, sans-serif" : (isLarge ? "9.5px -apple-system, sans-serif" : "10.5px -apple-system, sans-serif");
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
    <strong>[${n.type}] ${n.name}</strong> ${n.isSeed ? '<span style="color:#d97706; font-weight:600;">(Seed Anchor)</span>' : ''}<br>
    <span style="color:var(--muted);">${propEntries || 'key: ' + n.key}</span>
  `;
}

async function loadModelMetrics() {
  try {
    const res = await fetch("/model/metrics");
    const m = await res.json();
    if (!res.ok) return;
    const cv = m.cross_validation_5fold || {};
    const overall = cv.overall_cv_metrics || {};
    document.getElementById("mlCvAcc").textContent = ((cv.mean_accuracy || 0) * 100).toFixed(1) + "%";
    document.getElementById("mlCvF1").textContent = (cv.mean_macro_f1 || 0).toFixed(4);
    if (m.test_split_80_20) {
      document.getElementById("mlTestAcc").textContent = ((m.test_split_80_20.accuracy || 0) * 100).toFixed(1) + "%";
    }
    document.getElementById("mlDatasetInfo").textContent = `${m.dataset_size} / ${m.vocabulary_size}`;
    if (m.model_name) document.getElementById("mlModelName").textContent = m.model_name;

    const perClass = overall.per_class || {};
    const perClassBody = document.getElementById("mlPerClassBody");
    perClassBody.innerHTML = "";
    Object.entries(perClass).forEach(([c, stats]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${c}</strong></td>
        <td>${(stats.precision || 0).toFixed(4)}</td>
        <td>${(stats.recall || 0).toFixed(4)}</td>
        <td><span class="score-pill">${(stats.f1_score || 0).toFixed(4)}</span></td>
        <td>${stats.support || 0}</td>
      `;
      perClassBody.appendChild(tr);
    });

    const matrix = overall.confusion_matrix || [];
    const classes = overall.classes || [];
    const confBody = document.getElementById("mlConfusionBody");
    confBody.innerHTML = "";
    if (classes.length > 0 && matrix.length > 0) {
      const headerTr = document.createElement("tr");
      headerTr.innerHTML = `<th>True \ Pred</th>` + classes.map(c => `<th style="font-size:0.68rem;">${c.slice(0,4)}</th>`).join("");
      confBody.appendChild(headerTr);

      matrix.forEach((row, rIdx) => {
        const rowTr = document.createElement("tr");
        let cells = `<td style="font-size:0.7rem; font-weight:700;">${classes[rIdx]}</td>`;
        row.forEach((cnt, cIdx) => {
          const isDiag = rIdx === cIdx;
          const bg = isDiag ? "background:#f0fdf4; font-weight:700; color:#15803d;" : (cnt > 0 ? "background:#fef2f2; color:#b91c1c;" : "color:var(--muted);");
          cells += `<td style="text-align:center; ${bg}">${cnt}</td>`;
        });
        rowTr.innerHTML = cells;
        confBody.appendChild(rowTr);
      });
    }
  } catch (e) {
    console.error("Error loading model metrics:", e);
  }
}

async function retrainModel() {
  const btn = document.getElementById("btnRetrainModel");
  const origText = btn.textContent;
  btn.textContent = "Training 5 Folds...";
  btn.disabled = true;
  try {
    const res = await fetch("/model/train", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Training failed");
    await loadModelMetrics();
    alert("Model trained successfully! 5-Fold CV Accuracy: " + ((data.cross_validation_5fold.mean_accuracy || 0) * 100).toFixed(1) + "%");
  } catch (e) {
    alert("Training error: " + e.message);
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  loadPreset("whisperx");
  loadFullGraph();
  loadModelMetrics();
  requestAnimationFrame(drawGraph);
});
</script>
</body>
</html>
"""
