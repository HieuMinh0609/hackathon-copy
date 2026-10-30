"""Unit test cho ProjectService / OnboardingTemplateService: quản lý onboarding_template và document_link."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable
import pytest
from sqlalchemy import text

from backend.services.db import get_connection
from backend.services.project_service import OnboardingTemplate, OnboardingTemplateService, ProjectService


def test_project_service_seed_and_query(settings):
    svc = ProjectService(settings)
    projects = svc.list_projects()
    assert len(projects) >= 3

    codes = [p["code"] for p in projects]
    assert "PRJ_ECOMMERCE" in codes
    assert "PRJ_AI_BUDDY" in codes
    assert "PRJ_WAREHOUSE" in codes

    # Kiểm tra các trường template_code và document_link từ onboarding_template
    for p in projects:
        assert p["template_code"] == p["code"]
        assert p["document_link"] == p["doc_folder"]
        assert p["template_name"] == p["name"]

    # Xác thực dữ liệu được lưu trực tiếp trong bảng onboarding_template
    with get_connection(settings.database_url) as conn:
        rows = conn.execute(
            text("SELECT template_code, template_name, document_link FROM onboarding_template")
        ).mappings().all()
        db_codes = [r["template_code"] for r in rows]
        assert "PRJ_ECOMMERCE" in db_codes
        assert "PRJ_AI_BUDDY" in db_codes
        assert "PRJ_WAREHOUSE" in db_codes


def test_project_service_get_doc_folder(settings, tmp_path: Path):
    svc = ProjectService(settings)

    # Mỗi project có folder riêng theo project code.
    folder = svc.get_doc_folder("PRJ_AI_BUDDY")
    assert folder.exists()
    assert folder == settings.documents_dir / "projects" / "PRJ_AI_BUDDY"

    # API cũ không được chuyển project sang folder tùy ý.
    custom_doc_dir = tmp_path / "custom_docs_prj"
    custom_doc_dir.mkdir(parents=True, exist_ok=True)
    ok = svc.set_document_link("PRJ_ECOMMERCE", str(custom_doc_dir))
    assert ok is True
    scanned_folder = svc.get_doc_folder("PRJ_ECOMMERCE")
    assert scanned_folder == settings.documents_dir / "projects" / "PRJ_ECOMMERCE"

    tmpl = svc.get_template("PRJ_ECOMMERCE")
    assert tmpl is not None
    assert tmpl["document_link"] == "documents/projects/PRJ_ECOMMERCE"

    with pytest.raises(ValueError):
        svc.get_doc_folder("../outside")


def test_project_service_copies_legacy_documents_without_deleting_source(settings, tmp_path: Path):
    svc = ProjectService(settings)
    legacy = tmp_path / "legacy_docs"
    legacy.mkdir()
    source = legacy / "guide.md"
    source.write_text("Tài liệu cũ", encoding="utf-8")
    with get_connection(settings.database_url) as conn:
        conn.execute(
            text("UPDATE onboarding_template SET document_link=:link WHERE template_code=:code"),
            {"link": str(legacy), "code": "PRJ_ECOMMERCE"},
        )

    migrated_service = ProjectService(settings)
    migrated = migrated_service.get_doc_folder("PRJ_ECOMMERCE") / "guide.md"
    assert migrated.read_text(encoding="utf-8") == "Tài liệu cũ"
    assert source.exists()


def test_onboarding_template_dataclass_and_upsert(settings):
    svc = OnboardingTemplateService(settings)
    svc.upsert_template(
        template_code="PRJ_TEST_CUSTOM",
        template_name="Template Kiểm Thử",
        document_link="documents/test_custom",
    )

    t = svc.get_template("PRJ_TEST_CUSTOM")
    assert t is not None
    assert t["template_code"] == "PRJ_TEST_CUSTOM"
    assert t["template_name"] == "Template Kiểm Thử"
    assert t["document_link"] == "documents/projects/PRJ_TEST_CUSTOM"
    # Kiểm tra tương thích ngược
    assert t["code"] == "PRJ_TEST_CUSTOM"
    assert t["name"] == "Template Kiểm Thử"
    assert t["doc_folder"] == "documents/projects/PRJ_TEST_CUSTOM"

    obj = OnboardingTemplate(
        template_code="CODE1",
        template_name="NAME1",
        document_link="PATH1",
    )
    assert obj.code == "CODE1"
    assert obj.name == "NAME1"
    assert obj.doc_folder == "PATH1"


def test_project_service_create_project_and_members(settings):
    from backend.services.user_service import UserService

    UserService(settings)
    svc = ProjectService(settings)

    # 1. Tạo dự án mới
    prj = svc.create_project(
        code="PRJ_NEW_FINTECH",
        name="Hệ thống Fintech 4.0",
        description="Module thanh toán QR Code",
        role_name="Backend Developer",
        creator_email="alex.carter@example.com",
    )
    assert prj["code"] == "PRJ_NEW_FINTECH"
    assert prj["name"] == "Hệ thống Fintech 4.0"
    assert (settings.documents_dir / "projects" / "PRJ_NEW_FINTECH").is_dir()

    # 2. Kiểm tra người tạo đã được tự động thêm vào project_members
    members = svc.list_project_members("PRJ_NEW_FINTECH")
    assert len(members) == 1
    assert members[0]["user_email"] == "alex.carter@example.com"
    assert members[0]["project_role_key"] == "PROJECT_LEAD"

    # 3. Thêm thành viên mới vào dự án
    new_m = svc.add_project_member(
        project_code="PRJ_NEW_FINTECH",
        user_email="emma.wilson@example.com",
        role_in_project="Developer",
        added_by="alex.carter@example.com",
    )
    assert new_m["user_email"] == "emma.wilson@example.com"
    assert new_m["role_in_project"] == "Member"
    assert new_m["job_title"] == "Backend Developer"

    # 4. Tìm kiếm thành viên
    all_members = svc.list_project_members("PRJ_NEW_FINTECH")
    assert len(all_members) == 2

    search_emma = svc.list_project_members("PRJ_NEW_FINTECH", search="emma.wilson")
    assert len(search_emma) == 1
    assert search_emma[0]["user_email"] == "emma.wilson@example.com"

    search_lead = svc.list_project_members("PRJ_NEW_FINTECH", search="Lead")
    assert len(search_lead) == 1
    assert search_lead[0]["user_email"] == "alex.carter@example.com"

    # 5. Xóa thành viên
    deleted = svc.remove_project_member("PRJ_NEW_FINTECH", "emma.wilson@example.com")
    assert deleted is True
    remaining = svc.list_project_members("PRJ_NEW_FINTECH")
    assert len(remaining) == 1
    assert remaining[0]["user_email"] == "alex.carter@example.com"


def test_api_projects_and_members(settings, monkeypatch):
    import hashlib
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.core.context import build_context

    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)
    client = TestClient(app)

    session_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    headers = {"X-User-Email": "alex.carter@example.com", "X-Session-Key": session_key}

    project_lead_key = hashlib.md5(b"mack.johnson@example.com").hexdigest()
    denied = client.post(
        "/api/v1/projects",
        json={"code": "PRJ_FORBIDDEN", "name": "Không được tạo"},
        headers={"X-Session-Key": project_lead_key},
    )
    assert denied.status_code == 403
    assert "TEAM_LEAD" in denied.json()["detail"]

    # 1. API Tạo dự án mới
    res_create = client.post(
        "/api/v1/projects",
        json={
            "code": "PRJ_ECOMMERCE_V2",
            "name": "E-Commerce Thế hệ mới",
            "description": "Nền tảng thương mại điện tử microservices",
            "role_name": "Backend Developer",
            "duration_days": 30,
        },
        headers=headers,
    )
    assert res_create.status_code == 200
    assert res_create.json()["success"] is True
    assert res_create.json()["data"]["code"] == "PRJ_ECOMMERCE_V2"
    assert res_create.json()["data"]["duration_days"] == 30

    # 2. API Lấy danh sách thành viên
    res_members = client.get("/api/v1/projects/PRJ_ECOMMERCE_V2/members", headers=headers)
    assert res_members.status_code == 200
    members = res_members.json()["data"]
    assert len(members) >= 1
    assert any(m["user_email"] == "alex.carter@example.com" for m in members)

    # 3. API Thêm thành viên
    res_add = client.post(
        "/api/v1/projects/PRJ_ECOMMERCE_V2/members",
        json={
            "user_email": "mack.johnson@example.com",
            "role_in_project": "QA Lead",
        },
        headers=headers,
    )
    assert res_add.status_code == 200
    assert res_add.json()["data"]["user_email"] == "mack.johnson@example.com"
    assert res_add.json()["data"]["duration_days"] == 30
    assert res_add.json()["data"]["started_at"]
    assert res_add.json()["data"]["due_at"]

    # 4. API Tìm kiếm thành viên
    res_search = client.get("/api/v1/projects/PRJ_ECOMMERCE_V2/members?q=mack.johnson", headers=headers)
    assert res_search.status_code == 200
    assert len(res_search.json()["data"]) == 1

    # 5. API Xóa thành viên
    res_del = client.delete("/api/v1/projects/PRJ_ECOMMERCE_V2/members/mack.johnson@example.com", headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["data"]["removed"] is True


def test_dashboard_ui_create_project_and_member_dialogs():
    from unittest.mock import MagicMock
    from frontend.pages.dashboard_page import DashboardPage

    mock_ctx = MagicMock()
    mock_ctx.projects.list_projects.return_value = [
        {"code": "PRJ_DEMO", "name": "Dự án Demo", "description": "Mô tả", "updated_at": "2026-10-26"}
    ]
    mock_ctx.projects.list_members.return_value = [
        {"user_email": "alex.carter@example.com", "user_name": "Alex", "role_in_project": "Lead", "department": "Dev"}
    ]
    mock_ctx.list_users.return_value = [
        {"email": "alex.carter@example.com", "name": "Alex", "department": "Dev"},
        {"email": "emma.wilson@example.com", "name": "Emma", "department": "Dev"},
    ]

    dash = DashboardPage(
        username="Alex Carter",
        projects=[
            {"code": "PRJ_DEMO", "name": "Dự án Demo", "description": "Mô tả", "updated_at": "2026-10-26"}
        ],
        on_select_project=lambda p: None,
        on_logout=lambda: None,
        ctx=mock_ctx,
        user={"name": "Alex", "email": "alex.carter@example.com", "level": "TEAM_LEAD", "is_team_lead": True},
    )

    # Đảm bảo grid render thành công
    assert len(dash.projects) == 1
    # Kiểm tra mở dialog tạo dự án
    dash._open_create_project_dialog()
    # Kiểm tra mở dialog quản lý thành viên
    dash._open_project_members_dialog(dash.projects[0])

    # Kiểm tra khi dash đã được gắn vào page (self.page != None)
    mock_page = MagicMock()
    dash._Control__page = mock_page
    dash._open_project_members_dialog(dash.projects[0])
    assert mock_page.open.called


def test_member_opens_project_members_as_read_only():
    """Member được xem danh sách nhưng UI không tải ứng viên hay hiển thị vùng thêm thành viên."""
    from unittest.mock import MagicMock
    from frontend.pages.dashboard_page import DashboardPage

    mock_ctx = MagicMock()
    mock_ctx.projects.list_members.return_value = [
        {
            "user_email": "emma.wilson@example.com",
            "user_name": "Emma",
            "role_in_project": "Backend Developer",
            "department": "Engineering",
            "project_role_key": "MEMBER",
            "risk_status": "at_risk",
            "risk_reason": "Tiến độ thấp hơn kỳ vọng",
            "deadline_status": "active",
            "days_remaining": 2,
        }
    ]
    dashboard = DashboardPage(
        username="Emma",
        projects=[],
        on_select_project=lambda _: None,
        on_logout=lambda: None,
        ctx=mock_ctx,
        user={"name": "Emma", "email": "emma.wilson@example.com", "permission": "MEMBER"},
        load_projects_on_mount=False,
    )
    mock_page = MagicMock()
    dashboard._Control__page = mock_page

    dashboard._open_project_members_dialog(
        {"code": "PRJ_DEMO", "name": "Dự án Demo", "can_manage_template": False}
    )

    dialog = mock_page.open.call_args.args[0]
    add_members_panel = dialog.content.content.controls[0]
    assert add_members_panel.visible is False
    members_panel = dialog.content.content.controls[1]
    filter_row = members_panel.content.controls[1]
    assert filter_row.controls[1].visible is True
    member_row = members_panel.content.controls[2].content.controls[0]
    member_details = member_row.content.controls[0].controls[1]
    assert member_details.controls[0].controls[2].visible is True
    assert member_details.controls[2].visible is True
    mock_ctx.list_users.assert_not_called()
    mock_ctx.projects.add_member.assert_not_called()
    mock_ctx.projects.add_members_batch.assert_not_called()


def test_workspace_can_close_project():
    """Nút đóng workspace gọi điều hướng ngay, không phụ thuộc request tải Dashboard."""
    from unittest.mock import MagicMock
    from frontend.pages.workspace_page import WorkspacePage

    closed: list[bool] = []
    mock_ctx = MagicMock()
    mock_ctx.checklist.list_items.return_value = []
    mock_ctx.checklist.progress.return_value = {"percent": 0}
    workspace = WorkspacePage(
        ctx=mock_ctx,
        project={"code": "PRJ_DEMO", "name": "Dự án Demo"},
        user={"name": "Emma", "email": "emma.wilson@example.com", "permission": "MEMBER"},
        on_back=lambda: closed.append(True),
    )

    workspace._close_workspace()

    assert closed == [True]


def test_workspace_header_has_no_duplicate_back_or_unused_settings_action():
    """Header không lặp nút đóng và không còn icon Settings không cần thiết."""
    from unittest.mock import MagicMock

    import flet as ft

    from frontend.pages.workspace_page import WorkspacePage

    mock_ctx = MagicMock()
    mock_ctx.checklist.list_items.return_value = []
    mock_ctx.checklist.progress.return_value = {"percent": 0}
    user = {"name": "Alex", "email": "alex.carter@example.com", "permission": "TEAM_LEAD"}
    workspace = WorkspacePage(ctx=mock_ctx, user=user)

    header_actions = workspace.header.content.controls[1].controls

    assert not any(
        isinstance(control, ft.OutlinedButton) and control.text == "Đóng dự án"
        for control in header_actions
    )
    assert not any(
        isinstance(control, ft.IconButton) and control.icon == ft.Icons.SETTINGS_OUTLINED
        for control in header_actions
    )


def test_project_member_progress_filter_uses_selected_status():
    """Chọn trạng thái tiến độ phải lọc lại ngay danh sách thành viên trong dialog."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from frontend.pages.dashboard_page import DashboardPage

    mock_ctx = MagicMock()
    mock_ctx.projects.list_members.return_value = [
        {
            "user_email": "emma.wilson@example.com",
            "user_name": "Emma",
            "risk_status": "on_track",
            "project_role_key": "MEMBER",
        },
        {
            "user_email": "mack.johnson@example.com",
            "user_name": "Mack",
            "risk_status": "completed",
            "project_role_key": "MEMBER",
        },
    ]
    mock_ctx.list_users.return_value = []
    dashboard = DashboardPage(
        username="Alex",
        projects=[],
        on_select_project=lambda _: None,
        on_logout=lambda: None,
        ctx=mock_ctx,
        user={"name": "Alex", "email": "alex.carter@example.com", "permission": "TEAM_LEAD"},
        load_projects_on_mount=False,
    )
    mock_page = MagicMock()
    dashboard._Control__page = mock_page

    dashboard._open_project_members_dialog(
        {"code": "PRJ_DEMO", "name": "Dự án Demo", "can_manage_template": True}
    )

    dialog = mock_page.open.call_args.args[0]
    members_panel = dialog.content.content.controls[1]
    filter_row = members_panel.content.controls[1]
    risk_filter = filter_row.controls[1]
    members_column = members_panel.content.controls[2].content
    risk_filter.value = "completed"
    risk_filter.on_change(SimpleNamespace(control=risk_filter, data="completed"))

    assert len(members_column.controls) == 1


def test_new_workspace_refreshes_history_after_pending_chat_finishes(monkeypatch):
    """Quay lại dự án khi AI đang trả lời phải tự nhận response đã lưu sau đó."""
    from unittest.mock import MagicMock

    from frontend.pages import workspace_page
    from frontend.pages.workspace_page import WorkspacePage

    mock_ctx = MagicMock()
    mock_ctx.checklist.list_items.return_value = []
    mock_ctx.checklist.progress.return_value = {"percent": 0}
    mock_ctx.agent.get_history.side_effect = [
        [{"sender": "user", "message": "Câu hỏi đang chờ", "created_at": "2026-10-29T10:00:00"}],
        [
            {"sender": "user", "message": "Câu hỏi đang chờ", "created_at": "2026-10-29T10:00:00"},
            {"sender": "ai", "message": "Phản hồi đã lưu", "created_at": "2026-10-29T10:00:05"},
        ],
    ]
    workspace = WorkspacePage(
        ctx=mock_ctx,
        project={"code": "PRJ_DEMO", "name": "Dự án Demo"},
        user={"name": "Emma", "email": "emma.wilson@example.com", "permission": "MEMBER"},
    )
    workspace._mounted = True
    pending_request_id = "pending-request"
    workspace_page._set_pending_chat(workspace._chat_request_key, pending_request_id, True)
    monkeypatch.setattr(
        workspace_page.time,
        "sleep",
        lambda _: workspace_page._set_pending_chat(
            workspace._chat_request_key,
            pending_request_id,
            False,
        ),
    )

    try:
        workspace._load_chat_history()
    finally:
        workspace_page._set_pending_chat(workspace._chat_request_key, pending_request_id, False)

    assert mock_ctx.agent.get_history.call_count == 2
    assert len(workspace.chat_messages.controls) == 3


def test_workspace_allows_only_one_chat_until_user_cancels():
    """Trong lúc chờ AI, input bị khóa và nút gửi chỉ thực hiện hủy request hiện tại."""
    from unittest.mock import MagicMock

    from frontend.models import AgentReply
    from frontend.pages.workspace_page import WorkspacePage

    mock_ctx = MagicMock()
    mock_ctx.checklist.list_items.return_value = []
    mock_ctx.checklist.progress.return_value = {"percent": 0}
    mock_ctx.agent.chat.return_value = AgentReply(text="Response cũ không được hiển thị")
    workspace = WorkspacePage(
        ctx=mock_ctx,
        project={"code": "PRJ_DEMO", "name": "Dự án Demo"},
        user={"name": "Emma", "email": "emma.wilson@example.com", "permission": "MEMBER"},
    )
    mock_page = MagicMock()
    workers: list[tuple[object, tuple]] = []
    mock_page.run_thread.side_effect = lambda worker, *args: workers.append((worker, args))
    workspace._Control__page = mock_page
    workspace._mounted = True
    initial_message_count = len(workspace.chat_messages.controls)

    workspace.chat_input.value = "Câu hỏi thứ nhất"
    workspace._submit_chat()

    assert workspace._chat_running is True
    assert workspace.chat_input.disabled is True
    assert len(workers) == 1
    assert len(workspace.chat_messages.controls) == initial_message_count + 1

    workspace._submit_chat()  # Nút gửi đã đổi thành nút Hủy.

    assert workspace._chat_running is False
    assert workspace.chat_input.disabled is False
    assert len(workers) == 2
    assert len(workspace.chat_messages.controls) == initial_message_count + 2

    cancel_worker, cancel_args = workers[1]
    cancel_worker(*cancel_args)
    response_worker, response_args = workers[0]
    response_worker(*response_args)

    mock_ctx.agent.cancel_chat.assert_called_once()
    mock_ctx.agent.chat.assert_called_once()
    assert len(workspace.chat_messages.controls) == initial_message_count + 2


def test_workspace_replaces_running_check_play_icon_with_spinner():
    """Bước đang kiểm tra phải hiện loading đúng tại vị trí nút Play."""
    from unittest.mock import MagicMock

    import flet as ft

    from frontend.pages.workspace_page import WorkspacePage

    mock_ctx = MagicMock()
    mock_ctx.checklist.list_items.return_value = []
    mock_ctx.checklist.progress.return_value = {"percent": 0}
    workspace = WorkspacePage(
        ctx=mock_ctx,
        project={"code": "PRJ_DEMO", "name": "Dự án Demo"},
        user={"name": "Emma", "email": "emma.wilson@example.com", "permission": "MEMBER"},
    )

    workspace._running_check_key = "python-version"

    running_action = workspace._build_check_action("python-version", disabled=True)
    waiting_action = workspace._build_check_action("git-version", disabled=True)

    assert isinstance(running_action, ft.Container)
    assert isinstance(running_action.content, ft.ProgressRing)
    assert isinstance(waiting_action, ft.IconButton)
    assert waiting_action.icon == ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED
    assert waiting_action.disabled is True


def test_project_action_shows_loading_and_blocks_double_click():
    """Một action đang chạy chỉ được gửi đúng một lần dù người dùng click liên tục."""
    from unittest.mock import MagicMock
    from frontend.pages.dashboard_page import DashboardPage

    dashboard = DashboardPage(
        username="Alex",
        projects=[],
        on_select_project=lambda _: None,
        on_logout=lambda: None,
        ctx=MagicMock(),
        user={"name": "Alex", "email": "alex@example.com", "permission": "TEAM_LEAD"},
        load_projects_on_mount=False,
    )
    mock_page = MagicMock()
    workers: list[Callable[[], None]] = []
    mock_page.run_thread.side_effect = lambda worker: workers.append(worker)
    dashboard._Control__page = mock_page
    calls: list[str] = []

    dashboard._run_project_action("open:PRJ_DEMO", "Đang mở…", lambda: calls.append("opened"))
    dashboard._run_project_action("open:PRJ_DEMO", "Đang mở…", lambda: calls.append("duplicate"))

    assert len(workers) == 1
    assert mock_page.open.call_count == 1
    workers[0]()
    assert calls == ["opened"]
    assert mock_page.close.call_count == 1
    assert "open:PRJ_DEMO" not in dashboard._project_actions_in_progress


def test_add_project_member_enforces_template_role(settings):
    from backend.services.checklist_service import ChecklistService
    from backend.services.user_service import UserService

    svc = ProjectService(settings)
    users_svc = UserService(settings)
    cl_svc = ChecklistService(settings)

    # 1. Tạo project PRJ_BACKEND_ONLY
    prj = svc.create_project(
        code="PRJ_BACKEND_ONLY",
        name="Backend Only Project",
        creator_email="alex.carter@example.com",
    )

    # 2. Import task chỉ dành cho Backend Developer
    csv_data = """task_name,category,role,check_type,mandatory,owner_team,instructions,params,sort_order
Setup Python & Poetry,Môi trường,Backend Developer,SOFTWARE,true,DevOps,Cài python,"{""command"": ""python --version""}",1
"""
    cl_svc.import_tasks_from_csv(csv_data, project_code="PRJ_BACKEND_ONLY")

    # Chức danh không còn tạo role hoặc giới hạn checklist.
    p_info = svc.get_project("PRJ_BACKEND_ONLY")
    assert p_info is not None
    assert p_info["role_ids"] == []

    # 4. Thêm member có vai trò Backend Developer (emma.wilson@example.com hoặc alex.carter@example.com) -> thành công
    m_ok = svc.add_project_member(
        project_code="PRJ_BACKEND_ONLY",
        user_email="alex.carter@example.com",
        role_in_project="Backend Developer",
    )
    assert m_ok["user_email"] == "alex.carter@example.com"

    m_other = svc.add_project_member(
        project_code="PRJ_BACKEND_ONLY",
        user_email="mike.brown@example.com",
        job_title="Business Analyst",
    )
    assert m_other["job_title"] == "Business Analyst"


def test_list_projects_admin_vs_member_visibility(settings):
    from backend.services.user_service import UserService

    svc = ProjectService(settings)
    UserService(settings)

    # Tạo dự án 1 với creator là alex.carter@example.com
    svc.create_project(
        code="PRJ_ADMIN_VIEW_1",
        name="Project Admin View 1",
        creator_email="alex.carter@example.com",
    )
    # Tạo dự án 2 và gán Mack là MEMBER.
    svc.create_project(
        code="PRJ_ADMIN_VIEW_2",
        name="Project Admin View 2",
        creator_email="alex.carter@example.com",
    )
    svc.add_project_member(
        project_code="PRJ_ADMIN_VIEW_2",
        user_email="mack.johnson@example.com",
        role_in_project="QA Engineer",
        project_role_key="MEMBER",
    )
    svc.create_project(
        code="PRJ_ADMIN_VIEW_3",
        name="Project Admin View 3",
        creator_email="alex.carter@example.com",
    )

    # 1. Admin (alex.carter@example.com) xem toàn bộ dự án
    admin_prjs = svc.list_projects(user_email="alex.carter@example.com", is_admin=True)
    admin_codes = [p["code"] for p in admin_prjs]
    assert "PRJ_ADMIN_VIEW_1" in admin_codes
    assert "PRJ_ADMIN_VIEW_2" in admin_codes

    # 2. Member emma.wilson@example.com (chưa được gán vào dự án nào) -> không thấy dự án nào
    member_prjs = svc.list_projects(user_email="emma.wilson@example.com", is_admin=False)
    member_codes = [p["code"] for p in member_prjs]
    assert "PRJ_ADMIN_VIEW_1" not in member_codes
    assert "PRJ_ADMIN_VIEW_2" not in member_codes

    # 3. Thêm member emma.wilson@example.com vào PRJ_ADMIN_VIEW_1
    svc.add_project_member(
        project_code="PRJ_ADMIN_VIEW_1",
        user_email="emma.wilson@example.com",
        role_in_project="Developer",
    )

    # 4. Member emma.wilson@example.com chỉ thấy PRJ_ADMIN_VIEW_1, không thấy PRJ_ADMIN_VIEW_2
    member_prjs_after = svc.list_projects(user_email="emma.wilson@example.com", is_admin=False)
    member_codes_after = [p["code"] for p in member_prjs_after]
    assert "PRJ_ADMIN_VIEW_1" in member_codes_after
    assert "PRJ_ADMIN_VIEW_2" not in member_codes_after
    assert next(p for p in member_prjs_after if p["code"] == "PRJ_ADMIN_VIEW_1")["can_manage_template"] is False

    # Project Lead được quản lý template đúng dự án đã giao, không có quyền lan sang dự án khác.
    svc.add_project_member(
        project_code="PRJ_ADMIN_VIEW_1",
        user_email="mack.johnson@example.com",
        role_in_project="QA Engineer",
        project_role_key="PROJECT_LEAD",
    )
    leader_projects = svc.list_projects(user_email="mack.johnson@example.com", is_admin=False)
    project_one = next(p for p in leader_projects if p["code"] == "PRJ_ADMIN_VIEW_1")
    project_two = next(p for p in leader_projects if p["code"] == "PRJ_ADMIN_VIEW_2")
    leader_codes = {p["code"] for p in leader_projects}
    assert project_one["can_manage_template"] is True
    assert project_two["can_manage_template"] is False
    assert "PRJ_ADMIN_VIEW_3" not in leader_codes
    assert svc.is_user_project_lead_any_project("mack.johnson@example.com") is True


def test_roles_and_user_checklists_role_id(settings):
    from sqlalchemy import text
    from backend.services.db import get_connection
    from backend.services.user_service import UserService

    UserService(settings)
    svc = ProjectService(settings)

    # Bảng roles chỉ lưu ba quyền chuẩn.
    roles = svc.list_roles()
    assert {r["key_role"] for r in roles} == {"TEAM_LEAD", "PROJECT_LEAD", "MEMBER"}

    # 2. Tạo dự án mới và thêm member với role_id cụ thể
    svc.create_project(code="PRJ_ROLE_ID_TEST", name="Project Role ID Test")
    member_role = next(r for r in roles if r["key_role"] == "MEMBER")
    new_m = svc.add_project_member(
        project_code="PRJ_ROLE_ID_TEST",
        user_email="sophia.davis@example.com",
        job_title="QA Engineer",
    )
    assert new_m["role_id"] == member_role["role_id"]
    assert new_m["role_name"] == "Member"
    assert new_m["job_title"] == "QA Engineer"

    # 3. Kiểm tra trực tiếp bảng user_checklists trong database có lưu cột role_id
    with get_connection(settings.database_url) as conn:
        row = conn.execute(
            text("""
                SELECT uc.role_id, r.role_name
                FROM user_checklists uc
                JOIN roles r ON r.role_id = uc.role_id
                WHERE uc.checklist_id = :cid
            """),
            {"cid": new_m["id"]},
        ).mappings().first()
        assert row is not None
        assert row["role_id"] == member_role["role_id"]
        assert row["role_name"] == "Member"

    # 4. Kiểm tra list_project_members trả về role_id và role_name đúng
    members = svc.list_project_members("PRJ_ROLE_ID_TEST")
    assert len(members) == 1
    assert members[0]["role_id"] == member_role["role_id"]
    assert members[0]["role_name"] == "Member"
    assert members[0]["job_title"] == "QA Engineer"


def test_job_title_does_not_create_roles(settings):
    """Gán quyền dự án không được cập nhật chức danh đang lưu trên user."""
    from backend.services.user_service import UserService

    UserService(settings)
    svc = ProjectService(settings)
    svc.create_project(code="PRJ_ROLE_CANONICAL", name="Project Role Canonical")

    member = svc.add_project_member(
        project_code="PRJ_ROLE_CANONICAL",
        user_email="emma.wilson@example.com",
        role_in_project="  Project Lead ",
    )
    assert member["job_title"] == "Backend Developer"
    custom = svc.add_project_member(
        project_code="PRJ_ROLE_CANONICAL",
        user_email="sophia.davis@example.com",
        job_title="Role nhập tự do",
    )
    assert custom["job_title"] == "QA Engineer"

    roles = svc.list_roles()
    role_names = {role["role_name"] for role in roles}
    assert "Project Leader" not in role_names
    assert "Role nhập tự do" not in role_names
    assert all("key_role" in role and "role_code" not in role for role in roles)


def test_add_project_members_batch(settings):
    """Kiểm tra tính năng thêm hàng loạt thành viên (multi-select) vào dự án."""
    svc = ProjectService(settings)

    # 1. Tạo project và seed users
    svc.create_project(
        code="PRJ_BATCH_TEST",
        name="Dự án Batch Test",
        role_name="Developer",
        description="Test batch add",
    )

    roles = svc.list_roles()
    member_role = next(r for r in roles if r["key_role"] == "MEMBER")

    with get_connection(settings.database_url) as conn:
        conn.execute(
            text("INSERT INTO users (name, email, password, role_id, job_title, department) VALUES (:name, :email, '1234', :rid, 'Developer', :dept)"),
            {"name": "Batch 1", "email": "user_batch_1@example.com", "rid": member_role["role_id"], "dept": "Engineering"}
        )
        conn.execute(
            text("INSERT INTO users (name, email, password, role_id, job_title, department) VALUES (:name, :email, '1234', :rid, 'Developer', :dept)"),
            {"name": "Batch 2", "email": "user_batch_2@example.com", "rid": member_role["role_id"], "dept": "Engineering"}
        )

    # 2. Thêm hàng loạt thành viên
    members_to_add = [
        {
            "user_email": "user_batch_1@example.com",
            "user_name": "Batch 1",
            "department": "Engineering",
            "job_title": "Developer",
        },
        {
            "user_email": "user_batch_2@example.com",
            "user_name": "Batch 2",
            "department": "Engineering",
            "job_title": "Developer",
        },
    ]

    added = svc.add_project_members_batch("PRJ_BATCH_TEST", members=members_to_add, added_by="admin@example.com")
    assert len(added) == 2
    assert {m["user_email"] for m in added} == {"user_batch_1@example.com", "user_batch_2@example.com"}

    # 3. Kiểm tra list_project_members
    current = svc.list_project_members("PRJ_BATCH_TEST")
    emails = {m["user_email"] for m in current}
    assert "user_batch_1@example.com" in emails
    assert "user_batch_2@example.com" in emails


def test_project_duration_starts_independently_when_member_is_added(settings):
    svc = ProjectService(settings)
    project = svc.create_project(
        code="PRJ_DEADLINE",
        name="Dự án có thời hạn",
        duration_days=20,
    )
    assert project["duration_days"] == 20

    first = svc.add_project_member(
        project_code="PRJ_DEADLINE",
        user_email="emma.wilson@example.com",
        role_in_project="Developer",
        added_by="alex.carter@example.com",
    )
    started = datetime.fromisoformat(first["started_at"])
    due = datetime.fromisoformat(first["due_at"])
    assert due - started == timedelta(days=20)
    assert first["days_remaining"] in {19, 20}
    assert first["deadline_status"] == "active"
    assert first["risk_status"] == "on_track"

    member_project = next(
        project
        for project in svc.list_projects(user_email="emma.wilson@example.com", is_admin=False)
        if project["code"] == "PRJ_DEADLINE"
    )
    assert member_project["started_at"] == first["started_at"]
    assert member_project["due_at"] == first["due_at"]

    # Gán lại role cho member đã tồn tại không được reset đồng hồ onboarding.
    second = svc.add_project_member(
        project_code="PRJ_DEADLINE",
        user_email="emma.wilson@example.com",
        role_in_project="Developer",
        added_by="alex.carter@example.com",
    )
    assert second["started_at"] == first["started_at"]
    assert second["due_at"] == first["due_at"]


def test_member_deadline_reports_overdue_and_completed(settings):
    svc = ProjectService(settings)
    svc.create_project(code="PRJ_OVERDUE", name="Dự án quá hạn", duration_days=5)
    member = svc.add_project_member(
        project_code="PRJ_OVERDUE",
        user_email="emma.wilson@example.com",
        role_in_project="Developer",
    )
    old_start = datetime.now() - timedelta(days=10)
    old_due = old_start + timedelta(days=5)
    with get_connection(settings.database_url) as conn:
        conn.execute(
            text(
                "UPDATE user_checklists SET started_at=:started, due_at=:due "
                "WHERE checklist_id=:checklist_id"
            ),
            {
                "started": old_start.isoformat(),
                "due": old_due.isoformat(),
                "checklist_id": member["id"],
            },
        )

    listed = svc.list_project_members("PRJ_OVERDUE")[0]
    assert listed["deadline_status"] == "overdue"
    assert listed["days_remaining"] <= -5
    assert listed["risk_status"] == "overdue"

    project_summary = next(
        project
        for project in svc.list_projects(user_email="alex.carter@example.com", is_admin=True)
        if project["code"] == "PRJ_OVERDUE"
    )
    assert project_summary["overdue_count"] == 1

    with get_connection(settings.database_url) as conn:
        conn.execute(
            text("UPDATE user_checklists SET status='COMPLETED' WHERE checklist_id=:checklist_id"),
            {"checklist_id": member["id"]},
        )
    completed = svc.list_project_members("PRJ_OVERDUE")[0]
    assert completed["deadline_status"] == "completed"
    assert completed["risk_status"] == "completed"


def test_member_at_risk_when_progress_falls_behind_schedule(settings):
    svc = ProjectService(settings)
    svc.create_project(code="PRJ_AT_RISK", name="Dự án có nguy cơ", duration_days=10)
    member = svc.add_project_member(
        project_code="PRJ_AT_RISK",
        user_email="emma.wilson@example.com",
        role_in_project="Developer",
    )
    started = datetime.now() - timedelta(days=8)
    due = started + timedelta(days=10)
    with get_connection(settings.database_url) as conn:
        conn.execute(
            text(
                "UPDATE user_checklists SET started_at=:started, due_at=:due, "
                "status='IN_PROGRESS', progress=20 WHERE checklist_id=:checklist_id"
            ),
            {
                "started": started.isoformat(),
                "due": due.isoformat(),
                "checklist_id": member["id"],
            },
        )

    listed = svc.list_project_members("PRJ_AT_RISK")[0]
    assert listed["risk_status"] == "at_risk"
    assert listed["expected_progress"] >= 79
    assert "tiến độ" in listed["risk_reason"].lower()

    project_summary = next(
        project
        for project in svc.list_projects(user_email="alex.carter@example.com", is_admin=True)
        if project["code"] == "PRJ_AT_RISK"
    )
    assert project_summary["member_count"] == 1
    assert project_summary["risk_count"] == 1
    assert project_summary["overdue_count"] == 0


def test_project_duration_validation(settings):
    svc = ProjectService(settings)
    with pytest.raises(ValueError, match="1 đến 3650"):
        svc.create_project(code="PRJ_ZERO_DAY", name="Sai thời hạn", duration_days=0)
    with pytest.raises(ValueError, match="1 đến 3650"):
        svc.create_project(code="PRJ_TOO_LONG", name="Sai thời hạn", duration_days=3651)





