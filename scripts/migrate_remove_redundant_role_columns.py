"""Bỏ các cột role/task dư thừa khỏi PostgreSQL hiện có.

Chạy một lần trước khi triển khai phiên bản mới:
    python scripts/migrate_remove_redundant_role_columns.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.db import get_connection  # noqa: E402
from config.settings import get_settings  # noqa: E402


MIGRATION_STATEMENTS = (
    "DROP INDEX IF EXISTS idx_template_tasks_role",
    "ALTER TABLE onboarding_template_tasks DROP COLUMN IF EXISTS role_id",
    "ALTER TABLE onboarding_template_tasks DROP COLUMN IF EXISTS document_link",
    "ALTER TABLE roles DROP COLUMN IF EXISTS role_code",
    """
    CREATE OR REPLACE FUNCTION aibuddy_create_checklist_tasks()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        INSERT INTO user_checklists_tasks (checklist_id, template_task_id)
        SELECT NEW.checklist_id, task.template_task_id
        FROM onboarding_template_tasks task
        WHERE task.template_id = NEW.template_id
        ORDER BY task.sort_order, task.template_task_id
        ON CONFLICT (checklist_id, template_task_id) DO NOTHING;

        RETURN NEW;
    END;
    $$
    """,
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    settings = get_settings()
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        print("Migration này chỉ dành cho PostgreSQL.")
        return 1

    with get_connection(settings.database_url) as conn:
        for statement in MIGRATION_STATEMENTS:
            conn.execute(text(statement))

    print("Đã bỏ roles.role_code và onboarding_template_tasks.role_id/document_link.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
