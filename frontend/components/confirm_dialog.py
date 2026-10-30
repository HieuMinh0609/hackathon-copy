"""Hộp thoại xác nhận trước khi thực thi lệnh cài đặt."""
from __future__ import annotations

from typing import Callable

import flet as ft

from frontend.models import InstallPlan
from frontend import theme


def confirm_install_dialog(
    page: ft.Page, plan: InstallPlan, on_confirm: Callable[[], None],
    on_cancel: Callable[[], None] | None = None,
) -> None:
    resolved = False

    def close(_=None) -> None:
        nonlocal resolved
        if resolved:
            return
        resolved = True
        page.close(dlg)
        if on_cancel:
            on_cancel()

    def confirm(_=None) -> None:
        nonlocal resolved
        if resolved:
            return
        resolved = True
        page.close(dlg)
        on_confirm()

    dlg = ft.AlertDialog(
        modal=True,
        on_dismiss=close,
        title=ft.Text(f"Cài đặt {plan.software}?"),
        content=ft.Column(
            tight=True,
            width=480,
            controls=[
                ft.Text("AI Buddy sẽ chạy lệnh sau trên máy của bạn:", color=theme.TEXT_MUTED),
                ft.Container(
                    ft.Text(plan.display, font_family="Consolas", selectable=True, size=12, color=theme.TEXT),
                    bgcolor=theme.SURFACE_ALT,
                    border=ft.border.all(1, theme.BORDER),
                    padding=12,
                    border_radius=8,
                ),
                ft.Text("Công cụ cài có thể tải gói từ nguồn đã cấu hình và cần mạng. Quyền Administrator/UAC do hệ điều hành quyết định. Chỉ lệnh này được cấp phép; muốn thử lại cần xác nhận mới.", size=12, color=theme.TEXT_MUTED),
            ],
        ),
        actions=[
            ft.TextButton("Huỷ", on_click=close),
            ft.FilledButton("Đồng ý cài đặt", icon=ft.Icons.CHECK, bgcolor=theme.PRIMARY, on_click=confirm),
        ],
    )
    page.open(dlg)
