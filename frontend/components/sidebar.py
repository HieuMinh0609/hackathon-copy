"""Thanh điều hướng bên trái."""
from __future__ import annotations

from typing import Callable

import flet as ft

from frontend import theme


class Sidebar(ft.Container):
    def __init__(self, on_select: Callable[[int], None], app_name: str = "AI Buddy") -> None:
        rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            bgcolor=ft.Colors.TRANSPARENT,
            indicator_color=ft.Colors.with_opacity(0.25, theme.ACCENT),
            min_width=88,
            on_change=lambda e: on_select(e.control.selected_index),
            leading=ft.Container(
                margin=ft.margin.only(top=12, bottom=16),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                    controls=[
                        ft.Icon(ft.Icons.SMART_TOY_ROUNDED, size=34, color=theme.ACCENT_2),
                        ft.Text(app_name, size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                    ],
                ),
            ),
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.CHAT_BUBBLE_OUTLINE, selected_icon=ft.Icons.CHAT_BUBBLE, label="Chat"),
                ft.NavigationRailDestination(icon=ft.Icons.CHECKLIST_OUTLINED, selected_icon=ft.Icons.CHECKLIST, label="Checklist"),
                ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Cài đặt"),
            ],
        )
        self.rail = rail
        super().__init__(
            content=rail,
            bgcolor=theme.SURFACE,
            border=ft.border.only(right=ft.BorderSide(1, theme.BORDER)),
        )
