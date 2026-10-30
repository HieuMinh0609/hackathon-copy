"""Trang checklist onboarding."""
from __future__ import annotations

import flet as ft

from frontend.context import FrontendContext
from frontend import theme
from frontend.components.checklist_card import ChecklistCard
from frontend.components.confirm_dialog import confirm_install_dialog
from frontend.components.progress_card import ProgressCard


class ChecklistPage(ft.Column):
    def __init__(self, ctx: FrontendContext) -> None:
        self.ctx = ctx
        self.progress_card = ProgressCard()
        self.list_view = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        self.status_text = ft.Text("", size=12, color=theme.MUTED)
        self.run_btn = ft.FilledButton("Kiểm tra tất cả", icon=ft.Icons.PLAY_ARROW_ROUNDED, on_click=self._on_run_all)
        super().__init__(
            expand=True,
            spacing=14,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text("Checklist trước khi join dự án", size=24, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                        ft.Row(
                            spacing=8,
                            controls=[
                                self.run_btn,
                                ft.OutlinedButton("Xuất báo cáo", icon=ft.Icons.FILE_DOWNLOAD_OUTLINED, on_click=self._on_export),
                                ft.IconButton(ft.Icons.RESTART_ALT, tooltip="Đặt lại", on_click=self._on_reset),
                            ],
                        ),
                    ],
                ),
                self.progress_card,
                self.status_text,
                self.list_view,
            ],
        )

    def did_mount(self) -> None:
        self.refresh()

    # ---------- render ----------
    def refresh(self) -> None:
        svc = self.ctx.checklist
        controls: list[ft.Control] = []
        for cat in svc.categories():
            controls.append(ft.Text(cat.upper(), size=12, weight=ft.FontWeight.BOLD, color=theme.ACCENT, style=ft.TextStyle(letter_spacing=1.2)))
            for item in svc.list_items(cat):
                can_install = (item.check_type or "").upper() == "SOFTWARE" and self.ctx.verification.install_plan(item) is not None
                controls.append(ChecklistCard(item, can_install, self._on_verify, self._on_install, self._on_toggle))
        self.list_view.controls = controls
        self.progress_card.set_progress(svc.progress())
        if self.page:
            self.list_view.update()

    def _busy(self, busy: bool, text: str = "") -> None:
        self.run_btn.disabled = busy
        self.status_text.value = text
        if self.page:
            self.run_btn.update()
            self.status_text.update()

    # ---------- handlers ----------
    def _on_run_all(self, _=None) -> None:
        self.page.run_thread(self._run_all)

    def _run_all(self) -> None:
        self._busy(True, "Đang kiểm tra…")
        self.ctx.verification.verify_all(
            on_progress=lambda i, n, r: self._busy(True, f"Đang kiểm tra {i}/{n}…")
        )
        self._busy(False, "Hoàn tất kiểm tra.")
        self.refresh()

    def _on_verify(self, key: str) -> None:
        def work() -> None:
            self._busy(True, "Đang kiểm tra…")
            self.ctx.verification.verify_key(key)
            self._busy(False)
            self.refresh()

        self.page.run_thread(work)

    def _on_toggle(self, key: str, done: bool) -> None:
        user_email = getattr(self.ctx.client, "user_email", None)
        self.ctx.checklist.set_manual_done(key, done, user_email=user_email)
        self.refresh()

    def _on_install(self, key: str) -> None:
        item = self.ctx.checklist.get_item(key)
        plan = self.ctx.verification.install_plan(item) if item else None
        if plan is None:
            self.ctx.notifier.warning("Chưa hỗ trợ cài tự động mục này trên hệ điều hành hiện tại.")
            return

        def work() -> None:
            self._busy(True, f"Đang cài {plan.software}…")
            self.ctx.verification.run_install(plan, key)
            self._busy(False)
            self.refresh()

        confirm_install_dialog(self.page, plan, lambda: self.page.run_thread(work))

    def _on_export(self, _=None) -> None:
        path = self.ctx.checklist.export_report()
        self.ctx.notifier.success(f"Đã xuất báo cáo: {path}")

    def _on_reset(self, _=None) -> None:
        self.ctx.checklist.reset()
        self.refresh()
