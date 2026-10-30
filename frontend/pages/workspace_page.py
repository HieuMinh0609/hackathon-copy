"""Màn hình Không gian làm việc (WorkspaceScreen) - Chat AI, Checklist Drawer & Quản lý Tài liệu."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
from threading import Lock
import time
from typing import Any, Callable
import uuid

import flet as ft

from frontend.models import AgentReply, AppItem, InstallPlan
from frontend.install_progress import InstallProgress
from frontend.checklist_steps import CheckRun
from frontend.context import FrontendContext
from frontend import theme
from frontend.components.confirm_dialog import confirm_install_dialog
from frontend.components.message_bubble import MessageBubble, extract_runnable_commands
from shared.encoding import completed_output


_PENDING_CHAT_REQUESTS: dict[tuple[str, str], set[str]] = {}
_PENDING_CHAT_LOCK = Lock()


def _set_pending_chat(key: tuple[str, str], request_id: str, pending: bool) -> None:
    """Theo dõi request chat qua vòng đời Workspace để màn mới biết lúc cần đồng bộ lại."""
    with _PENDING_CHAT_LOCK:
        request_ids = _PENDING_CHAT_REQUESTS.setdefault(key, set())
        if pending:
            request_ids.add(request_id)
        else:
            request_ids.discard(request_id)
        if not request_ids:
            _PENDING_CHAT_REQUESTS.pop(key, None)


def _has_pending_chat(key: tuple[str, str]) -> bool:
    with _PENDING_CHAT_LOCK:
        return bool(_PENDING_CHAT_REQUESTS.get(key))


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


class WorkspacePage(ft.Container):
    def __init__(
        self,
        ctx: FrontendContext,
        project: dict[str, Any] | None = None,
        user: dict[str, Any] | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.user = user or {
            "name": "Developer",
            "email": "alex.carter@example.com",
            "permission": "TEAM_LEAD",
            "level": "TEAM_LEAD",
            "is_senior": True,
        }
        permission = str(self.user.get("permission", self.user.get("level", "")) or "").strip().upper()
        self.is_admin = permission == "TEAM_LEAD" or bool(self.user.get("is_team_lead", False))
        self.project = project or {
            "id": 1,
            "code": "PRJ_ECOMMERCE",
            "name": "Hệ thống Microservices E-commerce",
            "desc": "Bảo trì và phát triển module thanh toán mới.",
        }
        self.project_code = self.project.get("code") or f"PRJ_{self.project.get('id', 1)}"
        self.can_manage_template = self.is_admin or bool(self.project.get("can_manage_template", False))
        self.is_senior = self.can_manage_template
        self.on_back = on_back
        self.active_tab = "chat"  # "chat" | "docs"
        self.show_checklist = True
        self._install_progress = InstallProgress()
        self._install_running = False
        self._install_prompt_open = False
        self._check_runs: dict[str, CheckRun] = {}
        self._blocked_steps: set[str] = set()
        self._running_check_key: str | None = None
        self._auto_check_running = False
        self._checklist_results: dict[str, dict[str, Any]] = {}
        self._ingest_running = False
        self._mounted = False
        self._chat_request_key = (
            str(self.user.get("email") or "").strip().lower(),
            str(self.project_code).strip(),
        )
        self._chat_running = False
        self._active_chat_request_id: str | None = None
        self._cancelled_chat_request_ids: set[str] = set()

        # File picker for Docs tab
        self.file_picker = ft.FilePicker(on_result=self._on_files_picked)
        # File picker để chọn nơi lưu khi tải tài liệu xuống
        self.save_picker = ft.FilePicker(on_result=self._on_save_picked)
        self._pending_download: Path | None = None

        # File picker cho checklist (import & download sample)
        self.checklist_picker = ft.FilePicker(on_result=self._on_checklist_file_picked)
        self.checklist_template_save_picker = ft.FilePicker(on_result=self._on_save_checklist_template_picked)
        self._selected_checklist_file_path: str | None = None
        self._upload_dialog_file_text: ft.Text | None = None
        self._upload_dialog_confirm_btn: ft.ElevatedButton | None = None
        self._checklist_upload_dlg: ft.AlertDialog | None = None

        # Build views once
        self.chat_view = self._build_chat_view()
        self.docs_view = self._build_docs_view()
        self.docs_view.visible = False

        self.header = self._build_header()
        self.sidebar = self._build_sidebar()
        self.main_content = ft.Container(
            expand=True,
            content=ft.Stack(
                expand=True,
                controls=[
                    self.chat_view,
                    self.docs_view,
                ],
            ),
        )

        super().__init__(
            expand=True,
            bgcolor=theme.SURFACE,
            content=ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    self.header,
                    ft.Row(
                        spacing=0,
                        expand=True,
                        controls=[
                            self.sidebar,
                            self.main_content,
                        ],
                    ),
                ],
            ),
        )

    def did_mount(self) -> None:
        self._mounted = True
        if self.page:
            for picker in (self.file_picker, self.save_picker, self.checklist_picker, self.checklist_template_save_picker):
                if picker not in self.page.overlay:
                    self.page.overlay.append(picker)
            self.page.update()
            self.page.run_thread(self._load_chat_history)

    def will_unmount(self) -> None:
        self._mounted = False

    # ==================== HEADER ====================
    def _build_header(self) -> ft.Container:
        level_label = self.user.get("permission", self.user.get("level", "MEMBER"))
        user_name = self.user.get("name", "Developer")
        user_badge = ft.Container(
            content=ft.Row(
                spacing=6,
                tight=True,
                controls=[
                    ft.Icon(
                        ft.Icons.VERIFIED_USER_ROUNDED if self.is_senior else ft.Icons.ACCOUNT_CIRCLE_ROUNDED,
                        size=15,
                        color=theme.PRIMARY if self.is_senior else theme.TEXT_MUTED,
                    ),
                    ft.Text(
                        f"{user_name} • {level_label}",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=theme.PRIMARY if self.is_senior else theme.TEXT,
                    ),
                ],
            ),
            bgcolor=theme.PRIMARY_BG if self.is_senior else theme.SURFACE_ALT,
            border=ft.border.all(1, theme.PRIMARY_BORDER if self.is_senior else theme.BORDER),
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
            tooltip=f"Tài khoản: {self.user.get('email', '')}\nCấp bậc: {level_label} ({'TEAM_LEAD/PROJECT_LEAD: được quản lý template' if self.is_senior else 'MEMBER: chỉ thực thi'})",
        )
        deadline_badge: ft.Control | None = None
        if self.project.get("due_at"):
            deadline_status = str(self.project.get("deadline_status") or "active")
            days_remaining = int(self.project.get("days_remaining") or 0)
            if deadline_status == "completed":
                deadline_label, deadline_color, deadline_bg = "Đã hoàn thành", theme.EMERALD, theme.EMERALD_BG
            elif deadline_status == "overdue":
                deadline_label, deadline_color, deadline_bg = f"Quá hạn {abs(days_remaining)} ngày", theme.ERR, theme.ERR_BG
            else:
                deadline_label = f"Còn {max(0, days_remaining)} ngày"
                deadline_color = theme.WARN if days_remaining <= 3 else theme.PRIMARY
                deadline_bg = theme.WARN_BG if days_remaining <= 3 else theme.PRIMARY_BG
            deadline_badge = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.EVENT_ROUNDED, size=13, color=deadline_color),
                        ft.Text(deadline_label, size=10, weight=ft.FontWeight.W_600, color=deadline_color),
                    ],
                    spacing=4,
                    tight=True,
                ),
                bgcolor=deadline_bg,
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                tooltip=f"Hạn hoàn thành onboarding: {str(self.project.get('due_at'))[:10]}",
            )

        return ft.Container(
            height=58,
            bgcolor=theme.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.BORDER)),
            padding=ft.padding.symmetric(horizontal=18),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                icon_size=20,
                                icon_color=theme.TEXT_MUTED,
                                tooltip="Quay lại Dashboard",
                                on_click=lambda _: self._close_workspace(),
                            ),
                            ft.VerticalDivider(width=1, color=theme.BORDER, thickness=1),
                            ft.Text(self.project.get("name", "Workspace"), size=15, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                            *([deadline_badge] if deadline_badge else []),
                            ft.Container(
                                content=ft.Text("ONLINE", size=10, weight=ft.FontWeight.BOLD, color=theme.EMERALD),
                                bgcolor=theme.EMERALD_BG,
                                border=ft.border.all(1, theme.EMERALD_BORDER),
                                border_radius=12,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            user_badge,
                        ],
                    ),
                ],
            ),
        )

    def _close_workspace(self) -> None:
        """Rời workspace ngay; dữ liệu Dashboard sẽ được làm mới ở background."""
        self._mounted = False
        if self.on_back:
            self.on_back()

    # ==================== SIDEBAR ====================
    def _build_sidebar(self) -> ft.Container:
        self.nav_chat_btn = self._sidebar_item("Không gian AI", ft.Icons.FORUM_OUTLINED, "chat")
        self.nav_docs_btn = self._sidebar_item("Tài liệu Project", ft.Icons.DESCRIPTION_OUTLINED, "docs")

        return ft.Container(
            width=240,
            bgcolor=theme.SURFACE,
            border=ft.border.only(right=ft.BorderSide(1, theme.BORDER)),
            padding=ft.padding.all(14),
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                        content=ft.Text("CÔNG CỤ DỰ ÁN", size=11, weight=ft.FontWeight.BOLD, color=theme.TEXT_LIGHT),
                    ),
                    self.nav_chat_btn,
                    self.nav_docs_btn,
                ],
            ),
        )

    def _sidebar_item(self, title: str, icon: str, tab_id: str) -> ft.Container:
        is_active = self.active_tab == tab_id
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=8,
            bgcolor=theme.PRIMARY_BG if is_active else ft.Colors.TRANSPARENT,
            ink=True,
            on_click=lambda _, t=tab_id: self._switch_tab(t),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(icon, size=18, color=theme.PRIMARY if is_active else theme.TEXT_MUTED),
                    ft.Text(title, size=13, weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_500, color=theme.PRIMARY if is_active else theme.TEXT),
                ],
            ),
        )

    def _switch_tab(self, tab_id: str) -> None:
        if self.active_tab == tab_id:
            return
        self.active_tab = tab_id
        self._update_sidebar_styles()

        self.chat_view.visible = (self.active_tab == "chat")
        self.docs_view.visible = (self.active_tab == "docs")

        if self.active_tab == "docs":
            self._refresh_docs_list()

        if self.page:
            self.chat_view.update()
            self.docs_view.update()

    def _update_sidebar_styles(self) -> None:
        self.nav_chat_btn.bgcolor = theme.PRIMARY_BG if self.active_tab == "chat" else ft.Colors.TRANSPARENT
        self.nav_chat_btn.content.controls[0].color = theme.PRIMARY if self.active_tab == "chat" else theme.TEXT_MUTED
        self.nav_chat_btn.content.controls[1].color = theme.PRIMARY if self.active_tab == "chat" else theme.TEXT
        self.nav_chat_btn.content.controls[1].weight = ft.FontWeight.W_600 if self.active_tab == "chat" else ft.FontWeight.W_500

        self.nav_docs_btn.bgcolor = theme.PRIMARY_BG if self.active_tab == "docs" else ft.Colors.TRANSPARENT
        self.nav_docs_btn.content.controls[0].color = theme.PRIMARY if self.active_tab == "docs" else theme.TEXT_MUTED
        self.nav_docs_btn.content.controls[1].color = theme.PRIMARY if self.active_tab == "docs" else theme.TEXT
        self.nav_docs_btn.content.controls[1].weight = ft.FontWeight.W_600 if self.active_tab == "docs" else ft.FontWeight.W_500

        if self.page:
            self.nav_chat_btn.update()
            self.nav_docs_btn.update()

    # ==================== TAB: CHAT VIEW ====================
    def _build_chat_view(self) -> ft.Row:
        # Badge hiển thị khi đang bật chế độ Chuyên gia Checklist Qwen 2.5:7b
        self._checklist_mode_badge = ft.Container(
            visible=self.show_checklist,
            content=ft.Row(
                spacing=4,
                tight=True,
                controls=[
                    ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=12, color=theme.PRIMARY),
                    ft.Text("Chuyên gia Qwen 2.5:7b", size=11, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                ],
            ),
            bgcolor=theme.PRIMARY_BG,
            border=ft.border.all(1, theme.PRIMARY_BORDER),
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
        )

        self._checklist_switch_label = ft.Text(
            "Trợ lý Checklist",
            size=13,
            weight=ft.FontWeight.W_500,
            color=theme.PRIMARY if self.show_checklist else theme.TEXT_MUTED,
        )

        self.checklist_switch = ft.Switch(
            value=self.show_checklist,
            active_color=theme.PRIMARY,
            tooltip="Bật chế độ Chuyên gia Checklist Qwen 2.5:7b (hỗ trợ cài đặt, kiểm tra IP, code tối ưu)",
            on_change=self._toggle_checklist_drawer,
        )

        # Chat column (Left)
        chat_toolbar = ft.Container(
            height=54,
            bgcolor=theme.BG,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.BORDER)),
            padding=ft.padding.symmetric(horizontal=20),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=18, color=theme.PRIMARY),
                            ft.Text("Trợ lý AI-Buddy", size=14, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                            self._checklist_mode_badge,
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                                icon_size=18,
                                icon_color=theme.TEXT_LIGHT,
                                tooltip="Xóa làm mới lịch sử chat của dự án này",
                                on_click=lambda _: self._confirm_clear_chat_history(),
                            ),
                            ft.VerticalDivider(width=1, color=theme.BORDER, thickness=1),
                            self._checklist_switch_label,
                            self.checklist_switch,
                        ],
                    ),
                ],
            ),
        )

        self.chat_messages = ft.ListView(
            expand=True,
            spacing=16,
            auto_scroll=True,
            padding=ft.padding.all(20),
        )

        # Initial message
        date_str = datetime.now().strftime("%d/%m/%Y")
        self.chat_messages.controls.append(
            ft.Container(
                alignment=ft.alignment.center,
                padding=ft.padding.only(bottom=10),
                content=ft.Text(f"Khởi tạo phiên làm việc: {date_str}", size=11, color=theme.TEXT_LIGHT),
            )
        )
        self.chat_messages.controls.append(
            MessageBubble(
                "Chào bạn, tôi là AI Buddy! Tôi có thể giúp bạn kiểm tra môi trường, cài đặt công cụ cần thiết, "
                "hoặc giải đáp thắc mắc về tài liệu dự án.\n\n"
                "Khi bạn bật công tắc **Trợ lý Checklist**, hệ thống sẽ chủ động dùng mô hình **Ollama Qwen 2.5:7b** "
                "kết hợp cùng cẩm nang hướng dẫn để giải đáp cài đặt, kiểm tra IP access và viết code script tối ưu.",
                is_user=False,
                on_run_command=self._execute_command_from_chat,
                timestamp=datetime.now(),
            )
        )

        self.chat_typing = ft.Container(
            visible=False,
            padding=ft.padding.only(left=20, bottom=8),
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.ProgressRing(width=14, height=14, stroke_width=2, color=theme.PRIMARY),
                    ft.Text("AI Buddy (Qwen 2.5:7b) đang suy nghĩ…", size=12, color=theme.TEXT_MUTED, italic=True),
                ],
            ),
        )

        # Input và nút gửi cùng chiều cao cố định để thẳng hàng (Enter để gửi)
        CHAT_BAR_HEIGHT = 48
        initial_hint = (
            "Chuyên gia Checklist: Hỏi về cài đặt, IP access, viết code, sửa lỗi..."
            if self.show_checklist
            else "Nhắn tin yêu cầu AI xử lý..."
        )
        self.chat_input = ft.TextField(
            hint_text=initial_hint,
            expand=True,
            height=CHAT_BAR_HEIGHT,
            bgcolor=theme.BG,
            border_color=theme.BORDER,
            focused_border_color=theme.PRIMARY,
            border_radius=12,
            text_size=13,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=0),
            on_submit=self._submit_chat,
        )

        self.chat_send_btn = ft.Container(
            width=CHAT_BAR_HEIGHT,
            height=CHAT_BAR_HEIGHT,
            bgcolor=theme.PRIMARY,
            border_radius=12,
            alignment=ft.alignment.center,
            on_click=self._submit_chat,
            tooltip="Gửi tin nhắn",
            ink=True,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=6,
                color=ft.Colors.with_opacity(0.2, theme.PRIMARY),
                offset=ft.Offset(0, 2),
            ),
            content=ft.Icon(ft.Icons.SEND_ROUNDED, size=20, color=theme.TEXT_WHITE),
        )

        chat_bottom_bar = ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=14),
            border=ft.border.only(top=ft.BorderSide(1, theme.BORDER)),
            bgcolor=theme.SURFACE,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self.chat_input,
                    self.chat_send_btn,
                ],
            ),
        )

        chat_column = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                chat_toolbar,
                self.chat_messages,
                self.chat_typing,
                chat_bottom_bar,
            ],
        )

        # Checklist Drawer (Right)
        self.checklist_drawer = self._build_checklist_drawer()

        return ft.Row(
            spacing=0,
            expand=True,
            controls=[
                ft.Container(chat_column, expand=True),
                self.checklist_drawer,
            ],
        )

    def _toggle_checklist_drawer(self, e: ft.ControlEvent) -> None:
        self.show_checklist = e.control.value
        self.checklist_drawer.visible = self.show_checklist
        self._checklist_switch_label.color = theme.PRIMARY if self.show_checklist else theme.TEXT_MUTED
        self._checklist_mode_badge.visible = self.show_checklist
        if self.show_checklist:
            self.chat_input.hint_text = "Chuyên gia Checklist: Hỏi về cài đặt, IP access, viết code, sửa lỗi..."
        else:
            self.chat_input.hint_text = "Nhắn tin yêu cầu AI xử lý..."
        if self.page:
            self.checklist_drawer.update()
            self._checklist_switch_label.update()
            self._checklist_mode_badge.update()
            self.chat_input.update()

    def _submit_chat(self, _=None) -> None:
        if self._chat_running:
            self._cancel_chat_response()
            return
        text = (self.chat_input.value or "").strip()
        if not text:
            return
        request_id = uuid.uuid4().hex
        checklist_mode = self.show_checklist
        self._active_chat_request_id = request_id
        self._set_chat_running(True)
        self.chat_input.value = ""
        self._safe_update(self.chat_input)

        # Add user message
        self.chat_messages.controls.append(MessageBubble(text, is_user=True, timestamp=datetime.now()))
        self.chat_typing.visible = True
        self._safe_update(self.chat_messages, self.chat_typing)

        _set_pending_chat(self._chat_request_key, request_id, True)
        self.page.run_thread(self._handle_chat_response, text, request_id, checklist_mode)

    def _set_chat_running(self, running: bool) -> None:
        self._chat_running = running
        self.chat_input.disabled = running
        self.chat_send_btn.bgcolor = theme.ERR if running else theme.PRIMARY
        self.chat_send_btn.tooltip = "Hủy yêu cầu đang xử lý" if running else "Gửi tin nhắn"
        self.chat_send_btn.content = ft.Icon(
            ft.Icons.STOP_ROUNDED if running else ft.Icons.SEND_ROUNDED,
            size=20,
            color=theme.TEXT_WHITE,
        )
        self._safe_update(self.chat_input, self.chat_send_btn)

    def _cancel_chat_response(self) -> None:
        request_id = self._active_chat_request_id
        if not request_id:
            return
        self._cancelled_chat_request_ids.add(request_id)
        self._active_chat_request_id = None
        _set_pending_chat(self._chat_request_key, request_id, False)
        self._set_chat_running(False)
        self.chat_typing.visible = False
        self.chat_messages.controls.append(
            MessageBubble("Đã hủy yêu cầu đang xử lý.", is_user=False, timestamp=datetime.now())
        )
        self._safe_update(self.chat_typing, self.chat_messages)

        def cancel_work() -> None:
            try:
                self.ctx.agent.cancel_chat(request_id, project_code=self.project_code)
            except Exception as exc:
                if self._mounted:
                    self.ctx.notifier.warning(f"Không thể đồng bộ trạng thái hủy với backend: {exc}")

        if self.page:
            self.page.run_thread(cancel_work)
        else:
            cancel_work()

    def _handle_chat_response(
        self,
        text: str,
        request_id: str,
        checklist_mode: bool,
    ) -> None:
        reply = None
        error: Exception | None = None
        try:
            reply = self.ctx.agent.chat(
                text,
                project_code=self.project_code,
                checklist_mode=checklist_mode,
                request_id=request_id,
            )
        except Exception as exc:
            error = exc
        finally:
            _set_pending_chat(self._chat_request_key, request_id, False)

        if request_id in self._cancelled_chat_request_ids:
            self._cancelled_chat_request_ids.discard(request_id)
            return

        # Response đã được backend lưu. Workspace cũ không cập nhật control sau khi người dùng rời màn hình.
        if not self._mounted:
            return
        if self._active_chat_request_id != request_id:
            return

        self._active_chat_request_id = None
        self._set_chat_running(False)
        if error is not None:
            self.chat_typing.visible = False
            self._safe_update(self.chat_typing)
            self.ctx.notifier.error(f"AI chưa thể phản hồi: {error}")
            return
        if reply is None:
            return

        self.chat_typing.visible = False
        reply_time = getattr(reply, "created_at", None) or datetime.now()
        self.chat_messages.controls.append(
            MessageBubble(
                reply.text,
                is_user=False,
                sources=reply.sources,
                on_run_command=self._execute_command_from_chat,
                timestamp=reply_time,
            )
        )

        if self.page:
            self.chat_typing.update()
            self.chat_messages.update()

        # If install needed
        if reply.pending_install:
            plan, key = reply.pending_install, reply.pending_key
            if not self._install_running and not self._install_prompt_open:
                self._install_prompt_open = True
                self._install_progress.begin(plan.software)
                self._show_install_plan(plan, key)

        # Update checklist in case check commands were run
        self._refresh_checklist_items()

    def _load_chat_history(self) -> None:
        """Tải 50 tin nhắn hội thoại gần nhất của người dùng trong dự án này từ backend."""
        if not self.ctx or not hasattr(self.ctx, "agent"):
            return
        try:
            had_pending_request = _has_pending_chat(self._chat_request_key)
            self._refresh_chat_history_from_backend()
            # Nếu Workspace cũ còn chờ AI, đợi request đó lưu response rồi tải lại cho Workspace mới.
            if had_pending_request:
                deadline = time.monotonic() + 300
                while self._mounted and _has_pending_chat(self._chat_request_key) and time.monotonic() < deadline:
                    time.sleep(0.5)
                if self._mounted:
                    self._refresh_chat_history_from_backend()
        except Exception:
            # Nếu lỗi mạng hoặc backend chưa sẵn sàng, giữ nguyên lời chào khởi tạo
            pass

    def _refresh_chat_history_from_backend(self) -> None:
        history = self.ctx.agent.get_history(self.project_code, limit=50)
        if not history or not self._mounted:
            return
        controls: list[ft.Control] = [
            ft.Container(
                alignment=ft.alignment.center,
                padding=ft.padding.only(bottom=10),
                content=ft.Text(
                    f"Lịch sử hội thoại dự án ({len(history)} tin nhắn gần nhất)",
                    size=11,
                    color=theme.TEXT_LIGHT,
                ),
            )
        ]
        for item in history:
            is_user = item.get("sender") == "user"
            controls.append(
                MessageBubble(
                    item.get("message", ""),
                    is_user=is_user,
                    sources=item.get("sources", []) if not is_user else None,
                    on_run_command=self._execute_command_from_chat if not is_user else None,
                    timestamp=item.get("created_at"),
                )
            )
        self.chat_messages.controls = controls
        if self.chat_messages.page:
            self.chat_messages.update()
        elif self.page:
            self.page.update()

    def _confirm_clear_chat_history(self) -> None:
        """Hộp thoại xác nhận xóa làm mới lịch sử chat của dự án."""
        def on_confirm(_):
            if self.page:
                self.page.close(dlg)

            def work():
                try:
                    self.ctx.agent.clear_history(self.project_code)
                    self._reset_default_chat_messages()
                    if self.ctx and hasattr(self.ctx, "notifier"):
                        self.ctx.notifier.info("Đã làm mới lịch sử hội thoại của dự án này.")
                except Exception as exc:
                    if self.ctx and hasattr(self.ctx, "notifier"):
                        self.ctx.notifier.error(f"Không thể xóa lịch sử chat: {exc}")

            if self.page:
                self.page.run_thread(work)
            else:
                work()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.DELETE_SWEEP_ROUNDED, color=theme.WARN),
                ft.Text("Xóa lịch sử chat", size=16, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Text(
                "Bạn có chắc muốn xóa 50 tin nhắn lịch sử gần nhất của dự án này không? Thao tác này sẽ giúp bạn bắt đầu phiên làm việc mới.",
                size=13,
            ),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: self.page.close(dlg) if self.page else None),
                ft.ElevatedButton("Xác nhận xóa", bgcolor=theme.ERR, color=theme.TEXT_WHITE, on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self.page:
            self.page.open(dlg)

    def _reset_default_chat_messages(self) -> None:
        """Đặt lại khung chat về trạng thái ban đầu sau khi xóa lịch sử."""
        date_str = datetime.now().strftime("%d/%m/%Y")
        self.chat_messages.controls = [
            ft.Container(
                alignment=ft.alignment.center,
                padding=ft.padding.only(bottom=10),
                content=ft.Text(f"Khởi tạo phiên làm việc mới: {date_str}", size=11, color=theme.TEXT_LIGHT),
            ),
            MessageBubble(
                "Chào bạn, tôi là AI Buddy! Tôi có thể giúp bạn kiểm tra môi trường, cài đặt công cụ cần thiết, "
                "hoặc giải đáp thắc mắc về tài liệu dự án.\n\n"
                "Khi bạn bật công tắc **Trợ lý Checklist**, hệ thống sẽ chủ động dùng mô hình **Ollama Qwen 2.5:7b** "
                "kết hợp cùng cẩm nang hướng dẫn để giải đáp cài đặt, kiểm tra IP access và viết code script tối ưu.",
                is_user=False,
                on_run_command=self._execute_command_from_chat,
                timestamp=datetime.now(),
            ),
        ]
        if self.chat_messages.page:
            self.chat_messages.update()
        elif self.page:
            self.page.update()

    def _execute_command_from_chat(self, cmd: str) -> None:
        """Thực thi lệnh terminal được đề xuất từ khung chat khi người dùng bấm nút Run."""
        if hasattr(self, "_cmd_executing") and self._cmd_executing:
            if self.ctx and hasattr(self.ctx, "notifier"):
                self.ctx.notifier.warning("Đang có một lệnh đang chạy, vui lòng chờ trong giây lát.")
            return

        self._cmd_executing = True
        if self.ctx and hasattr(self.ctx, "notifier"):
            self.ctx.notifier.info(f"Đang thực thi lệnh: {cmd}...")

        # Tạo các control hiển thị trong Dialog Terminal
        terminal_status = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.ProgressRing(width=16, height=16, stroke_width=2, color=theme.PRIMARY),
                ft.Text("Đang thực thi lệnh trên hệ thống...", size=12, color=theme.PRIMARY, weight=ft.FontWeight.W_600),
            ],
        )

        output_text = ft.Text(
            f"> {cmd}\n[Đang chạy... Vui lòng đợi kết quả trả về]\n",
            size=12,
            font_family="Consolas, monospace",
            color="#E0E0E0",
            selectable=True,
        )

        terminal_container = ft.Container(
            bgcolor="#1E1E1E",
            border=ft.border.all(1, "#333333"),
            border_radius=8,
            padding=14,
            height=260,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[output_text],
            ),
        )

        def copy_output(_):
            if self.page:
                self.page.set_clipboard(output_text.value or "")
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success("Đã sao chép kết quả output vào clipboard!")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=theme.PRIMARY, size=22),
                    ft.Text("Thực thi lệnh Terminal", size=16, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=560,
                content=ft.Column(
                    spacing=10,
                    tight=True,
                    controls=[
                        terminal_status,
                        terminal_container,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Đóng", on_click=lambda _: self.page.close(dlg) if self.page else None),
                ft.OutlinedButton("Sao chép kết quả", icon=ft.Icons.COPY_ROUNDED, on_click=copy_output),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        if self.page:
            self.page.open(dlg)

        def work():
            import subprocess, os
            exit_code = -1
            raw_out = ""
            try:
                if os.name == "nt":
                    proc = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", cmd],
                        capture_output=True,
                        timeout=120,
                    )
                else:
                    proc = subprocess.run(
                        ["bash", "-c", cmd],
                        capture_output=True,
                        timeout=120,
                    )
                exit_code = proc.returncode
                stdout, stderr = completed_output(proc, encodings=("utf-8",))
                raw_out = (stdout + "\n" + stderr).strip()
            except subprocess.TimeoutExpired:
                exit_code = 124
                raw_out = "Lỗi: Lệnh đã chạy quá thời gian chờ (120 giây)."
            except Exception as exc:
                exit_code = -1
                raw_out = f"Lỗi khi thực thi lệnh: {exc}"
            finally:
                self._cmd_executing = False

            # Cập nhật kết quả vào Terminal Dialog
            if exit_code == 0:
                terminal_status.controls = [
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=theme.EMERALD, size=18),
                    ft.Text(f"Lệnh đã chạy thành công (Mã thoát: 0)", size=12, color=theme.EMERALD, weight=ft.FontWeight.BOLD),
                ]
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.success(f"Lệnh thực thi thành công ✓")
            else:
                terminal_status.controls = [
                    ft.Icon(ft.Icons.ERROR_ROUNDED, color=theme.ERR, size=18),
                    ft.Text(f"Lệnh kết thúc với lỗi (Mã thoát: {exit_code})", size=12, color=theme.ERR, weight=ft.FontWeight.BOLD),
                ]
                if self.ctx and hasattr(self.ctx, "notifier"):
                    self.ctx.notifier.error(f"Lệnh trả về mã lỗi: {exit_code}")

            output_text.value = f"> {cmd}\n\n{raw_out if raw_out else '(Lệnh đã thực thi xong, không có kết quả xuất ra màn hình)'}"
            if terminal_container.page:
                terminal_status.update()
                output_text.update()
            elif self.page:
                self.page.update()

            # Thêm tin nhắn kết quả vào dòng chat để người dùng theo dõi lịch sử
            chat_result_msg = f"💻 **Kết quả thực thi:** `{cmd}` ({'Thành công ✓' if exit_code == 0 else f'Mã lỗi {exit_code} ❌'})\n\n```output\n{raw_out or '(Không có kết quả xuất ra màn hình)'}\n```"
            self.chat_messages.controls.append(
                MessageBubble(
                    chat_result_msg,
                    is_user=False,
                    on_run_command=self._execute_command_from_chat,
                    timestamp=datetime.now(),
                )
            )
            if self.chat_messages.page:
                self.chat_messages.update()
            elif self.page:
                self.page.update()

            # Lưu log kết quả thực thi terminal vào lịch sử chat backend
            if self.ctx and hasattr(self.ctx, "agent") and hasattr(self.ctx.agent, "save_message"):
                try:
                    self.ctx.agent.save_message(
                        message=chat_result_msg,
                        project_code=self.project_code,
                        sender="ai",
                        metadata={
                            "type": "terminal_execution",
                            "command": cmd,
                            "exit_code": exit_code,
                        },
                    )
                except Exception:
                    pass

        if self.page:
            self.page.run_thread(work)
        else:
            work()

    @staticmethod
    def _safe_update(*controls: ft.Control) -> None:
        """Chỉ update control đã gắn vào page (tránh AssertionError khi đang ẩn/đã rời màn hình)."""
        for c in controls:
            if c.page:
                c.update()

    def _render_install_progress(self) -> None:
        progress = self._install_progress
        titles = ("Chuẩn bị lệnh", "Bạn cấp phép", "Chạy lệnh cài đặt", "Kiểm tra lại phiên bản")
        labels = {"pending": "Chờ", "running": "Đang chạy", "done": "Hoàn tất", "failed": "Lỗi", "cancelled": "Đã hủy"}
        colors = {"pending": theme.TEXT_MUTED, "running": theme.PRIMARY, "done": theme.OK,
                  "failed": theme.ERR, "cancelled": theme.WARN}
        rows: list[ft.Control] = [ft.Text(f"Cài đặt: {progress.software}", weight=ft.FontWeight.W_600, size=12)]
        for index, (title, state) in enumerate(zip(titles, progress.states)):
            icon = ft.ProgressRing(width=13, height=13, stroke_width=2, color=colors[state]) if state == "running" else ft.Icon(
                ft.Icons.CHECK_CIRCLE if state == "done" else ft.Icons.CANCEL if state in ("failed", "cancelled") else ft.Icons.RADIO_BUTTON_UNCHECKED,
                size=14, color=colors[state],
            )
            label = "Chờ bạn xác nhận" if index == 1 and state == "running" else labels[state]
            rows.append(ft.Row([icon, ft.Text(f"{index + 1}. {title} · {label}", size=11, color=colors[state])], spacing=6))
        rows.append(ft.Text(progress.detail, size=11, color=theme.TEXT_MUTED, selectable=True))
        self.install_progress_panel.content = ft.Column(rows, spacing=5, tight=True)
        self.install_progress_panel.visible = True
        self._safe_update(self.install_progress_panel)

    def _show_install_plan(self, plan: InstallPlan, key: str | None) -> None:
        self._install_progress.software = plan.software
        self._install_progress.advance(1, "Xem lệnh trong hộp thoại. Chưa có lệnh cài nào được chạy.")
        self._render_install_progress()

        def cancel() -> None:
            self._install_prompt_open = False
            self._install_progress.stop("Bạn đã hủy. Không thực thi lệnh cài đặt.", cancelled=True)
            self._render_install_progress()

        confirm_install_dialog(self.page, plan, lambda: self._start_install(plan, key), on_cancel=cancel)

    def _find_app_in_catalog(self, item: Any) -> AppItem | None:
        """Tìm bản ghi ứng dụng tương ứng trong bảng App Catalog theo mã hoặc tên."""
        if not self.ctx or not hasattr(self.ctx, "apps"):
            return None
        key = getattr(item, "key", "") or ""
        raw_code = key.removeprefix("sw_").strip().lower()

        # 1. Thử lấy trực tiếp bằng app_code (python, git, docker, node, vscode, psql, dbeaver, ollama, ...)
        try:
            app = self.ctx.apps.get_app(raw_code)
            if app:
                return app
        except Exception:
            pass

        # 2. Quét qua danh sách các ứng dụng trong App Catalog
        try:
            apps = self.ctx.apps.list_apps()
        except Exception:
            apps = []

        params = getattr(item, "params", {}) or {}
        cmd = str(params.get("command", "")).strip().lower()
        name = str(params.get("name") or getattr(item, "title", "")).strip().lower()

        for a in apps:
            a_code = a.app_code.lower()
            a_cmd = (a.check_command or "").lower()
            a_name = a.app_name.lower()

            if a_code == raw_code or (cmd and a_cmd == cmd):
                return a
            if name and (name in a_name or a_name in name):
                return a
        return None


    def _request_install(self, key: str) -> None:
        """Lấy kế hoạch chạy bộ cài đã lưu từ backend, hỏi xác nhận trước khi thực thi."""
        if self._install_running or self._install_prompt_open or self._auto_check_running or self._running_check_key or key in self._blocked_steps:
            return
        self._install_prompt_open = True
        self._install_progress.begin("Kiểm tra bộ cài đặt trong App Catalog")
        self._render_install_progress()

        def release() -> None:
            self._install_prompt_open = False

        def prepare() -> None:
            try:
                item = self.ctx.checklist.get_item(key)
                if not item:
                    release()
                    msg = f"Không tìm thấy mục checklist '{key}'."
                    self._install_progress.stop(msg)
                    self._render_install_progress()
                    self.ctx.notifier.error(msg)
                    return

                # 1. Kiểm tra ứng dụng trong bảng app_catalog
                app = self._find_app_in_catalog(item)
                if not app:
                    release()
                    item_name = item.params.get("name") or item.title
                    msg = f"Ứng dụng '{item_name}' chưa có trong danh mục ứng dụng (App Catalog)."
                    self._install_progress.stop(msg)
                    self._render_install_progress()
                    self.ctx.notifier.error(msg)
                    return

                # Backend giải quyết đường dẫn đã lưu và chỉ tạo plan; chưa chạy bộ cài.
                plan = self.ctx.verification.catalog_install_plan(app.app_code, key)
                self._show_install_plan(plan, key)

            except Exception as exc:
                release()
                err_msg = f"Lỗi xử lý cài đặt ứng dụng: {exc}"
                self._install_progress.stop(err_msg)
                self._render_install_progress()
                self.ctx.notifier.error(err_msg)

        self.page.run_thread(prepare)

    def _start_install(self, plan: InstallPlan, key: str | None) -> None:
        self._install_prompt_open = False
        if self._install_running or self._auto_check_running or self._running_check_key or key in self._blocked_steps:
            self._install_progress.stop("Có thao tác khác đang chạy. Hãy chờ rồi tạo lại yêu cầu cài đặt.")
            self._render_install_progress()
            self.ctx.notifier.warning("Vui lòng chờ thao tác hiện tại hoàn tất rồi thử lại.")
            return
        self._install_running = True
        self._install_progress.advance(2, "Đang chạy lệnh đã được cấp phép. Đợi xác nhận UAC nếu hệ điều hành yêu cầu.")
        self._render_install_progress()
        self.auto_check_button.disabled = True
        self._safe_update(self.auto_check_button)
        self.page.run_thread(self._do_install, plan, key)

    def _do_install(self, plan: InstallPlan, key: str | None) -> None:
        self.chat_typing.visible = True
        self.auto_check_status.value = f"Đang cài {plan.software}… Có thể cần xác nhận quyền từ hệ điều hành."
        self._safe_update(self.chat_typing, self.auto_check_status)
        try:
            self._refresh_checklist_items()
            reply = self.ctx.agent.confirm_install(plan, key)
            self.chat_messages.controls.append(
                MessageBubble(
                    reply.text,
                    is_user=False,
                    on_run_command=self._execute_command_from_chat,
                    timestamp=getattr(reply, "created_at", None) or datetime.now(),
                )
            )
            self._safe_update(self.chat_messages)
            if reply.install_ok is not True:
                self._install_progress.stop("Cài đặt chưa hoàn tất. Xem lỗi quyền, nguồn gói hoặc kiểm tra phiên bản trong chat.")
                self.auto_check_status.value = "Cài đặt chưa hoàn tất; muốn thử lại cần xác nhận mới."
                self.ctx.notifier.warning(self.auto_check_status.value)
                return
            self._install_progress.advance(3, "Đang chạy lại lệnh kiểm tra phiên bản thực tế…")
            self._render_install_progress()
            if key:
                result = self.ctx.verification.verify_key(key)
                self._checklist_results[key] = result
                if result["status"] == "passed":
                    self.auto_check_status.value = f"Kiểm tra lại đạt: {result['message']}"
                    self._install_progress.finish(self.auto_check_status.value)
                    self.ctx.notifier.success(self.auto_check_status.value)
                else:
                    self.auto_check_status.value = f"Kiểm tra lại chưa đạt: {result['message']}"
                    self._install_progress.stop(self.auto_check_status.value)
                    self.ctx.notifier.warning("Xem kết quả cài đặt trong chat. Nếu vừa cài xong, có thể cần mở lại ứng dụng để cập nhật PATH.")
            else:
                self.auto_check_status.value = "Lệnh cài đã kết thúc; chưa có mục checklist để kiểm tra phiên bản."
                self._install_progress.stop(self.auto_check_status.value)
        except Exception as exc:
            self.auto_check_status.value = "Không hoàn tất được cài đặt hoặc kiểm tra lại."
            self._install_progress.stop(f"{self.auto_check_status.value} {exc}")
            self.ctx.notifier.error(f"Lỗi cài đặt: {exc}")
        finally:
            self._render_install_progress()
            self._install_running = False
            self.chat_typing.visible = False
            self.auto_check_button.disabled = False
            self._safe_update(self.chat_typing, self.auto_check_button, self.auto_check_status)
            try:
                self._refresh_checklist_items()
            except Exception:
                pass  # Giữ UI hoạt động khi backend mất kết nối.

    # ==================== CHECKLIST DRAWER ====================
    def _build_checklist_drawer(self) -> ft.Container:
        self.checklist_progress_bar = ft.ProgressBar(
            value=0,
            color=theme.PRIMARY,
            bgcolor=theme.SURFACE_ALT,
            height=6,
        )
        self.checklist_percent_text = ft.Text("0%", size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED)
        self.checklist_items_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

        template_upload_action = ft.Container(
            content=ft.Row(
                spacing=4,
                tight=True,
                controls=[
                    ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=13, color=theme.PRIMARY),
                    ft.Text("Tải lên Checklist", size=11, weight=ft.FontWeight.W_600, color=theme.PRIMARY),
                ],
            ),
            bgcolor=theme.PRIMARY_BG,
            border=ft.border.all(1, theme.PRIMARY_BORDER),
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=5),
            on_click=lambda _: self._open_upload_checklist_dialog(),
            ink=True,
            tooltip="Mở cửa sổ tải lên checklist mới hoặc tải file mẫu CSV",
        )
        action_row = ft.Row(
            spacing=6,
            controls=[
                ft.Container(
                    content=ft.Row(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=13, color=theme.PRIMARY),
                            ft.Text("Auto", size=11, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                        ],
                    ),
                    bgcolor=theme.PRIMARY_BG,
                    border=ft.border.all(1, theme.PRIMARY_BORDER),
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=5),
                    on_click=lambda _: self._run_auto_checklist(),
                    ink=True,
                    tooltip="Tự động kiểm tra và quét môi trường",
                ),
                *([template_upload_action] if self.can_manage_template else []),
            ],
        )

        self.install_progress_panel = ft.Container(visible=False, padding=10, bgcolor=theme.SURFACE_ALT, border_radius=8)
        self.auto_check_button = action_row.controls[0]
        self.auto_check_status = ft.Text("", size=11, color=theme.TEXT_MUTED)
        self.auto_check_progress = ft.ProgressBar(visible=False, value=0, color=theme.PRIMARY)

        header = ft.Container(
            padding=ft.padding.all(16),
            bgcolor=theme.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.BORDER)),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("Checklist Chuẩn bị", size=15, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                        ],
                    ),
                    action_row,
                    self.auto_check_status,
                    self.auto_check_progress,
                    self.install_progress_panel,
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(self.checklist_progress_bar, expand=True, border_radius=4),
                            self.checklist_percent_text,
                        ],
                    ),
                ],
            ),
        )

        self._refresh_checklist_items()

        return ft.Container(
            width=380,
            bgcolor=theme.BG,
            border=ft.border.only(left=ft.BorderSide(1, theme.BORDER)),
            visible=self.show_checklist,
            content=ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    header,
                    ft.Container(
                        content=self.checklist_items_column,
                        expand=True,
                        padding=ft.padding.all(14),
                    ),
                ],
            ),
        )

    def _refresh_checklist_items(self) -> None:
        if not self.ctx or not hasattr(self.ctx, "checklist"):
            return
        items = self.ctx.checklist.list_items(project_code=self.project_code)
        prog = self.ctx.checklist.progress(project_code=self.project_code)

        self.checklist_progress_bar.value = prog["percent"] / 100
        self.checklist_percent_text.value = f"{prog['percent']}%"

        controls: list[ft.Control] = []
        if not items:
            controls.append(
                ft.Container(
                    alignment=ft.alignment.center,
                    padding=ft.padding.symmetric(vertical=30, horizontal=16),
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.PLAYLIST_ADD_ROUNDED, size=36, color=theme.TEXT_MUTED),
                            ft.Text(
                                f"Chưa có checklist cho dự án [{self.project_code}]",
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=theme.TEXT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                "Team Lead/Project Lead sẽ tải template; member chỉ có quyền thực thi checklist.",
                                size=11,
                                color=theme.TEXT_MUTED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.OutlinedButton(
                                "Tải lên Checklist",
                                icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                                visible=self.can_manage_template,
                                on_click=lambda _: self._open_upload_checklist_dialog(),
                            ),
                        ],
                    ),
                )
            )

        self._blocked_steps = set()
        previous_done = True
        for step_number, it in enumerate(items, 1):
            locked = not previous_done
            if locked:
                self._blocked_steps.add(it.key)
            is_done = it.status.lower() in ("passed", "completed")
            previous_done = previous_done and is_done
            busy = self._auto_check_running or self._install_running or self._running_check_key is not None
            icon = ft.Icons.CHECK_CIRCLE_ROUNDED if is_done else ft.Icons.RADIO_BUTTON_UNCHECKED
            icon_color = theme.PRIMARY if is_done else theme.TEXT_LIGHT

            title_style = ft.TextStyle(
                size=13,
                weight=ft.FontWeight.W_600,
                color=theme.EMERALD if is_done else theme.TEXT_LIGHT if locked else theme.TEXT,
                decoration=None,
            )

            result = self._checklist_results.get(it.key, {})
            desc = result.get("message") or it.message or it.description or ""
            if result.get("suggestion"):
                desc += " · " + result["suggestion"]
            result_status = result.get("status", it.status)
            result_color = theme.ERR if result_status == "failed" else (
                theme.WARN if result_status == "warning" else theme.TEXT_MUTED
            )
            is_auto = (it.check_type or "").upper() != "MANUAL"

            trailing_controls: list[ft.Control] = []
            # Cho chạy lại để phát hiện môi trường thay đổi sau lần kiểm tra trước.
            if is_auto:
                trailing_controls.append(self._build_check_action(it.key, disabled=locked or busy))

            if (it.check_type or "").upper() == "SOFTWARE" and result_status in ("failed", "warning"):
                trailing_controls.append(ft.TextButton(
                    "Cài đặt", icon=ft.Icons.DOWNLOAD_ROUNDED,
                    tooltip="Xem lệnh và xác nhận trước khi cài",
                    disabled=locked or busy,
                    on_click=lambda _, key=it.key: self._request_install(key),
                ))
            elif result_status in ("failed", "warning"):
                # Kiểm tra nếu mục bị lỗi có gợi ý lệnh thực thi (VD: netstat -ano | findstr :<port>)
                hint_str = str(it.params.get("hint") or "")
                suggested_cmds = extract_runnable_commands(desc) or extract_runnable_commands(hint_str)
                if suggested_cmds:
                    target_cmd = suggested_cmds[0]
                    trailing_controls.append(
                        ft.IconButton(
                            ft.Icons.TERMINAL_ROUNDED,
                            icon_size=17,
                            tooltip=f"Chạy lệnh đề xuất: {target_cmd}",
                            disabled=locked or busy,
                            icon_color=theme.PRIMARY,
                            on_click=lambda _, c=target_cmd: self._execute_command_from_chat(c),
                        )
                    )

            card = ft.Container(
                bgcolor=theme.EMERALD_BG if is_done else theme.SURFACE_ALT if locked else theme.SURFACE,
                border=ft.border.all(1, theme.EMERALD_BORDER if is_done else theme.BORDER),
                border_radius=10,
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                ink=True,
                on_click=None if is_auto or locked or busy else lambda _, key=it.key, done=is_done: self._toggle_checklist_item(key, done),
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=theme.EMERALD, size=24) if is_done else ft.Checkbox(
                            value=False,
                            disabled=is_auto or locked or busy,
                            active_color=theme.EMERALD,
                            on_change=lambda e, key=it.key: self._toggle_checklist_item(key, not e.control.value),
                        ),
                        ft.Column(
                            spacing=2,
                            expand=True,
                            controls=[
                                ft.Row(
                                    spacing=6,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Text(f"{step_number}. {it.title}", style=title_style),
                                    ],
                                ),
                                ft.Text("✓ Hoàn thành" if is_done else "🔒 Hoàn thành các bước trước để mở khóa" if locked else "Sẵn sàng thực hiện", size=11, color=theme.EMERALD if is_done else theme.TEXT_MUTED),
                                ft.Text(
                                    desc,
                                    size=11,
                                    color=result_color,
                                    tooltip=desc,
                                    max_lines=3,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ) if desc else ft.Container(),
                            ],
                        ),
                        *trailing_controls,
                    ],
                ),
            )
            run = self._check_runs.get(it.key)
            if run:
                detail_rows: list[ft.Control] = []
                for substep, (label, state) in enumerate(zip(run.labels, run.states), 1):
                    color = theme.EMERALD if state == "done" else theme.ERR if state == "failed" else theme.PRIMARY if state == "running" else theme.TEXT_MUTED
                    indicator = ft.ProgressRing(width=12, height=12, stroke_width=2, color=color) if state == "running" else ft.Icon(
                        ft.Icons.CHECK_CIRCLE if state == "done" else ft.Icons.CANCEL if state == "failed" else ft.Icons.RADIO_BUTTON_UNCHECKED, size=14, color=color,
                    )
                    detail_rows.append(ft.Row([indicator, ft.Text(f"{step_number}.{substep} {label}", size=11, color=color, expand=True)], spacing=6))
                if run.message:
                    detail_rows.append(ft.Text(run.message, size=11, selectable=True, color=theme.TEXT_MUTED))
                card.content = ft.Column([card.content, ft.Column(detail_rows, spacing=5)], spacing=8, tight=True)
            controls.append(card)

        self.checklist_items_column.controls = controls
        if self.checklist_items_column.page:
            self.checklist_progress_bar.update()
            self.checklist_percent_text.update()
            self.checklist_items_column.update()

    def _build_check_action(self, key: str, *, disabled: bool) -> ft.Control:
        """Giữ vòng xoay ngay tại vị trí nút Play để member biết bước nào đang chạy."""
        if self._running_check_key == key:
            return ft.Container(
                width=40,
                height=40,
                alignment=ft.alignment.center,
                tooltip="Đang kiểm tra…",
                content=ft.ProgressRing(
                    width=18,
                    height=18,
                    stroke_width=2,
                    color=theme.PRIMARY,
                ),
            )
        return ft.IconButton(
            ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED,
            icon_size=18,
            tooltip="Chạy lại kiểm tra thực tế",
            disabled=disabled,
            icon_color=theme.PRIMARY,
            on_click=lambda _, item_key=key: self._verify_single_item(item_key),
        )

    def _begin_check_run(self, key: str, item: Any) -> None:
        self._running_check_key = key
        self._check_runs[key] = CheckRun.start(item.check_type, item.params)
        self._refresh_checklist_items()

    def _verify_single_item(self, key: str) -> None:
        if self._auto_check_running or self._install_running or self._install_prompt_open or self._running_check_key or key in self._blocked_steps:
            return
        self._running_check_key = key

        def work() -> None:
            try:
                item = self.ctx.checklist.get_item(key)
                if item is None:
                    raise ValueError("Không tải được bước checklist.")
                self._begin_check_run(key, item)
                result = self.ctx.verification.verify_key(key)
                self._checklist_results[key] = result
                self._check_runs[key].finish(result)
                (self.ctx.notifier.success if result["status"] == "passed" else self.ctx.notifier.warning)(result["message"])
            except Exception as exc:
                if key in self._check_runs:
                    self._check_runs[key].fail(str(exc))
                self.ctx.notifier.error(f"Lỗi khi kiểm tra: {exc}")
            finally:
                self._running_check_key = None
                self._refresh_checklist_items()

        self.page.run_thread(work)

    def _toggle_checklist_item(self, key: str, is_currently_done: bool) -> None:
        if self._auto_check_running or self._install_running or self._install_prompt_open or self._running_check_key or key in self._blocked_steps:
            return
        self._running_check_key = key
        new_done = not is_currently_done

        def work() -> None:
            try:
                self._check_runs[key] = CheckRun.start("MANUAL", {})
                self._refresh_checklist_items()
                self.ctx.checklist.set_manual_done(
                    key=key, done=new_done, user_id=self.user.get("user_id") or self.user.get("id"),
                    user_email=self.user.get("email"), project_code=self.project_code,
                )
                self._checklist_results.pop(key, None)
                self._check_runs[key].finish({"status": "passed", "message": "Đã xác nhận hoàn thành." if new_done else "Đã bỏ xác nhận; các bước sau được khóa lại."})
            except Exception as exc:
                self._check_runs[key].fail(str(exc))
                self.ctx.notifier.error(f"Không lưu được xác nhận: {exc}")
            finally:
                self._running_check_key = None
                self._refresh_checklist_items()

        self.page.run_thread(work)

    def _run_auto_checklist(self) -> None:
        if self._auto_check_running or self._install_running or self._install_prompt_open or self._running_check_key:
            return
        self._auto_check_running = True
        self.auto_check_button.disabled = True
        self.auto_check_progress.visible = True
        self.auto_check_progress.value = 0
        self.auto_check_status.value = "Đang tải danh sách kiểm tra…"
        self._safe_update(self.auto_check_button, self.auto_check_progress, self.auto_check_status)

        def current(index: int, total: int, item: dict[str, Any]) -> None:
            self._running_check_key = item["key"]
            self._check_runs[item["key"]] = CheckRun.start(item["check_type"], item.get("params", {}))
            self._refresh_checklist_items()
            self.auto_check_status.value = f"Đang kiểm tra bước {index}/{total}: {item['title']}"
            self._safe_update(self.auto_check_status)

        def progress(index: int, total: int, result: dict[str, Any]) -> None:
            self._checklist_results[result["key"]] = result
            self._check_runs[result["key"]].finish(result)
            self._running_check_key = None
            self.auto_check_progress.value = index / total
            self._safe_update(self.auto_check_progress)
            self._refresh_checklist_items()

        def work() -> None:
            try:
                results = self.ctx.verification.verify_all(
                    project_code=self.project_code, on_progress=progress, on_current=current,
                )
                passed = sum(r["status"] == "passed" for r in results)
                failed = sum(r["status"] == "failed" for r in results)
                warning = sum(r["status"] == "warning" for r in results)
                summary = (
                    f"Đã kiểm tra {len(results)} mục: {passed} đạt, {failed} lỗi, {warning} cảnh báo."
                    if results else "Không có bước tự động sẵn sàng. Hãy xác nhận bước thủ công đầu tiên chưa hoàn thành, hoặc checklist đã hoàn tất."
                )
                remaining = next((item for item in self.ctx.checklist.list_items(project_code=self.project_code)
                                  if item.status.lower() not in {"passed", "completed"}), None)
                summary += (f" Dừng tại: {remaining.title}. Hoàn thành bước này rồi bấm Auto để tiếp tục."
                            if remaining else " Checklist đã hoàn thành.")
                if failed or warning:
                    summary += " Chọn Cài đặt ở mục phần mềm chưa đạt để xem lệnh và cấp phép."
                self.auto_check_status.value = summary
                self.chat_messages.controls.append(
                    MessageBubble(
                        summary,
                        is_user=False,
                        on_run_command=self._execute_command_from_chat,
                        timestamp=datetime.now(),
                    )
                )
                self._safe_update(self.chat_messages)
                (self.ctx.notifier.warning if failed or warning or not results else self.ctx.notifier.success)(summary)
            except Exception as exc:
                if self._running_check_key in self._check_runs:
                    self._check_runs[self._running_check_key].fail(str(exc))
                self.auto_check_status.value = "Kiểm tra bị gián đoạn. Các kết quả đã chạy vẫn được giữ lại."
                self.ctx.notifier.error(f"Không thể hoàn tất kiểm tra: {exc}")
            finally:
                self._running_check_key = None
                self._auto_check_running = False
                self.auto_check_button.disabled = False
                self.auto_check_progress.visible = False
                self._safe_update(self.auto_check_button, self.auto_check_progress, self.auto_check_status)
                try:
                    self._refresh_checklist_items()
                except Exception:
                    pass  # Backend có thể đang mất kết nối; vẫn phải mở lại nút Auto.

        self.page.run_thread(work)

    def _download_checklist_template(self) -> None:
        if not self.can_manage_template:
            self.ctx.notifier.error("Chỉ Team Lead hoặc Project Lead mới được tải template checklist.")
            return
        file_name = f"checklist_template_{self.project_code.lower()}.csv"
        self.checklist_template_save_picker.save_file(
            dialog_title="Lưu file mẫu Checklist CSV",
            file_name=file_name,
        )

    def _on_save_checklist_template_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return
        if not self.can_manage_template:
            self.ctx.notifier.error("Bạn không có quyền tải template checklist của dự án này.")
            return
        try:
            data = self.ctx.checklist.get_sample_template(self.project_code)
            content = data.get("content", "")
            Path(e.path).write_text(content, encoding="utf-8-sig")
            self.ctx.notifier.success(f"Đã lưu file mẫu checklist: {Path(e.path).name}")
        except Exception as exc:
            self.ctx.notifier.error(f"Không thể lưu file mẫu: {exc}")

    def _open_upload_checklist_dialog(self) -> None:
        if not self.can_manage_template:
            self.ctx.notifier.error("Member chỉ có quyền thực thi. Chỉ Team Lead hoặc Project Lead được tải lên template.")
            return
        self._selected_checklist_file_path = None
        self._upload_dialog_file_text = ft.Text(
            "Chưa chọn file nào",
            size=12,
            italic=True,
            color=theme.TEXT_MUTED,
        )
        self._upload_dialog_confirm_btn = ft.ElevatedButton(
            "Xác nhận Tải lên & Thay thế",
            icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
            disabled=True,
            bgcolor=theme.PRIMARY,
            color=theme.SURFACE,
            on_click=lambda _: self._confirm_upload_checklist(),
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED, color=theme.PRIMARY, size=24),
                    ft.Text("Tải lên Checklist Dự án", size=16, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    spacing=14,
                    tight=True,
                    controls=[
                        # Cảnh báo xoá và thay thế checklist cũ
                        ft.Container(
                            bgcolor=theme.WARNING_BG,
                            border=ft.border.all(1, theme.WARNING_BORDER),
                            border_radius=8,
                            padding=ft.padding.all(10),
                            content=ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                controls=[
                                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=18, color=theme.WARNING),
                                    ft.Text(
                                        f"Lưu ý: Tải lên file mới sẽ xoá toàn bộ checklist cũ và thay thế hoàn toàn danh sách kiểm tra của dự án [{self.project_code}].",
                                        size=12,
                                        weight=ft.FontWeight.W_500,
                                        color=theme.WARNING,
                                        expand=True,
                                    ),
                                ],
                            ),
                        ),
                        # Phần 1: Tải file mẫu CSV
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=ft.padding.all(12),
                            content=ft.Column(
                                spacing=6,
                                controls=[
                                    ft.Text("1. File mẫu Checklist CSV", size=13, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                    ft.Text(
                                        "Tải file mẫu chuẩn UTF-8 chứa sẵn ví dụ cấu hình checklist:",
                                        size=11,
                                        color=theme.TEXT_MUTED,
                                    ),
                                    ft.OutlinedButton(
                                        "Tải file mẫu Checklist CSV",
                                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                                        on_click=lambda _: self._download_checklist_template(),
                                    ),
                                ],
                            ),
                        ),
                        # Phần 2: Chọn file và tải lên
                        ft.Container(
                            bgcolor=theme.SURFACE_ALT,
                            border=ft.border.all(1, theme.BORDER),
                            border_radius=8,
                            padding=ft.padding.all(12),
                            content=ft.Column(
                                spacing=8,
                                controls=[
                                    ft.Text("2. Chọn file Checklist (CSV hoặc JSON)", size=13, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                    ft.Row(
                                        spacing=10,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.ElevatedButton(
                                                "Chọn file từ máy",
                                                icon=ft.Icons.ATTACH_FILE_ROUNDED,
                                                disabled=not self.can_manage_template,
                                                on_click=lambda _: self._pick_checklist_file_for_dialog(),
                                            ),
                                            ft.Container(content=self._upload_dialog_file_text, expand=True),
                                        ],
                                    ),
                                    ft.Text(
                                        "🔒 Chỉ Team Lead hoặc Project Lead mới có quyền tải lên checklist cho dự án."
                                        if not self.can_manage_template
                                        else "File tải lên sẽ thay thế và thiết lập checklist riêng cho dự án này.",
                                        size=11,
                                        color=theme.ERROR if not self.can_manage_template else theme.TEXT_MUTED,
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Đóng", on_click=lambda _: self._close_upload_checklist_dialog()),
                self._upload_dialog_confirm_btn,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._checklist_upload_dlg = dlg
        if self.page:
            self.page.open(dlg)

    def _close_upload_checklist_dialog(self) -> None:
        if self._checklist_upload_dlg and self.page:
            self.page.close(self._checklist_upload_dlg)
        self._checklist_upload_dlg = None

    def _pick_checklist_file_for_dialog(self) -> None:
        if not self.can_manage_template:
            self.ctx.notifier.error("Chỉ Team Lead hoặc Project Lead mới có quyền nhập checklist cho dự án.")
            return
        self.checklist_picker.pick_files(
            dialog_title="Chọn file Checklist CSV hoặc JSON",
            allowed_extensions=["csv", "json", "txt"],
        )

    def _on_checklist_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        file_path = e.files[0].path
        if not file_path:
            return

        self._selected_checklist_file_path = file_path
        if self._upload_dialog_file_text and self._checklist_upload_dlg:
            self._upload_dialog_file_text.value = f"Đã chọn: {Path(file_path).name}"
            self._upload_dialog_file_text.color = theme.TEXT
            self._upload_dialog_file_text.weight = ft.FontWeight.W_600
            if self._upload_dialog_confirm_btn:
                self._upload_dialog_confirm_btn.disabled = not self.can_manage_template
            if self._checklist_upload_dlg.page:
                self._checklist_upload_dlg.update()

    def _confirm_upload_checklist(self) -> None:
        if not self._selected_checklist_file_path:
            self.ctx.notifier.warning("Vui lòng chọn file checklist trước.")
            return
        if not self.can_manage_template:
            self.ctx.notifier.error("Chỉ Team Lead hoặc Project Lead mới có quyền nhập checklist cho dự án.")
            return

        file_path = self._selected_checklist_file_path

        def work():
            try:
                raw_bytes = Path(file_path).read_bytes()
                try:
                    content = raw_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    content = raw_bytes.decode("utf-8", errors="replace")

                res = self.ctx.checklist.import_checklist(
                    content=content,
                    project_code=self.project_code,
                    user_email=self.user.get("email"),
                )
                count = res.get("imported_count", 0)
                self.ctx.notifier.success(f"Đã thay thế checklist thành công: {count} mục mới cho dự án [{self.project_code}]!")
                self._close_upload_checklist_dialog()
                self._refresh_checklist_items()
            except Exception as exc:
                self.ctx.notifier.error(f"Tải lên checklist thất bại: {exc}")

        self.page.run_thread(work)

    # ==================== TAB: DOCS VIEW ====================
    def _build_docs_view(self) -> ft.Container:
        self.docs_list_column = ft.Column(spacing=10, tight=True)
        self.ingest_status_text = ft.Text("", size=12, color=theme.TEXT_MUTED)
        self.ingest_progress_bar = ft.ProgressBar(visible=False, color=theme.PRIMARY, bgcolor=theme.SURFACE_ALT)
        self.ingest_button = ft.FilledTonalButton(
            "Nạp vào Vector DB",
            icon=ft.Icons.CLOUD_SYNC_ROUNDED,
            disabled=not self.is_senior,
            tooltip="Quét folder riêng của dự án và nạp tài liệu vào ChromaDB" if self.is_senior else "🔒 Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền nạp tài liệu",
            on_click=lambda _: self._run_ingest(),
        )

        target_folder = self.ctx.projects.get_doc_folder(self.project_code)
        folder_display = str(target_folder).replace("\\", "/")

        if self.is_senior:
            upload_zone = ft.Container(
                bgcolor=theme.PRIMARY_BG,
                border=ft.border.all(1.5, theme.PRIMARY_BORDER),
                border_radius=16,
                padding=36,
                alignment=ft.alignment.center,
                ink=True,
                on_click=lambda _: self.file_picker.pick_files(
                    allow_multiple=True,
                    allowed_extensions=["pdf", "docx", "md", "txt"],
                    dialog_title=f"Chọn tài liệu nạp cho dự án [{self.project_code}]",
                ),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                    controls=[
                        ft.Container(
                            width=54,
                            height=54,
                            bgcolor=theme.SURFACE,
                            border_radius=27,
                            alignment=ft.alignment.center,
                            content=ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=28, color=theme.PRIMARY),
                        ),
                        ft.Text("Kéo thả tài liệu vào đây", size=16, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                        ft.Text("hoặc click để chọn file từ máy tính của bạn (.pdf, .docx, .md, .txt)", size=13, color=theme.TEXT_MUTED),
                        ft.Container(height=4),
                        ft.FilledButton(
                            "Chọn File",
                            icon=ft.Icons.ATTACH_FILE,
                            on_click=lambda _: self.file_picker.pick_files(
                                allow_multiple=True,
                                allowed_extensions=["pdf", "docx", "md", "txt"],
                            ),
                        ),
                    ],
                ),
            )
        else:
            upload_zone = ft.Container(
                bgcolor=theme.WARN_BG,
                border=ft.border.all(1, theme.WARN_BORDER),
                border_radius=14,
                padding=24,
                content=ft.Row(
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=44,
                            height=44,
                            bgcolor=theme.SURFACE,
                            border_radius=22,
                            alignment=ft.alignment.center,
                            content=ft.Icon(ft.Icons.LOCK_ROUNDED, color=theme.WARN, size=24),
                        ),
                        ft.Column(
                            spacing=3,
                            expand=True,
                            controls=[
                                ft.Text(
                                    "Phân quyền tài liệu: TEAM_LEAD hoặc PROJECT_LEAD",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme.TEXT,
                                ),
                                ft.Text(
                                    f"Tài khoản của bạn ({self.user.get('email', '')}) thuộc cấp bậc '{self.user.get('level', 'MEMBER')}'. "
                                    "Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền tải lên và nạp tài liệu vào ChromaDB.",
                                    size=12,
                                    color=theme.TEXT_MUTED,
                                ),
                            ],
                        ),
                    ],
                ),
            )

        self._refresh_docs_list()

        return ft.Container(
            expand=True,
            bgcolor=theme.BG,
            padding=ft.padding.symmetric(horizontal=36, vertical=28),
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=24,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[
                            ft.Column(
                                spacing=4,
                                tight=True,
                                controls=[
                                    ft.Text("Tài liệu Project", size=22, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                    ft.Text(f"Quản lý tài liệu dự án [{self.project_code}]. Thư mục DB: {target_folder.name}/", size=13, color=theme.TEXT_MUTED),
                                ],
                            ),
                            self.ingest_button,
                        ],
                    ),
                    upload_zone,
                    self.ingest_progress_bar,
                    self.ingest_status_text,
                    ft.Column(
                        spacing=12,
                        tight=True,
                        controls=[
                            ft.Text(f"TỆP TÀI LIỆU CỦA DỰ ÁN ({folder_display})", size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT_LIGHT),
                            self.docs_list_column,
                        ],
                    ),
                ],
            ),
        )

    def _refresh_docs_list(self) -> None:
        snapshot = self.ctx.projects.list_documents(self.project_code)
        target_folder = Path(snapshot["root"])
        files = [(Path(row["path"]), row) for row in snapshot["files"]]

        cards: list[ft.Control] = []
        if not files:
            cards.append(
                ft.Container(
                    bgcolor=theme.SURFACE,
                    border=ft.border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=20,
                    alignment=ft.alignment.center,
                    content=ft.Text(f"Chưa có tài liệu nào trong thư mục '{target_folder.name}' (cấu hình trong database)", size=13, color=theme.TEXT_MUTED),
                )
            )
        else:
            for f, metadata in sorted(files, key=lambda x: x[0].name):
                size_kb = round(metadata["size"] / 1024, 1)
                size_str = f"{size_kb} KB" if size_kb < 1024 else f"{round(size_kb / 1024, 2)} MB"
                mtime_str = datetime.fromtimestamp(metadata["mtime"]).strftime("%d/%m/%Y")

                action_buttons = [
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        icon_size=16,
                        icon_color=theme.TEXT_MUTED,
                        tooltip="Tải xuống",
                        on_click=lambda _, path=f: self._download_file(path),
                    ),
                ]
                if self.is_senior:
                    action_buttons.append(
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                            icon_size=16,
                            icon_color=theme.ERR,
                            tooltip="Xóa file",
                            on_click=lambda _, path=f: self._delete_file(path),
                        )
                    )

                item_row = ft.Container(
                    bgcolor=theme.SURFACE,
                    border=ft.border.all(1, theme.BORDER),
                    border_radius=12,
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
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
                                        border_radius=8,
                                        alignment=ft.alignment.center,
                                        content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=theme.PRIMARY, size=18),
                                    ),
                                    ft.Column(
                                        spacing=2,
                                        tight=True,
                                        controls=[
                                            ft.Text(f.name, size=13, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                                            ft.Text(f"{size_str} • Đã cập nhật {mtime_str}", size=11, color=theme.TEXT_MUTED),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=4,
                                controls=action_buttons,
                            ),
                        ],
                    ),
                )
                cards.append(item_row)

        self.docs_list_column.controls = cards
        if self.docs_list_column.page:
            self.docs_list_column.update()

    def _download_file(self, path: Path) -> None:
        self._pending_download = path
        self.save_picker.save_file(dialog_title="Lưu tài liệu", file_name=path.name)

    def _on_save_picked(self, e: ft.FilePickerResultEvent) -> None:
        src, self._pending_download = self._pending_download, None
        if not e.path or src is None:
            return  # người dùng huỷ
        try:
            self.ctx.projects.export_document(self.project_code, src, Path(e.path))
            self.ctx.notifier.success(f"Đã tải xuống: {Path(e.path).name}")
        except Exception as exc:
            self.ctx.notifier.error(f"Không thể lưu file: {exc}")

    def _delete_file(self, path: Path) -> None:
        if not self.is_senior:
            self.ctx.notifier.error("Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền xóa tài liệu.")
            return
        try:
            self.ctx.projects.delete_document(self.project_code, path)
            self.ctx.notifier.info(f"Đã xóa: {path.name}")
            self._refresh_docs_list()
        except Exception as exc:
            self.ctx.notifier.error(f"Không thể xóa file: {exc}")

    def _on_files_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        if not self.is_senior:
            self.ctx.notifier.error("Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền tải lên tài liệu.")
            return
        target_dir = self.ctx.projects.get_doc_folder(self.project_code)
        sources = [Path(f.path) for f in e.files if f.path]
        copied = self.ctx.projects.copy_documents(self.project_code, sources)

        self.ctx.notifier.success(f"Đã thêm {copied} tệp vào thư mục DB [{target_dir.name}].")
        self._refresh_docs_list()

    def _run_ingest(self) -> None:
        if not self.is_senior:
            self.ctx.notifier.error("Chỉ TEAM_LEAD hoặc PROJECT_LEAD mới có quyền nạp tài liệu vào ChromaDB.")
            return
        if self._ingest_running:
            return
        self._ingest_running = True
        self.ingest_button.disabled = True
        self._safe_update(self.ingest_button)

        def work():
            try:
                self.ingest_progress_bar.visible = True
                target_folder = self.ctx.projects.get_doc_folder(self.project_code)
                self.ingest_status_text.value = f"Đang quét folder riêng '{target_folder.name}'…"
                self._safe_update(self.ingest_progress_bar, self.ingest_status_text)

                snapshot = self.ctx.projects.list_documents(self.project_code)
                files_to_ingest = [Path(row["path"]) for row in snapshot["files"]]
                if not files_to_ingest:
                    self.ingest_status_text.value = f"⚠️ Thư mục '{target_folder.name}' chưa có tài liệu."
                    self.ctx.notifier.warning("Không có tài liệu nào để nạp.")
                    return

                self.ingest_status_text.value = f"Tìm thấy {len(files_to_ingest)} tệp. Đang tạo background job…"
                self._safe_update(self.ingest_progress_bar, self.ingest_status_text)

                def progress(i: int, n: int, name: str):
                    self.ingest_progress_bar.value = i / max(1, n)
                    self.ingest_status_text.value = f"({i}/{n}) {name}"
                    self._safe_update(self.ingest_progress_bar, self.ingest_status_text)

                rep = self.ctx.knowledge.ingest_paths(
                    paths=files_to_ingest,
                    reset=False,
                    progress=progress,
                    project_code=self.project_code,
                )
                self.ingest_status_text.value = f"✅ Đã nạp {len(files_to_ingest)} file từ DB folder [{target_folder.name}]: {rep.summary()}"
                self.ctx.notifier.success(f"Nạp thành công {rep.chunks} chunks vào ChromaDB cho [{self.project_code}]!")
            except Exception as exc:
                self.ingest_status_text.value = f"❌ Lỗi: {exc}"
                self.ctx.notifier.error("Nạp tài liệu thất bại.")
            finally:
                self.ingest_progress_bar.visible = False
                self._ingest_running = False
                self.ingest_button.disabled = False
                self._safe_update(self.ingest_progress_bar, self.ingest_status_text, self.ingest_button)

        self.page.run_thread(work)
