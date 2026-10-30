"""Màn hình Đăng nhập (LoginScreen) theo mẫu thiết kế AI-Buddy.

Kiểm tra xác thực email có trong bảng 'users' của Database trước khi vào hệ thống.
"""
from __future__ import annotations

from typing import Any, Callable

import flet as ft

from frontend import theme
from frontend.api_client import ApiError
from frontend.context import FrontendContext


class LoginPage(ft.Container):
    def __init__(self, ctx: FrontendContext, on_login: Callable[[dict[str, Any]], None]) -> None:
        self.ctx = ctx
        self.on_login = on_login

        self.email_input = ft.TextField(
            hint_text="Email công ty (ví dụ: alex.carter@example.com)",
            value="alex.carter@example.com",
            prefix_icon=ft.Icons.EMAIL_OUTLINED,
            bgcolor=theme.SURFACE,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=10,
            text_size=14,
            height=48,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
            on_submit=self._submit,
            on_change=self._clear_error,
        )

        self.password_input = ft.TextField(
            hint_text="Mật khẩu nội bộ (mặc định: 1234)",
            value="1234",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            bgcolor=theme.SURFACE,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=10,
            text_size=14,
            height=48,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
            on_submit=self._submit,
        )

        self.error_text = ft.Text(
            "",
            size=12,
            weight=ft.FontWeight.W_500,
            color=theme.ERR,
            visible=False,
        )

        self.login_btn_text = ft.Text(
            "Đăng nhập vào hệ thống",
            size=14,
            weight=ft.FontWeight.W_600,
            color=theme.TEXT_WHITE,
        )
        self.login_spinner = ft.ProgressRing(
            width=18,
            height=18,
            stroke_width=2,
            color=theme.TEXT_WHITE,
            visible=False,
        )

        self.login_btn = ft.Container(
            content=ft.Row(
                [
                    self.login_spinner,
                    self.login_btn_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            bgcolor=theme.PRIMARY,
            border_radius=10,
            padding=ft.padding.symmetric(vertical=13),
            alignment=ft.alignment.center,
            on_click=self._submit,
            ink=True,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color=ft.Colors.with_opacity(0.25, theme.PRIMARY),
                offset=ft.Offset(0, 3),
            ),
        )

        card_content = ft.Column(
            tight=True,
            spacing=18,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                # Logo
                ft.Container(
                    width=64,
                    height=64,
                    bgcolor=theme.PRIMARY,
                    border_radius=16,
                    alignment=ft.alignment.center,
                    shadow=ft.BoxShadow(
                        spread_radius=0,
                        blur_radius=16,
                        color=ft.Colors.with_opacity(0.3, theme.PRIMARY),
                        offset=ft.Offset(0, 6),
                    ),
                    content=ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=theme.TEXT_WHITE, size=34),
                ),
                # Titles
                ft.Column(
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("AI-Buddy", size=28, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                        ft.Text("Trợ lý ảo hỗ trợ lập trình viên onboarding", size=13, color=theme.TEXT_MUTED),
                    ],
                ),
                ft.Container(height=2),
                # Form inputs
                ft.Column(
                    spacing=12,
                    controls=[
                        self.email_input,
                        self.password_input,
                        self.error_text,
                        self.login_btn,
                    ],
                ),
            ],
        )

        login_card = ft.Container(
            width=460,
            padding=32,
            bgcolor=theme.SURFACE,
            border=ft.border.all(1, theme.BORDER),
            border_radius=20,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=30,
                color=ft.Colors.with_opacity(0.08, "#000000"),
                offset=ft.Offset(0, 10),
            ),
            content=card_content,
        )

        # Background with soft glow circles
        glow_circle1 = ft.Container(
            width=360,
            height=360,
            border_radius=180,
            bgcolor=ft.Colors.with_opacity(0.4, theme.PRIMARY_BG),
            left=100,
            top=60,
        )
        glow_circle2 = ft.Container(
            width=380,
            height=380,
            border_radius=190,
            bgcolor=ft.Colors.with_opacity(0.35, theme.PURPLE_BG),
            right=120,
            bottom=60,
        )

        super().__init__(
            expand=True,
            bgcolor=theme.BG,
            content=ft.Stack(
                expand=True,
                controls=[
                    glow_circle1,
                    glow_circle2,
                    ft.Container(
                        expand=True,
                        alignment=ft.alignment.center,
                        content=login_card,
                    ),
                ],
            ),
        )

    def _clear_error(self, _=None) -> None:
        if self.error_text.visible:
            self.error_text.visible = False
            self.error_text.value = ""
            if self.page:
                self.error_text.update()

    def _set_loading(self, loading: bool) -> None:
        self.login_spinner.visible = loading
        self.login_btn_text.value = "Đang xác thực..." if loading else "Đăng nhập vào hệ thống"
        if self.page:
            self.login_spinner.update()
            self.login_btn_text.update()

    def _submit(self, _=None) -> None:
        email = (self.email_input.value or "").strip()
        password = (self.password_input.value or "").strip()
        if not email:
            self.error_text.value = "⚠️ Vui lòng nhập địa chỉ email tài khoản."
            self.error_text.visible = True
            if self.page:
                self.error_text.update()
            return

        def work() -> None:
            self._set_loading(True)
            try:
                user = self.ctx.login(email, password=password)
                self.error_text.visible = False
                self.error_text.value = ""
                self.on_login(user)
            except ApiError as exc:
                self.error_text.value = f"❌ {exc}"
                self.error_text.visible = True
                if self.page:
                    self.error_text.update()
            except Exception as exc:
                self.error_text.value = f"❌ Không thể xác thực tài khoản: {exc}"
                self.error_text.visible = True
                if self.page:
                    self.error_text.update()
            finally:
                self._set_loading(False)

        if self.page:
            self.page.run_thread(work)
        else:
            work()
