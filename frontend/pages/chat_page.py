"""Trang chat với AI Buddy."""
from __future__ import annotations

import flet as ft

from frontend.context import FrontendContext
from frontend.models import AgentReply
from frontend import theme
from frontend.components.chat_box import ChatBox
from frontend.components.confirm_dialog import confirm_install_dialog

SUGGESTIONS = [
    "Dự án này làm về gì?",
    "Kiểm tra môi trường của tôi",
    "Quy trình xin cấp quyền IP?",
    "Kiểm tra 127.0.0.1:11434",
]


class ChatPage(ft.Column):
    def __init__(self, ctx: FrontendContext) -> None:
        self.ctx = ctx
        self.chat = ChatBox(self._on_send, on_link=lambda e: self.page.launch_url(e.data))
        self.chat.add_message(
            "Xin chào! Mình là **AI Buddy** 👋\n\n"
            "Mình có thể:\n- Trả lời câu hỏi về dự án (từ tài liệu nội bộ)\n"
            "- Kiểm tra môi trường & cài đặt phần mềm (luôn hỏi trước khi chạy)\n"
            "- Kiểm tra quyền truy cập IP/port bằng socket",
            is_user=False,
        )
        chips = ft.Row(
            wrap=True,
            spacing=8,
            controls=[
                ft.Chip(label=ft.Text(s, size=12), on_click=lambda e, s=s: self._on_send(s), bgcolor=theme.SURFACE_ALT)
                for s in SUGGESTIONS
            ],
        )
        super().__init__(
            expand=True,
            spacing=12,
            controls=[
                ft.Text("Trò chuyện với AI Buddy", size=24, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                chips,
                self.chat,
            ],
        )

    def _on_send(self, text: str) -> None:
        if self.chat.send_btn.disabled:
            return
        self.chat.add_message(text, is_user=True)
        self.chat.set_busy(True)
        self.page.run_thread(self._respond, text)

    def _respond(self, text: str) -> None:
        reply = self.ctx.agent.chat(text)
        self.chat.set_busy(False)
        self._show_reply(reply)

    def _show_reply(self, reply: AgentReply) -> None:
        self.chat.add_message(reply.text, is_user=False, sources=reply.sources)
        if reply.pending_install:
            plan, key = reply.pending_install, reply.pending_key
            confirm_install_dialog(self.page, plan, lambda: self.page.run_thread(self._do_install, plan, key))
        self.chat.focus_input()

    def _do_install(self, plan, key) -> None:
        self.chat.set_busy(True)
        self.chat.add_message(f"⏳ Đang cài **{plan.software}**… (có thể mất vài phút)", is_user=False)
        result = self.ctx.agent.confirm_install(plan, key)
        self.chat.set_busy(False)
        self._show_reply(result)
