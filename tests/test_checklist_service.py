import socket

import pytest

from backend.services.verification_service import VerificationService


def test_seed_and_progress(checklist):
    items = checklist.list_items()
    assert len(items) >= 15
    prog = checklist.progress()
    assert prog["percent"] == 0 and prog["pending"] == prog["total"]
    assert "Training dự án" in checklist.categories()


def test_seed_is_idempotent_and_keeps_status(checklist):
    checklist.update_status("train_goal", "passed", "ok")
    checklist.seed_defaults()
    assert checklist.get_item("train_goal").status == "passed"


def test_manual_toggle_and_invalid_status(checklist):
    checklist.set_manual_done("train_rules", True)
    assert checklist.get_item("train_rules").status == "passed"
    checklist.set_manual_done("train_rules", False)
    assert checklist.get_item("train_rules").status in ("pending", "ACTIVE")
    with pytest.raises(ValueError):
        checklist.update_status("train_rules", "bogus")
    with pytest.raises(KeyError):
        checklist.update_status("missing", "passed")


def test_export_report(checklist):
    checklist.set_manual_done("train_goal", True)
    path = checklist.export_report()
    text = path.read_text(encoding="utf-8")
    assert path.exists() and "Báo cáo checklist" in text and "✅" in text


def test_verify_port_free_and_busy(checklist):
    ver = VerificationService(checklist)
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    busy_port = server.getsockname()[1]
    item = checklist.get_item("port_8000")
    item.params["port"] = busy_port
    try:
        res = ver.verify_item(item)
        assert res.status == "failed"  # port_8000 là required
    finally:
        server.close()
    assert ver.verify_item(item).status == "passed"


def test_optional_failure_is_warning(checklist):
    ver = VerificationService(checklist)
    item = checklist.get_item("net_git_server")  # required: false
    item.params.update(host="127.0.0.1", port=1)  # port 1 chắc chắn đóng
    assert ver.verify_item(item).status == "warning"
    assert checklist.get_item("net_git_server").status == "warning"


def test_manual_items_are_not_overwritten_by_verify(checklist):
    ver = VerificationService(checklist)
    checklist.set_manual_done("train_goal", True)
    assert ver.verify_item(checklist.get_item("train_goal")).status == "passed"


def test_update_user_task_status(checklist):
    # Test cập nhật task cho user_id = 1
    res = checklist.update_user_task_status(user_id=1, key="app_python", done=True)
    assert res["status"] == "ok"
    assert res["done"] is True
    assert res["task_status"] == "COMPLETED"
    assert res["checklist_progress"] > 0

    # Bỏ tick
    res2 = checklist.update_user_task_status(user_id=1, key="app_python", done=False)
    assert res2["status"] == "ok"
    assert res2["done"] is False
    assert res2["task_status"] == "PENDING"


def test_user_is_marked_completed_after_all_assigned_tasks_pass(checklist):
    """Checklist của member phải chuyển COMPLETED đúng tại bước cuối cùng."""
    from sqlalchemy import text

    from backend.services.db import get_connection
    from backend.services.project_service import ProjectService

    ProjectService(checklist.settings).add_project_member(
        project_code="PRJ_ECOMMERCE",
        user_email="emma.wilson@example.com",
    )

    with get_connection(checklist.settings.database_url) as conn:
        assigned = conn.execute(
            text(
                """
                SELECT uc.checklist_id, uc.user_id, uct.template_task_id
                FROM user_checklists uc
                JOIN user_checklists_tasks uct ON uct.checklist_id = uc.checklist_id
                JOIN users u ON u.user_id = uc.user_id
                WHERE LOWER(u.email) = :email
                ORDER BY uc.checklist_id, uct.template_task_id
                """
            ),
            {"email": "emma.wilson@example.com"},
        ).mappings().all()

    assert assigned
    checklist_id = assigned[0]["checklist_id"]
    user_id = assigned[0]["user_id"]
    task_ids = [row["template_task_id"] for row in assigned if row["checklist_id"] == checklist_id]

    for index, task_id in enumerate(task_ids):
        result = checklist.update_user_task_status(
            user_id=user_id,
            key=f"task_{task_id}",
            done=True,
            sync_template_status=False,
        )
        expected_status = "COMPLETED" if index == len(task_ids) - 1 else "IN_PROGRESS"
        assert result["checklist_status"] == expected_status

    with get_connection(checklist.settings.database_url) as conn:
        saved = conn.execute(
            text("SELECT status, progress FROM user_checklists WHERE checklist_id = :checklist_id"),
            {"checklist_id": checklist_id},
        ).mappings().one()
    assert saved["status"] == "COMPLETED"
    assert saved["progress"] == 100


def test_member_checklist_status_is_isolated_per_user(checklist):
    """Một member hoàn thành không được làm checklist của member khác thành passed."""
    from sqlalchemy import text

    from backend.services.db import get_connection
    from backend.services.project_service import ProjectService

    projects = ProjectService(checklist.settings)
    projects.add_project_member("PRJ_ECOMMERCE", "emma.wilson@example.com")
    projects.add_project_member("PRJ_ECOMMERCE", "mack.johnson@example.com")
    first_item = checklist.list_items(template_code="PRJ_ECOMMERCE")[0]
    with get_connection(checklist.settings.database_url) as conn:
        emma_user_id = conn.execute(
            text("SELECT user_id FROM users WHERE LOWER(email) = :email"),
            {"email": "emma.wilson@example.com"},
        ).scalar_one()

    checklist.update_user_task_status(
        user_id=emma_user_id,
        key=first_item.key,
        done=True,
    )

    emma_item = checklist.list_items(
        template_code="PRJ_ECOMMERCE",
        user_email="emma.wilson@example.com",
    )[0]
    mack_item = checklist.list_items(
        template_code="PRJ_ECOMMERCE",
        user_email="mack.johnson@example.com",
    )[0]
    assert emma_item.status == "passed"
    assert mack_item.status == "ACTIVE"


def test_get_sample_template_csv(checklist):
    csv_text = checklist.get_sample_template_csv()
    assert csv_text.startswith("\ufeff")  # Chứa BOM UTF-8
    assert "task_name,category,check_type,mandatory,owner_team,instructions,params,sort_order" in csv_text
    assert "support_person" not in csv_text
    assert "Cài đặt Git" in csv_text
    assert "role_code" not in csv_text
    assert "SOFTWARE" in csv_text
    assert "HOST_REACHABLE" in csv_text
    assert "PORT_FREE" in csv_text
    assert "MANUAL" in csv_text


def test_schema_uses_single_role_key_and_shared_template_tasks(checklist):
    from sqlalchemy import text

    from backend.services.db import get_connection

    with get_connection(checklist.settings.database_url) as conn:
        role_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(roles)"))
        }
        task_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(onboarding_template_tasks)"))
        }

    assert "key_role" in role_columns
    assert "role_code" not in role_columns
    assert "role_id" not in task_columns
    assert "document_link" not in task_columns
    assert "support_user_id" not in task_columns


def test_import_tasks_from_csv(checklist):
    csv_content = """task_name,category,check_type,mandatory,owner_team,instructions,params,sort_order
Kiểm tra Redis Cache,Mạng nội bộ,HOST_REACHABLE,true,DevOps,Kiểm tra redis server,"{""host"": ""127.0.0.1"", ""port"": 6379}",101
Cài đặt Rust Toolchain,Môi trường,SOFTWARE,false,DevOps,Cài đặt Rust mới nhất,"{""command"": ""rustc --version""}",102
Đọc tài liệu Security,Tài liệu,MANUAL,true,Security Lead,Đọc chính sách bảo mật nội bộ,{},103
"""
    # Khởi tạo user_checklists trước để kiểm tra auto-sync
    checklist.update_user_task_status(user_id=1, key="app_python", done=True, template_code="PRJ_TEST_IMPORT")

    res = checklist.import_tasks_from_csv(csv_content, project_code="PRJ_TEST_IMPORT")
    assert res["status"] == "ok"
    assert res["imported_count"] == 3
    assert "Kiểm tra Redis Cache" in res["task_names"]

    # Kiểm tra đã lưu vào onboarding_template_tasks
    item = checklist.get_item("Kiểm tra Redis Cache")
    assert item is not None
    assert item.title == "Kiểm tra Redis Cache"
    assert item.check_type == "HOST_REACHABLE"
    assert item.params.get("port") == 6379

    # Kiểm tra idempotency (chạy lại không lỗi)
    res_again = checklist.import_tasks_from_csv(csv_content, project_code="PRJ_TEST_IMPORT")
    assert res_again["imported_count"] == 3


def test_import_tasks_from_csv_ignores_legacy_role_code(checklist):
    from sqlalchemy import text
    from backend.services.db import get_connection

    csv_content = """task_name,category,role_code,check_type,mandatory,owner_team,instructions,params,sort_order
Cài đặt Java JDK 21,Môi trường,MEMBER,SOFTWARE,true,Backend Team,Cài JDK 21,"{""command"": ""java -version""}",1
Kiểm tra Cypress Test,Kiểm thử,PROJECT_LEAD,SOFTWARE,true,QA Team,Cài Cypress,"{""command"": ""cypress -v""}",2
Đọc cẩm nang chung,Văn hóa,,MANUAL,true,HR,Đọc quy tắc văn hóa,{},3
"""
    res = checklist.import_tasks_from_csv(csv_content, project_code="PRJ_TEST_ROLE_CODE")
    assert res["status"] == "ok"
    assert res["imported_count"] == 3

    with get_connection(checklist.settings.database_url) as conn:
        rows = conn.execute(
            text("""
                SELECT ott.task_name
                FROM onboarding_template_tasks ott
                JOIN onboarding_template ot ON ot.template_id = ott.template_id
                WHERE ot.template_code = 'PRJ_TEST_ROLE_CODE'
                ORDER BY ott.sort_order ASC
            """)
        ).mappings().all()

        assert len(rows) == 3
        assert rows[0]["task_name"] == "Cài đặt Java JDK 21"
        assert rows[1]["task_name"] == "Kiểm tra Cypress Test"
        assert rows[2]["task_name"] == "Đọc cẩm nang chung"



def test_import_replaces_old_checklist_for_project(checklist):
    # 1. Nhập lần đầu: 2 tasks
    csv_old = """task_name,category,check_type,mandatory,owner_team,instructions,params,sort_order
Old Task 1,Môi trường,MANUAL,true,DevOps,Old instruction 1,{},1
Old Task 2,Môi trường,MANUAL,true,DevOps,Old instruction 2,{},2
"""
    checklist.import_tasks_from_csv(csv_old, project_code="PRJ_REPLACE_DEMO")
    items_before = checklist.list_items(template_code="PRJ_REPLACE_DEMO")
    assert len(items_before) == 2
    assert {i.title for i in items_before} == {"Old Task 1", "Old Task 2"}

    # 2. Nhập file mới: chỉ có 1 task mới -> Thay thế hoàn toàn checklist cũ
    csv_new = """task_name,category,check_type,mandatory,owner_team,instructions,params,sort_order
New Single Task,Môi trường,SOFTWARE,true,DevOps,New instruction,"{""name"": ""git"", ""command"": [""git"", ""--version""]}",1
"""
    res = checklist.import_tasks_from_csv(csv_new, project_code="PRJ_REPLACE_DEMO")
    assert res["imported_count"] == 1

    items_after = checklist.list_items(template_code="PRJ_REPLACE_DEMO")
    assert len(items_after) == 1
    assert items_after[0].title == "New Single Task"
    assert checklist.get_item("Old Task 1") is None

    # Tiến độ cũng tính đúng theo project mới
    prog = checklist.progress(template_code="PRJ_REPLACE_DEMO")
    assert prog["total"] == 1




def test_verify_legacy_software_command(checklist, monkeypatch):
    from backend.core.utils import system_utils
    item = checklist.get_item("app_git")
    item.params = {"command": "git --version"}
    calls = []
    def check(name, command, args, minimum):
        calls.append((command, args))
        return system_utils.SoftwareStatus(name, command, True, version="2.43", meets_min=True)
    monkeypatch.setattr(system_utils, "check_software", check)
    result = VerificationService(checklist).verify_item(item)
    assert result.status == "passed"
    assert calls == [("git", ["--version"])]


def test_wifi_type_import_and_verification(checklist, monkeypatch):
    from backend.core.utils import network_utils
    checklist.import_tasks_from_csv('[{"title":"Wi-Fi", "check_type":"WIFI", "required":false}]', "TEST_WIFI")
    item = checklist.list_items(template_code="TEST_WIFI")[0]
    assert item.check_type == "WIFI"
    monkeypatch.setattr(network_utils, "check_wifi", lambda: (False, "Chưa kết nối Wi-Fi"))
    assert VerificationService(checklist).verify_item(item).status == "warning"
    monkeypatch.setattr(network_utils, "check_wifi", lambda: (True, "Wi-Fi đã kết nối"))
    assert VerificationService(checklist).verify_item(item).status == "passed"


def test_step_blocker_uses_template_order_and_completion(checklist):
    checklist.import_tasks_from_csv('[{"title":"First", "check_type":"MANUAL"}, {"title":"Second", "check_type":"WIFI"}]', "SEQUENCE")
    items = checklist.list_items(template_code="SEQUENCE")
    first, second = items
    assert checklist.step_blocker(first.key) is None
    assert "bước 1" in checklist.step_blocker(second.key)
    checklist.update_status(first.key, "warning")
    assert checklist.step_blocker(second.key)
    checklist.update_status(first.key, "passed")
    assert checklist.step_blocker(second.key) is None
    checklist.update_status(first.key, "ACTIVE")
    assert checklist.step_blocker(second.key)


def test_import_tasks_are_shared_by_all_project_members(checklist):
    from backend.services.project_service import ProjectService
    from backend.services.user_service import UserService
    # Khởi tạo users để có sẵn các user mẫu và roles
    UserService(checklist.settings)

    csv_data = """task_name,category,role,check_type,mandatory,owner_team,instructions,params,sort_order
Setup Python & Poetry,Môi trường,MEMBER,SOFTWARE,true,DevOps,Cài python,"{""command"": ""python --version""}",1
Setup Playwright & Cypress,Môi trường,PROJECT_LEAD,SOFTWARE,true,QA Lead,Cài playwright,"{""command"": ""playwright --version""}",2
Đọc tài liệu chung,Tài liệu,,MANUAL,true,HR,Nội quy công ty,{},3
"""
    res = checklist.import_tasks_from_csv(csv_data, project_code="PRJ_ROLE_TEST")
    assert res["status"] == "ok"
    assert res["imported_count"] == 3
    projects = ProjectService(checklist.settings)
    projects.add_project_member("PRJ_ROLE_TEST", "alex.carter@example.com", project_role_key="MEMBER")
    projects.add_project_member("PRJ_ROLE_TEST", "mack.johnson@example.com", project_role_key="PROJECT_LEAD")

    # 1. Kiểm tra list_items không truyền user: trả về đủ cả 3 task
    all_items = checklist.list_items(template_code="PRJ_ROLE_TEST")
    assert len(all_items) == 3
    # Quyền dự án không lọc task; mọi thành viên nhận cùng checklist mẫu.
    be_user_items = checklist.list_items(template_code="PRJ_ROLE_TEST", user_email="alex.carter@example.com")
    be_titles = [i.title for i in be_user_items]
    assert "Setup Python & Poetry" in be_titles
    assert "Đọc tài liệu chung" in be_titles
    assert "Setup Playwright & Cypress" in be_titles
    assert len(be_user_items) == 3

    qa_user_items = checklist.list_items(template_code="PRJ_ROLE_TEST", user_email="mack.johnson@example.com")
    qa_titles = [i.title for i in qa_user_items]
    assert "Setup Playwright & Cypress" in qa_titles
    assert "Đọc tài liệu chung" in qa_titles
    assert "Setup Python & Poetry" in qa_titles
    assert len(qa_user_items) == 3

    # Progress cũng tính trên toàn bộ checklist mẫu.
    be_prog = checklist.progress(template_code="PRJ_ROLE_TEST", user_email="alex.carter@example.com")
    assert be_prog["total"] == 3

