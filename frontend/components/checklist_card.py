"""Thẻ hiển thị một mục checklist."""
from __future__ import annotations

from typing import Callable

import flet as ft

from frontend.models import ChecklistItem
from frontend import theme


class ChecklistCard(ft.Container):
    def __init__(
        self,
        item: ChecklistItem,
        can_install: bool,
        on_verify: Callable[[str], None],
        on_install: Callable[[str], None],
        on_toggle_manual: Callable[[str, bool], None],
    ) -> None:
        icon, color = theme.STATUS_STYLE.get(item.status, (ft.Icons.RADIO_BUTTON_UNCHECKED, theme.TEXT_LIGHT))
        actions: list[ft.Control] = []

        is_done = item.status in ("passed", "COMPLETED")
        actions.append(
            ft.Switch(
                value=is_done,
                active_color=theme.OK,
                tooltip="Tick / bỏ tick thủ công",
                on_change=lambda e, k=item.key: on_toggle_manual(k, e.control.value),
            )
        )

        check_type_upper = (item.check_type or "MANUAL").upper()
        if check_type_upper != "MANUAL":
            if can_install and item.status in ("failed", "warning"):
                actions.append(
                    ft.FilledTonalButton(
                        "Cài đặt", icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e, k=item.key: on_install(k)
                    )
                )
            actions.append(
                ft.IconButton(
                    ft.Icons.REFRESH_ROUNDED, tooltip="Kiểm tra lại", icon_color=theme.ACCENT,
                    on_click=lambda e, k=item.key: on_verify(k),
                )
            )

        title_row = [ft.Text(item.title, weight=ft.FontWeight.W_600, color=theme.TEXT, size=14)]
        if not item.required:
            title_row.append(
                ft.Container(
                    content=ft.Text("tuỳ chọn", size=10, color=theme.MUTED),
                    padding=ft.padding.symmetric(horizontal=6, vertical=1),
                    border=ft.border.all(1, theme.BORDER),
                    border_radius=8,
                )
            )

        details: list[ft.Control] = [ft.Row(title_row, spacing=8, wrap=True)]
        if item.description:
            details.append(ft.Text(item.description, size=12, color=theme.MUTED))
        if item.message:
            details.append(ft.Text(item.message, size=12, color=color, selectable=True))

        super().__init__(
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, color=color, size=26),
                    ft.Column(details, spacing=3, expand=True),
                    ft.Row(actions, spacing=4),
                ],
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            bgcolor=theme.SURFACE,
            border_radius=14,
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, color) if item.status != "pending" else theme.BORDER),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )
