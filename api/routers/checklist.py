"""Router quản lý Checklist qua JSON API."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request

from api.auth import require_template_manager
from api.dependencies import get_app_context
from api.schemas import ChecklistItemDto, ChecklistProgressDto, SetManualDoneRequest, ImportChecklistRequest
from backend.core.context import AppContext

router = APIRouter(prefix="/checklist", tags=["Checklist"])


@router.get("/items", response_model=list[ChecklistItemDto])
def list_checklist_items(
    category: str | None = Query(None, description="Lọc theo danh mục"),
    project_code: str | None = Query(None, description="Mã template/dự án cần lấy checklist"),
    user_email: str | None = Query(None, description="Email người dùng đang xem checklist"),
    x_user_email: str | None = Header(None, alias="X-User-Email"),
    ctx: AppContext = Depends(get_app_context),
) -> list[ChecklistItemDto]:
    """Lấy danh sách các mục checklist dùng chung của dự án."""
    target_email = x_user_email or user_email
    items = ctx.checklist.list_items(category=category, template_code=project_code, user_email=target_email)
    return [
        ChecklistItemDto(
            key=i.key,
            category=i.category,
            title=i.title,
            description=i.description,
            check_type=i.check_type,
            params=i.params,
            required=i.required,
            status=i.status,
            message=i.message,
            updated_at=i.updated_at,
        )
        for i in items
    ]


@router.get("/items/{key}", response_model=ChecklistItemDto)
def get_checklist_item(key: str, ctx: AppContext = Depends(get_app_context)) -> ChecklistItemDto:
    """Lấy thông tin chi tiết một mục checklist."""
    item = ctx.checklist.get_item(key)
    if not item:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mục checklist: {key}")
    return ChecklistItemDto(
        key=item.key,
        category=item.category,
        title=item.title,
        description=item.description,
        check_type=item.check_type,
        params=item.params,
        required=item.required,
        status=item.status,
        message=item.message,
        updated_at=item.updated_at,
    )


@router.get("/progress", response_model=ChecklistProgressDto)
def get_checklist_progress(
    project_code: str | None = Query(None, description="Mã dự án"),
    user_email: str | None = Query(None, description="Email người dùng"),
    x_user_email: str | None = Header(None, alias="X-User-Email"),
    ctx: AppContext = Depends(get_app_context),
) -> ChecklistProgressDto:
    """Lấy tiến độ hoàn thành checklist."""
    target_email = x_user_email or user_email
    p = ctx.checklist.progress(template_code=project_code, user_email=target_email)
    return ChecklistProgressDto(
        total=p.get("total", 0),
        percent=p.get("percent", 0),
        passed=p.get("passed", 0),
        failed=p.get("failed", 0),
        warning=p.get("warning", 0),
        pending=p.get("pending", 0),
        required_left=p.get("required_left", 0),
    )


@router.post("/items/{key}/manual", response_model=dict[str, Any])
def set_manual_done(
    key: str, req: SetManualDoneRequest, ctx: AppContext = Depends(get_app_context)
) -> dict[str, Any]:
    """Cập nhật xác nhận thủ công cho một mục checklist, có đồng bộ sang user_checklists_tasks nếu có user_id."""
    user_id = req.user_id
    if not user_id and req.user_email and hasattr(ctx, "users"):
        u = ctx.users.get_by_email(req.user_email)
        if u:
            user_id = u.user_id

    try:
        if user_id:
            res = ctx.checklist.update_user_task_status(
                user_id=user_id,
                key=key,
                done=req.done,
                template_code=req.project_code,
            )
            return res
        ctx.checklist.set_manual_done(key, req.done)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mục checklist: {key}")
    return {"status": "ok", "key": key, "done": req.done}


@router.post("/user-task", response_model=dict[str, Any])
def update_user_task(
    req: SetManualDoneRequest, ctx: AppContext = Depends(get_app_context)
) -> dict[str, Any]:
    """Cập nhật trạng thái mục checklist trong bảng user_checklists_tasks theo user_id."""
    key = req.key
    if not key:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp key của mục checklist.")

    user_id = req.user_id
    if not user_id and req.user_email and hasattr(ctx, "users"):
        u = ctx.users.get_by_email(req.user_email)
        if u:
            user_id = u.user_id

    if not user_id:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp user_id hoặc user_email.")

    try:
        return ctx.checklist.update_user_task_status(
            user_id=user_id,
            key=key,
            done=req.done,
            template_code=req.project_code,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mục checklist: {key}")


@router.post("/reset", response_model=dict[str, str])
def reset_checklist(request: Request, project_code: str | None = None, ctx: AppContext = Depends(get_app_context)) -> dict[str, str]:
    """Reset trạng thái toàn bộ checklist về pending."""
    require_template_manager(request, ctx, project_code=project_code, action="reset checklist")
    ctx.checklist.reset()
    return {"status": "ok", "message": "Đã reset toàn bộ checklist về trạng thái ban đầu."}


@router.post("/export", response_model=dict[str, str])
def export_checklist(ctx: AppContext = Depends(get_app_context)) -> dict[str, str]:
    """Xuất báo cáo checklist ra file Markdown/JSON."""
    report_path = ctx.checklist.export_report()
    return {"status": "ok", "export_path": str(report_path)}


@router.get("/template-sample", response_model=dict[str, Any])
def get_checklist_template_sample(request: Request, project_code: str, ctx: AppContext = Depends(get_app_context)) -> dict[str, Any]:
    """Tải nội dung file template CSV mẫu để import checklist."""
    require_template_manager(request, ctx, project_code=project_code, action="tải template checklist")
    csv_content = ctx.checklist.get_sample_template_csv()
    return {"filename": "checklist_template_sample.csv", "content": csv_content}


@router.post("/import", response_model=dict[str, Any])
def import_checklist(
    payload: ImportChecklistRequest,
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    ctx: AppContext = Depends(get_app_context),
) -> dict[str, Any]:
    """Import checklist; chỉ TEAM_LEADER hoặc PROJECT_LEADER của dự án."""
    del x_user_email
    require_template_manager(
        request,
        ctx,
        project_code=payload.project_code,
        action="import checklist cho dự án",
    )
    try:
        return ctx.checklist.import_tasks_from_csv(
            content=payload.content,
            project_code=payload.project_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
