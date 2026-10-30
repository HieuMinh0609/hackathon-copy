"""Dependencies container cho FastAPI REST API."""
from __future__ import annotations

from functools import lru_cache

from config.settings import Settings, get_settings
from backend.core.context import AppContext, build_context

_app_context: AppContext | None = None


def get_app_context() -> AppContext:
    global _app_context
    if _app_context is None:
        settings = get_settings()
        _app_context = build_context(settings)
    return _app_context


def set_app_context(ctx: AppContext) -> None:
    """Cho phép ghi đè context trong unit test."""
    global _app_context
    _app_context = ctx
