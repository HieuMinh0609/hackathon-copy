"""Router quản lý Onboarding Templates (Projects) qua JSON API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import require_template_manager
from api.dependencies import get_app_context
from api.schemas import DocFolderResponse, SetDocFolderRequest, TemplateDto, UpsertTemplateRequest
from backend.core.context import AppContext

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("", response_model=list[TemplateDto])
def list_templates(ctx: AppContext = Depends(get_app_context)) -> list[TemplateDto]:
    """Lấy danh sách tất cả các template onboarding từ DB."""
    records = ctx.projects.list_projects()
    return [TemplateDto(**r) for r in records]


@router.get("/{code}", response_model=TemplateDto)
def get_template(code: str, ctx: AppContext = Depends(get_app_context)) -> TemplateDto:
    """Lấy thông tin chi tiết một template theo mã template_code."""
    proj = ctx.projects.get_project(code)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy template có mã: {code}")
    return TemplateDto(**proj)


@router.post("", response_model=dict[str, str])
def upsert_template(req: UpsertTemplateRequest, request: Request, ctx: AppContext = Depends(get_app_context)) -> dict[str, str]:
    """Thêm mới hoặc cập nhật một template onboarding."""
    require_template_manager(request, ctx, action="thêm hoặc cập nhật template")
    ctx.projects.upsert_project(
        code=req.template_code,
        name=req.template_name,
        description=req.description,
        doc_folder=req.document_link,
    )
    return {"status": "ok", "message": f"Template {req.template_code} đã được lưu thành công."}


@router.get("/{code}/doc-folder", response_model=DocFolderResponse)
def get_doc_folder(code: str, ctx: AppContext = Depends(get_app_context)) -> DocFolderResponse:
    """Lấy đường dẫn thư mục tài liệu thực tế của template."""
    folder_path = ctx.projects.get_doc_folder(code)
    return DocFolderResponse(
        template_code=code,
        doc_folder=str(folder_path),
        exists=folder_path.exists() and folder_path.is_dir(),
    )


@router.put("/{code}/doc-folder", response_model=dict[str, Any])
def set_doc_folder(
    code: str, req: SetDocFolderRequest, request: Request, ctx: AppContext = Depends(get_app_context)
) -> dict[str, Any]:
    """Cập nhật đường dẫn thư mục tài liệu (document_link) cho template."""
    require_template_manager(request, ctx, project_code=code, action="cập nhật template")
    ok = ctx.projects.set_doc_folder(code, req.doc_folder)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Không cập nhật được thư mục cho template: {code}")
    return {"status": "ok", "template_code": code, "doc_folder": req.doc_folder}
