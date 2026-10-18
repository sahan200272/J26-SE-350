"""FastAPI Ingestion Service for Knowledge Graph.

IMPORTANT PRIVACY NOTE:
This service processes conversation payloads that may contain sensitive entity
and interaction data. To ensure privacy, this service MUST ALWAYS be bound to
localhost (127.0.0.1) and NEVER to 0.0.0.0 or public network interfaces.

Run command:
    uvicorn main:app --host 127.0.0.1 --port 8000
"""

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from graph_schema.adapters import triples_to_payload
from graph_schema.ingest import IngestResult, ingest_payload
from graph_schema.models import Payload
from graph_schema.schema import get_driver
from graphrag.baseline_keyword import compare_retrieval
from graphrag.context_builder import get_pending_items_context
from graphrag.models import RetrievalRequest, RetrievalResult
from graphrag.retriever import retrieve_subgraph

app = FastAPI(
    title="Knowledge Graph & GraphRAG API",
    description="Automated graph construction, entity ingestion, and multi-hop GraphRAG retrieval service bound strictly to 127.0.0.1.",
    version="1.1.0",
)


class TriplesRequest(BaseModel):
    source: str
    timestamp: Optional[str] = None
    triples: List[Any] = Field(default_factory=list)


@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Check service health and Neo4j connectivity."""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        driver.close()
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "degraded", "database": str(exc)}


@app.post("/ingest")
def ingest_endpoint(
    payload: Payload,
    dry_run: bool = Query(default=False, description="Run ingestion in rolled-back transaction"),
) -> Dict[str, Any]:
    """Ingest a validated graph Payload."""
    try:
        result: IngestResult = ingest_payload(payload, dry_run=dry_run)
        return result.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest/triples")
def ingest_triples_endpoint(
    req: TriplesRequest,
    dry_run: bool = Query(default=False, description="Run ingestion in rolled-back transaction"),
) -> Dict[str, Any]:
    """Convert triples to Payload and ingest."""
    try:
        payload = triples_to_payload(req.triples, source=req.source, timestamp=req.timestamp)
        result: IngestResult = ingest_payload(payload, dry_run=dry_run)
        return result.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/retrieve", response_model=RetrievalResult)
def retrieve_endpoint(request: RetrievalRequest) -> RetrievalResult:
    """Execute constrained multi-hop GraphRAG traversal with mathematical scoring."""
    try:
        return retrieve_subgraph(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/retrieve/compare")
def retrieve_compare_endpoint(request: RetrievalRequest) -> Dict[str, Any]:
    """Compare GraphRAG retrieval against flat keyword baseline to evaluate multi-hop gain."""
    try:
        return compare_retrieval(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/retrieve/pending")
def retrieve_pending_endpoint(
    include_private: bool = Query(default=False, description="Include private task/issue items"),
) -> Dict[str, Any]:
    """Retrieve actionable pending tasks, blockers, deadlines, and assignees for Component 4."""
    try:
        return get_pending_items_context(include_private=include_private)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    # Enforce localhost binding for privacy: NEVER bind to 0.0.0.0
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
