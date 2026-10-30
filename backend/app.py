"""FastAPI chạy cục bộ và là ranh giới duy nhất tới nghiệp vụ backend."""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from datetime import datetime
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from config.settings import get_settings
from backend.services.db import check_connection, describe
from backend.services.job_service import JobService

if TYPE_CHECKING:
    from backend.core.context import AppContext
    from backend.core.utils.system_utils import InstallPlan


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    project_code: str | None = None
    checklist_mode: bool = False
    request_id: str | None = Field(default=None, min_length=8, max_length=100)


class CancelChatRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    project_code: str | None = None


class SaveChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    project_code: str | None = "general"
    sender: str = "ai"
    sources: list[str] | None = None
    metadata: dict[str, Any] | None = None


class KeyRequest(BaseModel):
    key: str


class ManualRequest(KeyRequest):
    done: bool
    user_id: int | None = None
    user_email: str | None = None
    project_code: str | None = None


class ImportChecklistRequest(BaseModel):
    content: str = Field(min_length=1, description="Nội dung CSV hoặc JSON của checklist")
    project_code: str | None = None
    user_email: str | None = None


class ExecuteInstallRequest(BaseModel):
    confirmation_token: str
    key: str | None = None


class SettingsUpdate(BaseModel):
    ollama_base_url: str
    llm_model: str
    embedding_model: str
    user_role: str


class IngestRequest(BaseModel):
    paths: list[str]
    project_code: str | None = None
    reset: bool = False


class FileCopyRequest(BaseModel):
    source_paths: list[str]


class FileDeleteRequest(BaseModel):
    path: str


class FileExportRequest(BaseModel):
    source_path: str
    destination_path: str


class UpdateAppPathPayload(BaseModel):
    installer_path: str


class UpdateAppPayload(BaseModel):
    app_name: str | None = None
    category: str | None = None
    recommended_version: str | None = None
    installer_path: str | None = None
    check_command: str | None = None
    version_args: str | None = None
    install_args: str | None = None
    description: str | None = None
    is_required: bool | None = None


class CreateProjectPayload(BaseModel):
    code: str
    name: str
    description: str = ""
    role_name: str = "Developer"
    duration_days: int = Field(default=20, ge=1, le=3650)


class AddProjectMemberPayload(BaseModel):
    user_email: str = ""
    user_name: str = ""
    project_role_key: str = "MEMBER"
    department: str = ""
    user_emails: list[str] = []
    members: list[dict[str, Any]] = []


class AddProjectMembersBatchPayload(BaseModel):
    members: list[dict[str, Any]] = []
    user_emails: list[str] = []
    project_role_key: str = "MEMBER"


class CreateAppPayload(BaseModel):
    app_code: str
    app_name: str
    category: str = "Công cụ chung"
    recommended_version: str = ""
    installer_path: str = ""
    check_command: str = ""
    version_args: str = "--version"
    install_args: str = ""
    description: str = ""
    is_required: bool = True


class UploadInstallerPayload(BaseModel):
    source_path: str | None = None
    filename: str | None = None
    version: str | None = None


class ExportInstallerPayload(BaseModel):
    destination_dir: str
    version: str | None = None


class Envelope(BaseModel):
    success: bool = True
    data: Any = None
    error: str | None = None


import logging

logger = logging.getLogger("backend.api")

app = FastAPI(title="AI Buddy Backend", version="1.0.0", docs_url="/api/docs")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    if not request.url.path.endswith("/health/live"):
        logger.info("[BE] %s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


_plans: dict[str, tuple[InstallPlan, str | None, str, float]] = {}
_plans_lock = threading.Lock()
_cancelled_chat_requests: dict[tuple[str, str], float] = {}
_cancelled_chat_lock = threading.Lock()
# Chỉ chạy một ingest job tại một thời điểm để tránh cạnh tranh VRAM/ghi ChromaDB.
_jobs = JobService(max_workers=1)

# Cache tra cứu nhanh session key (MD5 email) -> user email
_session_cache: dict[str, str] = {}

PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/docs",
    "/openapi.json",
    "/favicon.ico",
}


@lru_cache(maxsize=1)
def _context() -> AppContext:
    from backend.core.context import build_context
    return build_context()


def _ctx() -> AppContext:
    try:
        return _context()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Backend chưa sẵn sàng: {exc}") from exc


def _get_user_by_session_key(session_key: str) -> Any | None:
    """Tra cứu người dùng theo session key (mã hóa MD5 của email)."""
    clean_key = session_key.strip().lower()
    if not clean_key:
        return None
    try:
        ctx = _ctx()
    except Exception:
        return None
    if not hasattr(ctx, "users"):
        return None

    cached_email = _session_cache.get(clean_key)
    if cached_email:
        user = ctx.users.get_by_email(cached_email)
        if user:
            return user

    for u in ctx.users.list_users():
        u_key = hashlib.md5(u.email.strip().lower().encode("utf-8")).hexdigest()
        if u_key == clean_key:
            _session_cache[clean_key] = u.email.strip().lower()
            return u
    return None


@app.middleware("http")
async def verify_session_key_middleware(request: Request, call_next):
    """Mọi API ngoại trừ login và health/docs bắt buộc phải xác thực bằng X-Session-Key (MD5 email)."""
    if request.method == "OPTIONS":
        return await call_next(request)

    clean_path = request.url.path.rstrip("/")
    if (
        clean_path in PUBLIC_PATHS
        or clean_path.startswith("/api/docs")
        or clean_path.startswith("/openapi")
        or (clean_path.startswith("/api/v1/apps/") and clean_path.endswith("/download"))
    ):
        return await call_next(request)

    session_key = (
        request.headers.get("x-session-key")
        or request.headers.get("X-Session-Key")
        or ""
    ).strip()

    if not session_key:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "Yêu cầu xác thực: Thiếu header 'X-Session-Key'. Vui lòng đăng nhập để nhận session key.",
                "data": None,
            },
        )

    user = _get_user_by_session_key(session_key)
    if not user:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "Xác thực thất bại: Session key không hợp lệ hoặc không tồn tại trong hệ thống. Vui lòng đăng nhập lại.",
                "data": None,
            },
        )

    request.state.current_user = user
    request.state.user_email = user.email
    return await call_next(request)


def _ok(data: Any = None) -> Envelope:
    return Envelope(data=data)


def _mark_chat_cancelled(owner: str, request_id: str) -> bool:
    """Ghi nhận hủy theo đúng user/request và tự dọn dấu vết cũ sau 10 phút."""
    key = (owner.strip().lower(), request_id.strip())
    with _cancelled_chat_lock:
        now = time.monotonic()
        for expired_key, expires_at in list(_cancelled_chat_requests.items()):
            if expires_at <= now:
                _cancelled_chat_requests.pop(expired_key, None)
        is_new = key not in _cancelled_chat_requests
        _cancelled_chat_requests[key] = now + 600
        return is_new


def _consume_chat_cancelled(owner: str, request_id: str | None) -> bool:
    if not request_id:
        return False
    key = (owner.strip().lower(), request_id.strip())
    with _cancelled_chat_lock:
        return _cancelled_chat_requests.pop(key, None) is not None


def _store_plan(plan: InstallPlan, key: str | None, owner: str) -> dict[str, Any]:
    token = secrets.token_urlsafe(24)
    with _plans_lock:
        now = time.monotonic()
        for expired in [token for token, saved in _plans.items() if saved[3] <= now]:
            _plans.pop(expired, None)
        _plans[token] = (plan, key, owner, now + 600)
    return {
        "software": plan.software,
        "manager": plan.manager,
        "command": plan.command,
        "description": plan.description,
        "display": plan.display,
        "confirmation_token": token,
    }


def _reply_data(reply: Any, owner: str, created_at: str | None = None) -> dict[str, Any]:
    return {
        "text": reply.text,
        "sources": list(reply.sources),
        "pending_install": _store_plan(reply.pending_install, reply.pending_key, owner) if reply.pending_install else None,
        "pending_key": reply.pending_key,
        "agent": reply.agent,
        "install_ok": getattr(reply, "install_ok", None),
        "created_at": created_at or datetime.now().isoformat(),
    }


def _item_data(item: Any) -> dict[str, Any]:
    return asdict(item)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _require_team_or_project_lead(
    user_email: str | None = None,
    action: str = "tải lên và nạp tài liệu vào ChromaDB",
    session_key: str | None = None,
    project_code: str | None = None,
    allow_any_project_lead: bool = False,
) -> None:
    """Kiểm tra hierarchy TEAM_LEAD > PROJECT_LEAD > MEMBER.

    Team Lead có quyền toàn cục; Project Lead chỉ quản lý dự án được giao.
    """
    ctx = _ctx()
    # Nếu context có users service thì thực hiện kiểm tra phân quyền
    if hasattr(ctx, "users"):
        user = None
        # Session là danh tính đã xác thực; không cho X-User-Email ghi đè để tránh giả mạo leader.
        if session_key:
            user = _get_user_by_session_key(session_key)
        elif user_email:
            user = ctx.users.get_by_email(user_email)

        if not user:
            raise HTTPException(
                status_code=403,
                detail=f"Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền {action}. Vui lòng đăng nhập lại.",
            )

        # 1. TEAM_LEAD là cấp cao nhất và có quyền toàn cục.
        user_perm = (getattr(user, "permission", "") or getattr(user, "level", "") or "").strip().upper()
        if getattr(user, "is_team_lead", False) or user_perm == "TEAM_LEAD":
            return

        # 2. Kiểm tra Project Lead theo assignment của dự án.
        is_leader = False
        if hasattr(ctx, "projects"):
            if allow_any_project_lead and not project_code:
                is_leader = ctx.projects.is_user_project_lead_any_project(user.email)
            else:
                is_leader = ctx.projects.is_user_project_lead(user.email, project_code=project_code)
        if not is_leader and not project_code and getattr(user, "is_project_lead", False):
            is_leader = True

        if not is_leader:
            proj_hint = f" của dự án {project_code}" if project_code else ""
            raise HTTPException(
                status_code=403,
                detail=f"Chỉ TEAM_LEAD hoặc PROJECT_LEAD{proj_hint} mới có quyền {action}. (Quyền hiện tại: MEMBER)",
            )


_require_senior_user = _require_team_or_project_lead


def _require_team_lead(
    user_email: str | None = None,
    action: str = "thực hiện thao tác này",
    session_key: str | None = None,
) -> None:
    """Các cấu hình toàn hệ thống chỉ dành cho cấp cao nhất TEAM_LEAD."""
    ctx = _ctx()
    if hasattr(ctx, "users"):
        user = None
        if session_key:
            user = _get_user_by_session_key(session_key)
        elif user_email:
            user = ctx.users.get_by_email(user_email)

        if not user:
            raise HTTPException(
                status_code=403,
                detail=f"Chỉ TEAM_LEAD mới có quyền {action}. Vui lòng đăng nhập tài khoản TEAM_LEAD.",
            )
        user_perm = (getattr(user, "permission", "") or getattr(user, "level", "") or "").strip().upper()
        if not getattr(user, "is_team_lead", False) and user_perm != "TEAM_LEAD":
            raise HTTPException(
                status_code=403,
                detail=f"Chỉ TEAM_LEAD mới có quyền {action}. (Quyền hiện tại: {getattr(user, 'permission', 'MEMBER')})",
            )


def _protect_team_lead_target(target_email: str, actor: Any, action: str) -> None:
    """TEAM_LEAD là admin toàn cục; Project Lead không được thêm/xóa admin khỏi dự án."""
    target = _ctx().users.get_by_email(target_email)
    if not target or not getattr(target, "is_team_lead", False):
        return
    if actor is None or not getattr(actor, "is_team_lead", False):
        raise HTTPException(
            status_code=403,
            detail=f"Chỉ TEAM_LEAD mới được {action} một tài khoản TEAM_LEAD.",
        )


@app.post("/api/v1/auth/login", response_model=Envelope)
def login(payload: LoginRequest) -> Envelope:
    """Xác thực tài khoản người dùng bằng email và mật khẩu (MD5) từ bảng users.
    Trả về thông tin user kèm session_key là mã hóa MD5 của email.
    """
    email = payload.email.strip().lower()
    user = _ctx().users.get_by_email(email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"Email '{email}' không tồn tại trong hệ thống. Vui lòng kiểm tra lại!",
        )
    if payload.password is not None and payload.password != "":
        auth_user = _ctx().users.authenticate(email, payload.password)
        if not auth_user:
            raise HTTPException(
                status_code=401,
                detail="Mật khẩu không chính xác! (Mật khẩu mặc định là 1234)",
            )
        user = auth_user

    session_key = hashlib.md5(user.email.strip().lower().encode("utf-8")).hexdigest()
    _session_cache[session_key] = user.email.strip().lower()

    user_data = user.to_dict()
    user_data["session_key"] = session_key
    return _ok(user_data)


@app.get("/api/v1/auth/users", response_model=Envelope)
def list_users() -> Envelope:
    """Lấy danh sách tài khoản demo trong hệ thống."""
    users = _ctx().users.list_users()
    return _ok([u.to_dict() for u in users])


@app.get("/api/v1/health", response_model=Envelope)
def health() -> Envelope:
    settings = get_settings()
    db_ok, db_message = check_connection(settings.database_url)
    return _ok({"status": "ok" if db_ok else "degraded", "database": {"ok": db_ok, "message": db_message}})


@app.get("/api/v1/health/live", response_model=Envelope)
def liveness() -> Envelope:
    """Probe nhẹ, không phụ thuộc PostgreSQL/Ollama."""
    return _ok({"status": "ok"})


@app.post("/api/v1/chat", response_model=Envelope)
def chat(payload: ChatRequest, request: Request) -> Envelope:
    ctx = _ctx()
    user_email = getattr(request.state, "user_email", None)
    project_code = payload.project_code or "general"

    # Lưu tin nhắn của người dùng
    if hasattr(ctx, "chat_history") and user_email:
        try:
            ctx.chat_history.save_message(
                user_email=user_email,
                project_code=project_code,
                sender="user",
                message=payload.message,
                metadata={
                    "checklist_mode": payload.checklist_mode,
                    "request_id": payload.request_id,
                },
            )
        except Exception:
            pass

    reply = ctx.agent.chat(
        payload.message,
        project_code=payload.project_code,
        checklist_mode=payload.checklist_mode,
    )

    # LLM có thể đã hoàn tất sau khi client bấm hủy; không lưu hoặc phát hành response cũ.
    if _consume_chat_cancelled(user_email or "", payload.request_id):
        return _ok({
            "text": "Yêu cầu đã được hủy.",
            "sources": [],
            "pending_install": None,
            "pending_key": None,
            "agent": "cancelled",
            "install_ok": None,
            "created_at": datetime.now().isoformat(),
            "cancelled": True,
        })

    # Lưu câu trả lời của trợ lý AI kèm nguồn tài liệu
    reply_created_at: str | None = None
    if hasattr(ctx, "chat_history") and user_email:
        try:
            saved_ai = ctx.chat_history.save_message(
                user_email=user_email,
                project_code=project_code,
                sender="ai",
                message=reply.text,
                sources=list(reply.sources),
                metadata={
                    "agent": reply.agent,
                    "install_ok": getattr(reply, "install_ok", None),
                    "request_id": payload.request_id,
                },
            )
            if saved_ai and isinstance(saved_ai, dict):
                reply_created_at = saved_ai.get("created_at")
        except Exception:
            pass

    return _ok(_reply_data(reply, user_email or "", created_at=reply_created_at))


@app.post("/api/v1/chat/cancel", response_model=Envelope)
def cancel_chat(payload: CancelChatRequest, request: Request) -> Envelope:
    """Đánh dấu response đang xử lý là đã hủy để không ghi kết quả muộn vào lịch sử."""
    user_email = str(getattr(request.state, "user_email", "") or "").strip().lower()
    if not user_email:
        raise HTTPException(status_code=401, detail="Thiếu thông tin người dùng xác thực")
    is_new = _mark_chat_cancelled(user_email, payload.request_id)
    if is_new and hasattr(_ctx(), "chat_history"):
        _ctx().chat_history.save_message(
            user_email=user_email,
            project_code=payload.project_code or "general",
            sender="ai",
            message="Đã hủy yêu cầu đang xử lý.",
            metadata={"type": "chat_cancelled", "request_id": payload.request_id},
        )
    return _ok({"cancelled": True, "request_id": payload.request_id})


@app.get("/api/v1/chat/history", response_model=Envelope)
def get_chat_history(
    request: Request,
    project_code: str = "general",
    limit: int = 50,
) -> Envelope:
    """Lấy danh sách tin nhắn hội thoại gần nhất (tối đa 50 tin) theo người dùng và dự án."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        return _ok([])
    ctx = _ctx()
    if not hasattr(ctx, "chat_history"):
        return _ok([])
    messages = ctx.chat_history.get_recent_messages(
        user_email=user_email,
        project_code=project_code,
        limit=limit,
    )
    return _ok(messages)


@app.post("/api/v1/chat/history", response_model=Envelope)
def save_chat_message(
    payload: SaveChatMessageRequest,
    request: Request,
) -> Envelope:
    """Lưu một tin nhắn hoặc log kết quả thực thi terminal vào lịch sử hội thoại."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Thiếu thông tin người dùng xác thực")
    ctx = _ctx()
    if not hasattr(ctx, "chat_history"):
        return _ok({})
    saved = ctx.chat_history.save_message(
        user_email=user_email,
        project_code=payload.project_code or "general",
        sender=payload.sender,
        message=payload.message,
        sources=payload.sources,
        metadata=payload.metadata,
    )
    return _ok(saved)


@app.delete("/api/v1/chat/history", response_model=Envelope)
def clear_chat_history(
    request: Request,
    project_code: str = "general",
) -> Envelope:
    """Xóa lịch sử hội thoại của người dùng trong một dự án để bắt đầu phiên mới."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        return _ok({"cleared": 0})
    ctx = _ctx()
    if not hasattr(ctx, "chat_history"):
        return _ok({"cleared": 0})
    count = ctx.chat_history.clear_history(
        user_email=user_email,
        project_code=project_code,
    )
    return _ok({"cleared": count})


@app.get("/api/v1/projects", response_model=Envelope)
def projects(
    request: Request,
    user_email: str | None = None,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
) -> Envelope:
    del x_user_email, user_email
    target_email = getattr(request.state, "user_email", None)
    current_user = getattr(request.state, "current_user", None)
    is_admin = False
    if current_user:
        is_admin = getattr(current_user, "is_team_lead", False) or (getattr(current_user, "level", "") or "").upper() == "TEAM_LEAD"
    return _ok(_ctx().projects.list_projects(user_email=target_email, is_admin=is_admin))


@app.post("/api/v1/projects", response_model=Envelope)
def create_project(
    payload: CreateProjectPayload,
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Tạo dự án mới trong hệ thống."""
    _require_team_lead(
        x_user_email,
        action="tạo dự án",
        session_key=x_session_key,
    )
    try:
        new_prj = _ctx().projects.create_project(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            role_name=payload.role_name,
            creator_email=getattr(request.state, "user_email", ""),
            duration_days=payload.duration_days,
        )
        return _ok(new_prj)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/projects/{code}/members", response_model=Envelope)
def list_project_members(
    code: str,
    request: Request,
    q: str | None = None,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Lấy danh sách thành viên; member của dự án chỉ nhận dữ liệu chỉ đọc."""
    current_user = getattr(request.state, "current_user", None)
    if current_user is None or not _ctx().projects.is_user_project_member(current_user.email, code):
        if not getattr(current_user, "is_team_lead", False):
            raise HTTPException(status_code=403, detail="Bạn không thuộc dự án này.")
    members = _ctx().projects.list_project_members(code, search=q)
    can_manage = bool(
        getattr(current_user, "is_team_lead", False)
        or _ctx().projects.is_user_project_lead(current_user.email, project_code=code)
    )
    if not can_manage:
        visible_keys = {
            "project_code", "user_email", "user_name", "role_id", "role_name", "job_title",
            "role_in_project", "department", "permission", "user_level", "project_role_key",
            "status", "progress", "started_at", "due_at", "days_remaining", "deadline_status",
            "risk_status", "risk_reason", "expected_progress", "duration_days",
        }
        members = [{key: value for key, value in member.items() if key in visible_keys} for member in members]
    return _ok(members)


@app.post("/api/v1/projects/{code}/members", response_model=Envelope)
def add_project_member(
    code: str,
    payload: AddProjectMemberPayload,
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Thêm thành viên vào dự án."""
    _require_team_or_project_lead(x_user_email, action="thêm thành viên vào dự án", session_key=x_session_key, project_code=code)
    _protect_team_lead_target(
        payload.user_email,
        getattr(request.state, "current_user", None),
        "thêm vào dự án",
    )
    try:
        member = _ctx().projects.add_project_member(
            project_code=code,
            user_email=payload.user_email,
            project_role_key=payload.project_role_key,
            added_by=getattr(request.state, "user_email", ""),
            user_name=payload.user_name,
            department=payload.department,
        )
        return _ok(member)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/projects/{code}/members/batch", response_model=Envelope)
def add_project_members_batch(
    code: str,
    payload: AddProjectMembersBatchPayload,
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Thêm hàng loạt thành viên vào dự án (Multi-select)."""
    _require_team_or_project_lead(x_user_email, action="thêm thành viên vào dự án", session_key=x_session_key, project_code=code)
    try:
        members_list = list(payload.members)
        if not members_list and payload.user_emails:
            for em in payload.user_emails:
                members_list.append({
                    "user_email": em,
                    "project_role_key": payload.project_role_key,
                })
        actor = getattr(request.state, "current_user", None)
        for item in members_list:
            target_email = str(item.get("user_email") or item.get("email") or "")
            _protect_team_lead_target(target_email, actor, "thêm vào dự án")
        added = _ctx().projects.add_project_members_batch(
            project_code=code,
            members=members_list,
            added_by=getattr(request.state, "user_email", ""),
        )
        return _ok(added)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/projects/{code}/members/{email}", response_model=Envelope)
def remove_project_member(
    code: str,
    email: str,
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Xóa thành viên khỏi dự án."""
    _require_team_or_project_lead(x_user_email, action="xóa thành viên khỏi dự án", session_key=x_session_key, project_code=code)
    _protect_team_lead_target(
        email,
        getattr(request.state, "current_user", None),
        "xóa khỏi dự án",
    )
    removed = _ctx().projects.remove_project_member(code, email)
    if not removed:
        raise HTTPException(status_code=404, detail="Không tìm thấy thành viên trong dự án.")
    return _ok({"removed": True})


@app.get("/api/v1/projects/{code}/document-folder", response_model=Envelope)
def project_document_folder(code: str) -> Envelope:
    return _ok({"path": str(_ctx().projects.get_doc_folder(code))})


@app.get("/api/v1/roles", response_model=Envelope)
def list_system_roles() -> Envelope:
    """Lấy danh sách các vai trò trong hệ thống từ bảng roles."""
    roles = _ctx().projects.list_roles()
    return _ok(roles)


@app.get("/api/v1/checklist", response_model=Envelope)
def checklist(
    request: Request,
    project_code: str | None = None,
    user_email: str | None = None,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
) -> Envelope:
    ctx = _ctx()
    del x_user_email, user_email
    target_email = getattr(request.state, "user_email", None)
    items = ctx.checklist.list_items(template_code=project_code, user_email=target_email)
    prog = ctx.checklist.progress(template_code=project_code, user_email=target_email)
    return _ok({"items": [_item_data(i) for i in items], "progress": prog})


@app.get("/api/v1/checklist/template-sample", response_model=Envelope)
def get_checklist_template_sample(
    project_code: str,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Tải template CSV mẫu; member chỉ được thực thi checklist, không được tải template."""
    _require_team_or_project_lead(
        x_user_email,
        action="tải template checklist",
        session_key=x_session_key,
        project_code=project_code,
    )
    csv_content = _ctx().checklist.get_sample_template_csv()
    return _ok({"filename": "checklist_template_sample.csv", "content": csv_content})


@app.post("/api/v1/checklist/import", response_model=Envelope)
def import_checklist(
    payload: ImportChecklistRequest,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Import checklist; chỉ TEAM_LEAD hoặc PROJECT_LEAD của dự án."""
    user_email = x_user_email or payload.user_email
    _require_team_or_project_lead(
        user_email,
        action="import checklist cho dự án",
        session_key=x_session_key,
        project_code=payload.project_code,
    )
    try:
        res = _ctx().checklist.import_tasks_from_csv(
            content=payload.content,
            project_code=payload.project_code,
        )
        return _ok(res)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/checklist/{key}", response_model=Envelope)
def checklist_item(key: str) -> Envelope:
    item = _ctx().checklist.get_item(key)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục checklist.")
    return _ok(_item_data(item))


@app.post("/api/v1/checklist/verify", response_model=Envelope)
def verify_all(
    request: Request,
    project_code: str | None = None,
    user_email: str | None = None,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
) -> Envelope:
    del x_user_email, user_email
    target_email = getattr(request.state, "user_email", None)
    results = _ctx().verification.verify_all(template_code=project_code, user_email=target_email)
    for result in results:
        _save_verification_for_current_user(request, result.key, result.status)
    return _ok([asdict(result) for result in results])


def _save_verification_for_current_user(request: Request, key: str, status: str) -> None:
    """Lưu kết quả verify vào checklist riêng để tiến độ dự án phản ánh đúng từng user."""
    normalized_status = status.strip().lower()
    if normalized_status not in {"passed", "failed", "warning"}:
        return
    current_user = getattr(request.state, "current_user", None)
    user_id = getattr(current_user, "user_id", None)
    if user_id is None:
        return
    _ctx().checklist.update_user_task_status(
        user_id=user_id,
        key=key,
        done=normalized_status == "passed",
        note=status,
        sync_template_status=False,
    )


@app.post("/api/v1/checklist/{key}/verify", response_model=Envelope)
def verify_one(key: str, request: Request) -> Envelope:
    try:
        result = _ctx().verification.verify_key(
            key,
            user_email=getattr(request.state, "user_email", None),
        )
        _save_verification_for_current_user(request, key, result.status)
        return _ok(asdict(result))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục checklist.") from exc


def _ensure_step_ready(key: str, user_email: str | None = None) -> None:
    try:
        blocker = (
            _ctx().checklist.step_blocker(key, user_email=user_email)
            if user_email
            else _ctx().checklist.step_blocker(key)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy bước checklist.") from exc
    if blocker:
        raise HTTPException(status_code=409, detail=blocker)


@app.put("/api/v1/checklist/{key}/manual", response_model=Envelope)
def manual(key: str, payload: ManualRequest, request: Request) -> Envelope:
    if key != payload.key:
        raise HTTPException(status_code=400, detail="Mã checklist không khớp.")
    _ensure_step_ready(payload.key, user_email=getattr(request.state, "user_email", None))
    ctx = _ctx()
    current_email = getattr(request.state, "user_email", None)
    current_user = ctx.users.get_by_email(current_email) if current_email and hasattr(ctx, "users") else None
    user_id = current_user.user_id if current_user else None

    if user_id:
        res = ctx.checklist.update_user_task_status(
            user_id=user_id,
            key=key,
            done=payload.done,
            template_code=payload.project_code,
        )
        return _ok(res)

    ctx.checklist.set_manual_done(key, payload.done)
    return _ok(_item_data(ctx.checklist.get_item(key)))


@app.post("/api/v1/checklist/user-task", response_model=Envelope)
def update_user_task(payload: ManualRequest, request: Request) -> Envelope:
    _ensure_step_ready(payload.key, user_email=getattr(request.state, "user_email", None))
    ctx = _ctx()
    current_email = getattr(request.state, "user_email", None)
    current_user = ctx.users.get_by_email(current_email) if current_email and hasattr(ctx, "users") else None
    user_id = current_user.user_id if current_user else None

    if not user_id:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp user_id hoặc user_email để cập nhật.")

    res = ctx.checklist.update_user_task_status(
        user_id=user_id,
        key=payload.key,
        done=payload.done,
        template_code=payload.project_code,
    )
    return _ok(res)


@app.delete("/api/v1/checklist", response_model=Envelope)
def reset_checklist(
    project_code: str | None = None,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    _require_team_or_project_lead(
        x_user_email,
        action="xóa dữ liệu template checklist",
        session_key=x_session_key,
        project_code=project_code,
    )
    _ctx().checklist.reset()
    return _ok()


@app.post("/api/v1/checklist/export", response_model=Envelope)
def export_checklist() -> Envelope:
    return _ok({"path": str(_ctx().checklist.export_report())})


@app.post("/api/v1/install/plan", response_model=Envelope)
def install_plan(payload: KeyRequest, request: Request) -> Envelope:
    _ensure_step_ready(payload.key)
    ctx = _ctx()
    item = ctx.checklist.get_item(payload.key)
    plan = ctx.verification.install_plan(item) if item else None
    return _ok(_store_plan(plan, payload.key, request.state.user_email) if plan else None)


@app.post("/api/v1/apps/{app_code}/install-plan", response_model=Envelope)
def catalog_install_plan(app_code: str, payload: KeyRequest, request: Request) -> Envelope:
    _ensure_step_ready(payload.key)
    ctx = _ctx()
    item = ctx.checklist.get_item(payload.key)
    if not item or (item.check_type or "").upper() != "SOFTWARE":
        raise HTTPException(status_code=400, detail="Chỉ cài đặt cho bước kiểm tra phần mềm.")
    try:
        plan = ctx.apps.installer_plan(app_code)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _ok(_store_plan(plan, payload.key, request.state.user_email))


@app.post("/api/v1/install/execute", response_model=Envelope)
def execute_install(payload: ExecuteInstallRequest, request: Request) -> Envelope:
    with _plans_lock:
        saved = _plans.get(payload.confirmation_token)
        if saved is None or saved[3] <= time.monotonic():
            _plans.pop(payload.confirmation_token, None)
            raise HTTPException(status_code=400, detail="Kế hoạch cài đặt đã hết hạn hoặc không hợp lệ.")
        plan, key, owner, _ = saved
        if owner != request.state.user_email or key != payload.key:
            raise HTTPException(status_code=403, detail="Kế hoạch cài đặt không thuộc tài khoản hoặc mục checklist này.")
        _plans.pop(payload.confirmation_token)
    if key:
        _ensure_step_ready(key)
    return _ok(_reply_data(_ctx().agent.confirm_install(plan, key), owner))


@app.get("/api/v1/apps", response_model=Envelope)
def list_apps(query: str | None = None, category: str | None = None) -> Envelope:
    return _ok(_ctx().apps.list_apps(query=query, category=category))


@app.get("/api/v1/apps/categories", response_model=Envelope)
def app_categories() -> Envelope:
    return _ok(_ctx().apps.categories())


@app.get("/api/v1/apps/{app_code}", response_model=Envelope)
def get_app(app_code: str) -> Envelope:
    app = _ctx().apps.get_app(app_code)
    if not app:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng dụng.")
    return _ok(app)


@app.put("/api/v1/apps/{app_code}/path", response_model=Envelope)
def update_app_path(app_code: str, payload: UpdateAppPathPayload) -> Envelope:
    try:
        return _ok(_ctx().apps.update_installer_path(app_code, payload.installer_path))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/v1/apps/{app_code}", response_model=Envelope)
def update_app(
    app_code: str,
    payload: UpdateAppPayload,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Cập nhật thông tin ứng dụng; chỉ cấp quản lý được phép."""
    _require_team_or_project_lead(x_user_email, action="chỉnh sửa thông tin ứng dụng", session_key=x_session_key)
    try:
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        return _ok(_ctx().apps.update_app(app_code, data))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/apps", response_model=Envelope)
def create_app(
    payload: CreateAppPayload,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    _require_team_or_project_lead(x_user_email, action="thêm ứng dụng mới vào danh mục", session_key=x_session_key)
    try:
        return _ok(_ctx().apps.create_app(payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/apps/{app_code}/check", response_model=Envelope)
def check_app(app_code: str) -> Envelope:
    app = _ctx().apps.get_app(app_code)
    if not app:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng dụng.")
    return _ok(_ctx().apps.check_app_status(app))


@app.delete("/api/v1/apps/{app_code}", response_model=Envelope)
def delete_app(
    app_code: str,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Xóa ứng dụng khỏi danh mục; chỉ TEAM_LEAD được phép."""
    _require_team_lead(x_user_email, action="xóa ứng dụng khỏi danh mục", session_key=x_session_key)
    deleted = _ctx().apps.delete_app(app_code)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy ứng dụng với mã '{app_code}'.")
    return _ok({"app_code": app_code, "deleted": True})



@app.post("/api/v1/apps/{app_code}/upload", response_model=Envelope)
def upload_app_installer(
    app_code: str,
    payload: UploadInstallerPayload,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Tải tệp bộ cài đặt lên máy chủ; chỉ cấp quản lý được phép."""
    _require_team_or_project_lead(
        x_user_email,
        action="tải bộ cài ứng dụng lên máy chủ",
        session_key=x_session_key,
        allow_any_project_lead=True,
    )
    try:
        updated = _ctx().apps.save_installer_file(
            app_code=app_code,
            source_path=payload.source_path,
            filename=payload.filename,
            version=payload.version,
        )
        return _ok(updated)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/apps/{app_code}/download")
def download_app_installer(app_code: str):
    """Tải tệp bộ cài đặt từ máy chủ về máy người dùng (Mọi tài khoản đều được tải)."""
    file_info = _ctx().apps.get_installer_file(app_code)
    if not file_info:
        raise HTTPException(
            status_code=404,
            detail=f"Ứng dụng '{app_code}' chưa có tệp bộ cài đặt được lưu trữ trên máy chủ.",
        )
    file_path, filename = file_info
    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Tệp bộ cài '{filename}' không còn tồn tại trên máy chủ.",
        )
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-cache",
        },
    )


@app.post("/api/v1/apps/{app_code}/export", response_model=Envelope)
def export_app_installer(app_code: str, payload: ExportInstallerPayload) -> Envelope:
    """Lưu tệp bộ cài đặt từ máy chủ vào thư mục chỉ định kèm version trên máy (Mọi tài khoản đều được tải)."""
    file_info = _ctx().apps.get_installer_file(app_code)
    if not file_info:
        raise HTTPException(
            status_code=404,
            detail=f"Ứng dụng '{app_code}' chưa có tệp bộ cài đặt được lưu trữ trên máy chủ.",
        )
    import shutil
    from backend.services.app_catalog_service import clean_version_tag

    file_path, filename = file_info
    dest_dir = Path(payload.destination_dir)
    app = _ctx().apps.get_app(app_code)
    clean_ver = clean_version_tag(payload.version or (app.get("recommended_version") if app else ""))
    folder_name = f"{app_code}_v{clean_ver}" if clean_ver else app_code
    target_dir = dest_dir / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    shutil.copy2(file_path, target)
    return _ok({
        "downloaded_path": str(target),
        "filename": filename,
        "folder": folder_name,
        "file_size": target.stat().st_size,
    })


@app.get("/api/v1/settings", response_model=Envelope)
def settings() -> Envelope:
    s = get_settings()
    return _ok({
        "ollama_base_url": s.ollama_base_url,
        "llm_model": s.llm_model,
        "embedding_model": s.embedding_model,
        "user_role": s.user_role,
        "roles": s.roles,
        "documents_dir": str(s.documents_dir),
        "database_description": describe(s.database_url),
    })


@app.put("/api/v1/settings", response_model=Envelope)
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    active_key = x_session_key or request.headers.get("x-session-key") or request.headers.get("X-Session-Key")
    active_email = x_user_email or getattr(request.state, "user_email", None)
    _require_team_lead(active_email, action="thay đổi cài đặt hệ thống", session_key=active_key)
    s = get_settings()
    if payload.user_role not in s.roles:
        raise HTTPException(status_code=400, detail="Vai trò không hợp lệ.")
    for key, value in payload.model_dump().items():
        setattr(s, key, value.strip() if isinstance(value, str) else value)
    s.save_user_overrides()
    return settings()


@app.get("/api/v1/status/ollama", response_model=Envelope)
def ollama_status() -> Envelope:
    from backend.core.llm import is_ollama_running, list_local_models
    s = get_settings()
    running = is_ollama_running(s)
    return _ok({"running": running, "models": list_local_models(s) if running else []})


@app.get("/api/v1/status/database", response_model=Envelope)
def database_status() -> Envelope:
    ok, message = check_connection(get_settings().database_url)
    return _ok({"ok": ok, "message": message})


@app.post("/api/v1/documents/ingest", response_model=Envelope)
def ingest_documents(
    payload: IngestRequest,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    _require_team_or_project_lead(x_user_email, session_key=x_session_key, project_code=payload.project_code)
    if payload.paths:
        report = _ctx().knowledge.ingest_paths(
            [Path(p) for p in payload.paths], reset=payload.reset, project_code=payload.project_code
        )
    else:
        report = _ctx().knowledge.ingest_all(reset=payload.reset, project_code=payload.project_code)
    return _ok(asdict(report))


@app.post("/api/v1/documents/ingest-jobs", response_model=Envelope, status_code=202)
def start_ingest_job(
    payload: IngestRequest,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    """Tạo job ingest và trả ngay job_id để frontend polling tiến độ."""
    _require_team_or_project_lead(x_user_email, session_key=x_session_key, project_code=payload.project_code)
    ctx = _ctx()
    paths = [Path(p) for p in payload.paths]
    if payload.project_code:
        project_root = ctx.projects.get_doc_folder(payload.project_code)
        invalid = [path for path in paths if not _inside(path, project_root)]
        if invalid:
            raise HTTPException(status_code=400, detail="Có tài liệu nằm ngoài thư mục của dự án.")

    def task(progress: Any) -> dict[str, Any]:
        if paths:
            report = ctx.knowledge.ingest_paths(
                paths,
                reset=payload.reset,
                progress=progress,
                project_code=payload.project_code,
            )
        else:
            report = ctx.knowledge.ingest_all(
                reset=payload.reset,
                progress=progress,
                project_code=payload.project_code,
            )
        return asdict(report)

    return _ok({"job_id": _jobs.submit(task)})


@app.get("/api/v1/jobs/{job_id}", response_model=Envelope)
def get_job(job_id: str) -> Envelope:
    state = _jobs.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình.")
    return _ok(state)


@app.get("/api/v1/projects/{code}/documents", response_model=Envelope)
def list_documents(code: str) -> Envelope:
    root = _ctx().projects.get_doc_folder(code)
    files = []
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}:
                stat = path.stat()
                files.append({"name": path.name, "path": str(path), "size": stat.st_size, "mtime": stat.st_mtime})
    return _ok({"root": str(root), "files": files})


@app.post("/api/v1/projects/{code}/documents", response_model=Envelope)
def copy_documents(
    code: str,
    payload: FileCopyRequest,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    _require_team_or_project_lead(x_user_email, session_key=x_session_key, project_code=code)
    import shutil
    root = _ctx().projects.get_doc_folder(code)
    root.mkdir(parents=True, exist_ok=True)
    copied = 0
    for raw in payload.source_paths:
        source = Path(raw)
        if source.is_file() and source.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}:
            shutil.copy2(source, root / source.name)
            copied += 1
    return _ok({"copied": copied})


@app.delete("/api/v1/projects/{code}/documents", response_model=Envelope)
def delete_document(
    code: str,
    payload: FileDeleteRequest,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_key: str | None = Header(default=None, alias="X-Session-Key"),
) -> Envelope:
    _require_team_or_project_lead(x_user_email, session_key=x_session_key, project_code=code)
    root = _ctx().projects.get_doc_folder(code)
    target = Path(payload.path)
    if not _inside(target, root) or not target.is_file():
        raise HTTPException(status_code=400, detail="Đường dẫn tài liệu không hợp lệ.")
    target.unlink()
    return _ok()


@app.post("/api/v1/projects/{code}/documents/export", response_model=Envelope)
def export_document(code: str, payload: FileExportRequest) -> Envelope:
    import shutil
    root = _ctx().projects.get_doc_folder(code)
    source = Path(payload.source_path)
    if not _inside(source, root) or not source.is_file():
        raise HTTPException(status_code=400, detail="Tài liệu nguồn không hợp lệ.")
    destination = Path(payload.destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return _ok({"path": str(destination)})
