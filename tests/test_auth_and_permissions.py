"""Test xác thực và hierarchy TEAM_LEAD > PROJECT_LEAD > MEMBER."""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app import app, FileCopyRequest, IngestRequest
from backend.core.context import build_context
from backend.services.verification_service import VerificationResult
from backend.services.user_service import (
    LEVEL_MEMBER,
    LEVEL_PROJECT_LEAD,
    LEVEL_TEAM_LEAD,
    UserService,
    has_management_permission,
    is_template_manager_role,
    is_senior_or_above,
)


def test_is_senior_or_above_levels() -> None:
    # Hai cấp leader có quyền quản trị; MEMBER chỉ thực thi.
    assert has_management_permission("PROJECT_LEAD") is True
    assert has_management_permission("TEAM_LEAD") is True
    assert is_senior_or_above("PROJECT_LEAD") is True
    assert is_senior_or_above(LEVEL_TEAM_LEAD) is True

    # MEMBER và các cấp bậc cũ như Senior / Junior / Middle không có quyền quản trị
    assert has_management_permission("MEMBER") is False
    assert is_senior_or_above("MEMBER") is False
    assert has_management_permission("Senior") is False
    assert is_senior_or_above("Senior") is False
    assert has_management_permission("Junior") is False
    assert has_management_permission("Middle") is False
    assert is_template_manager_role("Project Lead") is True
    assert is_template_manager_role("Team Lead") is True
    assert is_template_manager_role("Tech Lead") is False
    assert is_template_manager_role("QA Lead") is False
    assert has_management_permission(None) is False
    assert has_management_permission("") is False


def test_user_service_crud_and_lookup(settings) -> None:
    service = UserService(settings)
    users = service.list_users()
    assert len(users) >= 6

    # Tìm user TEAM_LEAD (Alex) và kiểm tra mật khẩu mặc định MD5.
    admin = service.get_by_email("alex.carter@example.com")
    assert admin is not None
    assert admin.permission == "TEAM_LEAD"
    assert admin.level == LEVEL_TEAM_LEAD
    assert admin.is_team_lead is True
    assert admin.can_manage is True
    assert admin.is_senior is True
    assert admin.password == "81dc9bdb52d04dc20036dbd8313ed055"

    # Mack có quyền hệ thống MEMBER; quyền Project Lead chỉ nằm trên assignment dự án.
    dat_user = service.get_by_email("mack.johnson@example.com")
    assert dat_user is not None
    assert dat_user.permission == "MEMBER"
    assert dat_user.role_name == "Member"
    assert dat_user.job_title == "QA Engineer"
    assert dat_user.is_member is True
    assert dat_user.is_project_lead is False
    assert dat_user.is_team_lead is False

    # Kiểm tra authenticate với mật khẩu đúng và sai
    assert service.authenticate("alex.carter@example.com", "1234") is not None
    assert service.authenticate("alex.carter@example.com", "wrong_password") is None

    # Tìm user MEMBER (Emma)
    member = service.get_by_email("emma.wilson@example.com")
    assert member is not None
    assert member.level == LEVEL_MEMBER
    assert member.is_member is True
    assert member.can_manage is False
    assert member.is_senior is False
    assert member.password == "81dc9bdb52d04dc20036dbd8313ed055"

    # User không tồn tại
    assert service.get_by_email("notfound@example.com") is None


def test_login_api_checks_email_and_returns_session_key(settings, monkeypatch) -> None:
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    client = TestClient(app)

    # 1. Email không tồn tại -> 404
    res = client.post("/api/v1/auth/login", json={"email": "hacker@example.com"})
    assert res.status_code == 404
    assert "không tồn tại trong hệ thống" in res.json()["detail"]

    # 2. Email đúng nhưng sai mật khẩu -> 401
    res_wrong_pw = client.post(
        "/api/v1/auth/login",
        json={"email": "emma.wilson@example.com", "password": "wrong_password"},
    )
    assert res_wrong_pw.status_code == 401
    assert "Mật khẩu không chính xác" in res_wrong_pw.json()["detail"]

    # 3. Email MEMBER hợp lệ kèm đúng mật khẩu -> 200, session_key = MD5(email)
    res_jr = client.post(
        "/api/v1/auth/login",
        json={"email": "emma.wilson@example.com", "password": "1234"},
    )
    assert res_jr.status_code == 200
    data_jr = res_jr.json()["data"]
    assert data_jr["email"] == "emma.wilson@example.com"
    assert data_jr["level"] == "MEMBER"
    assert data_jr["is_senior"] is False
    assert data_jr["can_manage"] is False
    assert data_jr["session_key"] == hashlib.md5(b"emma.wilson@example.com").hexdigest()

    # 4. Email ADMIN hợp lệ kèm đúng mật khẩu -> 200, session_key = MD5(email)
    res_sr = client.post(
        "/api/v1/auth/login",
        json={"email": "alex.carter@example.com", "password": "1234"},
    )
    assert res_sr.status_code == 200
    data_sr = res_sr.json()["data"]
    assert data_sr["email"] == "alex.carter@example.com"
    assert data_sr["level"] == "TEAM_LEAD"
    assert data_sr["is_senior"] is True
    assert data_sr["can_manage"] is True
    assert data_sr["session_key"] == hashlib.md5(b"alex.carter@example.com").hexdigest()


def test_session_key_authentication_and_enforcement(settings, monkeypatch) -> None:
    """Tất cả các API ngoại trừ login đều bắt buộc phải có X-Session-Key hợp lệ."""
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    client = TestClient(app)

    # 1. Gọi API không có header X-Session-Key -> 401
    res_no_key = client.get("/api/v1/apps")
    assert res_no_key.status_code == 401
    assert "X-Session-Key" in res_no_key.json()["error"]

    # 2. Gọi API với X-Session-Key không hợp lệ -> 401
    res_bad_key = client.get(
        "/api/v1/apps",
        headers={"X-Session-Key": "invalid_session_key_123456789012"},
    )
    assert res_bad_key.status_code == 401
    assert "Session key không hợp lệ" in res_bad_key.json()["error"]

    # 3. Đăng nhập với tài khoản MEMBER để lấy session key chính thức
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "emma.wilson@example.com", "password": "1234"},
    )
    assert login_res.status_code == 200
    member_session_key = login_res.json()["data"]["session_key"]
    assert member_session_key == hashlib.md5(b"emma.wilson@example.com").hexdigest()

    # 4. Dùng session key vừa lấy để truy cập API -> 200 OK
    res_with_key = client.get("/api/v1/apps", headers={"X-Session-Key": member_session_key})
    assert res_with_key.status_code == 200

    # 5. Dùng session key của ADMIN để tạo app (tự nhận diện quyền quản trị)
    admin_session_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    res_create = client.post(
        "/api/v1/apps",
        headers={"X-Session-Key": admin_session_key},
        json={"app_code": "admin_tool", "app_name": "Admin CLI"},
    )
    assert res_create.status_code == 200
    assert res_create.json()["data"]["app_code"] == "admin_tool"

    # 6. Project Lead theo dự án không có quyền tạo app toàn hệ thống.
    leader_session_key = hashlib.md5(b"mack.johnson@example.com").hexdigest()
    res_create_leader = client.post(
        "/api/v1/apps",
        headers={"X-Session-Key": leader_session_key},
        json={"app_code": "leader_tool", "app_name": "Leader CLI"},
    )
    assert res_create_leader.status_code == 403

    # 7. Dùng session key của MEMBER để tạo app -> 403 Forbidden.
    res_fail = client.post(
        "/api/v1/apps",
        headers={"X-Session-Key": member_session_key},
        json={"app_code": "member_fail", "app_name": "Member Tool"},
    )
    assert res_fail.status_code == 403
    assert "TEAM_LEAD" in res_fail.json()["detail"]


def test_upload_and_ingest_requires_senior_level(settings, tmp_path: Path, monkeypatch) -> None:
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    client = TestClient(app)
    admin_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    leader_key = hashlib.md5(b"mack.johnson@example.com").hexdigest()
    member_key = hashlib.md5(b"emma.wilson@example.com").hexdigest()

    # Tạo file test mẫu
    doc_file = tmp_path / "test_doc.md"
    doc_file.write_text("# Test Docs", encoding="utf-8")

    # 1. Thử upload không có header X-Session-Key -> 401
    res_no_key = client.post(
        "/api/v1/projects/PRJ_ECOMMERCE/documents",
        json={"source_paths": [str(doc_file)]},
    )
    assert res_no_key.status_code == 401

    # 2. Thử upload với tài khoản MEMBER -> 403 (chỉ TEAM_LEAD hoặc PROJECT_LEAD).
    res_member = client.post(
        "/api/v1/projects/PRJ_ECOMMERCE/documents",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
        json={"source_paths": [str(doc_file)]},
    )
    assert res_member.status_code == 403
    assert "TEAM_LEAD" in res_member.json()["detail"]

    # 3. Upload với tài khoản PROJECT_LEAD -> 200 Thành công
    res_leader = client.post(
        "/api/v1/projects/PRJ_ECOMMERCE/documents",
        headers={"X-Session-Key": leader_key, "X-User-Email": "mack.johnson@example.com"},
        json={"source_paths": [str(doc_file)]},
    )
    assert res_leader.status_code == 200
    assert res_leader.json()["data"]["copied"] == 1

    # 4. Upload với tài khoản ADMIN -> 200 Thành công
    res_admin = client.post(
        "/api/v1/projects/PRJ_ECOMMERCE/documents",
        headers={"X-Session-Key": admin_key, "X-User-Email": "alex.carter@example.com"},
        json={"source_paths": [str(doc_file)]},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["data"]["copied"] == 1

    # 5. Thử ingest với MEMBER -> 403 (bị chặn trước khi tạo job)
    res_ingest_member = client.post(
        "/api/v1/documents/ingest-jobs",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
        json={"paths": [], "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_ingest_member.status_code == 403

    # 6. Ingest với ADMIN -> 202 Đã chấp nhận job
    monkeypatch.setattr("backend.app._jobs.submit", lambda task: "mock_job_id_sr")
    res_ingest_admin = client.post(
        "/api/v1/documents/ingest-jobs",
        headers={"X-Session-Key": admin_key, "X-User-Email": "alex.carter@example.com"},
        json={"paths": [], "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_ingest_admin.status_code == 202
    assert res_ingest_admin.json()["data"]["job_id"] == "mock_job_id_sr"


def test_checklist_template_and_import_senior_permission(settings, monkeypatch) -> None:
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    admin_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    leader_key = hashlib.md5(b"mack.johnson@example.com").hexdigest()
    member_key = hashlib.md5(b"emma.wilson@example.com").hexdigest()

    client = TestClient(app)

    # 1. MEMBER không được tải template mẫu dù đã đăng nhập.
    res_sample_member = client.get(
        "/api/v1/checklist/template-sample?project_code=PRJ_ECOMMERCE",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
    )
    assert res_sample_member.status_code == 403

    # Header email không được phép giả mạo Team Lead khi session vẫn là MEMBER.
    res_spoofed = client.get(
        "/api/v1/checklist/template-sample?project_code=PRJ_ECOMMERCE",
        headers={"X-Session-Key": member_key, "X-User-Email": "mack.johnson@example.com"},
    )
    assert res_spoofed.status_code == 403

    # Project Lead chỉ quản lý dự án được giao, không có quyền chéo dự án.
    res_wrong_project = client.get(
        "/api/v1/checklist/template-sample?project_code=PRJ_AI_BUDDY",
        headers={"X-Session-Key": leader_key},
    )
    assert res_wrong_project.status_code == 403

    # MEMBER vẫn được xem/thực thi checklist của chính mình.
    res_member_checklist = client.get(
        "/api/v1/checklist?project_code=PRJ_ECOMMERCE",
        headers={"X-Session-Key": member_key},
    )
    assert res_member_checklist.status_code == 200
    assert "items" in res_member_checklist.json()["data"]

    # Team Lead được tải template mẫu.
    res_sample = client.get(
        "/api/v1/checklist/template-sample?project_code=PRJ_ECOMMERCE",
        headers={"X-Session-Key": leader_key, "X-User-Email": "mack.johnson@example.com"},
    )
    assert res_sample.status_code == 200
    sample_data = res_sample.json()["data"]
    assert sample_data["filename"] == "checklist_template_sample.csv"
    assert "task_name,category" in sample_data["content"] and "check_type" in sample_data["content"]

    csv_data = """task_name,category,check_type,mandatory,owner_team,instructions,params,sort_order
Cài đặt PostgreSQL Client,Môi trường,SOFTWARE,true,DevOps,Cài psql cli,"{""command"": ""psql --version""}",1
Kiểm tra API Gateway,Mạng nội bộ,PORT_FREE,true,DevOps,Cổng 8080 còn trống,"{""port"": 8080}",2
"""

    # 2. Thử import không có session key -> 401 Unauthorized
    res_no_key = client.post(
        "/api/v1/checklist/import",
        json={"content": csv_data, "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_no_key.status_code == 401

    # 3. Thử import với tài khoản MEMBER -> 403 Forbidden
    res_member = client.post(
        "/api/v1/checklist/import",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
        json={"content": csv_data, "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_member.status_code == 403
    assert "TEAM_LEAD" in res_member.json()["detail"]

    # 4. Import với tài khoản PROJECT_LEAD -> 200 OK
    res_leader = client.post(
        "/api/v1/checklist/import",
        headers={"X-Session-Key": leader_key, "X-User-Email": "mack.johnson@example.com"},
        json={"content": csv_data, "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_leader.status_code == 200

    # 5. Import với tài khoản ADMIN -> 200 OK
    res_admin = client.post(
        "/api/v1/checklist/import",
        headers={"X-Session-Key": admin_key, "X-User-Email": "alex.carter@example.com"},
        json={"content": csv_data, "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_admin.status_code == 200
    res_data = res_admin.json()["data"]
    assert res_data["status"] == "ok"
    assert res_data["imported_count"] == 2
    assert "Cài đặt PostgreSQL Client" in res_data["task_names"]

    # 6. Kiểm tra dữ liệu thực tế trong onboarding_template_tasks
    item = ctx.checklist.get_item("Cài đặt PostgreSQL Client")
    assert item is not None
    assert item.title == "Cài đặt PostgreSQL Client"
    assert item.check_type == "SOFTWARE"


def test_create_app_requires_senior_permission(settings, monkeypatch) -> None:
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    admin_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    leader_key = hashlib.md5(b"mack.johnson@example.com").hexdigest()
    member_key = hashlib.md5(b"emma.wilson@example.com").hexdigest()

    client = TestClient(app)

    # 1. Thử tạo app không có session key -> 401 Unauthorized
    res_no_key = client.post(
        "/api/v1/apps",
        json={"app_code": "k8s_tool", "app_name": "Kubectl CLI"},
    )
    assert res_no_key.status_code == 401

    # 2. Thử tạo app với tài khoản MEMBER -> 403 Forbidden
    res_member = client.post(
        "/api/v1/apps",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
        json={"app_code": "k8s_tool", "app_name": "Kubectl CLI"},
    )
    assert res_member.status_code == 403
    assert "TEAM_LEAD" in res_member.json()["detail"]

    # 3. PROJECT_LEAD theo dự án không được tạo app toàn hệ thống.
    res_leader = client.post(
        "/api/v1/apps",
        headers={"X-Session-Key": leader_key, "X-User-Email": "mack.johnson@example.com"},
        json={
            "app_code": "helm_tool",
            "app_name": "Helm CLI",
            "category": "Container & Hạ tầng",
        },
    )
    assert res_leader.status_code == 403

    # 4. Tạo app với tài khoản ADMIN -> 200 OK
    res_admin = client.post(
        "/api/v1/apps",
        headers={"X-Session-Key": admin_key, "X-User-Email": "alex.carter@example.com"},
        json={
            "app_code": "k8s_tool",
            "app_name": "Kubectl CLI",
            "category": "Container & Hạ tầng",
            "recommended_version": ">= 1.28",
            "check_command": "kubectl",
        },
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["data"]["app_code"] == "k8s_tool"

    # 5. Kiểm tra tìm kiếm app vừa tạo kèm session key
    search = client.get("/api/v1/apps?query=kubectl", headers={"X-Session-Key": admin_key})
    assert search.status_code == 200
    assert len(search.json()["data"]) == 1
    assert search.json()["data"][0]["app_code"] == "k8s_tool"


def test_settings_requires_admin_level(settings, monkeypatch) -> None:
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    admin_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    leader_key = hashlib.md5(b"mack.johnson@example.com").hexdigest()
    member_key = hashlib.md5(b"emma.wilson@example.com").hexdigest()

    client = TestClient(app)

    payload = {
        "ollama_base_url": "http://127.0.0.1:11434",
        "llm_model": "qwen2.5:7b",
        "embedding_model": "bge-m3",
        "user_role": "backend_developer",
    }

    # 1. MEMBER gọi PUT /api/v1/settings -> 403 Forbidden
    res_member = client.put(
        "/api/v1/settings",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
        json=payload,
    )
    assert res_member.status_code == 403
    assert "Chỉ TEAM_LEAD" in res_member.json()["detail"]

    # 2. PROJECT_LEAD gọi PUT /api/v1/settings -> 403 Forbidden
    res_leader = client.put(
        "/api/v1/settings",
        headers={"X-Session-Key": leader_key, "X-User-Email": "mack.johnson@example.com"},
        json=payload,
    )
    assert res_leader.status_code == 403
    assert "Chỉ TEAM_LEAD" in res_leader.json()["detail"]

    # 3. ADMIN gọi PUT /api/v1/settings -> 200 OK
    res_admin = client.put(
        "/api/v1/settings",
        headers={"X-Session-Key": admin_key, "X-User-Email": "alex.carter@example.com"},
        json=payload,
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["success"] is True


def test_ui_role_access():
    from pathlib import Path
    from unittest.mock import MagicMock
    from frontend.models import AppItem
    from frontend.pages.dashboard_page import DashboardPage
    from frontend.pages.workspace_page import WorkspacePage

    mock_ctx = MagicMock()
    mock_ctx.projects.get_doc_folder.return_value = Path("documents/projects/test")
    mock_ctx.projects.list_project_documents.return_value = []
    mock_ctx.checklist.list_items.return_value = []
    mock_ctx.checklist.progress.return_value = {"percent": 0}

    # 1. User MEMBER không thấy tab Ứng dụng & Cài đặt; Workspace không còn nút Settings.
    member_user = {"name": "Emma", "email": "emma.wilson@example.com", "level": "MEMBER", "is_admin": False}
    dash_member = DashboardPage(
        username="Emma",
        projects=[],
        on_select_project=lambda p: None,
        on_logout=lambda: None,
        ctx=mock_ctx,
        user=member_user,
    )
    assert dash_member.is_admin is False
    assert len(dash_member._tab_bar_row.controls) == 1
    # Thử switch tab 1 -> bị chặn
    dash_member._switch_tab(1)
    assert dash_member._active_tab_index == 0

    ws_member = WorkspacePage(ctx=mock_ctx, user=member_user)
    assert ws_member.is_admin is False
    assert not hasattr(ws_member, "settings_btn")

    # 2. PROJECT_LEAD truy cập Ứng dụng & Cài đặt và được chọn file upload.
    leader_user = {"name": "Mack", "email": "mack.johnson@example.com", "permission": "MEMBER", "level": "MEMBER", "is_template_manager": True, "is_admin": False}
    dash_leader = DashboardPage(
        username="Mack",
        projects=[],
        on_select_project=lambda p: None,
        on_logout=lambda: None,
        ctx=mock_ctx,
        user=leader_user,
    )
    assert dash_leader.is_admin is False
    assert dash_leader.can_manage_templates is True
    assert len(dash_leader._tab_bar_row.controls) == 2
    dash_leader._switch_tab(1)
    assert dash_leader._active_tab_index == 1
    dash_leader.upload_installer_picker = MagicMock()
    dash_leader._start_upload_installer(
        AppItem(app_code="project_tool", app_name="Project Tool")
    )
    dash_leader.upload_installer_picker.pick_files.assert_called_once()

    ws_leader = WorkspacePage(
        ctx=mock_ctx,
        user=leader_user,
        project={"code": "PRJ_TEST", "name": "Test", "can_manage_template": True},
    )
    assert ws_leader.is_admin is False
    assert ws_leader.can_manage_template is True
    assert not hasattr(ws_leader, "settings_btn")

    # 3. User ADMIN có tab Ứng dụng & Cài đặt ở Dashboard nhưng Workspace không còn nút Settings.
    admin_user = {"name": "Alex", "email": "alex.carter@example.com", "level": "TEAM_LEAD", "is_team_lead": True}
    dash_admin = DashboardPage(
        username="Alex",
        projects=[],
        on_select_project=lambda p: None,
        on_logout=lambda: None,
        ctx=mock_ctx,
        user=admin_user,
    )
    assert dash_admin.is_admin is True
    assert len(dash_admin._tab_bar_row.controls) == 2
    dash_admin._switch_tab(1)
    assert dash_admin._active_tab_index == 1

    ws_admin = WorkspacePage(ctx=mock_ctx, user=admin_user)
    assert ws_admin.is_admin is True
    assert not hasattr(ws_admin, "settings_btn")


def test_permission_hierarchy_has_exact_three_levels(settings) -> None:
    """Dữ liệu quyền chỉ dùng đúng hierarchy TEAM_LEAD > PROJECT_LEAD > MEMBER."""
    service = UserService(settings)
    users = service.list_users()
    for u in users:
        assert u.permission in ("TEAM_LEAD", "PROJECT_LEAD", "MEMBER"), f"User {u.email} có permission không hợp lệ: {u.permission}"
    by_email = {user.email: user.permission for user in users}
    assert by_email["alex.carter@example.com"] == "TEAM_LEAD"
    assert by_email["mack.johnson@example.com"] == "MEMBER"
    assert by_email["mike.brown@example.com"] == "MEMBER"
    assert by_email["emma.wilson@example.com"] == "MEMBER"


def test_project_lead_role_in_onboarding_template_task(settings, monkeypatch) -> None:
    """Kiểm tra quyền Project Lead được xác định theo vai trò trong onboarding_template_tasks theo từng dự án."""
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    # Đảm bảo template và tasks được seed đầy đủ
    ctx.projects.seed_defaults()
    ctx.checklist.seed_defaults()

    # Thêm user 'mike.brown@example.com' với vai trò Project Lead vào PRJ_WAREHOUSE
    ctx.projects.add_project_member(
        project_code="PRJ_WAREHOUSE",
        user_email="mike.brown@example.com",
        role_in_project="Business Analyst",
        project_role_key="PROJECT_LEAD",
        user_name="Mike Brown",
        department="Product",
    )

    # Thêm user 'emma.wilson@example.com' với vai trò Developer vào PRJ_WAREHOUSE
    ctx.projects.add_project_member(
        project_code="PRJ_WAREHOUSE",
        user_email="emma.wilson@example.com",
        role_in_project="Backend Developer",
        user_name="Emma Wilson",
        department="Engineering",
    )

    # 1. Kiểm tra trực tiếp qua service is_user_project_lead.
    assert ctx.projects.is_user_project_lead("mike.brown@example.com", "PRJ_WAREHOUSE") is True
    assert ctx.projects.is_user_project_lead("emma.wilson@example.com", "PRJ_WAREHOUSE") is False

    client = TestClient(app)
    leader_key = hashlib.md5(b"mike.brown@example.com").hexdigest()
    member_key = hashlib.md5(b"emma.wilson@example.com").hexdigest()

    # 2. Thành viên không phải Project Lead của dự án cố import checklist -> 403 Forbidden
    res_member = client.post(
        "/api/v1/checklist/import",
        headers={"X-Session-Key": member_key, "X-User-Email": "emma.wilson@example.com"},
        json={
            "content": "key,title,category,type\ntask_1,Task 1,Cat,MANUAL",
            "project_code": "PRJ_WAREHOUSE",
        },
    )
    assert res_member.status_code == 403
    assert "TEAM_LEAD" in res_member.json()["detail"]

    # Member của dự án được xem tiến độ/risk ở chế độ chỉ đọc.
    res_member_list = client.get(
        "/api/v1/projects/PRJ_WAREHOUSE/members",
        headers={"X-Session-Key": member_key},
    )
    assert res_member_list.status_code == 200
    assert res_member_list.json()["data"]
    assert all("progress" in item and "risk_status" in item for item in res_member_list.json()["data"])

    # Dù giả mạo X-User-Email, member vẫn không thể thêm thành viên qua API.
    res_member_add = client.post(
        "/api/v1/projects/PRJ_WAREHOUSE/members",
        headers={"X-Session-Key": member_key, "X-User-Email": "alex.carter@example.com"},
        json={"user_email": "mack.johnson@example.com", "role_in_project": "QA Engineer"},
    )
    assert res_member_add.status_code == 403

    # 3. Project Lead của dự án import checklist -> 200 OK
    res_leader = client.post(
        "/api/v1/checklist/import",
        headers={"X-Session-Key": leader_key, "X-User-Email": "mike.brown@example.com"},
        json={
            "content": "key,title,category,type\ntask_lead,Task Lead,Quản trị dự án,MANUAL",
            "project_code": "PRJ_WAREHOUSE",
        },
    )
    assert res_leader.status_code == 200


def test_verified_steps_mark_member_checklist_completed(settings, monkeypatch) -> None:
    """Kết quả verify tự động phải được tính vào tiến độ riêng của member."""
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)
    ctx.projects.seed_defaults()
    ctx.checklist.import_tasks_from_csv(
        "task_name,category,check_type,mandatory\nCheck one,Setup,SOFTWARE,true\nCheck two,Setup,SOFTWARE,true",
        project_code="PRJ_VERIFY_COMPLETE",
    )
    ctx.projects.add_project_member(
        project_code="PRJ_VERIFY_COMPLETE",
        user_email="emma.wilson@example.com",
    )
    items = ctx.checklist.list_items(template_code="PRJ_VERIFY_COMPLETE")
    monkeypatch.setattr(
        ctx.verification,
        "verify_key",
        lambda key, user_email=None: VerificationResult(key=key, status="passed", message="Đạt"),
    )

    client = TestClient(app)
    member_headers = {"X-Session-Key": hashlib.md5(b"emma.wilson@example.com").hexdigest()}
    first = client.post(f"/api/v1/checklist/{items[0].key}/verify", headers=member_headers)
    assert first.status_code == 200
    assert ctx.projects.list_project_members("PRJ_VERIFY_COMPLETE")[0]["status"] == "IN_PROGRESS"

    second = client.post(f"/api/v1/checklist/{items[1].key}/verify", headers=member_headers)
    assert second.status_code == 200
    completed = ctx.projects.list_project_members("PRJ_VERIFY_COMPLETE")[0]
    assert completed["status"] == "COMPLETED"
    assert completed["progress"] == 100
    assert completed["risk_status"] == "completed"


def test_only_team_lead_can_add_or_remove_team_lead_membership(settings, monkeypatch) -> None:
    """PROJECT_LEAD không được tác động TEAM_LEAD; TEAM_LEAD có toàn quyền admin."""
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)
    client = TestClient(app)

    project_code = "PRJ_WAREHOUSE"
    project_lead_key = hashlib.md5(b"mike.brown@example.com").hexdigest()
    team_lead_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    payload = {"user_email": "alex.carter@example.com", "project_role_key": "MEMBER"}

    denied_add = client.post(
        f"/api/v1/projects/{project_code}/members",
        headers={"X-Session-Key": project_lead_key},
        json=payload,
    )
    assert denied_add.status_code == 403
    assert "Chỉ TEAM_LEAD" in denied_add.json()["detail"]

    allowed_add = client.post(
        f"/api/v1/projects/{project_code}/members",
        headers={"X-Session-Key": team_lead_key},
        json=payload,
    )
    assert allowed_add.status_code == 200
    assert allowed_add.json()["data"]["system_role_key"] == "TEAM_LEAD"

    denied_remove = client.delete(
        f"/api/v1/projects/{project_code}/members/alex.carter@example.com",
        headers={"X-Session-Key": project_lead_key},
    )
    assert denied_remove.status_code == 403
    assert "Chỉ TEAM_LEAD" in denied_remove.json()["detail"]

    allowed_remove = client.delete(
        f"/api/v1/projects/{project_code}/members/alex.carter@example.com",
        headers={"X-Session-Key": team_lead_key},
    )
    assert allowed_remove.status_code == 200
    assert allowed_remove.json()["data"]["removed"] is True




