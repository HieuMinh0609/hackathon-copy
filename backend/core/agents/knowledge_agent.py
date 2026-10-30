"""Agent trả lời câu hỏi về dự án bằng RAG (ChromaDB + Qwen-2.5)."""
from __future__ import annotations

from backend.core.agents.base import AgentReply
from backend.core.llm import LLMClient, LLMUnavailable
from config.settings import get_prompt
from backend.services.knowledge_service import KnowledgeService


class KnowledgeAgent:
    name = "knowledge"

    def __init__(self, knowledge: KnowledgeService, llm: LLMClient) -> None:
        self.knowledge = knowledge
        self.llm = llm

    def handle(self, message: str, project_code: str | None = None) -> AgentReply:
        try:
            if project_code:
                docs = self.knowledge.search_project(project_code, message)
            else:
                docs = self.knowledge.search(message)
        except Exception as exc:
            return AgentReply(
                "⚠️ Chưa truy cập được kho tri thức. Hãy bật Ollama, pull model embedding "
                f"và nạp tài liệu ở trang **Cài đặt**.\n\n`{exc}`",
                agent=self.name,
            )
        if not docs:
            return AgentReply(
                "Mình chưa tìm thấy tài liệu liên quan. Hãy nạp tài liệu ở trang **Cài đặt** "
                "hoặc hỏi mentor/quản lý dự án nhé.",
                agent=self.name,
            )

        sources = self.knowledge.sources(docs)
        system = get_prompt("knowledge_qa", context=self.knowledge.format_context(docs))
        try:
            answer = self.llm.ask(message, system=system)
        except LLMUnavailable as exc:
            excerpts = "\n\n".join(f"> {d.page_content[:300]}…" for d in docs[:2])
            answer = f"⚠️ Model chưa sẵn sàng ({exc}). Đoạn tài liệu liên quan nhất:\n\n{excerpts}"
        return AgentReply(answer, sources=sources, agent=self.name)
