"""Thẻ tiến độ tổng quan."""
from __future__ import annotations

from typing import Any

import flet as ft

from frontend import theme


class ProgressCard(ft.Container):
    def __init__(self) -> None:
        self.ring = ft.ProgressRing(width=84, height=84, stroke_width=9, value=0, color=theme.ACCENT_2,
                                    bgcolor=theme.SURFACE_ALT)
        self.percent = ft.Text("0%", size=20, weight=ft.FontWeight.BOLD, color=theme.TEXT)
        self.headline = ft.Text("Chưa kiểm tra", size=18, weight=ft.FontWeight.W_700, color=theme.TEXT)
        self.detail = ft.Text("", size=12, color=theme.MUTED)
        self.badges = ft.Row(spacing=8, wrap=True)
        super().__init__(
            content=ft.Row(
                spacing=20,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Stack([self.ring, ft.Container(self.percent, width=84, height=84, alignment=ft.alignment.center)]),
                    ft.Column([self.headline, self.detail, self.badges], spacing=6, expand=True),
                ],
            ),
            padding=20,
            border_radius=18,
            border=ft.border.all(1, theme.BORDER),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[theme.SURFACE_ALT, theme.SURFACE],
            ),
        )

    @staticmethod
    def _badge(label: str, color: str) -> ft.Container:
        return ft.Container(
            ft.Text(label, size=11, color=color, weight=ft.FontWeight.W_600),
            padding=ft.padding.symmetric(horizontal=10, vertical=3),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.15, color),
        )

    def set_progress(self, p: dict[str, Any]) -> None:
        self.ring.value = p["percent"] / 100
        self.percent.value = f"{p['percent']}%"
        self.headline.value = "Sẵn sàng join dự án 🚀" if p["ready"] else "Đang chuẩn bị…"
        self.detail.value = f"Bắt buộc: {p['required_passed']}/{p['required_total']}  •  Tổng: {p['passed']}/{p['total']}"
        self.badges.controls = [
            self._badge(f"✅ {p['passed']} đạt", theme.OK),
            self._badge(f"❌ {p['failed']} lỗi", theme.ERR),
            self._badge(f"⚠️ {p['warning']} cảnh báo", theme.WARN),
            self._badge(f"⏳ {p['pending']} chờ", theme.MUTED),
        ]
        if self.page:
            self.update()
