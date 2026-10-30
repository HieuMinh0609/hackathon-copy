"""AI Buddy - Điểm vào ứng dụng Flet Desktop (Clean Modern Light Theme)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import flet as ft

from frontend.context import FrontendContext, Notification, build_frontend_context
from frontend import theme
from frontend.pages.dashboard_page import DashboardPage
from frontend.pages.connection_page import ConnectionPage
from frontend.pages.login_page import LoginPage
from frontend.pages.workspace_page import WorkspacePage
from frontend.server_config import ServerConfigStore

logger = logging.getLogger("frontend")

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
# Font đóng gói sẵn trong frontend/assets/fonts (offline, không tải từ Google Fonts)
FONT_FAMILY = "BeVietnamPro"

_SNACK_COLORS = {
    "info": theme.PRIMARY,
    "success": theme.EMERALD,
    "warning": theme.WARN,
    "error": theme.ERR,
}


def main(page: ft.Page) -> None:
    logger.info("[FE] Khoi dong Flet Desktop UI")
    server_config = ServerConfigStore()
    ctx: FrontendContext = build_frontend_context(server_config.load())

    page.title = "AI-Buddy - Trợ lý ảo hỗ trợ lập trình viên"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.fonts = {FONT_FAMILY: "fonts/BeVietnamPro-Regular.ttf"}
    page.theme = ft.Theme(
        color_scheme_seed=theme.PRIMARY,
        use_material3=True,
        font_family=FONT_FAMILY,
    )
    page.bgcolor = theme.BG
    page.padding = 0
    page.window.width = 1260
    page.window.height = 820
    page.window.min_width = 980
    page.window.min_height = 640

    # SnackBar handler
    def show_snack(note: Notification) -> None:
        if not page:
            return
        logger.info("[FE THONG BAO %s] %s", note.level.upper(), note.message)
        bg_col = _SNACK_COLORS.get(note.level, theme.PRIMARY)
        page.open(
            ft.SnackBar(
                content=ft.Text(note.message, color=theme.TEXT_WHITE, size=13, weight=ft.FontWeight.W_500),
                bgcolor=bg_col,
                behavior=ft.SnackBarBehavior.FLOATING,
                margin=ft.margin.all(16),
                duration=3500,
            )
        )

    ctx.notifier.subscribe(show_snack)

    # State Router
    app_state: dict[str, Any] = {
        "view": "connection",  # "connection" | "login" | "dashboard" | "workspace"
        "username": "Developer",
        "user": None,
        "project": None,
        "projects": [],
        "navigation_token": 0,
    }

    container_root = ft.Container(expand=True)

    def build_dashboard(projects: list[dict[str, Any]]) -> DashboardPage:
        return DashboardPage(
            ctx=ctx,
            username=app_state["username"],
            projects=projects,
            on_select_project=lambda selected: navigate_to("workspace", selected),
            on_logout=lambda: (ctx.logout(), navigate_to("login")),
            user=app_state.get("user"),
            load_projects_on_mount=False,
        )

    def refresh_dashboard_projects(navigation_token: int) -> None:
        """Tải dữ liệu qua HTTP ở background để nút đóng workspace không chặn UI."""
        user_info = app_state.get("user") or {}
        try:
            projects = ctx.projects.list_projects(user_email=user_info.get("email"))
        except Exception as exc:
            ctx.notifier.error(f"Không tải được danh sách dự án: {exc}")
            return

        if app_state["view"] != "dashboard" or app_state["navigation_token"] != navigation_token:
            return
        app_state["projects"] = projects
        container_root.content = build_dashboard(projects)
        if container_root.page:
            container_root.update()

    def navigate_to(view: str, project: dict[str, Any] | None = None) -> None:
        logger.info("[FE CHUYEN MAN HINH] -> %s", view)
        app_state["navigation_token"] += 1
        navigation_token = app_state["navigation_token"]
        app_state["view"] = view
        if project is not None:
            app_state["project"] = project
        elif view == "dashboard":
            app_state["project"] = None

        if view == "connection":
            container_root.content = ConnectionPage(
                client=ctx.client,
                config_store=server_config,
                on_connected=lambda _: navigate_to("login"),
            )
        elif view == "login":
            container_root.content = LoginPage(
                ctx=ctx,
                on_login=lambda user: on_logged_in(user),
            )
        elif view == "dashboard":
            container_root.content = build_dashboard(app_state["projects"])
        elif view == "workspace":
            container_root.content = WorkspacePage(
                ctx=ctx,
                project=app_state["project"],
                user=app_state["user"],
                on_back=lambda: navigate_to("dashboard"),
            )
        page.update()
        if view == "dashboard":
            page.run_thread(refresh_dashboard_projects, navigation_token)

    def on_logged_in(user: dict[str, Any] | str) -> None:
        app_state["projects"] = []
        if isinstance(user, dict):
            app_state["user"] = user
            app_state["username"] = user.get("name") or user.get("email", "Developer")
            ctx.client.set_user_email(user.get("email"))
            logger.info("[FE DANG NHAP] %s (%s)", app_state["username"], user.get("email"))
        else:
            app_state["username"] = user or "Developer"
            logger.info("[FE DANG NHAP] %s", app_state["username"])
        navigate_to("dashboard")

    # Chỉ hiển thị Login sau khi backend đã phản hồi health check.
    navigate_to("connection")
    page.add(container_root)


if __name__ == "__main__":
    ft.app(target=main, assets_dir=str(ASSETS_DIR))
