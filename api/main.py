"""FastAPI application entrypoint cho AI Buddy Backend."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import get_app_context
from api.routers import agent, apps, checklist, health, knowledge, templates, verification


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Khởi tạo DB schema và seed mặc định khi Backend khởi động
    ctx = get_app_context()
    ctx.settings.ensure_dirs()
    yield


app = FastAPI(
    title="AI Buddy REST API",
    description="Backend API phục vụ ứng dụng AI Buddy Onboarding (Chat AI, RAG, Checklist, Templates, App Catalog).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware cho phép mọi Frontend gọi tới
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router với tiền tố /api và /api/v1 để đồng bộ với backend/app.py và client
for prefix in ("/api", "/api/v1"):
    app.include_router(health.router, prefix=prefix)
    app.include_router(templates.router, prefix=prefix)
    app.include_router(checklist.router, prefix=prefix)
    app.include_router(verification.router, prefix=prefix)
    app.include_router(agent.router, prefix=prefix)
    app.include_router(knowledge.router, prefix=prefix)
    app.include_router(apps.router, prefix=prefix)


@app.get("/", tags=["Root"])
def root() -> dict[str, str]:
    return {
        "app": "AI Buddy Backend API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }
