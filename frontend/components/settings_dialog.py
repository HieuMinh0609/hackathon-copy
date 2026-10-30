"""Hộp thoại Cài đặt (Settings Dialog) cho Workspace."""
from __future__ import annotations

from typing import Any

import flet as ft

from frontend.context import FrontendContext
from frontend import theme


def open_settings_dialog(
    page: ft.Page,
    ctx: FrontendContext,
    current_user: dict[str, Any] | None = None,
) -> None:
    curr_user = current_user or {}
    level = str(curr_user.get("permission") or curr_user.get("level") or "").strip().upper()
    is_admin = level == "TEAM_LEAD" or bool(curr_user.get("is_team_lead", False))
    if not is_admin:
        if ctx.notifier:
            ctx.notifier.warning("Chỉ TEAM_LEAD mới có quyền truy cập Cài đặt hệ thống.")
        return

    s = ctx.settings
    field_style = dict(
        border_radius=10,
        border_color=theme.BORDER,
        focused_border_color=theme.PRIMARY,
        bgcolor=theme.SURFACE,
        text_size=13,
        height=44,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
    )

    role_dropdown = ft.Dropdown(
        label="Vai trò của bạn",
        value=s.user_role,
        options=[ft.dropdown.Option(k, v) for k, v in s.roles.items()],
        **field_style,
    )
    base_url_input = ft.TextField(label="Ollama URL", value=s.ollama_base_url, **field_style)
    llm_model_input = ft.TextField(label="LLM model", value=s.llm_model, **field_style)
    embed_model_input = ft.TextField(label="Embedding model", value=s.embedding_model, **field_style)

    ollama_status = ft.Text("", size=12)
    db_status = ft.Text("", size=12)

    def close_dlg(_=None) -> None:
        page.close(dlg)

    def save_settings(_=None) -> None:
        if not is_admin:
            if ctx.notifier:
                ctx.notifier.error("Chỉ TEAM_LEAD mới có quyền thay đổi Cài đặt hệ thống.")
            return
        s.ollama_base_url = base_url_input.value.strip()
        s.llm_model = llm_model_input.value.strip()
        s.embedding_model = embed_model_input.value.strip()
        s.user_role = role_dropdown.value
        s.save_user_overrides()
        ctx.notifier.success("Đã lưu cài đặt thành công.")
        close_dlg()

    def test_ollama(_=None) -> None:
        s.ollama_base_url = base_url_input.value.strip()
        s.llm_model = llm_model_input.value.strip()
        s.embedding_model = embed_model_input.value.strip()

        def work() -> None:
            status = ctx.ollama_status()
            if status["running"]:
                models = status["models"]
                missing = [m for m in (s.llm_model, s.embedding_model) if not any(x.split(":")[0] == m.split(":")[0] for x in models)]
                if missing:
                    ollama_status.value = f"⚠️ Sẵn sàng nhưng thiếu model: {', '.join(missing)}"
                    ollama_status.color = theme.WARN
                else:
                    ollama_status.value = f"✅ Kết nối tốt ({len(models)} models)"
                    ollama_status.color = theme.OK
            else:
                ollama_status.value = "❌ Không kết nối được Ollama"
                ollama_status.color = theme.ERR
            if dlg.page:
                ollama_status.update()

        ollama_status.value = "Đang kiểm tra…"
        ollama_status.color = theme.TEXT_MUTED
        ollama_status.update()
        page.run_thread(work)

    def test_db(_=None) -> None:
        def work() -> None:
            status = ctx.database_status()
            ok, msg = status["ok"], status["message"]
            db_status.value = ("✅ " if ok else "❌ ") + msg
            db_status.color = theme.OK if ok else theme.ERR
            if dlg.page:
                db_status.update()

        db_status.value = "Đang kiểm tra…"
        db_status.color = theme.TEXT_MUTED
        db_status.update()
        page.run_thread(work)

    content = ft.Container(
        width=480,
        content=ft.Column(
            tight=True,
            spacing=16,
            controls=[
                ft.Text("CẤU HÌNH OLLAMA & MÔ HÌNH", size=12, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                base_url_input,
                ft.Row([ft.Container(llm_model_input, expand=True), ft.Container(embed_model_input, expand=True)], spacing=10),
                role_dropdown,
                ft.Row(
                    [
                        ft.OutlinedButton("Kiểm tra Ollama", icon=ft.Icons.NETWORK_CHECK, on_click=test_ollama),
                        ollama_status,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
                ft.Divider(color=theme.BORDER, height=1),
                ft.Text("DATABASE (PostgreSQL)", size=12, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                ft.Text(s.database_description, size=12, color=theme.TEXT_MUTED, selectable=True),
                ft.Row(
                    [
                        ft.OutlinedButton("Kiểm tra kết nối DB", icon=ft.Icons.STORAGE, on_click=test_db),
                        db_status,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
            ],
        ),
    )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text("Cài đặt hệ thống", size=18, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                ft.IconButton(ft.Icons.CLOSE_ROUNDED, icon_size=20, on_click=close_dlg),
            ],
        ),
        content=content,
        actions=[
            ft.TextButton("Đóng", on_click=close_dlg),
            ft.FilledButton("Lưu thay đổi", icon=ft.Icons.SAVE_OUTLINED, on_click=save_settings),
        ],
        actions_padding=ft.padding.symmetric(horizontal=16, vertical=12),
    )
    page.open(dlg)
