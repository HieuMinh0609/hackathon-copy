"""Khung chat: danh sách tin nhắn + ô nhập."""
from __future__ import annotations

from typing import Callable

import flet as ft

from frontend import theme
from frontend.components.message_bubble import MessageBubble


class ChatBox(ft.Column):
    def __init__(self, on_send: Callable[[str], None], on_link=None) -> None:
        self._on_send = on_send
        self._on_link = on_link
        self.messages = ft.ListView(expand=True, spacing=14, auto_scroll=True, padding=ft.padding.only(right=8))
        self.typing = ft.Row(
            visible=False,
            spacing=8,
            controls=[
                ft.ProgressRing(width=16, height=16, stroke_width=2, color=theme.ACCENT_2),
                ft.Text("AI Buddy đang suy nghĩ…", size=12, color=theme.MUTED, italic=True),
            ],
        )
        self.input = ft.TextField(
            hint_text="Hỏi về dự án, gõ “kiểm tra môi trường” hoặc “kiểm tra 192.168.1.10:5432”…",
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=4,
            shift_enter=True,
            border_radius=14,
            border_color=theme.BORDER,
            focused_border_color=theme.ACCENT,
            bgcolor=theme.SURFACE,
            on_submit=self._submit,
        )
        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_color=theme.BG,
            bgcolor=theme.ACCENT_2,
            on_click=self._submit,
            tooltip="Gửi",
        )
        super().__init__(
            expand=True,
            spacing=10,
            controls=[
                self.messages,
                self.typing,
                ft.Row([self.input, self.send_btn], vertical_alignment=ft.CrossAxisAlignment.END),
            ],
        )

    def _submit(self, _=None) -> None:
        text = (self.input.value or "").strip()
        if not text or self.send_btn.disabled:
            return
        self.input.value = ""
        self.input.update()
        self._on_send(text)

    # ---- API cho page ----
    def add_message(
        self,
        text: str,
        is_user: bool,
        sources: list[str] | None = None,
        timestamp: Any = None,
    ) -> None:
        self.messages.controls.append(MessageBubble(text, is_user, sources, self._on_link, timestamp=timestamp))
        if self.page:
            self.messages.update()

    def set_busy(self, busy: bool) -> None:
        self.typing.visible = busy
        self.send_btn.disabled = busy
        if self.page:
            self.typing.update()
            self.send_btn.update()

    def focus_input(self) -> None:
        if self.page:
            self.input.focus()
