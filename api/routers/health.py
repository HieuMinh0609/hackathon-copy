"""Router kiểm tra trạng thái sức khỏe hệ thống Backend (Health Check)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_app_context
from api.schemas import HealthResponse
from backend.core.context import AppContext
from backend.core.llm import is_ollama_running
from backend.services.db import check_connection

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
def health_check(ctx: AppContext = Depends(get_app_context)) -> HealthResponse:
    db_ok, db_msg = check_connection(ctx.settings.database_url)
    ollama_ok = is_ollama_running(ctx.settings)

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        app_name=ctx.settings.app_name,
        database=db_msg,
        database_ok=db_ok,
        ollama_ok=ollama_ok,
    )
