"""Gỡ cột người hỗ trợ khỏi task checklist trên PostgreSQL hiện có.

Chạy một lần trước khi triển khai phiên bản mới:
    python scripts/migrate_remove_checklist_support_person.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.db import get_connection  # noqa: E402
from config.settings import get_settings  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    settings = get_settings()
    if make_url(settings.database_url).get_backend_name() != "postgresql":
        print("Migration này chỉ dành cho PostgreSQL.")
        return 1

    with get_connection(settings.database_url) as conn:
        conn.execute(
            text(
                """
                ALTER TABLE onboarding_template_tasks
                DROP COLUMN IF EXISTS support_user_id
                """
            )
        )

    print("Đã gỡ onboarding_template_tasks.support_user_id.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
