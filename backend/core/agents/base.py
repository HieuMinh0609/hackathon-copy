"""Kiểu dữ liệu dùng chung cho các agent."""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.utils.system_utils import InstallPlan


@dataclass
class AgentReply:
    text: str
    sources: list[str] = field(default_factory=list)
    # Nếu có, UI phải hỏi xác nhận người dùng rồi mới chạy (nguyên tắc "hỏi trước khi thực thi")
    pending_install: InstallPlan | None = None
    pending_key: str | None = None
    agent: str = "ai_buddy"
    install_ok: bool | None = None
