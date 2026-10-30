"""Khởi tạo database PostgreSQL và nạp checklist mặc định.

Chạy:
    python scripts/init_database.py          # tạo bảng + seed
    python scripts/init_database.py --check  # chỉ kiểm tra kết nối
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings  # noqa: E402
from backend.services.checklist_service import ChecklistService  # noqa: E402
from backend.services.db import check_connection  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Khởi tạo database AI Buddy")
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra kết nối, không tạo bảng")
    args = parser.parse_args()

    settings = get_settings()
    ok, message = check_connection(settings.database_url)
    print(("✅ " if ok else "❌ ") + message)
    if not ok:
        if settings.uses_postgres:
            print("Gợi ý: kiểm tra POSTGRES_* trong .env, Postgres đã chạy chưa (docker compose up -d db), firewall/VPN.")
        return 1
    if args.check:
        return 0

    svc = ChecklistService(settings)
    print(f"Checklist items: {len(svc.list_items())}")

    from backend.services.project_service import ProjectService
    proj_svc = ProjectService(settings)
    print(f"Projects seeded in database: {len(proj_svc.list_projects())}")

    from backend.services.user_service import UserService
    user_svc = UserService(settings)
    print(f"Users seeded in database: {len(user_svc.list_users())} (Mật khẩu mặc định: 1234 - MD5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
