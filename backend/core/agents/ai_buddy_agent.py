"""Agent điều phối: nhận tin nhắn, chọn agent chuyên trách (knowledge / checklist / networking)."""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from backend.core.agents.base import AgentReply
from backend.core.utils import network_utils
from backend.core.utils.system_utils import InstallPlan

if TYPE_CHECKING:
    from backend.core.agents.checklist_agent import ChecklistAgent
    from backend.core.agents.knowledge_agent import KnowledgeAgent
    from backend.core.agents.networking_agent import NetworkingAgent

_CHECKLIST_PHRASES = (
    "checklist", "check list", "kiem tra moi truong", "kiem tra cai dat",
    "kiem tra ung dung", "moi truong cua toi", "kiem tra version", "kiem tra phien ban",
)
_NETWORK_WORDS = {"telnet", "ping", "socket", "traceroute"}


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


def detect_intent(message: str) -> str:
    """Định tuyến theo luật (nhanh, chạy offline, không tốn LLM)."""
    plain = strip_accents(message)
    tokens = set(re.findall(r"\w+", plain))

    if network_utils.parse_host_port(message) or tokens & _NETWORK_WORDS:
        return "networking"
    if "port" in tokens and ("kiem" in tokens or "trung" in tokens):
        return "networking"
    if any(p in plain for p in _CHECKLIST_PHRASES) or re.match(r"^\s*(cai|install)\s+\w+", plain):
        return "checklist"
    return "knowledge"


class AiBuddyAgent:
    name = "ai_buddy"

    def __init__(
        self, knowledge: KnowledgeAgent, checklist: ChecklistAgent, networking: NetworkingAgent
    ) -> None:
        self.knowledge_agent = knowledge
        self.checklist_agent = checklist
        self.networking_agent = networking

    def chat(self, message: str, project_code: str | None = None, checklist_mode: bool = False) -> AgentReply:
        message = message.strip()
        if not message:
            return AgentReply("Bạn hãy nhập câu hỏi nhé 🙂")
        
        # Khi bật switch checklist_mode, chủ động điều phối tới ChecklistAgent (Qwen 2.5:7b)
        if checklist_mode:
            intent = "checklist"
            agent = self.checklist_agent
        else:
            intent = detect_intent(message)
            agent = {
                "networking": self.networking_agent,
                "checklist": self.checklist_agent,
            }.get(intent, self.knowledge_agent)

        try:
            if agent == self.knowledge_agent:
                return agent.handle(message, project_code=project_code)
            if agent == self.checklist_agent:
                return agent.handle(message, project_code=project_code, checklist_mode=checklist_mode)
            return agent.handle(message)
        except Exception as exc:  # luôn trả lời được, không làm sập UI
            return AgentReply(f"⚠️ Đã có lỗi khi xử lý: `{exc}`", agent=intent)

    def confirm_install(self, plan: InstallPlan, key: str | None = None) -> AgentReply:
        """Gọi sau khi người dùng bấm xác nhận trên UI."""
        return self.checklist_agent.execute_install(plan, key)
