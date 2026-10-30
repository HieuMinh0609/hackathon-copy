"""Router quản lý danh mục ứng dụng cần cài đặt (App Catalog) qua JSON API."""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from api.dependencies import get_app_context
from api.auth import require_installer_uploader
from api.schemas import AppCatalogDto, CreateAppRequest, ExportInstallerRequest, UpdateAppPathRequest, UploadInstallerRequest
from backend.core.context import AppContext

router = APIRouter(prefix="/apps", tags=["App Catalog"])


@router.get("", response_model=list[AppCatalogDto])
def list_apps(
    query: str | None = Query(None, description="Từ khóa tìm kiếm"),
    category: str | None = Query(None, description="Danh mục ứng dụng"),
    ctx: AppContext = Depends(get_app_context),
) -> list[AppCatalogDto]:
    """Lấy danh sách các ứng dụng trong danh mục kèm trạng thái cài đặt thực tế trên máy."""
    rows = ctx.apps.list_apps(query=query, category=category)
    return [AppCatalogDto(**r) for r in rows]


@router.get("/categories", response_model=list[str])
def get_categories(ctx: AppContext = Depends(get_app_context)) -> list[str]:
    """Lấy danh sách các danh mục ứng dụng."""
    return ctx.apps.categories()


@router.get("/{app_code}", response_model=AppCatalogDto)
def get_app(app_code: str, ctx: AppContext = Depends(get_app_context)) -> AppCatalogDto:
    """Lấy thông tin chi tiết một ứng dụng."""
    app = ctx.apps.get_app(app_code)
    if not app:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy ứng dụng với mã '{app_code}'.")
    return AppCatalogDto(**app)


@router.put("/{app_code}/path", response_model=AppCatalogDto)
def update_installer_path(
    app_code: str,
    payload: UpdateAppPathRequest,
    ctx: AppContext = Depends(get_app_context),
) -> AppCatalogDto:
    """Cập nhật đường dẫn bộ cài đặt / file thực thi cho ứng dụng."""
    try:
        updated = ctx.apps.update_installer_path(app_code, payload.installer_path)
        return AppCatalogDto(**updated)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=AppCatalogDto)
def create_app(
    payload: CreateAppRequest,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    ctx: AppContext = Depends(get_app_context),
) -> AppCatalogDto:
    """Thêm ứng dụng; chỉ TEAM_LEADER hoặc PROJECT_LEADER."""
    if hasattr(ctx, "users"):
        if not x_user_email:
            raise HTTPException(
                status_code=403,
                detail="Chỉ TEAM_LEADER hoặc PROJECT_LEADER mới có quyền thêm ứng dụng.",
            )
        user = ctx.users.get_by_email(x_user_email)
        if not user or not getattr(user, "can_manage", False):
            curr_lv = user.level if user else "Unknown"
            raise HTTPException(
                status_code=403,
                detail=f"Chỉ TEAM_LEADER hoặc PROJECT_LEADER mới có quyền thêm ứng dụng. (Quyền hiện tại: {curr_lv})",
            )
    try:
        created = ctx.apps.create_app(payload.model_dump())
        return AppCatalogDto(**created)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{app_code}/check", response_model=dict[str, Any])
def check_app_status(
    app_code: str,
    ctx: AppContext = Depends(get_app_context),
) -> dict[str, Any]:
    """Kiểm tra trạng thái cài đặt của ứng dụng trên máy."""
    app = ctx.apps.get_app(app_code)
    if not app:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy ứng dụng với mã '{app_code}'.")
    return ctx.apps.check_app_status(app)


@router.post("/{app_code}/upload", response_model=AppCatalogDto)
def upload_installer(
    app_code: str,
    payload: UploadInstallerRequest,
    request: Request,
    ctx: AppContext = Depends(get_app_context),
) -> AppCatalogDto:
    """Tải bộ cài; chỉ TEAM_LEAD hoặc PROJECT_LEAD đã xác thực."""
    require_installer_uploader(request, ctx)
    try:
        updated = ctx.apps.save_installer_file(
            app_code=app_code,
            source_path=payload.source_path,
            filename=payload.filename,
            version=payload.version,
        )
        return AppCatalogDto(**updated)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{app_code}/download")
def download_installer(
    app_code: str,
    ctx: AppContext = Depends(get_app_context),
):
    """Tải tệp bộ cài đặt từ máy chủ về máy người dùng (Mọi tài khoản đều được tải)."""
    file_info = ctx.apps.get_installer_file(app_code)
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
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.post("/{app_code}/export", response_model=dict[str, Any])
def export_installer(
    app_code: str,
    payload: ExportInstallerRequest,
    ctx: AppContext = Depends(get_app_context),
) -> dict[str, Any]:
    """Lưu tệp bộ cài đặt từ máy chủ vào thư mục chỉ định kèm version trên máy (Mọi tài khoản đều được tải)."""
    file_info = ctx.apps.get_installer_file(app_code)
    if not file_info:
        raise HTTPException(
            status_code=404,
            detail=f"Ứng dụng '{app_code}' chưa có tệp bộ cài đặt được lưu trữ trên máy chủ.",
        )
    file_path, filename = file_info
    dest_dir = Path(payload.destination_dir)

    app = ctx.apps.get_app(app_code)
    from backend.services.app_catalog_service import clean_version_tag

    clean_ver = clean_version_tag(payload.version or (app.get("recommended_version") if app else ""))
    folder_name = f"{app_code}_v{clean_ver}" if clean_ver else app_code
    target_dir = dest_dir / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    shutil.copy2(file_path, target)
    return {
        "downloaded_path": str(target),
        "filename": filename,
        "folder": folder_name,
        "file_size": target.stat().st_size,
    }
