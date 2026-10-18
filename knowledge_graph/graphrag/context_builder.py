"""Context synthesizer formatting GraphRAG subgraphs for Agentic Core and Notification Engine."""

from typing import Any, Dict, List, Optional
from neo4j import Driver

from graph_schema.schema import get_driver
from graphrag.models import RetrievalResult


def build_formatted_context(result: RetrievalResult) -> str:
    """Format a RetrievalResult into a structured Markdown prompt block.

    Includes:
      - ### [Seed Entities]
      - ### [Multi-Hop Relational Paths with Scores]
      - ### [Entity Details & Properties]
      - ### [Conversation Provenance]
    """
    lines: List[str] = [
        f"## GraphRAG Subgraph Context for Query: \"{result.query}\"",
        f"**Detected Intent:** `{result.detected_intent}` | **Latency:** `{result.latency_ms} ms`",
        "",
    ]

    # 1. [Seed Entities]
    lines.append("### [Seed Entities]")
    if not result.anchors:
        lines.append("_No anchor entities resolved._")
    else:
        for a in result.anchors:
            lines.append(f"- **{a.name}** ({a.type}) [match: `{a.match_type}`, score: {a.score:.2f}]")
    lines.append("")

    # 2. [Multi-Hop Relational Paths with Scores]
    lines.append("### [Multi-Hop Relational Paths with Scores]")
    if not result.ranked_paths:
        lines.append("_No relational paths traversed._")
    else:
        for idx, path in enumerate(result.ranked_paths, start=1):
            breakdown = (
                f"length: {path.length}, final_score: {path.final_score:.4f} | "
                f"decay: {path.hop_decay:.3f}, conf: {path.confidence_score:.2f}, "
                f"intent: {path.intent_salience:.2f}, recency: {path.recency_score:.2f}"
            )
            # Format hop sequence
            chain_parts = [f"({path.hops[0].from_node['type']}: {path.hops[0].from_node['name']})"]
            for hop in path.hops:
                conf_str = f" [conf: {hop.confidence:.2f}]" if hop.confidence < 1.0 else ""
                chain_parts.append(f"--[{hop.relationship_type}{conf_str}]--> ({hop.to_node['type']}: {hop.to_node['name']})")
            
            chain_repr = " ".join(chain_parts)
            lines.append(f"{idx}. {chain_repr}")
            lines.append(f"   _{breakdown}_")
    lines.append("")

    # 3. [Entity Details & Properties]
    lines.append("### [Entity Details & Properties]")
    if not result.nodes:
        lines.append("_No entity details._")
    else:
        for n in sorted(result.nodes, key=lambda x: (x.get("type", ""), x.get("name", ""))):
            props_dict = n.get("props", {})
            props_str = ", ".join(f"{k}: {v}" for k, v in sorted(props_dict.items()) if v)
            if props_str:
                lines.append(f"- **{n['type']}**: \"{n['name']}\" {{{props_str}}}")
            else:
                lines.append(f"- **{n['type']}**: \"{n['name']}\"")
    lines.append("")

    # 4. [Conversation Provenance]
    lines.append("### [Conversation Provenance]")
    if not result.provenance:
        lines.append("_No conversation provenance records linked._")
    else:
        for p in result.provenance:
            src_str = f" (source: `{p.source}`)" if p.source else ""
            lines.append(f"- Session **{p.conversation_name}** -[:{p.relationship}]-> Entity `{p.entity_key}`{src_str}")
    lines.append("")

    return "\n".join(lines)


def get_pending_items_context(
    driver: Optional[Driver] = None,
    include_private: bool = False,
) -> Dict[str, Any]:
    """Retrieve actionable pending tasks, blockers, deadlines, and assignees for Proactive Notifications.

    Returns:
        Dictionary containing structured tasks list and formatted Markdown context string.
    """
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    query = """
    MATCH (t:Task)
    WHERE t.key IS NOT NULL
      AND (t['status'] IN ['open', 'in progress', 'blocked'] OR t['status'] IS NULL)
      AND ($include_private OR coalesce(t['sensitivity'], 'normal') <> 'private')
    OPTIONAL MATCH (t)-[:DUE_ON]->(d:Deadline)
    WHERE ($include_private OR coalesce(d['sensitivity'], 'normal') <> 'private')
    OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(p:Person)
    WHERE ($include_private OR coalesce(p['sensitivity'], 'normal') <> 'private')
    OPTIONAL MATCH (t)-[:BLOCKED_BY]->(i:Issue)
    WHERE ($include_private OR coalesce(i['sensitivity'], 'normal') <> 'private')
    RETURN t.key AS task_key,
           t.name AS task_name,
           t['status'] AS status,
           t['priority'] AS priority,
           t['description'] AS description,
           d.name AS deadline,
           d['date'] AS deadline_date,
           p.name AS assignee,
           collect(DISTINCT {name: i.name, severity: i['severity'], status: i['status']}) AS blockers
    ORDER BY CASE t['priority']
        WHEN 'urgent' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
        ELSE 5 END,
        t.name ASC
    """

    tasks: List[Dict[str, Any]] = []
    try:
        with driver.session() as session:
            records = session.run(query, include_private=include_private)
            for rec in records:
                raw_blockers = rec["blockers"] or []
                clean_blockers = [b for b in raw_blockers if b.get("name")]
                tasks.append({
                    "task_key": rec["task_key"],
                    "task_name": rec["task_name"],
                    "status": rec["status"] or "open",
                    "priority": rec["priority"] or "medium",
                    "description": rec["description"],
                    "deadline": rec["deadline_date"] or rec["deadline"],
                    "assignee": rec["assignee"],
                    "blockers": clean_blockers,
                })
    finally:
        if close_driver:
            driver.close()

    # Build Markdown Context block for Component 4
    md_lines: List[str] = [
        "### [Pending Tasks & Blockers for Proactive Notifications]",
        f"Total Active Tasks: {len(tasks)}",
        "",
    ]

    if not tasks:
        md_lines.append("_No active pending tasks found._")
    else:
        for t in tasks:
            status_badge = f"[{t['status'].upper()}]"
            prio_badge = f"[{t['priority'].upper()}]"
            assignee_str = f", Assignee: {t['assignee']}" if t['assignee'] else ""
            deadline_str = f", Due: {t['deadline']}" if t['deadline'] else ""
            md_lines.append(f"- **{t['task_name']}** {status_badge} {prio_badge}{assignee_str}{deadline_str}")
            if t["blockers"]:
                for b in t["blockers"]:
                    sev = f" (severity: {b.get('severity')})" if b.get('severity') else ""
                    md_lines.append(f"  - ⚠️ Blocked by Issue: \"{b['name']}\"{sev}")

    return {
        "tasks": tasks,
        "count": len(tasks),
        "formatted_context": "\n".join(md_lines),
    }
