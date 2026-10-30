"""Router kiểm tra môi trường và cài đặt phần mềm qua JSON API."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_app_context
from api.schemas import InstallPlanDto, RunInstallRequest, RunInstallResponse, VerificationResultDto
from backend.core.context import AppContext
from backend.core.utils.system_utils import InstallPlan

router = APIRouter(prefix="/verification", tags=["Verification"])


@router.post("/verify-key", response_model=VerificationResultDto)
def verify_key(key: str, ctx: AppContext = Depends(get_app_context)) -> VerificationResultDto:
    """Thực hiện kiểm tra cho một mục checklist cụ thể theo key."""
    try:
        res = ctx.verification.verify_key(key)
        return VerificationResultDto(
            key=res.key,
            status=res.status,
            message=res.message,
            suggestion=res.suggestion,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mục checklist: {key}")


@router.post("/verify-all", response_model=list[VerificationResultDto])
def verify_all(ctx: AppContext = Depends(get_app_context)) -> list[VerificationResultDto]:
    """Thực hiện kiểm tra tất cả các mục checklist tự động."""
    results = ctx.verification.verify_all()
    return [
        VerificationResultDto(
            key=r.key,
            status=r.status,
            message=r.message,
            suggestion=r.suggestion,
        )
        for r in results
    ]


@router.get("/install-plan/{key}", response_model=InstallPlanDto | None)
def get_install_plan(key: str, ctx: AppContext = Depends(get_app_context)) -> InstallPlanDto | None:
    """Tạo kế hoạch cài đặt (chưa thực thi) cho một mục phần mềm."""
    item = ctx.checklist.get_item(key)
    if not item:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mục checklist: {key}")
    plan = ctx.verification.install_plan(item)
    if not plan:
        return None
    return InstallPlanDto(
        software=plan.software,
        manager=plan.manager,
        command=list(plan.command),
        description=plan.description,
    )


@router.post("/run-install", response_model=RunInstallResponse)
def run_install(req: RunInstallRequest, ctx: AppContext = Depends(get_app_context)) -> RunInstallResponse:
    """Thực thi lệnh cài đặt sau khi người dùng đã xác nhận trên giao diện."""
    plan = InstallPlan(
        software=req.plan.software,
        manager=req.plan.manager,
        command=req.plan.command,
        description=req.plan.description,
    )
    ok, output = ctx.verification.run_install(plan, req.key)
    return RunInstallResponse(ok=ok, output=output)
