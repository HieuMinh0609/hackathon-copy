"""Màn hình Bảng điều khiển (DashboardScreen) - Danh sách dự án gần đây & Danh mục ứng dụng cần cài đặt."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Any, Callable

import flet as ft

from frontend import theme
from frontend.models import AppItem

_PROJECT_STYLES = (
    (ft.Icons.STORAGE_ROUNDED, theme.EMERALD, theme.EMERALD_BG),
    (ft.Icons.AUTO_AWESOME_ROUNDED, theme.PURPLE, theme.PURPLE_BG),
    (ft.Icons.TERMINAL_ROUNDED, theme.PRIMARY, theme.PRIMARY_BG),
)

_CATEGORY_ICONS: dict[str, tuple[str, str, str]] = {
    "Môi trường lập trình": (ft.Icons.TERMINAL_ROUNDED, theme.PRIMARY, theme.PRIMARY_BG),
    "Quản lý mã nguồn": (ft.Icons.MERGE_TYPE_ROUNDED, theme.PURPLE, theme.PURPLE_BG),
    "Container & Hạ tầng": (ft.Icons.VIEW_IN_AR_ROUNDED, theme.EMERALD, theme.EMERALD_BG),
    "Môi trường Web & Tooling": (ft.Icons.WEB_ROUNDED, theme.PRIMARY, theme.PRIMARY_BG),
    "Công cụ lập trình": (ft.Icons.CODE_ROUNDED, theme.PURPLE, theme.PURPLE_BG),
    "Cơ sở dữ liệu": (ft.Icons.STORAGE_ROUNDED, theme.EMERALD, theme.EMERALD_BG),
    "Trí tuệ nhân tạo": (ft.Icons.AUTO_AWESOME_ROUNDED, theme.PRIMARY, theme.PRIMARY_BG),
}

_PROJECT_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def _format_bytes(size: int | None) -> str:
    if not size or size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    val = float(size)
    for u in units:
        if val < 1024.0 or u == units[-1]:
            return f"{val:.1f} {u}" if u != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} GB"


def _format_deadline(value: str | None) -> str:
    if not value:
        return "Chưa bắt đầu"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)[:10]


def _clean_version_tag(ver_str: str | None) -> str:
    """Chuẩn hóa chuỗi phiên bản để tạo tên thư mục hoặc tên tệp (ví dụ '>= 3.11' -> '3.11')."""
    if not ver_str:
        return ""
    v = str(ver_str).strip()
    v = re.sub(r"^[><=^~vV\s]+", "", v)
    v = re.sub(r'[\\/:*?"<>|\s]', "_", v)
    v = v.strip("._-")
    return v.lower()


def _resolve_fixed_download_dir() -> Path:
    """Tự động xác định và đảm bảo thư mục lưu trữ cố định hoạt động trên mọi máy:
    1. data/downloads (cố định trong dự án)
    2. ~/Downloads/AI_Buddy_Installers (thư mục người dùng cá nhân)
    3. <tempdir>/ai_buddy_downloads (thư mục tạm hệ thống luôn ghi được)
    """
    import tempfile
    candidates = [
        Path("data/downloads").resolve(),
        (Path.home() / "Downloads" / "AI_Buddy_Installers").resolve(),
        (Path(tempfile.gettempdir()) / "ai_buddy_downloads").resolve(),
    ]
    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            # Kiểm tra quyền ghi thực tế bằng file tạm
            test_f = p / ".write_test"
            test_f.write_text("ok", encoding="utf-8")
            test_f.unlink(missing_ok=True)
            return p
        except Exception:
            continue
    return Path.cwd().resolve()


class DashboardPage(ft.Container):
    def __init__(
        self,
        username: str,
        projects: list[dict[str, Any]],
        on_select_project: Callable[[dict[str, Any]], None],
        on_logout: Callable[[], None],
        ctx: Any = None,
        user: dict[str, Any] | None = None,
        load_projects_on_mount: bool = True,
    ) -> None:
        self.ctx = ctx
        self.user = user or {
            "name": username or "Developer",
            "email": "alex.carter@example.com",
            "permission": "TEAM_LEAD",
            "level": "TEAM_LEAD",
            "is_senior": True,
        }
        permission = str(self.user.get("permission", self.user.get("level", "")) or "").strip().upper()
        self.is_admin = permission == "TEAM_LEAD" or bool(self.user.get("is_team_lead", False))
        self.username = username or self.user.get("name") or "Developer"
        self.projects = projects
        self.can_manage_templates = (
            self.is_admin
            or bool(self.user.get("is_template_manager", False))
            or any(bool(project.get("can_manage_template", False)) for project in projects)
        )
        self.is_senior = self.can_manage_templates
        self.can_create_projects = self.is_admin
        self.on_select_project = on_select_project
        self.on_logout = on_logout
        self._load_projects_on_mount = load_projects_on_mount
        self._project_actions_in_progress: set[str] = set()

        # Trạng thái tìm kiếm & lọc App Catalog
        self._search_query = ""
        self._selected_category = "Tất cả"
        self._apps: list[AppItem] = []
        self._editing_app: AppItem | None = None
        self._edit_path_field: ft.TextField | None = None
        self._target_path_field: ft.TextField | None = None
        self._add_name_field: ft.TextField | None = None
        self._add_code_field: ft.TextField | None = None
        self._edit_dlg: ft.AlertDialog | None = None
        self._add_dlg: ft.AlertDialog | None = None

        # File pickers: chọn đường dẫn cục bộ, tải về máy và tải lên máy chủ
        self.installer_file_picker = ft.FilePicker(on_result=self._on_installer_file_picked)
        self.save_installer_picker = ft.FilePicker(on_result=self._on_save_destination_picked)
        self.upload_installer_picker = ft.FilePicker(on_result=self._on_upload_source_picked)
        self._downloading_app: AppItem | None = None
        self._uploading_app: AppItem | None = None
        self._pending_upload_path: str = ""
        self._pending_upload_name: str = ""
        self._confirm_upload_dlg: ft.AlertDialog | None = None

        level_label = self.user.get("permission", self.user.get("level", "MEMBER"))
        # Header
        header = ft.Container(
            bgcolor=theme.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.BORDER)),
            padding=ft.padding.symmetric(horizontal=32, vertical=16),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=42,
                                height=42,
                                bgcolor=theme.PRIMARY,
                                border_radius=10,
                                alignment=ft.alignment.center,
                                shadow=ft.BoxShadow(
                                    spread_radius=0,
                                    blur_radius=8,
                                    color=ft.Colors.with_opacity(0.2, theme.PRIMARY),
                                    offset=ft.Offset(0, 3),
                                ),
                                content=ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=theme.TEXT_WHITE, size=22),
                            ),
                            ft.Column(
                                spacing=2,
                                tight=True,
                                controls=[
                                    ft.Text("AI-Buddy Dashboard", size=18, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                    ft.Row(
                                        spacing=6,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.Text(f"Xin chào, {self.username}", size=12, color=theme.TEXT_MUTED),
                                            ft.Container(
                                                content=ft.Row(
                                                    spacing=4,
                                                    tight=True,
                                                    controls=[
                                                        ft.Icon(
                                                            ft.Icons.VERIFIED_USER_ROUNDED if self.is_senior else ft.Icons.ACCOUNT_CIRCLE_ROUNDED,
                                                            size=12,
                                                            color=theme.PRIMARY if self.is_senior else theme.TEXT_MUTED,
                                                        ),
                                                        ft.Text(
                                                            level_label,
                                                            size=10,
                                                            weight=ft.FontWeight.W_600,
                                                            color=theme.PRIMARY if self.is_senior else theme.TEXT_MUTED,
                                                        ),
                                                    ],
                                                ),
                                                bgcolor=theme.PRIMARY_BG if self.is_senior else theme.SURFACE_ALT,
                                                border=ft.border.all(1, theme.PRIMARY_BORDER if self.is_senior else theme.BORDER),
                                                border_radius=10,
                                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                                tooltip=f"Cấp bậc: {level_label} ({'TEAM_LEAD: quản lý hệ thống' if self.is_admin else 'Thành viên dự án'})",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        content=ft.Row(
                            spacing=6,
                            controls=[
                                ft.Icon(ft.Icons.LOGOUT_ROUNDED, size=16, color=theme.TEXT_MUTED),
                                ft.Text("Đăng xuất", size=13, weight=ft.FontWeight.W_500, color=theme.TEXT_MUTED),
                            ],
                        ),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        border_radius=8,
                        border=ft.border.all(1, theme.BORDER),
                        on_click=lambda _: self.on_logout(),
                        ink=True,
                        tooltip="Đăng xuất khỏi hệ thống",
                    ),
                ],
            ),
        )

        # Trạng thái tab (0: Dự án gần đây, 1: Ứng dụng & Cài đặt)
        self._active_tab_index = 0
        self._prevent_project_select = False

        # Projects Grid Container & Dynamic Render
        self._projects_grid_container = ft.Container()
        self._render_projects_grid()

        # Tab 1 View: Dự án gần đây
        self._projects_view = ft.Column(
            spacing=24,
            tight=True,
            visible=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=4,
                            tight=True,
                            controls=[
                                ft.Text("Dự án gần đây", size=24, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                ft.Text("Chọn dự án để bắt đầu phiên làm việc cùng AI hoặc bấm template icon / thành viên để quản lý", size=14, color=theme.TEXT_MUTED),
                            ],
                        ),
                        ft.FilledButton(
                            "Tạo dự án mới",
                            icon=ft.Icons.ADD_ROUNDED if self.can_create_projects else ft.Icons.LOCK_OUTLINE_ROUNDED,
                            disabled=not self.can_create_projects,
                            tooltip=(
                                "Tạo dự án / Onboarding Template mới"
                                if self.can_create_projects
                                else "Chỉ Team Lead được tạo dự án"
                            ),
                            on_click=lambda _: self._open_create_project_dialog(),
                        ),
                    ],
                ),
                self._projects_grid_container,
            ],
        )

        # Tab 2 View: Danh mục ứng dụng & cài đặt
        self._apps_view = self._build_app_catalog_section()
        self._apps_view.visible = False

        # Content container chứa cả 2 view (ẩn hiện theo tab)
        self._content_container = ft.Column(
            spacing=0,
            controls=[
                self._projects_view,
                self._apps_view,
            ],
        )

        # Project Lead cần truy cập App Catalog để tải bộ cài; cấu hình hệ thống
        # và thao tác xóa vẫn được khóa riêng cho Team Lead.
        tab_buttons = [
            self._create_tab_button(0, "Dự án gần đây", ft.Icons.SPACE_DASHBOARD_OUTLINED),
        ]
        if self.can_manage_templates:
            tab_buttons.append(
                self._create_tab_button(1, "Ứng dụng & Cài đặt", ft.Icons.DNS_OUTLINED)
            )
        self._tab_bar_row = ft.Row(
            spacing=28,
            controls=tab_buttons,
        )

        tab_bar_container = ft.Container(
            bgcolor=theme.BG,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.BORDER)),
            padding=ft.padding.only(left=40, right=40, top=14, bottom=0),
            content=self._tab_bar_row,
        )

        # Main Scrollable Body với khoảng đệm an toàn tránh thanh cuộn đè lên nội dung
        main_body = ft.Container(
            expand=True,
            padding=ft.padding.only(left=40, right=20, top=20, bottom=24),
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
                controls=[
                    ft.Container(
                        padding=ft.padding.only(right=18, bottom=36),
                        content=self._content_container,
                    ),
                ],
            ),
        )

        super().__init__(
            expand=True,
            bgcolor=theme.BG,
            content=ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    header,
                    tab_bar_container,
                    main_body,
                ],
            ),
        )

    def _run_project_action(self, key: str, message: str, action: Callable[[], None]) -> None:
        """Hiển thị tiến trình thật và chặn gửi lặp cùng một thao tác dự án."""
        if key in self._project_actions_in_progress:
            return
        self._project_actions_in_progress.add(key)

        if not self.page:
            try:
                action()
            finally:
                self._project_actions_in_progress.discard(key)
            return

        active_page = self.page
        loading_dialog = ft.AlertDialog(
            modal=True,
            content=ft.Row(
                controls=[
                    ft.ProgressRing(width=22, height=22, stroke_width=2.5, color=theme.PRIMARY),
                    ft.Text(message, size=13, weight=ft.FontWeight.W_500, color=theme.TEXT),
                ],
                spacing=14,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        active_page.open(loading_dialog)

        def work() -> None:
            try:
                action()
            except Exception as exc:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Thao tác dự án thất bại: {exc}")
            finally:
                self._project_actions_in_progress.discard(key)
                try:
                    active_page.close(loading_dialog)
                except Exception:
                    pass

        try:
            active_page.run_thread(work)
        except Exception:
            self._project_actions_in_progress.discard(key)
            active_page.close(loading_dialog)
            raise

    def _create_tab_button(self, index: int, title: str, icon: str) -> ft.Container:
        is_active = (self._active_tab_index == index)
        color = theme.PRIMARY if is_active else theme.TEXT_MUTED
        indicator_color = theme.PRIMARY if is_active else ft.Colors.TRANSPARENT
        weight = ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500

        return ft.Container(
            padding=ft.padding.only(left=12, right=12, top=8, bottom=12),
            border=ft.border.only(bottom=ft.BorderSide(3, indicator_color)),
            content=ft.Row(
                spacing=8,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=18, color=color),
                    ft.Text(title, size=14, weight=weight, color=color),
                ],
            ),
            ink=True,
            on_click=lambda _, idx=index: self._switch_tab(idx),
        )

    def _switch_tab(self, index: int) -> None:
        if index == 1 and not self.can_manage_templates:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.warning("Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền truy cập phần Ứng dụng & Cài đặt.")
            return
        if self._active_tab_index == index:
            return
        self._active_tab_index = index
        tab_buttons = [
            self._create_tab_button(0, "Dự án gần đây", ft.Icons.SPACE_DASHBOARD_OUTLINED),
        ]
        if self.can_manage_templates:
            tab_buttons.append(
                self._create_tab_button(1, "Ứng dụng & Cài đặt", ft.Icons.DNS_OUTLINED)
            )
        self._tab_bar_row.controls = tab_buttons
        self._projects_view.visible = (self._active_tab_index == 0)
        self._apps_view.visible = (self._active_tab_index == 1)
        if self.page:
            self._tab_bar_row.update()
            self._content_container.update()
            if self._active_tab_index == 1:
                if self._apps:
                    self._render_apps_table()
                self._load_apps()

    def _ensure_pickers_in_overlay(self) -> None:
        """Đảm bảo tất cả FilePicker đều có mặt trong page.overlay của Flet."""
        if self.page:
            changed = False
            for picker in (self.installer_file_picker, self.save_installer_picker, self.upload_installer_picker):
                if picker not in self.page.overlay:
                    self.page.overlay.append(picker)
                    changed = True
            if changed:
                self.page.update()

    def did_mount(self) -> None:
        self._ensure_pickers_in_overlay()
        self._load_apps()
        if self._load_projects_on_mount:
            if self.page:
                self.page.run_thread(self._load_projects)
            else:
                self._load_projects()

    def _load_projects(self) -> None:
        if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "list_projects"):
            try:
                user_email = (self.user or {}).get("email")
                self.projects = self.ctx.projects.list_projects(user_email=user_email)
                self.can_manage_templates = (
                    self.is_admin
                    or bool(self.user.get("is_template_manager", False))
                    or any(bool(project.get("can_manage_template", False)) for project in self.projects)
                )
                self.is_senior = self.can_manage_templates
                self._render_projects_grid()
            except Exception:
                pass

    def _render_projects_grid(self) -> None:
        cards: list[ft.Control] = []
        for index, raw in enumerate(self.projects):
            icon, icon_color, icon_bg = _PROJECT_STYLES[index % len(_PROJECT_STYLES)]
            p = {
                **raw,
                "code": raw.get("code") or raw.get("template_code", ""),
                "name": raw.get("name") or raw.get("template_name", "Dự án"),
                "desc": raw.get("description", "") or "Tài liệu onboarding của dự án.",
                "updated": raw.get("updated_at", "")[:10] or "Đã cấu hình",
                "icon": icon, "icon_color": icon_color, "icon_bg": icon_bg,
            }
            cards.append(self._create_project_card(p))

        if not cards:
            self._projects_grid_container.content = ft.Container(
                bgcolor=theme.SURFACE,
                border=ft.border.all(1, theme.BORDER),
                border_radius=16,
                padding=ft.padding.symmetric(horizontal=24, vertical=36),
                alignment=ft.alignment.center,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                    controls=[
                        ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=48, color=theme.TEXT_LIGHT),
                        ft.Text("Chưa có dự án nào được gán." if not self.is_admin else "Chưa có dự án nào được tạo.", size=15, weight=ft.FontWeight.W_600, color=theme.TEXT),
                        ft.Text("Bạn chưa là thành viên của dự án nào. Vui lòng liên hệ Team Lead để được thêm vào dự án." if not self.is_admin else "Bấm 'Tạo dự án mới' ở trên để thêm dự án đầu tiên vào danh sách.", size=13, color=theme.TEXT_MUTED),
                    ],
                ),
            )
        else:
            self._projects_grid_container.content = ft.ResponsiveRow(
                spacing=20,
                run_spacing=20,
                controls=[
                    ft.Container(c, col={"xs": 12, "md": 6, "lg": 4}) for c in cards
                ],
            )
        try:
            if hasattr(self, "_Control__page") and self.page:
                self._projects_grid_container.update()
        except Exception:
            pass

    def _create_project_card(self, p: dict[str, Any]) -> ft.Container:
        risk_count = int(p.get("risk_count") or 0)
        overdue_count = int(p.get("overdue_count") or 0)
        can_view_risk = True
        return ft.Container(
            bgcolor=theme.SURFACE,
            border=ft.border.all(1, theme.BORDER),
            border_radius=16,
            padding=22,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color=ft.Colors.with_opacity(0.04, "#000000"),
                offset=ft.Offset(0, 3),
            ),
            ink=True,
            on_click=lambda _: self._handle_project_card_click(p),
            content=ft.Column(
                spacing=14,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=44,
                                height=44,
                                bgcolor=p["icon_bg"],
                                border_radius=10,
                                alignment=ft.alignment.center,
                                content=ft.Icon(p["icon"], color=p["icon_color"], size=24),
                                tooltip=f"Xem thông tin dự án [{p['code']}]",
                                ink=True,
                                on_click=lambda e, prj=p: self._on_template_icon_clicked(e, prj),
                            ),
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(p["updated"], size=12, color=theme.TEXT_LIGHT, weight=ft.FontWeight.W_500),
                                    ft.Container(
                                        content=ft.Row(
                                            spacing=4,
                                            tight=True,
                                            controls=[
                                                ft.Icon(ft.Icons.PEOPLE_OUTLINE_ROUNDED, size=14, color=theme.PRIMARY),
                                                ft.Text("Thành viên", size=11, weight=ft.FontWeight.W_600, color=theme.PRIMARY),
                                            ],
                                        ),
                                        padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                        bgcolor=theme.PRIMARY_BG,
                                        border=ft.border.all(1, theme.PRIMARY_BORDER),
                                        border_radius=8,
                                        tooltip=(
                                            f"Quản lý thành viên dự án [{p['code']}]"
                                            if self.is_admin or bool(p.get("can_manage_template", False))
                                            else f"Xem thành viên dự án [{p['code']}] (chỉ đọc)"
                                        ),
                                        ink=True,
                                        on_click=lambda e, prj=p: self._on_template_icon_clicked(e, prj),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Text(
                        p["name"],
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=theme.TEXT,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        p["desc"],
                        size=13,
                        color=theme.TEXT_MUTED,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Icon(ft.Icons.SCHEDULE_ROUNDED, size=15, color=theme.WARN),
                            ft.Text(
                                f"Thời hạn onboarding: {int(p.get('duration_days') or 20)} ngày",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=theme.TEXT_MUTED,
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        visible=can_view_risk and (risk_count > 0 or overdue_count > 0),
                        controls=[
                            ft.Container(
                                visible=risk_count > 0,
                                content=ft.Row(
                                    spacing=4,
                                    tight=True,
                                    controls=[
                                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=14, color=theme.WARN),
                                        ft.Text(f"{risk_count} thành viên có nguy cơ", size=11, weight=ft.FontWeight.W_600, color=theme.WARN),
                                    ],
                                ),
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=theme.WARN_BG,
                                border=ft.border.all(1, theme.WARN_BORDER),
                                border_radius=8,
                            ),
                            ft.Container(
                                visible=overdue_count > 0,
                                content=ft.Row(
                                    spacing=4,
                                    tight=True,
                                    controls=[
                                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, size=14, color=theme.ERR),
                                        ft.Text(f"{overdue_count} thành viên quá hạn", size=11, weight=ft.FontWeight.W_600, color=theme.ERR),
                                    ],
                                ),
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=theme.ERR_BG,
                                border=ft.border.all(1, theme.ERR_BORDER),
                                border_radius=8,
                            ),
                        ],
                    ),
                    ft.Container(
                        padding=ft.padding.only(top=10),
                        border=ft.border.only(top=ft.BorderSide(1, theme.BORDER_LIGHT)),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    "Vào không gian làm việc",
                                    size=13,
                                    weight=ft.FontWeight.W_600,
                                    color=theme.PRIMARY,
                                ),
                                ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=18, color=theme.PRIMARY),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _on_template_icon_clicked(self, e: ft.ControlEvent, prj: dict[str, Any]) -> None:
        self._prevent_project_select = True
        project_code = str(prj.get("code") or prj.get("template_code") or "project")
        self._run_project_action(
            f"members:{project_code}",
            "Đang tải thành viên và vai trò dự án…",
            lambda: self._open_project_members_dialog(prj),
        )

    def _handle_project_card_click(self, p: dict[str, Any]) -> None:
        if getattr(self, "_prevent_project_select", False):
            self._prevent_project_select = False
            return
        project_code = str(p.get("code") or p.get("template_code") or "project")
        self._run_project_action(
            f"open:{project_code}",
            "Đang mở không gian dự án…",
            lambda: self.on_select_project(p),
        )

    def _open_create_project_dialog(self) -> None:
        if not self.can_create_projects:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.error("Chỉ Team Lead mới được tạo dự án.")
            return
        code_input = ft.TextField(
            label="Mã dự án (Template Code, ví dụ: PRJ_FINTECH)",
            hint_text="Chỉ dùng chữ cái, số, dấu '.', '_', '-'",
            text_size=13,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
        )
        name_input = ft.TextField(
            label="Tên dự án",
            hint_text="Ví dụ: Hệ thống Ngân hàng số",
            text_size=13,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
        )
        desc_input = ft.TextField(
            label="Mô tả dự án",
            hint_text="Mô tả mục tiêu và nội dung onboarding của dự án...",
            text_size=13,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            multiline=True,
            max_lines=3,
        )
        role_dropdown = ft.Dropdown(
            label="Vai trò chính (Template Role)",
            value="Backend Developer",
            options=[
                ft.dropdown.Option("Backend Developer"),
                ft.dropdown.Option("Frontend Developer"),
                ft.dropdown.Option("QA Engineer"),
                ft.dropdown.Option("Business Analyst"),
                ft.dropdown.Option("DevOps / Infrastructure"),
                ft.dropdown.Option("Fullstack Developer"),
            ],
            text_size=13,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
        )
        duration_input = ft.TextField(
            label="Thời hạn hoàn thành onboarding (ngày)",
            hint_text="Ví dụ: 20",
            value="20",
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix_text="ngày",
            text_size=13,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
        )
        error_text = ft.Text("", size=12, color=theme.ERR, visible=False)

        def do_create(_):
            code_val = (code_input.value or "").strip().upper()
            name_val = (name_input.value or "").strip()
            desc_val = (desc_input.value or "").strip()
            role_val = role_dropdown.value or "Developer"
            try:
                duration_val = int((duration_input.value or "").strip())
            except ValueError:
                duration_val = 0

            if not code_val:
                error_text.value = "Vui lòng nhập mã dự án."
                error_text.visible = True
                if error_text.page:
                    error_text.update()
                return

            if not _PROJECT_CODE_RE.fullmatch(code_val):
                error_text.value = "Mã dự án không hợp lệ. Chỉ chấp nhận chữ, số, '.', '_', '-'."
                error_text.visible = True
                if error_text.page:
                    error_text.update()
                return

            if not name_val:
                error_text.value = "Vui lòng nhập tên dự án."
                error_text.visible = True
                if error_text.page:
                    error_text.update()
                return
            if not 1 <= duration_val <= 3650:
                error_text.value = "Thời hạn hoàn thành phải từ 1 đến 3650 ngày."
                error_text.visible = True
                if error_text.page:
                    error_text.update()
                return

            try:
                if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "create_project"):
                    new_prj = self.ctx.projects.create_project(
                        code=code_val,
                        name=name_val,
                        description=desc_val,
                        role_name=role_val,
                        duration_days=duration_val,
                    )
                else:
                    new_prj = {
                        "code": code_val, "template_code": code_val,
                        "name": name_val, "template_name": name_val,
                        "description": desc_val, "updated_at": "Vừa tạo",
                        "duration_days": duration_val,
                    }

                # Thêm vào danh sách dự án
                self.projects = [new_prj] + [p for p in self.projects if (p.get("code") or p.get("template_code")) != code_val]
                self._render_projects_grid()

                if self.page:
                    self.page.close(dlg)
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã tạo thành công dự án '{name_val}' ({code_val})!")
            except Exception as exc:
                error_text.value = f"Lỗi tạo dự án: {exc}"
                error_text.visible = True
                if error_text.page:
                    error_text.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.CREATE_NEW_FOLDER_ROUNDED, color=theme.PRIMARY),
                ft.Text("Tạo dự án gần đây mới", size=18, weight=ft.FontWeight.BOLD),
            ], spacing=10),
            content=ft.Container(
                width=480,
                content=ft.Column(
                    spacing=14,
                    tight=True,
                    controls=[
                        ft.Text("Dự án mới sẽ được tạo trong hệ thống và sinh thư mục tài liệu onboarding riêng.", size=13, color=theme.TEXT_MUTED),
                        code_input,
                        name_input,
                        role_dropdown,
                        duration_input,
                        desc_input,
                        error_text,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self.page.close(dlg) if self.page else None),
                ft.FilledButton(
                    "Tạo dự án",
                    icon=ft.Icons.CHECK_ROUNDED,
                    on_click=lambda _: self._run_project_action(
                        "create-project",
                        "Đang tạo dự án và thư mục tài liệu…",
                        lambda: do_create(None),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self.page:
            self.page.open(dlg)

    def _open_project_members_dialog(self, project: dict[str, Any]) -> None:
        can_manage_members = self.is_admin or bool(project.get("can_manage_template", False))
        prj_code = str(project.get("code") or project.get("template_code", "")).strip()
        prj_name = str(project.get("name") or project.get("template_name", "Dự án")).strip()

        # Danh sách thành viên hiện tại của dự án
        current_members: list[dict[str, Any]] = []
        all_system_users: list[dict[str, Any]] = []

        # Tải danh sách từ backend
        if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "list_members"):
            try:
                current_members = self.ctx.projects.list_members(prj_code)
            except Exception:
                current_members = []
        if can_manage_members and self.ctx and hasattr(self.ctx, "list_users"):
            try:
                all_system_users = self.ctx.list_users()
            except Exception:
                all_system_users = []

        members_list_column = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        count_badge = ft.Text(f"{len(current_members)} thành viên", size=12, weight=ft.FontWeight.W_600, color=theme.PRIMARY)
        search_field = ft.TextField(
            hint_text="Tìm kiếm theo tên, email, vai trò...",
            hint_style=ft.TextStyle(size=12, color=theme.TEXT_MUTED),
            text_size=12,
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            dense=True,
            height=38,
            expand=True,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )
        risk_filter = ft.Dropdown(
            value="all",
            options=[
                ft.dropdown.Option(key="all", text="Tất cả trạng thái"),
                ft.dropdown.Option(key="at_risk", text="Có nguy cơ"),
                ft.dropdown.Option(key="overdue", text="Quá hạn"),
                ft.dropdown.Option(key="on_track", text="Đúng tiến độ"),
                ft.dropdown.Option(key="completed", text="Hoàn thành"),
            ],
            text_size=11,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            dense=True,
            width=165,
            visible=True,
        )

        candidate_users = [
            user
            for user in (all_system_users or [])
            if self.is_admin or str(user.get("permission") or user.get("level") or "MEMBER").upper() != "TEAM_LEAD"
        ]

        # Multi-select state
        selected_candidate_emails: set[str] = set()

        def get_available_candidates() -> list[dict[str, Any]]:
            joined_emails = {m.get("user_email", "").strip().lower() for m in current_members}
            return [
                u for u in candidate_users
                if (u.get("email") or "").strip().lower() not in joined_emails
            ]

        candidates_column = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
        selected_count_badge = ft.Text("Đã chọn: 0", size=11, weight=ft.FontWeight.W_600, color=theme.PRIMARY)

        project_role_dropdown = ft.Dropdown(
            label="Quyền trong dự án",
            value="MEMBER",
            options=[
                ft.dropdown.Option(key="MEMBER", text="Member"),
                ft.dropdown.Option(key="PROJECT_LEAD", text="Project Lead"),
            ],
            text_size=12,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            dense=True,
            expand=1,
        )

        batch_add_btn = ft.FilledButton(
            text="Chọn thành viên để thêm",
            icon=ft.Icons.PERSON_ADD_ROUNDED,
            disabled=True,
        )

        add_error_text = ft.Text("", size=11, color=theme.ERR, visible=False)

        def update_batch_btn():
            count = len(selected_candidate_emails)
            selected_count_badge.value = f"Đã chọn: {count}"
            if count > 0:
                batch_add_btn.text = f"Thêm {count} thành viên vào dự án"
                batch_add_btn.disabled = False
            else:
                batch_add_btn.text = "Chọn thành viên để thêm"
                batch_add_btn.disabled = True
            if selected_count_badge.page:
                selected_count_badge.update()
            if batch_add_btn.page:
                batch_add_btn.update()

        def on_toggle_candidate(email: str, checked: bool):
            clean_em = email.strip().lower()
            if checked:
                selected_candidate_emails.add(clean_em)
            else:
                selected_candidate_emails.discard(clean_em)
            update_batch_btn()
            render_candidates_view(candidate_search_field.value or "")

        def select_all_candidates(_):
            q = (candidate_search_field.value or "").strip().lower()
            avail = get_available_candidates()
            for u in avail:
                u_name = u.get("name", "").lower()
                u_email = u.get("email", "").lower()
                if not q or (q in u_name or q in u_email):
                    selected_candidate_emails.add(u_email)
            render_candidates_view(candidate_search_field.value or "")
            update_batch_btn()

        def deselect_all_candidates(_):
            selected_candidate_emails.clear()
            render_candidates_view(candidate_search_field.value or "")
            update_batch_btn()

        candidate_search_field = ft.TextField(
            hint_text="Lọc tìm ứng viên theo tên hoặc email...",
            hint_style=ft.TextStyle(size=11, color=theme.TEXT_MUTED),
            text_size=11,
            prefix_icon=ft.Icons.FILTER_LIST_ROUNDED,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            dense=True,
            height=34,
            expand=True,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
            on_change=lambda e: render_candidates_view(e.control.value),
        )

        select_all_btn = ft.TextButton(
            "Chọn tất cả",
            icon=ft.Icons.SELECT_ALL_ROUNDED,
            on_click=select_all_candidates,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )
        deselect_all_btn = ft.TextButton(
            "Bỏ chọn",
            icon=ft.Icons.CLEAR_ALL_ROUNDED,
            on_click=deselect_all_candidates,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        def render_candidates_view(query: str = ""):
            q = query.strip().lower()
            avail = get_available_candidates()
            filtered = [
                u for u in avail
                if not q or (
                    q in u.get("name", "").lower()
                    or q in u.get("email", "").lower()
                )
            ]

            items: list[ft.Control] = []
            if not filtered:
                msg = "Tất cả ứng viên phù hợp vai trò đã tham gia dự án." if not avail else "Không tìm thấy ứng viên khớp từ khóa."
                items.append(
                    ft.Container(
                        alignment=ft.alignment.center,
                        padding=ft.padding.symmetric(vertical=14),
                        content=ft.Text(msg, size=11, color=theme.TEXT_MUTED, italic=True),
                    )
                )
            else:
                for u in filtered:
                    u_email = (u.get("email") or "").strip()
                    u_name = u.get("name") or u_email.split("@")[0]
                    is_checked = u_email.lower() in selected_candidate_emails

                    cb = ft.Checkbox(
                        label=f"{u_name} ({u_email})",
                        value=is_checked,
                        on_change=lambda e, em=u_email: on_toggle_candidate(em, e.control.value),
                        label_style=ft.TextStyle(size=11, color=theme.TEXT, weight=ft.FontWeight.W_500),
                        active_color=theme.PRIMARY,
                    )
                    items.append(
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            border_radius=6,
                            bgcolor=theme.PRIMARY_BG if is_checked else ft.Colors.TRANSPARENT,
                            content=cb,
                        )
                    )

            candidates_column.controls = items
            if candidates_column.page:
                candidates_column.update()

        def do_batch_add(_):
            nonlocal current_members
            selected_list = list(selected_candidate_emails)
            if not selected_list:
                add_error_text.value = "Vui lòng chọn ít nhất 1 thành viên từ danh sách bên trên."
                add_error_text.visible = True
                if add_error_text.page:
                    add_error_text.update()
                return

            members_payload = []
            for em in selected_list:
                u = next((usr for usr in all_system_users if usr.get("email", "").lower() == em.lower()), None)
                u_name = (u.get("name") if u else "") or em.split("@")[0]
                u_dept = (u.get("department") if u else "") or "Engineering"
                members_payload.append({
                    "user_email": em,
                    "user_name": u_name,
                    "department": u_dept,
                    "project_role_key": project_role_dropdown.value or "MEMBER",
                })

            try:
                if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "add_members_batch"):
                    new_added = self.ctx.projects.add_members_batch(prj_code, members=members_payload)
                    if isinstance(new_added, list) and new_added:
                        current_members = list(current_members) + new_added
                    else:
                        current_members = list(current_members) + members_payload
                else:
                    for item in members_payload:
                        if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "add_member"):
                            self.ctx.projects.add_member(
                                code=prj_code,
                                user_email=item["user_email"],
                                project_role_key=item["project_role_key"],
                                user_name=item["user_name"],
                                department=item["department"],
                            )
                    current_members = list(current_members) + members_payload

                selected_candidate_emails.clear()
                add_error_text.visible = False
                if add_error_text.page:
                    add_error_text.update()

                render_candidates_view(candidate_search_field.value or "")
                update_batch_btn()
                render_members_view(search_field.value or "")

                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã thêm thành công {len(members_payload)} thành viên vào dự án!")
            except Exception as exc:
                add_error_text.value = f"Lỗi thêm thành viên: {exc}"
                add_error_text.visible = True
                if add_error_text.page:
                    add_error_text.update()

        batch_add_btn.on_click = lambda _: self._run_project_action(
            f"batch-add:{prj_code}",
            "Đang thêm thành viên vào dự án…",
            lambda: do_batch_add(None),
        )

        def render_members_view(query: str = "", selected_risk: str | None = None):
            q = query.strip().lower()
            risk_value = str(selected_risk or risk_filter.value or "all").strip().lower()
            filtered = [
                m for m in current_members
                if (
                    risk_value == "all"
                    or str(m.get("risk_status") or "not_started").strip().lower() == risk_value
                ) and (
                    not q or (
                        q in m.get("user_name", "").lower()
                        or q in m.get("user_email", "").lower()
                        or q in m.get("role_in_project", "").lower()
                        or q in m.get("department", "").lower()
                    )
                )
            ]
            is_filtered = bool(q) or risk_value != "all"
            count_badge.value = f"{len(filtered)}/{len(current_members)} thành viên" if is_filtered else f"{len(current_members)} thành viên"

            rows: list[ft.Control] = []
            if not filtered:
                rows.append(
                    ft.Container(
                        alignment=ft.alignment.center,
                        padding=ft.padding.symmetric(vertical=16),
                        content=ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=6,
                            controls=[
                                ft.Icon(ft.Icons.PERSON_OFF_ROUNDED, size=32, color=theme.TEXT_LIGHT),
                                ft.Text("Không tìm thấy thành viên nào phù hợp.", size=12, color=theme.TEXT_MUTED),
                            ],
                        ),
                    )
                )
            else:
                for idx, m in enumerate(filtered):
                    u_email = m.get("user_email", "")
                    u_name = m.get("user_name") or u_email.split("@")[0]
                    project_role_key = str(m.get("project_role_key") or "MEMBER").upper()
                    system_role_key = str(m.get("system_role_key") or "MEMBER").upper()
                    u_dept = m.get("department", "Engineering")
                    deadline_status = str(m.get("deadline_status") or "not_started")
                    risk_status = str(m.get("risk_status") or "not_started")
                    risk_reason = str(m.get("risk_reason") or "")
                    days_remaining = m.get("days_remaining")
                    due_label = _format_deadline(m.get("due_at"))
                    if deadline_status == "completed":
                        deadline_text = f"Đã hoàn thành • Hạn {due_label}"
                        deadline_color = theme.EMERALD
                    elif deadline_status == "overdue":
                        overdue_days = abs(int(days_remaining or 0))
                        deadline_text = f"Quá hạn {overdue_days} ngày • Hạn {due_label}"
                        deadline_color = theme.ERR
                    elif days_remaining is not None:
                        deadline_text = f"Còn {max(0, int(days_remaining))} ngày • Hạn {due_label}"
                        deadline_color = theme.WARN if int(days_remaining) <= 3 else theme.TEXT_MUTED
                    else:
                        deadline_text = "Chưa bắt đầu tính thời hạn"
                        deadline_color = theme.TEXT_LIGHT
                    risk_styles = {
                        "at_risk": ("Có nguy cơ", theme.WARN, theme.WARN_BG, theme.WARN_BORDER),
                        "overdue": ("Quá hạn", theme.ERR, theme.ERR_BG, theme.ERR_BORDER),
                        "completed": ("Hoàn thành", theme.EMERALD, theme.EMERALD_BG, theme.EMERALD_BORDER),
                        "on_track": ("Đúng tiến độ", theme.PRIMARY, theme.PRIMARY_BG, theme.PRIMARY_BORDER),
                        "not_started": ("Chưa bắt đầu", theme.TEXT_MUTED, theme.SURFACE_ALT, theme.BORDER),
                    }
                    risk_label, risk_color, risk_bg, risk_border = risk_styles.get(
                        risk_status,
                        risk_styles["not_started"],
                    )
                    initial = (u_name[0] if u_name else "U").upper()

                    row_ctrl = ft.Container(
                        bgcolor=theme.SURFACE,
                        border=ft.border.all(1, theme.BORDER),
                        border_radius=8,
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Row(
                                    spacing=12,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Container(
                                            width=36,
                                            height=36,
                                            bgcolor=theme.PRIMARY_BG,
                                            border=ft.border.all(1, theme.PRIMARY_BORDER),
                                            border_radius=18,
                                            alignment=ft.alignment.center,
                                            content=ft.Text(initial, size=14, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                                        ),
                                        ft.Column(
                                            spacing=2,
                                            tight=True,
                                            controls=[
                                                ft.Row([
                                                    ft.Text(u_name, size=13, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                                    ft.Container(
                                                        content=ft.Text(
                                                            "Team Lead" if system_role_key == "TEAM_LEAD" else (
                                                                "Project Lead" if project_role_key == "PROJECT_LEAD" else "Member"
                                                            ),
                                                            size=9,
                                                            weight=ft.FontWeight.W_600,
                                                            color=theme.PURPLE if system_role_key == "TEAM_LEAD" or project_role_key == "PROJECT_LEAD" else theme.TEXT_MUTED,
                                                        ),
                                                        bgcolor=theme.PURPLE_BG if system_role_key == "TEAM_LEAD" or project_role_key == "PROJECT_LEAD" else theme.SURFACE_ALT,
                                                        border_radius=4,
                                                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                                        tooltip="Quyền của user trong dự án này",
                                                    ),
                                                    ft.Container(
                                                        content=ft.Text(risk_label, size=9, weight=ft.FontWeight.W_600, color=risk_color),
                                                        bgcolor=risk_bg,
                                                        border=ft.border.all(1, risk_border),
                                                        border_radius=4,
                                                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                                        tooltip=risk_reason,
                                                        visible=True,
                                                    ),
                                                ], spacing=6),
                                                 ft.Text(f"{u_email} • {u_dept}", size=11, color=theme.TEXT_MUTED),
                                                 ft.Row(
                                                     spacing=4,
                                                     controls=[
                                                         ft.Icon(ft.Icons.EVENT_ROUNDED, size=12, color=deadline_color),
                                                         ft.Text(deadline_text, size=10, color=deadline_color, weight=ft.FontWeight.W_500),
                                                     ],
                                                     visible=True,
                                                 ),
                                            ],
                                        ),
                                    ],
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                    icon_size=18,
                                    icon_color=theme.ERR,
                                    tooltip=f"Xóa {u_name} khỏi dự án",
                                    on_click=lambda _, email=u_email, name=u_name: remove_member(email, name),
                                    visible=can_manage_members and (self.is_admin or system_role_key != "TEAM_LEAD"),
                                ),
                            ],
                        ),
                    )
                    rows.append(row_ctrl)

            if can_manage_members and q:
                not_joined = [
                    u for u in all_system_users
                    if (q in u.get("name", "").lower() or q in u.get("email", "").lower())
                    and not any(m.get("user_email", "").lower() == u.get("email", "").lower() for m in current_members)
                ]
                if not_joined:
                    rows.append(
                        ft.Container(
                            padding=ft.padding.only(top=10, bottom=4),
                            content=ft.Text("GỢI Ý THÊM TỪ TÀI KHOẢN HỆ THỐNG", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_LIGHT),
                        )
                    )
                    for su in not_joined:
                        s_name = su.get("name", "")
                        s_email = su.get("email", "")
                        s_dept = su.get("department", "")
                        rows.append(
                            ft.Container(
                                bgcolor=theme.SURFACE_ALT,
                                border=ft.border.all(1, theme.BORDER_LIGHT),
                                border_radius=8,
                                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                content=ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        ft.Column(
                                            spacing=1,
                                            tight=True,
                                            controls=[
                                                ft.Text(s_name, size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                                ft.Text(f"{s_email} ({s_dept})", size=11, color=theme.TEXT_MUTED),
                                            ],
                                        ),
                                        ft.FilledTonalButton(
                                            "+ Thêm vào dự án",
                                            on_click=lambda _, em=s_email, nm=s_name, dp=s_dept: quick_add(em, nm, dp),
                                        ),
                                    ],
                                ),
                            )
                        )

            members_list_column.controls = rows
            if members_list_column.page:
                members_list_column.update()
            if count_badge.page:
                count_badge.update()

        def quick_add(email: str, name: str, dept: str):
            self._run_project_action(
                f"add-member:{prj_code}:{email.strip().lower()}",
                f"Đang thêm {name or email} vào dự án…",
                lambda: add_member_to_prj(email, name, dept),
            )

        def remove_member(email: str, name: str):
            self._run_project_action(
                f"remove-member:{prj_code}:{email.strip().lower()}",
                f"Đang xóa {name or email} khỏi dự án…",
                lambda: remove_member_work(email, name),
            )

        def remove_member_work(email: str, name: str):
            nonlocal current_members
            try:
                if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "remove_member"):
                    self.ctx.projects.remove_member(prj_code, email)
                current_members = [m for m in current_members if m.get("user_email", "").lower() != email.lower()]
                render_members_view(search_field.value or "")
                render_candidates_view(candidate_search_field.value or "")
                update_batch_btn()
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã xóa '{name}' khỏi dự án.")
            except Exception as exc:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Lỗi khi xóa thành viên: {exc}")

        def add_member_to_prj(email: str, name: str, dept: str):
            nonlocal current_members
            clean_email = email.strip().lower()
            if not clean_email or "@" not in clean_email:
                add_error_text.value = "Vui lòng chọn hoặc nhập email hợp lệ."
                add_error_text.visible = True
                if add_error_text.page:
                    add_error_text.update()
                return

            if any(m.get("user_email", "").lower() == clean_email for m in current_members):
                add_error_text.value = f"Tài khoản '{clean_email}' đã là thành viên của dự án."
                add_error_text.visible = True
                if add_error_text.page:
                    add_error_text.update()
                return

            try:
                if self.ctx and hasattr(self.ctx, "projects") and hasattr(self.ctx.projects, "add_member"):
                    new_m = self.ctx.projects.add_member(
                        code=prj_code,
                        user_email=clean_email,
                        project_role_key=project_role_dropdown.value or "MEMBER",
                        user_name=name,
                        department=dept,
                    )
                else:
                    new_m = {
                        "project_code": prj_code,
                        "user_email": clean_email,
                        "user_name": name or clean_email.split("@")[0],
                        "department": dept or "Engineering",
                        "project_role_key": project_role_dropdown.value or "MEMBER",
                    }
                current_members = list(current_members) + [new_m]
                add_error_text.visible = False
                if add_error_text.page:
                    add_error_text.update()
                render_candidates_view(candidate_search_field.value or "")
                update_batch_btn()
                render_members_view(search_field.value or "")
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã thêm '{clean_email}' vào dự án!")
            except Exception as exc:
                add_error_text.value = f"Lỗi thêm thành viên: {exc}"
                add_error_text.visible = True
                if add_error_text.page:
                    add_error_text.update()

        def on_risk_filter_changed(event: ft.ControlEvent) -> None:
            selected = str(event.control.value or event.data or "all")
            risk_filter.value = selected
            render_members_view(search_field.value or "", selected_risk=selected)

        search_field.on_change = lambda e: render_members_view(e.control.value)
        risk_filter.on_change = on_risk_filter_changed

        # Initial render
        render_candidates_view("")
        render_members_view("")
        update_batch_btn()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.GROUPS_ROUNDED, color=theme.PRIMARY, size=24),
                        ft.Column([
                            ft.Text(
                                f"Quản lý thành viên: {prj_name}" if can_manage_members else f"Thành viên dự án: {prj_name}",
                                size=17,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(f"Mã dự án: {prj_code}", size=12, color=theme.TEXT_MUTED),
                            ft.Text(
                                f"Thời hạn mỗi thành viên: {int(project.get('duration_days') or 20)} ngày từ lúc được thêm",
                                size=11,
                                color=theme.WARN,
                            ),
                        ], spacing=1),
                    ], spacing=10),
                ],
            ),
            content=ft.Container(
                width=960,
                height=560,
                content=ft.Row(
                    spacing=14,
                    expand=True,
                    controls=[
                        # Cột 1: Chọn thành viên vào dự án (Multi-Select)
                        ft.Container(
                            expand=1,
                            bgcolor=theme.BG,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=10,
                            padding=12,
                            visible=can_manage_members,
                            content=ft.Column(
                                spacing=8,
                                expand=True,
                                controls=[
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.Row([
                                                ft.Icon(ft.Icons.CHECKLIST_ROUNDED, size=16, color=theme.PRIMARY),
                                                ft.Text("CHỌN THÀNH VIÊN VÀO DỰ ÁN", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_LIGHT),
                                            ], spacing=6),
                                            selected_count_badge,
                                        ],
                                    ),
                                    ft.Row([
                                        candidate_search_field,
                                        select_all_btn,
                                        deselect_all_btn,
                                    ], spacing=4),
                                    ft.Container(
                                        expand=True,
                                        border=ft.border.all(1, theme.BORDER_LIGHT),
                                        border_radius=8,
                                        bgcolor=theme.SURFACE,
                                        padding=ft.padding.symmetric(horizontal=6, vertical=4),
                                        content=candidates_column,
                                    ),
                                    project_role_dropdown,
                                    batch_add_btn,
                                    add_error_text,
                                ],
                            ),
                        ),
                        # Cột 2: Danh sách thành viên hiện có trong dự án
                        ft.Container(
                            expand=1,
                            bgcolor=theme.SURFACE,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=10,
                            padding=12,
                            content=ft.Column(
                                spacing=8,
                                expand=True,
                                controls=[
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.Row([
                                                ft.Icon(ft.Icons.PEOPLE_ROUNDED, size=16, color=theme.PRIMARY),
                                                ft.Text("DANH SÁCH THÀNH VIÊN TRONG DỰ ÁN", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_LIGHT),
                                            ], spacing=6),
                                            count_badge,
                                        ],
                                    ),
                                    ft.Row(
                                        spacing=8,
                                        controls=[search_field, risk_filter],
                                    ),
                                    ft.Container(
                                        expand=True,
                                        content=members_list_column,
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.FilledButton("Đóng", on_click=lambda _: self.page.close(dlg) if self.page else None),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self.page:
            self.page.open(dlg)

    # ==================== SECTION: APP CATALOG ====================
    def _build_app_catalog_section(self) -> ft.Container:
        # Ô tìm kiếm
        self.search_field = ft.TextField(
            hint_text="Tìm kiếm theo tên ứng dụng, danh mục, đường dẫn...",
            hint_style=ft.TextStyle(size=12, color=theme.TEXT_MUTED),
            text_size=13,
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
            expand=True,
            dense=True,
            on_change=lambda e: self._on_search_changed(e.control.value),
        )

        # Danh sách chip danh mục (Khởi tạo sẵn chip 'Tất cả' đang active)
        self.category_chips_row = ft.Row(
            spacing=8,
            scroll=ft.ScrollMode.HIDDEN,
            controls=[
                ft.Container(
                    content=ft.Text("Tất cả", size=11, weight=ft.FontWeight.W_600, color=theme.PRIMARY),
                    bgcolor=theme.PRIMARY_BG,
                    border=ft.border.all(1, theme.PRIMARY_BORDER),
                    border_radius=16,
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                )
            ],
        )

        # Cột chứa bảng danh sách ứng dụng (Khởi tạo sẵn placeholder đang tải)
        self.apps_list_column = ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Container(
                    alignment=ft.alignment.center,
                    padding=ft.padding.symmetric(vertical=40),
                    content=ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.ProgressRing(width=16, height=16, stroke_width=2, color=theme.PRIMARY),
                            ft.Text("Đang tải danh mục ứng dụng cần cài đặt...", size=13, color=theme.TEXT_MUTED),
                        ],
                    ),
                )
            ],
        )

        # Header bảng
        table_header = ft.Container(
            bgcolor=theme.SURFACE_ALT,
            border=ft.border.all(1, theme.BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("ỨNG DỤNG", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED, expand=3),
                    ft.Text("DANH MỤC", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED, expand=2),
                    ft.Text("PHIÊN BẢN CỐ ĐỊNH", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED, expand=2),
                    ft.Text("ĐƯỜNG DẪN TRÊN SERVER BE", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED, expand=5),
                    ft.Container(
                        width=145,
                        alignment=ft.alignment.center,
                        content=ft.Text("THAO TÁC", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED),
                    ),
                ],
            ),
        )

        section_header = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.APPS_ROUNDED, size=22, color=theme.PRIMARY),
                                ft.Text("Danh mục ứng dụng cần cài đặt", size=20, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                            ],
                        ),
                        ft.Text(
                            "Lưu trữ danh sách phần mềm và đường dẫn bộ cài trên máy tính phục vụ tự động hóa cài đặt.",
                            size=13,
                            color=theme.TEXT_MUTED,
                        ),
                    ],
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.IconButton(
                            ft.Icons.REFRESH_ROUNDED,
                            tooltip="Làm mới danh mục ứng dụng từ máy chủ",
                            icon_color=theme.TEXT_MUTED,
                            on_click=lambda _: self._load_apps(),
                        ),
                        ft.FilledTonalButton(
                            "Thêm ứng dụng",
                            icon=ft.Icons.ADD_ROUNDED if self.is_admin else ft.Icons.LOCK_OUTLINE_ROUNDED,
                            disabled=not self.is_admin,
                            tooltip=(
                                "Thêm ứng dụng mới vào danh mục (Quyền TEAM_LEAD)"
                                if self.is_admin
                                else "🔒 Chỉ TEAM_LEAD mới có quyền thêm ứng dụng vào danh mục"
                            ),
                            on_click=lambda _: self._open_add_app_dialog(),
                        ),
                    ],
                ),
            ],
        )

        return ft.Container(
            content=ft.Column(
                spacing=16,
                controls=[
                    section_header,
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.search_field,
                        ],
                    ),
                    ft.Container(
                        content=self.category_chips_row,
                        padding=ft.padding.only(bottom=4),
                    ),
                    ft.Column(
                        spacing=6,
                        controls=[
                            table_header,
                            self.apps_list_column,
                        ],
                    ),
                ],
            )
        )

    def _load_apps(self) -> None:
        if not self.ctx:
            return

        if not self._apps:
            self.apps_list_column.controls = [
                ft.Container(
                    alignment=ft.alignment.center,
                    padding=ft.padding.symmetric(vertical=40),
                    content=ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.ProgressRing(width=16, height=16, stroke_width=2, color=theme.PRIMARY),
                            ft.Text("Đang tải danh mục ứng dụng cần cài đặt...", size=13, color=theme.TEXT_MUTED),
                        ],
                    ),
                )
            ]
            if self.apps_list_column.page:
                self.apps_list_column.update()

        def work():
            try:
                apps = self.ctx.apps.list_apps(query=self._search_query, category=self._selected_category)
                self._apps = apps
                cats = self.ctx.apps.categories()
                self._render_category_chips(cats)
                self._render_apps_table()
            except Exception as exc:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Lỗi tải danh mục ứng dụng: {exc}")
                self._render_apps_error(str(exc))

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    def _render_apps_error(self, err_msg: str) -> None:
        self.apps_list_column.controls = [
            ft.Container(
                alignment=ft.alignment.center,
                padding=ft.padding.symmetric(vertical=30),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, size=40, color=theme.ERR),
                        ft.Text(f"Không thể tải danh mục ứng dụng: {err_msg}", size=13, color=theme.ERR, text_align=ft.TextAlign.CENTER),
                        ft.ElevatedButton(
                            "Thử lại",
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda _: self._load_apps(),
                        ),
                    ],
                ),
            )
        ]
        if self.apps_list_column.page:
            self.apps_list_column.update()
        elif self.page:
            self.page.update()

    def _on_search_changed(self, text_val: str) -> None:
        self._search_query = text_val.strip()
        self._load_apps()

    def _select_category(self, cat: str) -> None:
        self._selected_category = cat
        self._load_apps()

    def _render_category_chips(self, categories: list[str]) -> None:
        chips: list[ft.Control] = []
        all_cats = ["Tất cả", *categories]
        for cat in all_cats:
            is_active = (cat == self._selected_category)
            chips.append(
                ft.Container(
                    content=ft.Text(
                        cat,
                        size=11,
                        weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_500,
                        color=theme.PRIMARY if is_active else theme.TEXT_MUTED,
                    ),
                    bgcolor=theme.PRIMARY_BG if is_active else theme.SURFACE_ALT,
                    border=ft.border.all(1, theme.PRIMARY_BORDER if is_active else theme.BORDER),
                    border_radius=16,
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    ink=True,
                    on_click=lambda _, c=cat: self._select_category(c),
                )
            )
        self.category_chips_row.controls = chips
        if self.category_chips_row.page:
            self.category_chips_row.update()
        elif self.page:
            self.page.update()

    def _render_apps_table(self) -> None:
        if not self._apps:
            self.apps_list_column.controls = [
                ft.Container(
                    alignment=ft.alignment.center,
                    padding=ft.padding.symmetric(vertical=30),
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.SEARCH_OFF_ROUNDED, size=36, color=theme.TEXT_MUTED),
                            ft.Text("Không tìm thấy ứng dụng phù hợp.", size=13, color=theme.TEXT_MUTED),
                        ],
                    ),
                )
            ]
            if self.apps_list_column.page:
                self.apps_list_column.update()
            elif self.page:
                self.page.update()
            return

        rows: list[ft.Control] = []
        for app in self._apps:
            # Icon styling
            icon, icon_color, icon_bg = _CATEGORY_ICONS.get(
                app.category, (ft.Icons.APPS_ROUNDED, theme.PRIMARY, theme.PRIMARY_BG)
            )

            # Đường dẫn cài đặt hiển thị & Huy hiệu file trên server BE
            path_display = app.installer_path or "Chưa có file cài trên server BE"
            
            if app.has_installer_file:
                server_badge = ft.Container(
                    content=ft.Row(
                        spacing=3,
                        tight=True,
                        controls=[
                            ft.Icon(ft.Icons.CLOUD_DONE_ROUNDED, size=11, color=theme.PURPLE),
                            ft.Text(f"Server ({_format_bytes(app.installer_file_size)})", size=10, weight=ft.FontWeight.W_600, color=theme.PURPLE),
                        ],
                    ),
                    bgcolor=theme.PURPLE_BG,
                    border=ft.border.all(1, theme.PURPLE_BORDER),
                    border_radius=4,
                    padding=ft.padding.symmetric(horizontal=5, vertical=1),
                    tooltip="Bộ cài đặt đã được lưu trên máy chủ BE, có thể bấm Tải xuống ngay.",
                )
            else:
                server_badge = ft.Container(
                    content=ft.Row(
                        spacing=3,
                        tight=True,
                        controls=[
                            ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, size=11, color=theme.TEXT_LIGHT),
                            ft.Text("Server: Chưa có", size=10, color=theme.TEXT_LIGHT),
                        ],
                    ),
                    bgcolor=theme.SURFACE_ALT,
                    border=ft.border.all(1, theme.BORDER),
                    border_radius=4,
                    padding=ft.padding.symmetric(horizontal=5, vertical=1),
                    tooltip="Chưa có file trên máy chủ BE. Tài khoản TEAM_LEAD có thể tải lên.",
                )

            path_box = ft.Container(
                content=ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(
                            ft.Icons.FOLDER_ROUNDED if app.installer_path else ft.Icons.FOLDER_OFF_ROUNDED,
                            size=14,
                            color=theme.PRIMARY if app.installer_path else theme.TEXT_LIGHT,
                        ),
                        ft.Text(
                            path_display,
                            size=11,
                            color=theme.TEXT if app.installer_path else theme.TEXT_LIGHT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                        server_badge,
                    ],
                ),
                bgcolor=theme.SURFACE_ALT,
                border=ft.border.all(1, theme.BORDER),
                border_radius=6,
                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                tooltip=f"Đường dẫn file cài trên server BE (suffix): {app.installer_path}" if app.installer_path else "Chưa có file cài trên server BE (TEAM_LEAD tải lên kho lưu trữ)",
                expand=5,
            )

            # Thao tác: tải xuống cho mọi user; tải lên cho Team/Project Lead;
            # chỉnh sửa metadata và xóa ứng dụng vẫn chỉ dành cho Team Lead.
            action_buttons: list[ft.Control] = []
            
            # 1. Nút Tải xuống từ máy chủ (Cho tất cả user)
            if app.has_installer_file:
                action_buttons.append(
                    ft.IconButton(
                        ft.Icons.FILE_DOWNLOAD_ROUNDED,
                        width=32,
                        height=32,
                        padding=0,
                        icon_size=16,
                        icon_color=theme.PRIMARY,
                        tooltip=f"Tải bộ cài đặt từ máy chủ về máy ({_format_bytes(app.installer_file_size)})",
                        on_click=lambda _, a=app: self._download_single_app(a),
                    )
                )
            else:
                action_buttons.append(
                    ft.IconButton(
                        ft.Icons.FILE_DOWNLOAD_ROUNDED,
                        width=32,
                        height=32,
                        padding=0,
                        icon_size=16,
                        icon_color=theme.TEXT_LIGHT,
                        tooltip="Chưa có file bộ cài trên máy chủ (Cần TEAM_LEAD hoặc PROJECT_LEAD tải lên)",
                        on_click=lambda _, a=app: self._download_single_app(a),
                    )
                )

            # 2. Nút Tải lên máy chủ (Team Lead hoặc Project Lead, chặn tải lên trùng)
            if self.can_manage_templates:
                if app.has_installer_file:
                    action_buttons.append(
                        ft.IconButton(
                            ft.Icons.CLOUD_DONE_ROUNDED,
                            width=32,
                            height=32,
                            padding=0,
                            icon_size=16,
                            icon_color=theme.TEXT_LIGHT,
                            tooltip=f"Ứng dụng và phiên bản '{app.recommended_version or 'cố định'}' đã có bộ cài trên máy chủ (Không cho phép tải lên trùng)",
                            on_click=lambda _, a=app: self._warn_duplicate_upload(a),
                        )
                    )
                else:
                    action_buttons.append(
                        ft.IconButton(
                            ft.Icons.CLOUD_UPLOAD_ROUNDED,
                            width=32,
                            height=32,
                            padding=0,
                            icon_size=16,
                            icon_color=theme.PURPLE,
                            tooltip="Tải file bộ cài lên máy chủ (Quyền TEAM_LEAD hoặc PROJECT_LEAD)",
                            on_click=lambda _, a=app: self._start_upload_installer(a),
                        )
                    )

            # 3. Nút Sửa đường dẫn trên server BE (Chỉ dành cho ADMIN)
            if self.is_admin:
                action_buttons.append(
                    ft.IconButton(
                        ft.Icons.EDIT_ROUNDED,
                        width=32,
                        height=32,
                        padding=0,
                        icon_size=16,
                        icon_color=theme.TEXT_MUTED,
                        tooltip="Chỉnh sửa phiên bản, lệnh kiểm tra & bộ cài đặt (Quyền TEAM_LEAD)",
                        on_click=lambda _, a=app: self._open_edit_path_dialog(a),
                    )
                )

            # 4. Nút Xóa ứng dụng khỏi danh mục (Chỉ dành cho ADMIN)
            if self.is_admin:
                action_buttons.append(
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE_ROUNDED,
                        width=32,
                        height=32,
                        padding=0,
                        icon_size=16,
                        icon_color=theme.ERR,
                        tooltip=f"Xóa ứng dụng '{app.app_name}' khỏi danh mục (Quyền TEAM_LEAD)",
                        on_click=lambda _, a=app: self._confirm_delete_app(a),
                    )
                )

            actions_box = ft.Container(
                width=145,
                content=ft.Row(
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=action_buttons,
                ),
            )

            card_row = ft.Container(
                bgcolor=theme.SURFACE,
                border=ft.border.all(1, theme.BORDER),
                border_radius=10,
                padding=ft.padding.symmetric(horizontal=16, vertical=10),
                content=ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        # Ứng dụng (Tên & Code)
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            expand=3,
                            controls=[
                                ft.Container(
                                    width=34,
                                    height=34,
                                    bgcolor=icon_bg,
                                    border_radius=8,
                                    alignment=ft.alignment.center,
                                    content=ft.Icon(icon, color=icon_color, size=18),
                                ),
                                ft.Column(
                                    spacing=1,
                                    tight=True,
                                    expand=True,
                                    controls=[
                                        ft.Text(app.app_name, size=13, weight=ft.FontWeight.W_600, color=theme.TEXT),
                                        ft.Text(app.app_code, size=10, color=theme.TEXT_LIGHT),
                                    ],
                                ),
                            ],
                        ),
                        # Danh mục
                        ft.Container(
                            content=ft.Text(app.category, size=11, color=theme.TEXT_MUTED),
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER_LIGHT),
                            border_radius=6,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            expand=2,
                        ),
                        # Phiên bản cố định
                        ft.Text(app.recommended_version or "—", size=11, weight=ft.FontWeight.W_600, color=theme.TEXT, expand=2),
                        # Đường dẫn
                        path_box,
                        # Thao tác
                        actions_box,
                    ],
                ),
            )
            rows.append(card_row)

        self.apps_list_column.controls = rows
        if self.apps_list_column.page:
            self.apps_list_column.update()
        elif self.page:
            self.page.update()

    # ==================== DOWNLOAD & UPLOAD BỘ CÀI ĐẶT ====================
    def _download_single_app(self, app: AppItem) -> None:
        # Thử đồng bộ nhanh từ server nếu cache frontend chưa kịp cập nhật trạng thái file
        if self.ctx:
            try:
                fresh = self.ctx.apps.get_app(app.app_code)
                if fresh and fresh.has_installer_file:
                    app.has_installer_file = True
                    app.installer_path = fresh.installer_path
                    app.installer_file_size = fresh.installer_file_size
                    for it in self._apps:
                        if it.app_code == app.app_code:
                            it.has_installer_file = True
                            it.installer_path = fresh.installer_path
                            it.installer_file_size = fresh.installer_file_size
                    self._render_apps_table()
            except Exception:
                pass

        if not app.has_installer_file:
            if self.can_manage_templates:
                dlg: ft.AlertDialog | None = None
                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Row([
                        ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, color=theme.WARN, size=22),
                        ft.Text("Chưa có file cài trên máy chủ", size=16, weight=ft.FontWeight.BOLD),
                    ]),
                    content=ft.Container(
                        width=460,
                        content=ft.Column(
                            tight=True,
                            spacing=10,
                            controls=[
                                ft.Text(
                                    f"Ứng dụng '{app.app_name}' chưa có file bộ cài đặt được lưu trên máy chủ BE.",
                                    size=13,
                                    color=theme.TEXT,
                                ),
                                ft.Text(
                                    "Bạn có quyền TEAM_LEAD hoặc PROJECT_LEAD. Bạn có muốn tải tệp cài đặt lên máy chủ để các thành viên khác có thể tải về không?",
                                    size=12,
                                    color=theme.TEXT_MUTED,
                                ),
                            ],
                        ),
                    ),
                    actions=[
                        ft.TextButton("Đóng", on_click=lambda _: self.page.close(dlg) if self.page and dlg else None),
                        ft.FilledButton(
                            "Tải file lên server ngay",
                            icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
                            bgcolor=theme.PRIMARY,
                            on_click=lambda _: (self.page.close(dlg) if self.page and dlg else None, self._start_upload_installer(app)),
                        ),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                if self.page:
                    self.page.open(dlg)
            else:
                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Row([
                        ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, color=theme.WARN, size=22),
                        ft.Text("Chưa có file cài trên máy chủ", size=16, weight=ft.FontWeight.BOLD),
                    ]),
                    content=ft.Container(
                        width=450,
                        content=ft.Column(
                            tight=True,
                            spacing=10,
                            controls=[
                                ft.Text(
                                    f"Ứng dụng '{app.app_name}' hiện chưa có file bộ cài đặt được lưu trữ trên máy chủ.",
                                    size=13,
                                    color=theme.TEXT,
                                ),
                                ft.Text(
                                    "Vui lòng liên hệ TEAM_LEAD hoặc PROJECT_LEAD để tải file cài đặt lên máy chủ.",
                                    size=12,
                                    color=theme.TEXT_MUTED,
                                ),
                            ],
                        ),
                    ),
                    actions=[
                        ft.TextButton("Đã hiểu", on_click=lambda _: self.page.close(dlg) if self.page and dlg else None),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                if self.page:
                    self.page.open(dlg)
            return

        clean_ver = _clean_version_tag(app.recommended_version)
        ver_tag = f"_v{clean_ver}" if clean_ver else ""
        default_filename = f"{app.app_code}{ver_tag}_installer.exe"
        if app.installer_path:
            p_name = Path(app.installer_path).name
            if p_name and "." in p_name:
                stem = Path(p_name).stem
                suffix = Path(p_name).suffix
                if clean_ver and clean_ver not in stem.lower():
                    default_filename = f"{stem}{ver_tag}{suffix}"
                else:
                    default_filename = p_name

        downloads_dir = _resolve_fixed_download_dir()

        self._downloading_app = app
        self._pending_download_filename = default_filename
        self._show_download_choice_dialog(app, default_filename, downloads_dir)

    def _show_download_choice_dialog(self, app: AppItem, default_filename: str, downloads_dir: Path) -> None:
        """Hộp thoại cho phép người dùng chọn vị trí lưu tệp cài đặt (Downloads hoặc chọn thư mục tùy ý)."""
        dlg: ft.AlertDialog | None = None

        def choose_custom_location(_):
            if self.page and dlg:
                self.page.close(dlg)
            self._ensure_pickers_in_overlay()
            ext = Path(default_filename).suffix.lstrip(".") or "exe"
            self.save_installer_picker.save_file(
                dialog_title=f"Chọn vị trí lưu tệp bộ cài đặt {app.app_name}",
                file_name=default_filename,
                initial_directory=str(downloads_dir),
                file_type=ft.FilePickerFileType.CUSTOM if ext else ft.FilePickerFileType.ANY,
                allowed_extensions=[ext] if ext else None,
            )

        def save_to_downloads(_):
            if self.page and dlg:
                self.page.close(dlg)
            self._execute_download_app(app, downloads_dir / default_filename, exact_path=False)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.DOWNLOAD_FOR_OFFLINE_ROUNDED, color=theme.PRIMARY, size=24),
                    ft.Text(f"Tải bộ cài đặt: {app.app_name}", size=16, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    spacing=12,
                    tight=True,
                    controls=[
                        ft.Text(
                            "Tệp bộ cài đặt đã sẵn sàng trên máy chủ Backend. Bạn có thể chọn lưu nhanh vào thư mục Downloads hoặc chọn một vị trí lưu trữ bất kỳ trên máy:",
                            size=13,
                            color=theme.TEXT,
                        ),
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=12,
                            content=ft.Column(
                                spacing=5,
                                tight=True,
                                controls=[
                                    ft.Row(
                                        spacing=6,
                                        controls=[
                                            ft.Icon(ft.Icons.ATTACH_FILE_ROUNDED, size=15, color=theme.PRIMARY),
                                            ft.Text(f"Tên tệp: {default_filename}", size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                        ],
                                    ),
                                    ft.Text(f"Dung lượng: {_format_bytes(app.installer_file_size)}", size=11, color=theme.TEXT_MUTED),
                                    ft.Text(f"Phiên bản khuyến nghị: {app.recommended_version or 'Mới nhất'}", size=11, color=theme.TEXT_MUTED),
                                    ft.Text(f"Đường dẫn nguồn trên Server (suffix): {app.installer_path or 'Chưa cấu hình'}", size=11, color=theme.TEXT_LIGHT),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self.page.close(dlg) if self.page and dlg else None),
                ft.OutlinedButton(
                    "Chọn nơi lưu khác...",
                    icon=ft.Icons.DRIVE_FILE_MOVE_ROUNDED,
                    tooltip="Mở hộp thoại để bạn chọn thư mục và ổ đĩa lưu file tùy ý trên máy",
                    on_click=choose_custom_location,
                ),
                ft.FilledButton(
                    "Lưu vào Downloads",
                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                    bgcolor=theme.PRIMARY,
                    color=theme.SURFACE,
                    tooltip=f"Lưu nhanh vào {downloads_dir}",
                    on_click=save_to_downloads,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self.page:
            self.page.open(dlg)

    def _execute_download_app(self, app: AppItem, target_dest: Path, exact_path: bool = False) -> None:
        try:
            target_dest.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            if hasattr(self.ctx, "notifier"):
                self.ctx.notifier.error(f"Không thể tạo thư mục lưu file: {e}")
            return

        # Các control hiển thị tiến trình tải xuống thời gian thực
        progress_bar = ft.ProgressBar(
            value=0.0,
            bgcolor=theme.SURFACE_ALT,
            color=theme.PRIMARY,
            height=10,
            border_radius=5,
        )
        percent_text = ft.Text("0%", size=14, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
        bytes_text = ft.Text("0 B / ...", size=12, color=theme.TEXT_MUTED)
        status_text = ft.Text(f"Đang chuẩn bị tải về '{target_dest.name}'...", size=12, color=theme.TEXT)
        icon_cloud = ft.Icon(ft.Icons.CLOUD_DOWNLOAD_ROUNDED, size=28, color=theme.PRIMARY)

        download_dlg: ft.AlertDialog | None = None
        download_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    icon_cloud,
                    ft.Column(
                        spacing=2,
                        tight=True,
                        controls=[
                            ft.Text("Tiến trình tải bộ cài đặt", size=16, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                            ft.Text(f"{app.app_name} ({app.recommended_version or 'Mặc định'})", size=12, color=theme.TEXT_MUTED),
                        ],
                    ),
                ],
            ),
            content=ft.Container(
                width=480,
                content=ft.Column(
                    spacing=14,
                    tight=True,
                    controls=[
                        # Tên tệp và thư mục lưu trữ
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=ft.padding.symmetric(horizontal=12, vertical=10),
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=16, color=theme.PRIMARY),
                                    ft.Column(
                                        spacing=1,
                                        tight=True,
                                        expand=True,
                                        controls=[
                                            ft.Text(target_dest.name, size=12, weight=ft.FontWeight.W_600, color=theme.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                            ft.Text(str(target_dest.parent), size=10, color=theme.TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                        ],
                                    ),
                                ],
                            ),
                        ),
                        # Trạng thái & Phần trăm
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                status_text,
                                percent_text,
                            ],
                        ),
                        # Thanh tiến trình
                        progress_bar,
                        # Dung lượng bytes đã tải
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text("Dung lượng tải:", size=11, color=theme.TEXT_MUTED),
                                bytes_text,
                            ],
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton(
                    "Đóng cửa sổ",
                    tooltip="Đóng cửa sổ này (quá trình tải vẫn tiếp tục ngầm)",
                    on_click=lambda _: self.page.close(download_dlg) if self.page and download_dlg else None,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        if self.page:
            self.page.open(download_dlg)

        last_update_ts = [0.0]

        def on_download_progress(downloaded: int, total: int):
            now = time.monotonic()
            is_finished = (total > 0 and downloaded >= total)
            # Throttle cập nhật UI để giao diện luôn mượt mà
            if not is_finished and (now - last_update_ts[0] < 0.08):
                return
            last_update_ts[0] = now

            if total > 0:
                fraction = min(max(downloaded / total, 0.0), 1.0)
                progress_bar.value = fraction
                pct = int(fraction * 100)
                percent_text.value = f"{pct}%"
                bytes_text.value = f"{_format_bytes(downloaded)} / {_format_bytes(total)}"
                status_text.value = f"Đang tải về máy ({pct}%)..." if pct < 100 else "Đang hoàn tất ghi tệp..."
            else:
                progress_bar.value = None
                percent_text.value = ""
                bytes_text.value = f"Đã tải: {_format_bytes(downloaded)}"
                status_text.value = "Đang nhận dữ liệu từ máy chủ..."

            if progress_bar.page:
                progress_bar.update()
            if percent_text.page:
                percent_text.update()
            if bytes_text.page:
                bytes_text.update()
            if status_text.page:
                status_text.update()

        def work():
            try:
                saved = self.ctx.apps.download_installer(
                    app.app_code,
                    target_dest,
                    exact_path=exact_path,
                    on_progress=on_download_progress,
                )
                if self.page and download_dlg:
                    self.page.close(download_dlg)

                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã tải thành công bộ cài {app.app_name} về: {saved.name}")
                self._show_installer_downloaded_dialog(app, saved)
                self._load_apps()
            except Exception as exc:
                if self.page and download_dlg:
                    self.page.close(download_dlg)
                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Lỗi khi tải bộ cài đặt: {exc}")

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    def _show_installer_downloaded_dialog(self, app: AppItem, saved_path: Path) -> None:
        """Hộp thoại thông báo khi bộ cài đặt đã được tải từ Server BE về máy thành công."""
        dlg: ft.AlertDialog | None = None

        def open_folder(_):
            if self.page and dlg:
                self.page.close(dlg)
            try:
                if os.name == "nt":
                    import subprocess
                    subprocess.Popen(f'explorer /select,"{saved_path.resolve()}"')
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", str(saved_path.parent)])
            except Exception as e:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Không thể mở thư mục: {e}")

        def run_installer(_):
            if self.page and dlg:
                self.page.close(dlg)
            try:
                if os.name == "nt":
                    os.startfile(str(saved_path.resolve()))
                else:
                    import subprocess
                    subprocess.Popen([str(saved_path.resolve())])
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.info(f"Đang khởi chạy trình cài đặt {app.app_name}...")
            except Exception as e:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Không thể khởi chạy bộ cài: {e}")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=theme.EMERALD, size=24),
                    ft.Text(f"Đã tải xong: {app.app_name}", size=16, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=500,
                content=ft.Column(
                    spacing=12,
                    tight=True,
                    controls=[
                        ft.Text(
                            f"Bộ cài đặt phần mềm {app.app_name} đã được tải từ máy chủ BE về máy tính của bạn thành công.",
                            size=13,
                            color=theme.TEXT,
                        ),
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=12,
                            content=ft.Column(
                                spacing=4,
                                controls=[
                                    ft.Row(
                                        spacing=6,
                                        controls=[
                                            ft.Icon(ft.Icons.ATTACH_FILE_ROUNDED, size=15, color=theme.PRIMARY),
                                            ft.Text(f"Tệp: {saved_path.name}", size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                        ],
                                    ),
                                    ft.Text(
                                        f"Vị trí lưu: {saved_path.resolve()}",
                                        size=11,
                                        color=theme.TEXT_MUTED,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                            ),
                        ),
                        ft.Text(
                            "Bạn có thể bấm 'Mở thư mục chứa file' để xem tệp hoặc 'Chạy cài đặt ngay' để tiến hành cài đặt.",
                            size=12,
                            color=theme.TEXT_MUTED,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Đóng", on_click=lambda _: self.page.close(dlg) if self.page and dlg else None),
                ft.OutlinedButton("Mở thư mục chứa file", icon=ft.Icons.FOLDER_OPEN_ROUNDED, on_click=open_folder),
                ft.FilledButton(
                    "Chạy cài đặt ngay",
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    bgcolor=theme.PRIMARY,
                    color=theme.SURFACE,
                    on_click=run_installer,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self.page:
            self.page.open(dlg)

    def _on_save_destination_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path or not self._downloading_app:
            return
        app = self._downloading_app
        dest_path = Path(e.path)
        self._execute_download_app(app, dest_path, exact_path=True)

    def _warn_duplicate_upload(self, app: AppItem) -> None:
        if self.ctx and hasattr(self.ctx, "notifier"):
            self.ctx.notifier.warning(
                f"Ứng dụng '{app.app_name}' phiên bản '{app.recommended_version or 'cố định'}' đã có bộ cài đặt trên máy chủ. Không cho phép tải lên trùng nhau."
            )

    def _start_upload_installer(self, app: AppItem) -> None:
        if not self.can_manage_templates:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.error("Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền tải file lên máy chủ.")
            return

        if app.has_installer_file:
            self._warn_duplicate_upload(app)
            return

        self._ensure_pickers_in_overlay()
        self._uploading_app = app
        self.upload_installer_picker.pick_files(
            dialog_title=f"Chọn file bộ cài để tải lên máy chủ cho {app.app_name}",
            allowed_extensions=["exe", "msi", "bat", "cmd", "zip", "sh", "tar", "gz"],
        )

    def _on_upload_source_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files or not self._uploading_app:
            return
        picked = e.files[0]
        if not picked.path:
            return

        self._pending_upload_path = picked.path
        self._pending_upload_name = picked.name
        self._open_confirm_upload_dialog(picked.path, picked.name, picked.size)

    def _open_confirm_upload_dialog(self, file_path: str, file_name: str, file_size: int | None) -> None:
        if not self._uploading_app:
            return
        app = self._uploading_app
        size_str = _format_bytes(file_size)
        clean_ver = _clean_version_tag(app.recommended_version)
        server_folder_name = f"{app.app_code}_v{clean_ver}" if clean_ver else app.app_code

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CLOUD_UPLOAD_ROUNDED, color=theme.PRIMARY, size=24),
                    ft.Text("Tải bộ cài đặt lên máy chủ", size=16, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=500,
                content=ft.Column(
                    spacing=12,
                    tight=True,
                    controls=[
                        ft.Text(
                            f"Bạn đang tải file bộ cài đặt cho ứng dụng: {app.app_name} ({app.app_code})",
                            size=13,
                            weight=ft.FontWeight.W_600,
                            color=theme.TEXT,
                        ),
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=12,
                            content=ft.Column(
                                spacing=6,
                                tight=True,
                                controls=[
                                    ft.Row(
                                        spacing=6,
                                        controls=[
                                            ft.Icon(ft.Icons.ATTACH_FILE_ROUNDED, size=16, color=theme.PRIMARY),
                                            ft.Text(f"Tệp: {file_name}", size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                        ],
                                    ),
                                    ft.Text(f"Dung lượng: {size_str}", size=11, color=theme.TEXT_MUTED),
                                    ft.Text(
                                        f"Đường dẫn nguồn: {file_path}",
                                        size=11,
                                        color=theme.TEXT_LIGHT,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        f"Thư mục lưu máy chủ: {server_folder_name}/",
                                        size=11,
                                        weight=ft.FontWeight.W_600,
                                        color=theme.PRIMARY,
                                    ),
                                ],
                            ),
                        ),
                        ft.Container(
                            bgcolor=theme.PURPLE_BG,
                            border=ft.border.all(1, theme.PURPLE_BORDER),
                            border_radius=8,
                            padding=10,
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=16, color=theme.PURPLE),
                                    ft.Text(
                                        f"File sẽ được lưu vào kho lưu trữ máy chủ kèm số hiệu phiên bản ({server_folder_name}/). Bảng app_catalog lưu suffix của file, prefix được cấu hình qua INSTALLER_PREFIX trong .env.",
                                        size=11,
                                        color=theme.PURPLE,
                                        expand=True,
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self._close_confirm_upload_dialog()),
                ft.FilledButton(
                    "Xác nhận tải lên máy chủ",
                    icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
                    bgcolor=theme.PRIMARY,
                    color=theme.SURFACE,
                    on_click=lambda _: self._execute_upload_installer(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._confirm_upload_dlg = dlg
        if self.page:
            self.page.open(dlg)

    def _close_confirm_upload_dialog(self) -> None:
        if self._confirm_upload_dlg and self.page:
            self.page.close(self._confirm_upload_dlg)
        self._confirm_upload_dlg = None

    def _execute_upload_installer(self) -> None:
        if not self.can_manage_templates:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.error("Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền tải file lên máy chủ.")
            return
        if not self._uploading_app or not self._pending_upload_path or not self.ctx:
            return
        app = self._uploading_app
        path = self._pending_upload_path
        name = self._pending_upload_name
        clean_ver = _clean_version_tag(app.recommended_version)

        def work():
            try:
                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.info(f"Đang tải {name} lên máy chủ...")
                updated_app = self.ctx.apps.upload_installer(app.app_code, source_path=path, filename=name, version=clean_ver)
                self._close_confirm_upload_dialog()
                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã tải bộ cài cho {app.app_name} lên máy chủ thành công!")
                # Cập nhật ngay bản ghi bộ nhớ để kích hoạt nút tải xuống ngay
                app.has_installer_file = True
                app.installer_path = updated_app.installer_path
                app.installer_file_size = updated_app.installer_file_size
                for it in self._apps:
                    if it.app_code == app.app_code:
                        it.has_installer_file = True
                        it.installer_path = updated_app.installer_path
                        it.installer_file_size = updated_app.installer_file_size
                self._render_apps_table()
                self._load_apps()
            except Exception as exc:
                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Tải lên máy chủ thất bại: {exc}")

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    # ==================== DIALOG: CHỈNH SỬA THÔNG TIN ỨNG DỤNG ====================
    def _open_edit_path_dialog(self, app: AppItem) -> None:
        if not self.is_admin:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.error("Chỉ TEAM_LEAD mới có quyền sửa thông tin ứng dụng.")
            return
        self._editing_app = app
        self._pending_edit_file_source = ""
        clean_ver = _clean_version_tag(app.recommended_version)
        folder_suggest = f"{app.app_code}_v{clean_ver}/setup.exe" if clean_ver else f"{app.app_code}/setup.exe"

        self._edit_ver_field = ft.TextField(
            label="Phiên bản yêu cầu (Version)",
            value=app.recommended_version or "",
            hint_text="Ví dụ: 3.11.8, 2.43.0...",
            text_size=12,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            expand=True,
        )

        self._edit_cmd_field = ft.TextField(
            label="Lệnh kiểm tra (Check Command)",
            value=app.check_command or "",
            hint_text="Ví dụ: python, git, node, code...",
            text_size=12,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            expand=3,
        )

        self._edit_args_field = ft.TextField(
            label="Tham số kiểm tra (Args)",
            value=app.version_args or "--version",
            hint_text="Ví dụ: --version, -v...",
            text_size=12,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            expand=2,
        )

        self._edit_path_field = ft.TextField(
            label="Đường dẫn file cài trên Server BE (Suffix)",
            value=app.installer_path or "",
            hint_text=f"Ví dụ: {folder_suggest}",
            hint_style=ft.TextStyle(size=12, color=theme.TEXT_MUTED),
            text_size=12,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=8,
            expand=True,
        )
        self._target_path_field = self._edit_path_field
        self._add_name_field = None
        self._add_code_field = None

        server_status_text = (
            f"Đã có file trên máy chủ ({_format_bytes(app.installer_file_size)}) ✓"
            if app.has_installer_file
            else "Chưa có file cài đặt trên Server BE (Bấm 'Chọn file từ máy' để tải lên)"
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.EDIT_NOTE_ROUNDED, color=theme.PRIMARY, size=24),
                    ft.Text(f"Chỉnh sửa ứng dụng: {app.app_name} ({app.app_code})", size=15, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=560,
                content=ft.Column(
                    spacing=12,
                    tight=True,
                    controls=[
                        # 1. Phiên bản yêu cầu (Version)
                        ft.Row(
                            spacing=10,
                            controls=[
                                self._edit_ver_field,
                            ],
                        ),
                        # 2. Lệnh kiểm tra & Tham số
                        ft.Row(
                            spacing=10,
                            controls=[
                                self._edit_cmd_field,
                                self._edit_args_field,
                            ],
                        ),
                        # 3. File cài đặt trên máy chủ
                        ft.Column(
                            spacing=4,
                            tight=True,
                            controls=[
                                ft.Text(
                                    "Bộ cài đặt trên Server BE (đường dẫn tương đối / suffix):",
                                    size=11,
                                    weight=ft.FontWeight.W_600,
                                    color=theme.TEXT_MUTED,
                                ),
                                ft.Row(
                                    spacing=8,
                                    controls=[
                                        self._edit_path_field,
                                        ft.ElevatedButton(
                                            "Chọn file từ máy",
                                            icon=ft.Icons.FILE_OPEN_ROUNDED,
                                            tooltip="Chọn file từ máy tính cá nhân để tự động tải lên Server BE",
                                            on_click=lambda _: self.installer_file_picker.pick_files(
                                                dialog_title=f"Chọn bộ cài cho {app.app_name}",
                                                allowed_extensions=["exe", "msi", "bat", "cmd", "zip", "sh"],
                                            ),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        # 4. Gợi ý & Trạng thái
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=ft.padding.all(10),
                            content=ft.Column(
                                spacing=4,
                                controls=[
                                    ft.Row(
                                        spacing=6,
                                        controls=[
                                            ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=14, color=theme.PRIMARY),
                                            ft.Text("Thông tin thực thi & lưu trữ:", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                        ],
                                    ),
                                    ft.Text(f"• Trạng thái server: {server_status_text}", size=11, color=theme.OK if app.has_installer_file else theme.TEXT_MUTED),
                                    ft.Text("• Khi bấm Lưu, nếu đã chọn file từ máy tính hệ thống sẽ tự động tải lên máy chủ BE.", size=11, color=theme.PRIMARY),
                                    ft.Text("• Chỉ lưu suffix (subpath). Thư mục gốc do INSTALLER_PREFIX quản lý.", size=10, color=theme.TEXT_MUTED),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self._close_edit_dialog()),
                ft.FilledButton(
                    "Lưu thay đổi",
                    icon=ft.Icons.SAVE_ROUNDED,
                    bgcolor=theme.PRIMARY,
                    color=theme.SURFACE,
                    on_click=lambda _: self._save_app_path(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._edit_dlg = dlg
        if self.page:
            self.page.open(dlg)

    def _close_edit_dialog(self) -> None:
        if self._edit_dlg and self.page:
            self.page.close(self._edit_dlg)
        self._edit_dlg = None

    def _on_installer_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        picked = e.files[0].path
        if not picked:
            return
        fname = Path(picked).name

        # Nếu đang ở popup Sửa thông tin ứng dụng:
        if self._target_path_field == self._edit_path_field and self._editing_app:
            self._pending_edit_file_source = picked
            cur_ver = self._edit_ver_field.value.strip() if hasattr(self, "_edit_ver_field") and self._edit_ver_field and self._edit_ver_field.value else self._editing_app.recommended_version
            clean_ver = _clean_version_tag(cur_ver)
            server_folder = f"{self._editing_app.app_code}_v{clean_ver}" if clean_ver else self._editing_app.app_code
            server_path_preview = f"{server_folder}/{fname}"
            if self._edit_path_field:
                self._edit_path_field.value = server_path_preview
                if self._edit_path_field.page:
                    self._edit_path_field.update()
        else:
            self._pending_add_file_source = picked
            code_guess = self._add_code_field.value.strip() if self._add_code_field else ""
            if not code_guess:
                code_guess = Path(picked).stem.lower().replace("-", "_").replace(" ", "_").split("_")[0]
            server_path_preview = f"{code_guess}/{fname}"
            if self._target_path_field:
                self._target_path_field.value = server_path_preview
                if self._target_path_field.page:
                    self._target_path_field.update()

        # Nếu đang ở popup Thêm mới và tên/mã còn trống, tự động trích xuất gợi ý từ file được chọn
        if self._add_name_field and not self._add_name_field.value:
            suggested_name = Path(picked).stem.replace("-", " ").replace("_", " ").title()
            self._add_name_field.value = suggested_name
            if self._add_name_field.page:
                self._add_name_field.update()
        if self._add_code_field and not self._add_code_field.value:
            suggested_code = Path(picked).stem.lower().replace("-", "_").replace(" ", "_").split("_")[0]
            self._add_code_field.value = suggested_code
            if self._add_code_field.page:
                self._add_code_field.update()

    def _save_app_path(self) -> None:
        if not self._editing_app or not self.ctx:
            return
        app = self._editing_app
        app_code = app.app_code
        new_path = self._edit_path_field.value.strip() if self._edit_path_field else (app.installer_path or "")
        new_ver = self._edit_ver_field.value.strip() if hasattr(self, "_edit_ver_field") and self._edit_ver_field else (app.recommended_version or "")
        new_cmd = self._edit_cmd_field.value.strip() if hasattr(self, "_edit_cmd_field") and self._edit_cmd_field else (app.check_command or "")
        new_args = self._edit_args_field.value.strip() if hasattr(self, "_edit_args_field") and self._edit_args_field else (app.version_args or "--version")
        local_src = getattr(self, "_pending_edit_file_source", "")

        def work():
            try:
                # 1. Nếu có file được chọn từ máy cá nhân -> Tải lên Server BE
                if local_src and Path(local_src).is_file():
                    clean_ver = _clean_version_tag(new_ver)
                    if hasattr(self.ctx, "notifier"):
                        self.ctx.notifier.info(f"Đang tải {Path(local_src).name} lên máy chủ...")
                    uploaded = self.ctx.apps.upload_installer(
                        app_code,
                        source_path=local_src,
                        filename=Path(local_src).name,
                        version=clean_ver,
                    )
                    new_server_path = uploaded.installer_path
                    app.has_installer_file = True
                    app.installer_file_size = uploaded.installer_file_size
                else:
                    new_server_path = new_path

                # 2. Cập nhật các thông tin version, check_command, version_args, installer_path
                update_payload = {
                    "recommended_version": new_ver,
                    "check_command": new_cmd,
                    "version_args": new_args,
                    "installer_path": new_server_path,
                }
                updated = self.ctx.apps.update_app(app_code, update_payload)

                # Đồng bộ trạng thái vào đối tượng hiển thị
                app.recommended_version = updated.recommended_version
                app.check_command = updated.check_command
                app.version_args = updated.version_args
                app.installer_path = updated.installer_path
                if updated.has_installer_file:
                    app.has_installer_file = True
                    app.installer_file_size = updated.installer_file_size

                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Đã cập nhật thông tin ứng dụng {app.app_name} thành công!")
                self._close_edit_dialog()
                self._render_apps_table()
                self._load_apps()
            except Exception as exc:
                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Lỗi khi cập nhật ứng dụng: {exc}")

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    def _check_single_app(self, app: AppItem) -> None:
        if not self.ctx:
            return

        def work():
            try:
                res = self.ctx.apps.check_app(app.app_code)
                is_inst = res.get("is_installed", False)
                ver = res.get("installed_version") or "OK"
                if hasattr(self.ctx, "notifier"):
                    if is_inst:
                        self.ctx.notifier.success(f"{app.app_name}: Đã cài đặt trên máy ({ver}) ✓")
                    else:
                        self.ctx.notifier.warning(f"{app.app_name}: Chưa tìm thấy hoặc chưa cài đặt trên máy.")
                self._load_apps()
            except Exception as exc:
                if hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Kiểm tra thất bại: {exc}")

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    # ==================== DIALOG: THÊM ỨNG DỤNG MỚI ====================
    def _open_add_app_dialog(self) -> None:
        if not self.is_admin:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.error("Chỉ TEAM_LEAD mới có quyền thêm ứng dụng vào danh mục.")
            return

        code_input = ft.TextField(label="Mã ứng dụng (viết liền, e.g. postman)", text_size=12, border_color=theme.BORDER)
        name_input = ft.TextField(label="Tên ứng dụng (e.g. Postman Desktop)", text_size=12, border_color=theme.BORDER)
        cat_input = ft.Dropdown(
            label="Danh mục",
            options=[
                ft.dropdown.Option("Môi trường lập trình"),
                ft.dropdown.Option("Quản lý mã nguồn"),
                ft.dropdown.Option("Container & Hạ tầng"),
                ft.dropdown.Option("Môi trường Web & Tooling"),
                ft.dropdown.Option("Công cụ lập trình"),
                ft.dropdown.Option("Cơ sở dữ liệu"),
                ft.dropdown.Option("Trí tuệ nhân tạo"),
                ft.dropdown.Option("Công cụ chung"),
            ],
            value="Công cụ chung",
        )
        ver_input = ft.TextField(
            label="Phiên bản cố định (ví dụ: 3.11, 2.43.0)",
            hint_text="Nhập 1 phiên bản cố định duy nhất...",
            hint_style=ft.TextStyle(size=11, color=theme.TEXT_MUTED),
            text_size=12,
            border_color=theme.BORDER,
        )
        cmd_input = ft.TextField(label="Lệnh kiểm tra (e.g. postman)", text_size=12, border_color=theme.BORDER)
        path_input = ft.TextField(
            label="Đường dẫn file cài trên Server BE (nếu có)",
            hint_text="Ví dụ: postman_v10.0/setup.exe",
            hint_style=ft.TextStyle(size=11, color=theme.TEXT_MUTED),
            text_size=12,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            expand=True,
        )
        self._target_path_field = path_input
        self._add_name_field = name_input
        self._add_code_field = code_input
        self._pending_add_file_source = ""

        path_field_row = ft.Row(
            spacing=8,
            controls=[
                path_input,
                ft.ElevatedButton(
                    "Chọn file từ máy",
                    icon=ft.Icons.FILE_OPEN_ROUNDED,
                    tooltip="Duyệt và chọn file bộ cài (.exe, .msi, .bat, .cmd, .zip) từ máy tính để tải lên Server BE",
                    on_click=lambda _: self.installer_file_picker.pick_files(
                        dialog_title="Chọn file bộ cài đặt ứng dụng",
                        allowed_extensions=["exe", "msi", "bat", "cmd", "zip", "sh"],
                    ),
                ),
            ],
        )
        desc_input = ft.TextField(label="Mô tả ứng dụng", text_size=12, border_color=theme.BORDER, multiline=True, max_lines=2)

        def save_new_app(_):
            if not self.is_admin:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error("Chỉ TEAM_LEAD mới có quyền thêm ứng dụng vào danh mục.")
                return

            data = {
                "app_code": code_input.value.strip(),
                "app_name": name_input.value.strip(),
                "category": cat_input.value,
                "recommended_version": ver_input.value.strip(),
                "check_command": cmd_input.value.strip(),
                "installer_path": path_input.value.strip(),
                "description": desc_input.value.strip(),
            }
            if not data["app_code"] or not data["app_name"]:
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.warning("Vui lòng điền mã và tên ứng dụng.")
                return

            def work():
                try:
                    self.ctx.apps.create_app(data)
                    local_src = getattr(self, "_pending_add_file_source", "")
                    if local_src and Path(local_src).is_file():
                        clean_ver = _clean_version_tag(data.get("recommended_version"))
                        if hasattr(self.ctx, "notifier"):
                            self.ctx.notifier.info(f"Đang tải bộ cài cho {data['app_name']} lên máy chủ...")
                        self.ctx.apps.upload_installer(
                            data["app_code"],
                            source_path=local_src,
                            filename=Path(local_src).name,
                            version=clean_ver,
                        )
                    if hasattr(self.ctx, "notifier"):
                        self.ctx.notifier.success(f"Đã thêm ứng dụng {data['app_name']} vào danh mục!")
                    if self._add_dlg and self.page:
                        self.page.close(self._add_dlg)
                    self._add_dlg = None
                    self._load_apps()
                except Exception as exc:
                    if hasattr(self.ctx, "notifier"):
                        self.ctx.notifier.error(f"Thêm ứng dụng thất bại: {exc}")

            if self.page:
                self.page.run_thread(work)
            else:
                work()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.ADD_BOX_ROUNDED, color=theme.PRIMARY), ft.Text("Thêm ứng dụng vào danh mục", size=16, weight=ft.FontWeight.BOLD)]),
            content=ft.Container(
                width=540,
                content=ft.Column(
                    spacing=10,
                    tight=True,
                    controls=[
                        code_input,
                        name_input,
                        cat_input,
                        ver_input,
                        cmd_input,
                        path_field_row,
                        desc_input,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self.page.close(dlg) if self.page else None),
                ft.FilledButton("Lưu ứng dụng", bgcolor=theme.PRIMARY, color=theme.SURFACE, on_click=save_new_app),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._add_dlg = dlg
        if self.page:
            self.page.open(dlg)

    def _confirm_delete_app(self, app: AppItem) -> None:
        """Xác nhận và xóa ứng dụng khỏi danh mục (Chỉ ADMIN)."""
        dlg: ft.AlertDialog | None = None

        def do_delete(_):
            if self.page and dlg:
                self.page.close(dlg)

            def work():
                try:
                    success = self.ctx.apps.delete_app(app.app_code)
                    if success:
                        if self.ctx and hasattr(self.ctx, "notifier"):
                            self.ctx.notifier.success(f"Đã xóa ứng dụng '{app.app_name}' khỏi danh mục thành công.")
                        self._apps = [a for a in self._apps if a.app_code != app.app_code]
                        self._load_apps()
                    else:
                        if self.ctx and hasattr(self.ctx, "notifier"):
                            self.ctx.notifier.error(f"Không tìm thấy hoặc không thể xóa ứng dụng '{app.app_name}'.")
                except Exception as exc:
                    if self.ctx and hasattr(self.ctx, "notifier"):
                        self.ctx.notifier.error(f"Lỗi khi xóa ứng dụng: {exc}")

            if self.page:
                self.page.run_thread(work)
            else:
                work()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_ROUNDED, color=theme.ERR, size=24),
                ft.Text("Xác nhận xóa ứng dụng", size=16, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Container(
                width=450,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text(
                            f"Bạn có chắc chắn muốn xóa ứng dụng '{app.app_name}' ({app.app_code}) khỏi danh mục không?",
                            size=13,
                            color=theme.TEXT,
                        ),
                        ft.Container(
                            bgcolor=theme.ERR_BG,
                            border=ft.border.all(1, theme.ERR_BORDER),
                            border_radius=8,
                            padding=ft.padding.all(10),
                            content=ft.Row([
                                ft.Icon(ft.Icons.SECURITY_ROUNDED, size=16, color=theme.ERR),
                                ft.Text(
                                    "Thao tác này chỉ dành riêng cho TEAM_LEAD và không thể hoàn tác.",
                                    size=12,
                                    color=theme.ERR,
                                    expand=True,
                                ),
                            ]),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self.page.close(dlg) if self.page and dlg else None),
                ft.FilledButton(
                    "Xác nhận xóa",
                    icon=ft.Icons.DELETE_ROUNDED,
                    style=ft.ButtonStyle(bgcolor=theme.ERR, color="white"),
                    on_click=do_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        if self.page:
            self.page.open(dlg)
