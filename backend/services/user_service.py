"""Quản lý tài khoản người dùng từ bảng 'users' trong PostgreSQL/SQLite."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any

from sqlalchemy import text

from config.settings import Settings
from backend.services.db import get_connection, init_schema

DEFAULT_PASSWORD_RAW = "1234"
DEFAULT_PASSWORD_MD5 = "81dc9bdb52d04dc20036dbd8313ed055"  # MD5 của "1234"

PERMISSION_TEAM_LEAD = "TEAM_LEAD"
PERMISSION_PROJECT_LEAD = "PROJECT_LEAD"
PERMISSION_MEMBER = "MEMBER"
VALID_PERMISSIONS = {PERMISSION_TEAM_LEAD, PERMISSION_PROJECT_LEAD, PERMISSION_MEMBER}

LEVEL_TEAM_LEAD = PERMISSION_TEAM_LEAD
LEVEL_PROJECT_LEAD = PERMISSION_PROJECT_LEAD
LEVEL_MEMBER = PERMISSION_MEMBER
VALID_LEVELS = {LEVEL_TEAM_LEAD, LEVEL_PROJECT_LEAD, LEVEL_MEMBER}
MANAGEMENT_LEVELS = {LEVEL_TEAM_LEAD, LEVEL_PROJECT_LEAD}

_TEMPLATE_MANAGER_LEVELS = {
    "PROJECT LEAD",
    "TEAM LEAD",
}


def is_template_manager_role(role_name: str | None) -> bool:
    """Chuẩn hóa cấp quyền template; không suy quyền từ role chuyên môn như Tech Lead/QA Lead."""
    if not role_name:
        return False
    normalized = role_name.strip().upper().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized in _TEMPLATE_MANAGER_LEVELS


def hash_password_md5(raw_password: str) -> str:
    """Mã hóa mật khẩu bằng thuật toán MD5."""
    return hashlib.md5(raw_password.encode("utf-8")).hexdigest()


def has_management_permission(permission_or_level: str | None) -> bool:
    """Kiểm tra quyền quản trị toàn cục hoặc vai trò quản lý template đã định danh rõ."""
    if not permission_or_level:
        return False
    return is_template_manager_role(permission_or_level.strip().upper())


def is_senior_or_above(permission_or_level: str | None) -> bool:
    """Alias tương thích ngược cho has_management_permission."""
    return has_management_permission(permission_or_level)


@dataclass
class User:
    user_id: int
    name: str
    email: str
    password: str = DEFAULT_PASSWORD_MD5
    role_id: int | None = None
    role_name: str = ""
    job_title: str = ""
    department: str = ""
    permission: str = PERMISSION_MEMBER
    created_at: str = ""

    @property
    def level(self) -> str:
        """Alias cho permission để tương thích ngược."""
        return self.permission

    @level.setter
    def level(self, val: str) -> None:
        clean = (val or "").strip().upper()
        self.permission = clean if clean in VALID_PERMISSIONS else PERMISSION_MEMBER

    @property
    def is_team_lead(self) -> bool:
        return (self.permission or "").strip().upper() == PERMISSION_TEAM_LEAD

    @property
    def is_project_lead(self) -> bool:
        return (self.permission or "").strip().upper() == PERMISSION_PROJECT_LEAD

    @property
    def is_template_manager(self) -> bool:
        return self.is_team_lead or self.is_project_lead

    @property
    def is_member(self) -> bool:
        return (self.permission or "").strip().upper() == PERMISSION_MEMBER

    @property
    def can_manage(self) -> bool:
        """Team Lead có quyền toàn cục; Project Lead quản lý dự án được giao."""
        return self.is_template_manager

    @property
    def is_senior(self) -> bool:
        return self.can_manage

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "role_id": self.role_id,
            "role_name": self.role_name,
            "job_title": self.job_title,
            "department": self.department,
            "permission": self.permission,
            "level": self.permission,
            "is_team_lead": self.is_team_lead,
            "is_project_lead": self.is_project_lead,
            "is_template_manager": self.is_template_manager,
            "can_manage": self.can_manage,
            "is_senior": self.is_senior,
            "created_at": self.created_at,
        }


DEFAULT_USERS = [
    {
        "name": "Alex Carter",
        "email": "alex.carter@example.com",
        "role_name": "Backend Developer",
        "department": "Engineering",
        "permission": PERMISSION_TEAM_LEAD,
    },
    {
        "name": "Mack Johnson",
        "email": "mack.johnson@example.com",
        "role_name": "QA Engineer",
        "department": "QA",
        "permission": PERMISSION_MEMBER,
    },
    {
        "name": "Mike Brown",
        "email": "mike.brown@example.com",
        "role_name": "Business Analyst",
        "department": "Product",
        "permission": PERMISSION_MEMBER,
    },
    {
        "name": "Emma Wilson",
        "email": "emma.wilson@example.com",
        "role_name": "Backend Developer",
        "department": "Engineering",
        "permission": PERMISSION_MEMBER,
    },
    {
        "name": "Sophia Davis",
        "email": "sophia.davis@example.com",
        "role_name": "QA Engineer",
        "department": "QA",
        "permission": PERMISSION_MEMBER,
    },
    {
        "name": "Daniel Miller",
        "email": "daniel.miller@example.com",
        "role_name": "Business Analyst",
        "department": "Product",
        "permission": PERMISSION_MEMBER,
    },
]


class UserService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        init_schema(settings.database_url)
        self.seed_defaults()

    @property
    def _url(self) -> str:
        return self.settings.database_url

    def seed_defaults(self) -> int:
        now = datetime.now().isoformat()
        inserted = 0
        with get_connection(self._url) as conn:
            roles_map: dict[str, int] = {}
            try:
                for r in conn.execute(text("SELECT role_id, role_name FROM roles")).all():
                    roles_map[r[1].strip().lower()] = r[0]
            except Exception:
                pass

            for u in DEFAULT_USERS:
                perm_val = u["permission"]
                role_id = roles_map.get("team lead" if perm_val == PERMISSION_TEAM_LEAD else "member")
                # Quyền hệ thống được tham chiếu bằng role key, không lưu chuỗi rời trên user.
                conn.execute(
                    text(
                        """
                        INSERT INTO users (name, email, password, role_id, job_title, department, created_at)
                        VALUES (:name, :email, :password, :role_id, :job_title, :department, :created_at)
                        ON CONFLICT (email) DO UPDATE SET
                            name = excluded.name,
                            password = COALESCE(users.password, excluded.password),
                            role_id = COALESCE(excluded.role_id, users.role_id),
                            job_title = COALESCE(NULLIF(users.job_title, ''), excluded.job_title),
                            department = excluded.department
                        """
                    ),
                    {
                        "name": u["name"],
                        "email": u["email"].strip().lower(),
                        "password": DEFAULT_PASSWORD_MD5,
                        "role_id": role_id,
                        "job_title": u["role_name"],
                        "department": u["department"],
                        "created_at": now,
                    },
                )
                inserted += 1

        return inserted

    def get_by_email(self, email: str) -> User | None:
        clean_email = email.strip().lower()
        with get_connection(self._url) as conn:
            sql = """
                SELECT u.user_id, u.name, u.email,
                       COALESCE(u.password, '81dc9bdb52d04dc20036dbd8313ed055') as password,
                       u.role_id, u.job_title, u.department,
                       COALESCE(r.key_role, 'MEMBER') as permission,
                       u.created_at,
                       COALESCE(r.role_name, '') as role_name
                FROM users u
                LEFT JOIN roles r ON r.role_id = u.role_id
                WHERE LOWER(u.email) = :email
            """
            row = conn.execute(text(sql), {"email": clean_email}).mappings().first()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                name=row["name"],
                email=row["email"],
                password=str(row["password"]),
                role_id=row["role_id"],
                role_name=row["role_name"],
                job_title=row["job_title"] or "",
                department=row["department"],
                permission=row["permission"] or PERMISSION_MEMBER,
                created_at=str(row["created_at"]),
            )

    def list_users(self) -> list[User]:
        with get_connection(self._url) as conn:
            sql = """
                SELECT u.user_id, u.name, u.email,
                       COALESCE(u.password, '81dc9bdb52d04dc20036dbd8313ed055') as password,
                       u.role_id, u.job_title, u.department,
                       COALESCE(r.key_role, 'MEMBER') as permission,
                       u.created_at,
                       COALESCE(r.role_name, '') as role_name
                FROM users u
                LEFT JOIN roles r ON r.role_id = u.role_id
                ORDER BY u.user_id
            """
            rows = conn.execute(text(sql)).mappings().all()
            return [
                User(
                    user_id=row["user_id"],
                    name=row["name"],
                    email=row["email"],
                    password=str(row["password"]),
                    role_id=row["role_id"],
                    role_name=row["role_name"],
                    job_title=row["job_title"] or "",
                    department=row["department"],
                    permission=row["permission"] or PERMISSION_MEMBER,
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]

    def authenticate(self, email: str, raw_password: str | None = None) -> User | None:
        """Xác thực người dùng qua email và mật khẩu (MD5). Nếu raw_password là None, trả về User nếu tồn tại."""
        user = self.get_by_email(email)
        if not user:
            return None
        if raw_password is not None and raw_password != "":
            if hash_password_md5(raw_password) != user.password:
                return None
        return user

    def update_password(self, email: str, new_password_raw: str) -> bool:
        """Cập nhật mật khẩu mới (mã hóa MD5) cho người dùng."""
        hashed = hash_password_md5(new_password_raw)
        with get_connection(self._url) as conn:
            res = conn.execute(
                text("UPDATE users SET password = :pwd WHERE LOWER(email) = :email"),
                {"pwd": hashed, "email": email.strip().lower()},
            )
            return res.rowcount > 0
