"""FastAPI application exposing Member 2 to the React dashboard.

Design rules
------------
* The API is a thin layer. All logic lives in the existing modules
  (knowledge base, retrieval service, agents, benchmark), so the dashboard,
  the CLI scripts and Member 1's Orchestrator all behave identically.
* Reading is open to whoever can reach the server. By default that is only
  this computer (host 127.0.0.1).
* Every change (import or delete passages, add or delete benchmark questions)
  needs the admin token in the `X-Admin-Token` header. If `M2_ADMIN_TOKEN` is
  not set, editing is switched off completely.
* Error responses never echo submitted values (questions, sponsor data):
  validation errors list field names and messages only.
* Heavy model calls run one at a time (a lock) so two browser tabs cannot
  load two copies of a 1.3 GB model at once.
"""

from __future__ import annotations

import hmac
import json
import threading
from pathlib import Path, PureWindowsPath
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import S4ControlAgent
from app.config import Settings, get_settings
from app.evaluation.benchmark import BenchmarkItem
from app.evaluation.case_store import BenchmarkCaseStore, CaseExistsError, CaseNotFoundError
from app.integration import Member2Components, create_member2_components
from app.knowledge_base.coverage import build_coverage, load_expected_sources
from app.knowledge_base.indexing import InputFileError, index_text
from app.knowledge_base.metadata import MetadataCorruptionError
from app.logging_utils import get_logger, log_event
from app.retrieval.vector_search import InvalidQueryError, build_where
from app.schemas import AgentRequest, SearchFilters

logger = get_logger("api")
API_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    filters: SearchFilters | None = None
    candidate_k: int | None = Field(default=None, ge=1, le=200)
    final_k: int | None = Field(default=None, ge=1, le=50)
    use_reranker: bool | None = None


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(default="upload.jsonl", max_length=200)
    content: str = Field(min_length=1)
    strict: bool = False
    dry_run: bool = False


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app(
    components: Member2Components | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or (components.settings if components else get_settings())
    m2 = components or create_member2_components(settings)
    cases = BenchmarkCaseStore(settings.benchmark_file)
    model_lock = threading.Lock()

    app = FastAPI(
        title="Agentic QA-RAG · Retrieval & Knowledge Base API",
        version=API_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-Admin-Token"],
        )

    # -- errors -----------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default response echoes the submitted input; strip it.
        detail = [
            {"loc": [str(x) for x in err.get("loc", ())], "msg": err.get("msg", "invalid value")}
            for err in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(InvalidQueryError)
    async def _invalid_query(_: Request, exc: InvalidQueryError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(MetadataCorruptionError)
    async def _corrupt(_: Request, exc: MetadataCorruptionError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    # -- auth -------------------------------------------------------------
    def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
        if not settings.admin_token:
            raise HTTPException(
                status_code=403,
                detail="Editing is switched off. Set M2_ADMIN_TOKEN in member2-rag/.env and restart the server.",
            )
        if not x_admin_token or not hmac.compare_digest(x_admin_token, settings.admin_token):
            raise HTTPException(status_code=401, detail="Editor token is missing or wrong.")

    def run_model(fn, *args, **kwargs):
        """Run a model-backed call with one-at-a-time locking and clear errors."""
        with model_lock:
            try:
                return fn(*args, **kwargs)
            except (InvalidQueryError, InputFileError, HTTPException):
                raise
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            except (OSError, ImportError) as exc:
                log_event(logger, 40, "model_unavailable", error_type=type(exc).__name__)
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "The embedding or reranker model could not be loaded. The first run needs "
                        "internet access to download it from Hugging Face; check the server log."
                    ),
                ) from None

    # -- status -----------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "api_version": API_VERSION,
            "knowledge_base_size": m2.retrieval.store.count(),
            "collection": settings.collection_name,
            "embedding_model": settings.embedding_model,
            "reranker_model": settings.reranker_model if m2.retrieval.reranker else None,
            "candidate_k": settings.candidate_k,
            "final_k": settings.final_k,
            "editing_enabled": bool(settings.admin_token),
            "benchmark_file": settings.benchmark_file.name,
        }

    # -- passages ---------------------------------------------------------
    @app.get("/api/passages")
    def list_passages(
        ctd_section: str | None = Query(default=None, max_length=40),
        organization: str | None = Query(default=None, max_length=100),
        document_type: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=25, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        try:
            filters = SearchFilters(
                ctd_sections=[ctd_section] if ctd_section else [],
                include_parent_sections=False,
                issuing_organizations=[organization] if organization else [],
                document_types=[document_type] if document_type else [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc).splitlines()[0]) from None
        total, page = m2.retrieval.store.list_passages(build_where(filters), limit, offset)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "chunk_id": p.chunk_id,
                    "text": p.text,
                    "metadata": p.metadata.model_dump(mode="json"),
                    "provenance_complete": p.metadata.provenance_complete,
                    "missing_provenance": p.metadata.missing_provenance(),
                }
                for p in page
            ],
        }

    @app.get("/api/passages/facets")
    def passage_facets() -> dict[str, dict[str, int]]:
        return m2.retrieval.store.facets()

    @app.get("/api/coverage")
    def coverage() -> dict[str, Any]:
        report = build_coverage(m2.retrieval.store.all_metadata(), load_expected_sources(settings.sources_manifest))
        report["collection"] = settings.collection_name
        report["manifest"] = settings.sources_manifest.name
        return report

    @app.post("/api/passages/import", dependencies=[Depends(require_admin)])
    def import_passages(body: ImportRequest) -> dict[str, Any]:
        if len(body.content.encode("utf-8")) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB.")
        if not body.filename.lower().endswith((".jsonl", ".ndjson")):
            raise HTTPException(status_code=422, detail="Upload a .jsonl file (one passage per line).")
        try:
            report = run_model(
                index_text, body.content, m2.retrieval.store, m2.retrieval.embedder,
                source_name=Path(body.filename).name, strict=body.strict, dry_run=body.dry_run,
            )
        except InputFileError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        out = report.as_dict()
        out["dry_run"] = body.dry_run
        return out

    @app.delete("/api/passages/{chunk_id}", dependencies=[Depends(require_admin)])
    def delete_passage(chunk_id: str) -> dict[str, Any]:
        if not m2.retrieval.store.get([chunk_id]):
            raise HTTPException(status_code=404, detail="No passage with that chunk_id.")
        m2.retrieval.store.delete([chunk_id])
        log_event(logger, 20, "passage_deleted", chunk_id=chunk_id)
        return {"deleted": chunk_id, "knowledge_base_size": m2.retrieval.store.count()}

    # -- retrieval and agents ---------------------------------------------
    @app.post("/api/search")
    def search(body: SearchRequest) -> dict[str, Any]:
        result = run_model(
            m2.retrieval.retrieve, body.query, filters=body.filters, candidate_k=body.candidate_k,
            final_k=body.final_k, use_reranker=body.use_reranker,
        )
        return result.model_dump(mode="json")

    def _run_agent(name: str, request: AgentRequest) -> list[dict[str, Any]]:
        findings = run_model(m2.agents[name].run, request)
        # Returned in full: the caller supplied any sponsor data in this request
        # and the dashboard needs the comparison rows. Nothing is logged or stored.
        return [f.model_dump(mode="json") for f in findings]

    @app.post("/api/agents/evidence-rera")
    def evidence_rera(request: AgentRequest) -> list[dict[str, Any]]:
        return _run_agent(EvidenceReraAgent.name, request)

    @app.post("/api/agents/s4-control")
    def s4_control(request: AgentRequest) -> list[dict[str, Any]]:
        return _run_agent(S4ControlAgent.name, request)

    # -- benchmark --------------------------------------------------------
    @app.get("/api/benchmark/cases")
    def list_cases() -> list[dict[str, Any]]:
        try:
            return [c.model_dump(mode="json") for c in cases.list()]
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"Benchmark file is invalid: {exc}") from None

    @app.post("/api/benchmark/cases", dependencies=[Depends(require_admin)], status_code=201)
    def add_case(item: BenchmarkItem) -> dict[str, Any]:
        try:
            return cases.add(item).model_dump(mode="json")
        except CaseExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.delete("/api/benchmark/cases/{question_id}", dependencies=[Depends(require_admin)])
    def delete_case(question_id: str) -> dict[str, str]:
        try:
            cases.delete(question_id)
        except CaseNotFoundError:
            raise HTTPException(status_code=404, detail="No benchmark question with that id.") from None
        return {"deleted": question_id}

    @app.get("/api/benchmark/results")
    def benchmark_results(limit: int = Query(default=5, ge=1, le=50)) -> list[dict[str, Any]]:
        files = sorted(settings.results_dir.glob("retrieval_benchmark_*.json"), reverse=True)[:limit]
        out = []
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out.append({
                "file": path.name,
                # File name only (never a local path); PureWindowsPath splits on both / and \.
                "benchmark_file": PureWindowsPath(data.get("benchmark_file") or "").name or None,
                "created_at": data.get("created_at"),
                "num_questions": data.get("num_questions"),
                "benchmark_sha256": data.get("benchmark_sha256"),
                "runs": [
                    {
                        "name": r.get("config", {}).get("name"),
                        "config": r.get("config", {}),
                        "knowledge_base_size": r.get("knowledge_base_size"),
                        "queries_evaluated": r.get("queries_evaluated"),
                        "aggregate": r.get("aggregate", {}),
                        "latency": r.get("latency", {}),
                        "ragas": r.get("ragas"),
                        "checks": r.get("checks", {}),
                    }
                    for r in data.get("runs", [])
                ],
            })
        return out

    # -- built dashboard (optional) ----------------------------------------
    dist = Path(settings.web_dist)
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")

    return app
