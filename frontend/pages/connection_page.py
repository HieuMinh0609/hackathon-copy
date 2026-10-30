"""Màn hình chờ backend sẵn sàng trước khi cho phép đăng nhập."""
from __future__ import annotations

import logging
import math
from typing import Callable

import flet as ft

from frontend import theme
from frontend.api_client import ApiClient
from frontend.server_config import ServerConfigStore, normalize_server_url, probe_until_connected


logger = logging.getLogger("frontend.connection")
CONNECTION_TIMEOUT_SECONDS = 15.0
RETRY_INTERVAL_SECONDS = 1.0


class ConnectionPage(ft.Container):
    def __init__(
        self,
        client: ApiClient,
        config_store: ServerConfigStore,
        on_connected: Callable[[str], None],
    ) -> None:
        self.client = client
        self.config_store = config_store
        self.on_connected = on_connected
        self._attempt_id = 0

        self.icon_box = ft.Container(
            width=68,
            height=68,
            bgcolor=theme.PRIMARY_BG,
            border_radius=18,
            alignment=ft.alignment.center,
            content=ft.Icon(ft.Icons.CLOUD_SYNC_ROUNDED, color=theme.PRIMARY, size=36),
        )
        self.title = ft.Text("Đang kết nối máy chủ", size=24, weight=ft.FontWeight.BOLD, color=theme.TEXT)
        self.status = ft.Text(
            "AI-Buddy đang kiểm tra trạng thái server...",
            size=13,
            color=theme.TEXT_MUTED,
            text_align=ft.TextAlign.CENTER,
        )
        self.spinner = ft.ProgressRing(width=28, height=28, stroke_width=3, color=theme.PRIMARY)
        self.server_label = ft.Text("", size=12, color=theme.TEXT_LIGHT, text_align=ft.TextAlign.CENTER)
        self.server_input = ft.TextField(
            label="Địa chỉ máy chủ",
            hint_text="http://127.0.0.1:8765",
            prefix_icon=ft.Icons.DNS_OUTLINED,
            value=self.client.base_url,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=10,
            text_size=14,
            on_submit=self._retry,
        )
        self.error_text = ft.Text("", size=12, color=theme.ERR, visible=False)
        self.retry_button = ft.FilledButton(
            "Kết nối lại",
            icon=ft.Icons.REFRESH_ROUNDED,
            bgcolor=theme.PRIMARY,
            on_click=self._retry,
        )
        self.default_button = ft.OutlinedButton(
            "Dùng địa chỉ mặc định",
            icon=ft.Icons.HOME_OUTLINED,
            on_click=self._use_default,
        )
        self.configure_button = ft.TextButton(
            "Cài đặt địa chỉ máy chủ",
            icon=ft.Icons.SETTINGS_ETHERNET_ROUNDED,
            on_click=self._show_configuration,
        )
        self.configuration = ft.Column(
            spacing=12,
            visible=False,
            controls=[
                self.server_input,
                self.error_text,
                ft.Row(
                    [self.default_button, self.retry_button],
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                ),
            ],
        )

        card = ft.Container(
            width=500,
            padding=36,
            bgcolor=theme.SURFACE,
            border=ft.border.all(1, theme.BORDER),
            border_radius=20,
            shadow=ft.BoxShadow(
                blur_radius=30,
                color=ft.Colors.with_opacity(0.08, "#000000"),
                offset=ft.Offset(0, 10),
            ),
            content=ft.Column(
                tight=True,
                spacing=16,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self.icon_box,
                    self.title,
                    self.status,
                    self.spinner,
                    self.server_label,
                    self.configure_button,
                    self.configuration,
                ],
            ),
        )
        super().__init__(
            expand=True,
            bgcolor=theme.BG,
            alignment=ft.alignment.center,
            content=card,
        )

    def did_mount(self) -> None:
        self._start_connection(self.client.base_url)

    def will_unmount(self) -> None:
        self._attempt_id += 1

    def _update(self) -> None:
        if self.page:
            self.update()

    def _set_loading(self, server_url: str) -> None:
        self.icon_box.bgcolor = theme.PRIMARY_BG
        self.icon_box.content = ft.Icon(ft.Icons.CLOUD_SYNC_ROUNDED, color=theme.PRIMARY, size=36)
        self.title.value = "Đang kết nối máy chủ"
        self.status.value = f"Đang chờ server phản hồi, tối đa {int(CONNECTION_TIMEOUT_SECONDS)} giây..."
        self.status.color = theme.TEXT_MUTED
        self.server_label.value = server_url
        self.spinner.visible = True
        self.configure_button.visible = True
        self.configuration.visible = False
        self.error_text.visible = False
        self.retry_button.disabled = True
        self._update()

    def _show_failure(self, message: str) -> None:
        self.icon_box.bgcolor = theme.ERR_BG
        self.icon_box.content = ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, color=theme.ERR, size=36)
        self.title.value = "Không kết nối được máy chủ"
        self.status.value = message
        self.status.color = theme.ERR
        self.spinner.visible = False
        self.configure_button.visible = False
        self.configuration.visible = True
        self.retry_button.disabled = False
        self._update()

    def _show_configuration(self, _=None) -> None:
        self._attempt_id += 1
        self._show_failure("Hãy kiểm tra hoặc thay đổi địa chỉ máy chủ, sau đó thử kết nối lại.")

    def _use_default(self, _=None) -> None:
        self.server_input.value = self.config_store.default_url
        self._retry()

    def _retry(self, _=None) -> None:
        try:
            server_url = normalize_server_url(self.server_input.value or "")
        except ValueError as exc:
            self.error_text.value = str(exc)
            self.error_text.visible = True
            self._update()
            return
        self.server_input.value = server_url
        self.client.set_base_url(server_url)
        self._start_connection(server_url)

    def _start_connection(self, server_url: str) -> None:
        self._attempt_id += 1
        attempt_id = self._attempt_id
        self._set_loading(server_url)

        def work() -> None:
            result = probe_until_connected(
                check=lambda: self.client.health_check(timeout=1.5),
                timeout_seconds=CONNECTION_TIMEOUT_SECONDS,
                retry_interval=RETRY_INTERVAL_SECONDS,
                should_stop=lambda: attempt_id != self._attempt_id,
                on_retry=lambda remaining: self._show_remaining(attempt_id, remaining),
            )
            if attempt_id != self._attempt_id:
                return
            if result.connected:
                try:
                    self.config_store.save(server_url)
                except OSError as exc:
                    logger.warning("Khong luu duoc dia chi server: %s", exc)
                logger.info("Da ket noi server %s sau %d lan thu", server_url, result.attempts)
                self.on_connected(server_url)
                return
            self._show_failure(
                f"Server không phản hồi sau {int(CONNECTION_TIMEOUT_SECONDS)} giây. "
                "Kiểm tra server, mạng nội bộ hoặc nhập địa chỉ khác."
            )

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    def _show_remaining(self, attempt_id: int, remaining: float) -> None:
        if attempt_id != self._attempt_id:
            return
        seconds = max(0, math.ceil(remaining))
        self.status.value = f"Chưa nhận được phản hồi. Còn {seconds} giây trước khi hết thời gian chờ..."
        self._update()
