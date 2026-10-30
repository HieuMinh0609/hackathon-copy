"""Router quan ly RAG Knowledge Base qua JSON API.

Bao gom endpoint SSE de stream tien trinh nap ChromaDB tung file theo thoi gian thuc.

Event protocol:
  data: {"type": "start",    "total": 10}
  data: {"type": "progress", "i": 1, "n": 10, "file": "guide.pdf", "percent": 10}
  data: {"type": "done",     "files": 10, "chunks": 142, "errors": [], "summary": "..."}
  data: {"type": "error",    "message": "..."}
"""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from api.dependencies import get_app_context
from api.schemas import (
    DocumentDto,
    IngestPathsRequest,
    IngestReportDto,
    SearchKnowledgeRequest,
    SearchResultItemDto,
)
from backend.core.context import AppContext

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get("/projects", response_model=list[str])
def list_knowledge_projects(ctx: AppContext = Depends(get_app_context)) -> list[str]:
    """Danh sach cac ma du an co tai lieu trong vector store."""
    return ctx.knowledge.list_projects()


@router.get("/documents", response_model=list[DocumentDto])
def get_project_documents(
    project_code: str = Query(..., description="Ma du an can lay tai lieu"),
    ctx: AppContext = Depends(get_app_context),
) -> list[DocumentDto]:
    """Lay danh sach cac chunk tai lieu da nap cua du an."""
    docs = ctx.knowledge.get_project_docs(project_code)
    return [
        DocumentDto(
            id=d.metadata.get("id"),
            content=d.page_content,
            metadata=d.metadata,
        )
        for d in docs
    ]


@router.post("/search", response_model=list[SearchResultItemDto])
def search_knowledge(
    req: SearchKnowledgeRequest, ctx: AppContext = Depends(get_app_context)
) -> list[SearchResultItemDto]:
    """Tim kiem tuong dong ngu nghia trong co so tri thuc RAG."""
    results = ctx.knowledge.search_with_scores(req.query, k=req.k)
    return [
        SearchResultItemDto(
            content=doc.page_content,
            metadata=doc.metadata,
            score=round(score, 4),
        )
        for doc, score in results
    ]


@router.post("/ingest-paths", response_model=IngestReportDto)
def ingest_paths(
    req: IngestPathsRequest, ctx: AppContext = Depends(get_app_context)
) -> IngestReportDto:
    """Nap danh sach tep tai lieu cu the vao ChromaDB (dong bo, khong stream)."""
    path_objs = [Path(p) for p in req.paths]
    report = ctx.knowledge.ingest_paths(
        paths=path_objs,
        reset=req.reset,
        project_code=req.project_code,
    )
    return IngestReportDto(
        files=report.files,
        chunks=report.chunks,
        errors=report.errors,
        summary=report.summary(),
    )


@router.post("/ingest-all", response_model=IngestReportDto)
def ingest_all(
    reset: bool = False,
    project_code: str | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> IngestReportDto:
    """Nap toan bo tai lieu tu thu muc documents/ (dong bo, khong stream)."""
    report = ctx.knowledge.ingest_all(reset=reset, project_code=project_code)
    return IngestReportDto(
        files=report.files,
        chunks=report.chunks,
        errors=report.errors,
        summary=report.summary(),
    )


@router.post("/ingest-paths-stream")
def ingest_paths_stream(
    req: IngestPathsRequest,
    ctx: AppContext = Depends(get_app_context),
) -> EventSourceResponse:
    """SSE: Stream tien trinh nap danh sach file cu the vao ChromaDB."""
    path_objs = [Path(p) for p in req.paths]
    return EventSourceResponse(
        _ingest_paths_generator(ctx, path_objs, reset=req.reset, project_code=req.project_code)
    )


@router.get("/ingest-stream")
def ingest_stream_all(
    reset: bool = False,
    project_code: str | None = None,
    ctx: AppContext = Depends(get_app_context),
) -> EventSourceResponse:
    """SSE: Stream tien trinh nap toan bo thu muc documents/ vao ChromaDB."""
    return EventSourceResponse(
        _ingest_all_generator(ctx, reset=reset, project_code=project_code)
    )


def _run_in_thread_with_queue(fn: Any) -> "queue.Queue[dict[str, Any] | None]":
    """Chay fn(queue) trong daemon thread, tra Queue nhan event."""
    q: queue.Queue[dict[str, Any] | None] = queue.Queue()
    threading.Thread(target=fn, args=(q,), daemon=True).start()
    return q


def _ingest_paths_generator(
    ctx: AppContext,
    paths: list[Path],
    reset: bool = False,
    project_code: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Generator SSE: chay ingest_paths trong thread, yield event JSON."""

    def _worker(q: "queue.Queue[dict[str, Any] | None]") -> None:
        try:
            n = len(paths)
            q.put({"type": "start", "total": n})

            def progress(i: int, total: int, file_name: str) -> None:
                pct = round(i / total * 100) if total else 0
                q.put({"type": "progress", "i": i, "n": total, "file": file_name, "percent": pct})

            report = ctx.knowledge.ingest_paths(
                paths=paths,
                reset=reset,
                progress=progress,
                project_code=project_code,
            )
            q.put({
                "type": "done",
                "files": report.files,
                "chunks": report.chunks,
                "errors": report.errors,
                "summary": report.summary(),
            })
        except Exception as exc:
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    q = _run_in_thread_with_queue(_worker)

    async def _generate() -> AsyncGenerator[dict[str, Any], None]:
        while True:
            event = q.get()
            if event is None:
                break
            yield {"data": json.dumps(event, ensure_ascii=False)}

    return _generate()


def _ingest_all_generator(
    ctx: AppContext,
    reset: bool = False,
    project_code: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Generator SSE cho ingest toan bo thu muc documents/."""

    def _worker(q: "queue.Queue[dict[str, Any] | None]") -> None:
        try:
            def progress(i: int, total: int, file_name: str) -> None:
                pct = round(i / total * 100) if total else 0
                q.put({"type": "progress", "i": i, "n": total, "file": file_name, "percent": pct})

            report = ctx.knowledge.ingest_all(
                reset=reset,
                progress=progress,
                project_code=project_code,
            )
            q.put({
                "type": "done",
                "files": report.files,
                "chunks": report.chunks,
                "errors": report.errors,
                "summary": report.summary(),
            })
        except Exception as exc:
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    q = _run_in_thread_with_queue(_worker)

    async def _generate() -> AsyncGenerator[dict[str, Any], None]:
        while True:
            event = q.get()
            if event is None:
                break
            yield {"data": json.dumps(event, ensure_ascii=False)}

    return _generate()
