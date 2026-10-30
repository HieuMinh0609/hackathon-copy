"""Router xử lý tin nhắn Chat AI Buddy qua JSON API."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_app_context
from api.schemas import AgentReplyDto, ChatRequest, ConfirmInstallRequest, InstallPlanDto
from backend.core.context import AppContext
from backend.core.utils.system_utils import InstallPlan

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/chat", response_model=AgentReplyDto)
def chat(req: ChatRequest, ctx: AppContext = Depends(get_app_context)) -> AgentReplyDto:
    """Gửi tin nhắn tới AI Buddy Agent và nhận câu trả lời dạng JSON."""
    reply = ctx.agent.chat(req.message, project_code=req.project_code, checklist_mode=req.checklist_mode)

    plan_dto = None
    if reply.pending_install:
        plan_dto = InstallPlanDto(
            software=reply.pending_install.software,
            manager=reply.pending_install.manager,
            command=list(reply.pending_install.command),
            description=reply.pending_install.description,
        )

    return AgentReplyDto(
        text=reply.text,
        sources=reply.sources,
        pending_install=plan_dto,
        pending_key=reply.pending_key,
        agent=reply.agent,
    )


@router.post("/confirm-install", response_model=AgentReplyDto)
def confirm_install(req: ConfirmInstallRequest, ctx: AppContext = Depends(get_app_context)) -> AgentReplyDto:
    """Xác nhận và chạy kế hoạch cài đặt do Agent đề xuất."""
    plan = InstallPlan(
        software=req.plan.software,
        manager=req.plan.manager,
        command=req.plan.command,
        description=req.plan.description,
    )
    reply = ctx.agent.confirm_install(plan, req.key)
    return AgentReplyDto(
        text=reply.text,
        sources=reply.sources,
        pending_install=None,
        pending_key=None,
        agent=reply.agent,
    )
