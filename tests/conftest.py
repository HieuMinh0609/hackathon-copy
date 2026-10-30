import dataclasses
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from config.settings import get_settings
from backend.services.checklist_service import ChecklistService
import backend.services.db as db_module

TABLE_STATEMENTS_TEST_SQLITE = [
    """
    CREATE TABLE IF NOT EXISTS roles (
        role_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        role_name   TEXT NOT NULL UNIQUE,
        key_role    TEXT UNIQUE,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        email       TEXT NOT NULL UNIQUE,
        password    TEXT NOT NULL DEFAULT '81dc9bdb52d04dc20036dbd8313ed055',
        role_id     INTEGER REFERENCES roles(role_id),
        job_title   TEXT DEFAULT '',
        department  TEXT DEFAULT '',
        created_at  TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS people_directory (
        person_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        department    TEXT NOT NULL,
        position      TEXT NOT NULL,
        team_account  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS onboarding_template (
        template_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        template_code TEXT UNIQUE,
        template_name TEXT NOT NULL,
        version       INTEGER NOT NULL DEFAULT 1,
        is_active     INTEGER NOT NULL DEFAULT 1,
        duration_days INTEGER NOT NULL DEFAULT 20,
        document_link TEXT DEFAULT '',
        created_at    TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS onboarding_template_tasks (
        template_task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id      INTEGER REFERENCES onboarding_template(template_id),
        task_name        TEXT NOT NULL,
        category         TEXT NOT NULL,
        mandatory        INTEGER NOT NULL DEFAULT 1,
        owner_team       TEXT,
        instructions     TEXT,
        owner_person_id  INTEGER,
        sort_order       INTEGER NOT NULL DEFAULT 0,
        check_type       TEXT NOT NULL DEFAULT 'MANUAL',
        params           TEXT NOT NULL DEFAULT '{}',
        status           TEXT NOT NULL DEFAULT 'ACTIVE',
        updated_at       TEXT,
        UNIQUE (template_id, task_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_checklists (
        checklist_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER NOT NULL REFERENCES users(user_id),
        template_id    INTEGER NOT NULL REFERENCES onboarding_template(template_id),
        role_id        INTEGER REFERENCES roles(role_id),
        project_role_id INTEGER REFERENCES roles(role_id),
        status         TEXT NOT NULL DEFAULT 'NOT_STARTED',
        progress       INTEGER NOT NULL DEFAULT 0,
        started_at     TEXT,
        due_at         TEXT,
        created_at     TEXT DEFAULT '',
        updated_at     TEXT DEFAULT '',
        UNIQUE (user_id, template_id)
    )
    """,
    """
    INSERT OR IGNORE INTO roles (role_name, description) VALUES
    ('Member', 'Thành viên dự án'),
    ('Project Lead', 'Quản lý / Trưởng dự án, điều phối kế hoạch và tiến độ onboarding'),
    ('Team Lead', 'Trưởng nhóm, được quản lý template và thành viên của dự án được giao'),
    ('Tech Lead', 'Trưởng nhóm kỹ thuật, chịu trách nhiệm kiến trúc kỹ thuật và tiêu chuẩn mã nguồn'),
    ('Solution Architect', 'Kiến trúc sư giải pháp kỹ thuật và hệ thống phân tán'),
    ('Backend Developer', 'Lập trình viên Backend, xây dựng API và kiến trúc cơ sở dữ liệu'),
    ('Developer', 'Lập trình viên phát triển phần mềm'),
    ('Frontend Developer', 'Lập trình viên Frontend, thiết kế và tối ưu giao diện người dùng'),
    ('Fullstack Developer', 'Lập trình viên Fullstack, phát triển cả ứng dụng client và dịch vụ server'),
    ('Mobile Developer', 'Lập trình viên ứng dụng di động iOS/Android'),
    ('QA Lead', 'Trưởng nhóm kiểm thử chất lượng, chiến lược QA và phê duyệt release'),
    ('QA Engineer', 'Kỹ sư kiểm thử chất lượng, test case và automation testing'),
    ('Tester', 'Chuyên viên kiểm thử phần mềm thủ công (Manual Testing) và kiểm tra giao diện'),
    ('Business Analyst', 'Chuyên viên phân tích nghiệp vụ, làm rõ yêu cầu và tài liệu sản phẩm'),
    ('Product Owner', 'Chủ sản phẩm, định hình roadmap và quản lý backlog dự án'),
    ('Scrum Master', 'Điều phối viên Scrum, tối ưu quy trình Agile và loại bỏ rào cản đội ngũ'),
    ('DevOps Engineer', 'Kỹ sư DevOps, thiết lập CI/CD, vận hành hạ tầng cloud và containerization'),
    ('System Administrator', 'Quản trị viên hệ thống mạng, server và cấp phát tài nguyên'),
    ('Security Specialist', 'Chuyên viên an toàn thông tin, bảo mật mã nguồn và hệ thống'),
    ('Data Engineer', 'Kỹ sư dữ liệu, xây dựng pipeline ETL và kho dữ liệu phân tích'),
    ('AI Engineer', 'Kỹ sư AI/Machine Learning, tích hợp mô hình LLM và RAG'),
    ('UI/UX Designer', 'Chuyên viên thiết kế trải nghiệm và giao diện người dùng'),
    ('HR Specialist', 'Chuyên viên nhân sự và vận hành onboarding, hỗ trợ thủ tục gia nhập và chính sách công ty'),
    ('IT Support', 'Hỗ trợ kỹ thuật nội bộ, cài đặt thiết bị và cấp phát tài khoản')
    """,
    """
    UPDATE roles
    SET key_role = UPPER(REPLACE(REPLACE(role_name, '/', '_'), ' ', '_'))
    WHERE key_role IS NULL
    """,
    """
    DELETE FROM roles WHERE key_role NOT IN ('TEAM_LEAD', 'PROJECT_LEAD', 'MEMBER')
    """,
    """
    CREATE TABLE IF NOT EXISTS user_checklists_tasks (
        task_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        checklist_id     INTEGER NOT NULL REFERENCES user_checklists(checklist_id) ON DELETE CASCADE,
        template_task_id INTEGER NOT NULL REFERENCES onboarding_template_tasks(template_task_id),
        status           TEXT NOT NULL DEFAULT 'PENDING',
        completed_at     TEXT,
        note             TEXT,
        blocker_reason   TEXT,
        created_at       TEXT DEFAULT '',
        updated_at       TEXT DEFAULT '',
        UNIQUE (checklist_id, template_task_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_catalog (
        app_id              INTEGER PRIMARY KEY AUTOINCREMENT,
        app_code            TEXT NOT NULL UNIQUE,
        app_name            TEXT NOT NULL,
        category            TEXT NOT NULL DEFAULT 'Công cụ chung',
        recommended_version TEXT,
        installer_path      TEXT,
        check_command       TEXT NOT NULL DEFAULT '',
        version_args        TEXT NOT NULL DEFAULT '--version',
        install_args        TEXT DEFAULT '',
        description         TEXT,
        is_required         INTEGER NOT NULL DEFAULT 1,
        created_at          TEXT DEFAULT '',
        updated_at          TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email      TEXT NOT NULL,
        project_code    TEXT NOT NULL,
        sender          TEXT NOT NULL,
        message         TEXT NOT NULL,
        sources         TEXT DEFAULT '[]',
        metadata        TEXT DEFAULT '{}',
        created_at      TEXT DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_history_user_project ON chat_history (user_email, project_code, created_at)
    """,
]


@pytest.fixture(autouse=True)
def _patch_sqlite_for_tests(monkeypatch):
    """Fixture tự động cô lập SQLite cho unit test, giữ cho production db.py thuần túy PostgreSQL."""
    orig_get_engine = db_module.get_engine

    def test_get_engine(url: str):
        if url.startswith("sqlite"):
            with db_module._lock:
                engine = db_module._engines.get(url)
                if engine is None:
                    engine = create_engine(url, poolclass=NullPool)
                    db_module._engines[url] = engine
                return engine
        return orig_get_engine(url)

    def test_init_schema(url: str):
        if url.startswith("sqlite"):
            with db_module.get_connection(url) as conn:
                for stmt in TABLE_STATEMENTS_TEST_SQLITE:
                    conn.execute(text(stmt))
        else:
            db_module.init_schema(url)

    monkeypatch.setattr(db_module, "get_engine", test_get_engine)
    monkeypatch.setattr(db_module, "init_schema", test_init_schema)
    monkeypatch.setattr("backend.services.checklist_service.init_schema", test_init_schema)
    monkeypatch.setattr("backend.services.project_service.init_schema", test_init_schema)
    monkeypatch.setattr("backend.services.user_service.init_schema", test_init_schema)
    monkeypatch.setattr("backend.services.app_catalog_service.init_schema", test_init_schema)
    monkeypatch.setattr("backend.services.chat_history_service.init_schema", test_init_schema)



@pytest.fixture()
def settings(tmp_path: Path):
    """Settings trỏ data_dir vào thư mục tạm để test không đụng dữ liệu thật."""
    s = dataclasses.replace(
        get_settings(),
        data_dir=tmp_path,
        database_url_override=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    s.ensure_dirs()
    return s


@pytest.fixture()
def checklist(settings) -> ChecklistService:
    return ChecklistService(settings)
