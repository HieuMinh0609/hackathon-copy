"""Phân quyền cho các route tương thích cũ; không tin email do client tự khai báo."""
from __future__ import annotations

import hashlib
from typing import Any

from fastapi import HTTPException, Request

from backend.core.context import AppContext


def authenticated_user(request: Request, ctx: AppContext) -> Any:
    """Xác thực session key trực tiếp vì legacy app không dùng middleware của backend/app.py."""
    session_key = (request.headers.get("X-Session-Key") or "").strip().lower()
    if not session_key:
        raise HTTPException(status_code=401, detail="Thiếu X-Session-Key. Vui lòng đăng nhập.")
    for user in ctx.users.list_users():
        expected = hashlib.md5(user.email.strip().lower().encode("utf-8")).hexdigest()
        if session_key == expected:
            return user
    raise HTTPException(status_code=401, detail="Session key không hợp lệ.")


def require_template_manager(
    request: Request,
    ctx: AppContext,
    project_code: str | None = None,
    action: str = "quản lý template",
) -> Any:
    """Cho phép Team Leader hoặc Project Leader của đúng dự án."""
    user = authenticated_user(request, ctx)
    if getattr(user, "is_team_lead", False) or getattr(user, "is_project_lead", False):
        return user
    if ctx.projects.is_user_project_lead(user.email, project_code=project_code):
        return user
    raise HTTPException(
        status_code=403,
        detail=f"Chỉ TEAM_LEADER hoặc PROJECT_LEADER mới có quyền {action}.",
    )


def require_installer_uploader(request: Request, ctx: AppContext) -> Any:
    """Cho phép Team Lead hoặc Project Lead của ít nhất một dự án upload bộ cài."""
    user = authenticated_user(request, ctx)
    if getattr(user, "is_team_lead", False) or getattr(user, "is_project_lead", False):
        return user
    if ctx.projects.is_user_project_lead_any_project(user.email):
        return user
    raise HTTPException(
        status_code=403,
        detail="Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền tải bộ cài lên máy chủ.",
    )
