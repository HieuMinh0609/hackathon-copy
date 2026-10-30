"""Agent mạng: phân tích IP/port bằng socket + subprocess và sinh code kiểm tra."""
from __future__ import annotations

from config.settings import get_prompt
from backend.core.agents.base import AgentReply
from backend.core.llm import LLMClient, LLMUnavailable
from backend.core.utils import network_utils


class NetworkingAgent:
    name = "networking"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def handle(self, message: str) -> AgentReply:
        targets = network_utils.parse_host_port(message)
        if not targets:
            ips = ", ".join(network_utils.get_local_ips()) or "không xác định"
            return AgentReply(
                "Bạn hãy gửi địa chỉ cần kiểm tra, ví dụ: `kiểm tra 192.168.1.10:5432` "
                f"hoặc `telnet db.company.local:443`.\n\nIP máy bạn hiện tại: `{ips}`",
                agent=self.name,
            )

        parts: list[str] = []
        for host, port in targets[:3]:
            report = network_utils.analyze_connectivity(host, port)
            block = report.to_markdown()
            if port:
                script = network_utils.generate_check_script(host, port)
                block += f"\n\nCode Python (socket) để tự kiểm tra:\n```python\n{script}```"
            parts.append(block)
            try:
                explain = self.llm.ask(
                    "Hãy giải thích kết quả.",
                    system=get_prompt("networking_analysis", report=report.to_markdown()),
                )
                parts.append(f"💡 **Phân tích**\n{explain}")
            except LLMUnavailable:
                pass  # vẫn có chẩn đoán rule-based ở trên
        return AgentReply("\n\n---\n\n".join(parts), agent=self.name)
