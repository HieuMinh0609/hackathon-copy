"""Quản lý Onboarding Template và Thư mục tài liệu (document_link) từ bảng onboarding_template."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
import re
import shutil
from typing import Any

from sqlalchemy import text

from config.settings import Settings
from backend.services.db import get_connection, init_schema
from backend.services.user_service import (
    PERMISSION_MEMBER,
    PERMISSION_PROJECT_LEAD,
    PERMISSION_TEAM_LEAD,
    has_management_permission,
)

_PROJECT_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

# Tên cũ chỉ được chấp nhận ở biên API để dữ liệu lưu trữ luôn dùng một tên chuẩn.
_ROLE_NAME_ALIASES = {
    "devops": "DevOps Engineer",
    "hr": "HR Specialist",
}


def canonicalize_role_name(role_name: str) -> str:
    """Chuẩn hóa alias role nhưng giữ nguyên tên canonical do bảng `roles` quản lý."""
    clean_name = " ".join((role_name or "").strip().split())
    return _ROLE_NAME_ALIASES.get(clean_name.casefold(), clean_name)


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _deadline_metadata(
    started_at: Any,
    due_at: Any,
    duration_days: int,
    checklist_status: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Tính trạng thái hạn từ mốc đã đóng băng của member, không phụ thuộc thời lượng mới."""
    started = _as_datetime(started_at)
    due = _as_datetime(due_at)
    if due is None and started is not None:
        due = started + timedelta(days=duration_days)
    if started is None or due is None:
        return {
            "started_at": "",
            "due_at": "",
            "days_remaining": None,
            "deadline_status": "not_started",
        }

    reference = now
    if reference is None:
        reference = datetime.now(tz=due.tzinfo) if due.tzinfo else datetime.now()
    elif due.tzinfo and reference.tzinfo is None:
        reference = reference.replace(tzinfo=due.tzinfo)
    elif not due.tzinfo and reference.tzinfo:
        reference = reference.replace(tzinfo=None)

    seconds_remaining = (due - reference).total_seconds()
    days_remaining = math.ceil(seconds_remaining / 86400)
    status = checklist_status.strip().upper()
    if status == "COMPLETED":
        deadline_status = "completed"
    elif seconds_remaining < 0:
        deadline_status = "overdue"
    else:
        deadline_status = "active"
    return {
        "started_at": started.isoformat(),
        "due_at": due.isoformat(),
        "days_remaining": days_remaining,
        "deadline_status": deadline_status,
    }


def _risk_metadata(
    started_at: Any,
    due_at: Any,
    duration_days: int,
    checklist_status: str = "",
    progress: Any = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Phát hiện nguy cơ theo hạn và độ lệch giữa tiến độ thực tế/kỳ vọng."""
    deadline = _deadline_metadata(
        started_at,
        due_at,
        duration_days,
        checklist_status,
        now=now,
    )
    try:
        actual_progress = max(0, min(100, int(progress or 0)))
    except (TypeError, ValueError):
        actual_progress = 0

    if deadline["deadline_status"] == "completed":
        return {"risk_status": "completed", "risk_reason": "Đã hoàn thành", "expected_progress": 100}
    if deadline["deadline_status"] == "overdue":
        return {"risk_status": "overdue", "risk_reason": "Đã quá hạn onboarding", "expected_progress": 100}

    started = _as_datetime(deadline["started_at"])
    due = _as_datetime(deadline["due_at"])
    if started is None or due is None:
        return {"risk_status": "not_started", "risk_reason": "Chưa bắt đầu tính thời hạn", "expected_progress": 0}

    reference = now
    if reference is None:
        reference = datetime.now(tz=due.tzinfo) if due.tzinfo else datetime.now()
    elif due.tzinfo and reference.tzinfo is None:
        reference = reference.replace(tzinfo=due.tzinfo)
    elif not due.tzinfo and reference.tzinfo:
        reference = reference.replace(tzinfo=None)

    total_seconds = max(1.0, (due - started).total_seconds())
    elapsed_ratio = max(0.0, min(1.0, (reference - started).total_seconds() / total_seconds))
    expected_progress = int(round(elapsed_ratio * 100))
    days_remaining = deadline["days_remaining"]

    if days_remaining is not None and int(days_remaining) <= 3 and actual_progress < 100:
        reason = f"Chỉ còn {max(0, int(days_remaining))} ngày, tiến độ {actual_progress}%"
        return {"risk_status": "at_risk", "risk_reason": reason, "expected_progress": expected_progress}

    progress_gap = expected_progress - actual_progress
    if elapsed_ratio >= 0.2 and progress_gap >= 20:
        reason = f"Tiến độ {actual_progress}%, thấp hơn mức kỳ vọng {expected_progress}%"
        return {"risk_status": "at_risk", "risk_reason": reason, "expected_progress": expected_progress}

    return {"risk_status": "on_track", "risk_reason": "Đang đúng tiến độ", "expected_progress": expected_progress}


@dataclass
class OnboardingTemplate:
    template_code: str
    template_name: str
    document_link: str = ""
    template_id: int | None = None
    version: int = 1
    is_active: bool = True
    duration_days: int = 20
    created_at: str = ""

    # Thuộc tính tương thích ngược cho các màn hình/service gọi theo Project
    @property
    def code(self) -> str:
        return self.template_code

    @property
    def name(self) -> str:
        return self.template_name

    @property
    def doc_folder(self) -> str:
        return self.document_link

    @property
    def description(self) -> str:
        return ""


# Alias tương thích ngược
Project = OnboardingTemplate


DEFAULT_TEMPLATES = [
    {
        "template_code": "PRJ_ECOMMERCE",
        "template_name": "Hệ thống Microservices E-commerce",
        "role_name": "Backend Developer",
        "document_link": "documents/projects/PRJ_ECOMMERCE",
        "description": "Bảo trì và phát triển module thanh toán mới.",
        "code": "PRJ_ECOMMERCE",
        "name": "Hệ thống Microservices E-commerce",
        "doc_folder": "documents/projects/PRJ_ECOMMERCE",
    },
    {
        "template_code": "PRJ_AI_BUDDY",
        "template_name": "Ứng dụng AI nội bộ",
        "role_name": "QA Engineer",
        "document_link": "documents/projects/PRJ_AI_BUDDY",
        "description": "Tích hợp mô hình ngôn ngữ lớn (LLMs).",
        "code": "PRJ_AI_BUDDY",
        "name": "Ứng dụng AI nội bộ",
        "doc_folder": "documents/projects/PRJ_AI_BUDDY",
    },
    {
        "template_code": "PRJ_WAREHOUSE",
        "template_name": "App Quản lý Kho",
        "role_name": "Business Analyst",
        "document_link": "documents/projects/PRJ_WAREHOUSE",
        "description": "Fix bugs UI và tối ưu hóa API call.",
        "code": "PRJ_WAREHOUSE",
        "name": "App Quản lý Kho",
        "doc_folder": "documents/projects/PRJ_WAREHOUSE",
    },
]

# Alias tương thích ngược
DEFAULT_PROJECTS = DEFAULT_TEMPLATES


DEFAULT_PROJECT_MEMBERS = [
    # PRJ_ECOMMERCE
    {"project_code": "PRJ_ECOMMERCE", "user_email": "alex.carter@example.com", "role_in_project": "Tech Lead", "user_name": "Alex Carter", "department": "Engineering"},
    {"project_code": "PRJ_ECOMMERCE", "user_email": "emma.wilson@example.com", "role_in_project": "Backend Developer", "user_name": "Emma Wilson", "department": "Engineering"},
    {"project_code": "PRJ_ECOMMERCE", "user_email": "mack.johnson@example.com", "role_in_project": "QA Lead", "project_role_key": "PROJECT_LEAD", "user_name": "Mack Johnson", "department": "QA"},
    # PRJ_AI_BUDDY
    {"project_code": "PRJ_AI_BUDDY", "user_email": "alex.carter@example.com", "role_in_project": "Tech Lead", "user_name": "Alex Carter", "department": "Engineering"},
    {"project_code": "PRJ_AI_BUDDY", "user_email": "mack.johnson@example.com", "role_in_project": "QA Engineer", "project_role_key": "MEMBER", "user_name": "Mack Johnson", "department": "QA"},
    {"project_code": "PRJ_AI_BUDDY", "user_email": "sophia.davis@example.com", "role_in_project": "QA Engineer", "user_name": "Sophia Davis", "department": "QA"},
    # PRJ_WAREHOUSE
    {"project_code": "PRJ_WAREHOUSE", "user_email": "mike.brown@example.com", "role_in_project": "Business Analyst", "project_role_key": "PROJECT_LEAD", "user_name": "Mike Brown", "department": "Product"},
    {"project_code": "PRJ_WAREHOUSE", "user_email": "daniel.miller@example.com", "role_in_project": "Business Analyst", "user_name": "Daniel Miller", "department": "Product"},
    {"project_code": "PRJ_WAREHOUSE", "user_email": "emma.wilson@example.com", "role_in_project": "Fullstack Developer", "user_name": "Emma Wilson", "department": "Engineering"},
]


class ProjectService:
    """Quản lý dự án và assignment user-project trong ``user_checklists``."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        init_schema(settings.database_url)
        # Chuẩn hóa link trước và sau seed để mọi project luôn dùng đúng thư mục riêng.
        self._normalize_document_links()
        self.seed_defaults()
        self._normalize_document_links()

    @property
    def _url(self) -> str:
        return self.settings.database_url

    def seed_defaults(self) -> int:
        """Seed danh sách onboarding template mặc định và thành viên dự án nếu chưa tồn tại trong database."""
        now = datetime.now().isoformat()
        inserted = 0
        with get_connection(self._url) as conn:
            for t in DEFAULT_TEMPLATES:
                conn.execute(
                    text(
                        """
                        INSERT INTO onboarding_template (template_code, template_name, document_link, created_at)
                        VALUES (:template_code, :template_name, :document_link, :created_at)
                        ON CONFLICT (template_code) DO UPDATE SET
                            template_name = excluded.template_name,
                            document_link = excluded.document_link
                        """
                    ),
                    {
                        "template_code": t["template_code"],
                        "template_name": t["template_name"],
                        "document_link": t["document_link"],
                        "created_at": now,
                    },
                )
                inserted += 1

            # Seed project members via user_checklists
            try:
                for pm in DEFAULT_PROJECT_MEMBERS:
                    self._ensure_user_checklist_member(
                        conn,
                        project_code=pm["project_code"],
                        user_email=pm["user_email"],
                        user_name=pm["user_name"],
                        role_in_project=pm["role_in_project"],
                        department=pm["department"],
                        project_role_key=pm.get("project_role_key", "MEMBER"),
                        now=now,
                    )
            except Exception:
                pass
        return inserted

    def _canonical_doc_folder(self, code: str) -> Path:
        """Mỗi project chỉ được ghi trong documents/projects/<project_code>."""
        normalized = code.strip()
        if not _PROJECT_CODE_RE.fullmatch(normalized):
            raise ValueError(f"Mã dự án không hợp lệ: {code!r}")
        return self.settings.documents_dir / "projects" / normalized

    def _canonical_document_link(self, code: str) -> str:
        folder = self._canonical_doc_folder(code)
        try:
            return folder.relative_to(self.settings.base_dir).as_posix()
        except ValueError:
            return folder.as_posix()

    def _normalize_document_links(self) -> None:
        """Đưa document_link về thư mục chuẩn dựa trên project code."""
        with get_connection(self._url) as conn:
            rows = conn.execute(
                text("SELECT template_code, document_link FROM onboarding_template")
            ).mappings().all()
            for row in rows:
                code = row["template_code"]
                if not code or not _PROJECT_CODE_RE.fullmatch(str(code).strip()):
                    continue
                self._migrate_legacy_documents(str(code), str(row["document_link"] or ""))
                conn.execute(
                    text("UPDATE onboarding_template SET document_link=:document_link WHERE template_code=:code"),
                    {"code": code, "document_link": self._canonical_document_link(str(code))},
                )

    def _migrate_legacy_documents(self, code: str, old_link: str) -> None:
        """Copy tài liệu cũ sang folder project; không xóa nguồn và không ghi đè file đích."""
        target_root = self._canonical_doc_folder(code)
        target_root.mkdir(parents=True, exist_ok=True)
        if not old_link.strip():
            return
        source_root = Path(old_link.strip())
        if not source_root.is_absolute():
            source_root = self.settings.base_dir / source_root
        if not source_root.is_dir() or source_root.resolve() == target_root.resolve():
            return

        supported = {".pdf", ".docx", ".md", ".txt"}
        for source in list(source_root.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in supported:
                continue
            if source.resolve().is_relative_to(target_root.resolve()):
                continue
            destination = target_root / source.relative_to(source_root)
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def is_user_project_lead(self, user_email: str, project_code: str | None = None) -> bool:
        """Kiểm tra role hệ thống và role riêng của user trong từng dự án."""
        clean_email = (user_email or "").strip().lower()
        if not clean_email:
            return False
        with get_connection(self._url) as conn:
            user_row = conn.execute(
                text(
                    """
                    SELECT COALESCE(system_role.key_role, 'MEMBER') AS access_key
                    FROM users u
                    LEFT JOIN roles system_role ON system_role.role_id = u.role_id
                    WHERE LOWER(u.email) = :email
                    """
                ),
                {"email": clean_email},
            ).mappings().first()
            if not user_row:
                return False
            access_key = str(user_row["access_key"] or "MEMBER").strip().upper()
            if access_key == PERMISSION_TEAM_LEAD:
                return True
            if not project_code:
                return False
            clean_project_code = project_code.strip() if project_code else None
            membership = conn.execute(
                text(
                    """
                    SELECT project_role.key_role
                    FROM user_checklists uc
                    JOIN onboarding_template ot ON ot.template_id = uc.template_id
                    JOIN users u ON u.user_id = uc.user_id
                    JOIN roles project_role ON project_role.role_id = uc.project_role_id
                    WHERE LOWER(u.email) = :email
                      AND (
                          :project_code IS NULL
                          OR ot.template_code = :project_code
                          OR ot.template_name = :project_code
                      )
                      AND project_role.key_role = 'PROJECT_LEAD'
                    LIMIT 1
                    """
                ),
                {"email": clean_email, "project_code": clean_project_code},
            ).mappings().first()
            return bool(membership and str(membership["key_role"]).upper() == PERMISSION_PROJECT_LEAD)

    def is_user_project_lead_any_project(self, user_email: str) -> bool:
        """Kiểm tra user có PROJECT_LEAD ở ít nhất một dự án hay không."""
        clean_email = (user_email or "").strip().lower()
        if not clean_email:
            return False
        with get_connection(self._url) as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM user_checklists uc
                    JOIN users u ON u.user_id = uc.user_id
                    JOIN roles project_role ON project_role.role_id = uc.project_role_id
                    WHERE LOWER(u.email) = :email
                      AND project_role.key_role = 'PROJECT_LEAD'
                    LIMIT 1
                    """
                ),
                {"email": clean_email},
            ).first()
            return row is not None

    def is_user_project_member(self, user_email: str, project_code: str) -> bool:
        """Kiểm tra user có assignment trong đúng dự án, không suy quyền từ dữ liệu frontend."""
        clean_email = (user_email or "").strip().lower()
        clean_code = (project_code or "").strip()
        if not clean_email or not clean_code:
            return False
        with get_connection(self._url) as conn:
            membership = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM user_checklists uc
                    JOIN onboarding_template ot ON ot.template_id = uc.template_id
                    JOIN users u ON u.user_id = uc.user_id
                    WHERE LOWER(u.email) = :email
                      AND ot.template_code = :project_code
                    LIMIT 1
                    """
                ),
                {"email": clean_email, "project_code": clean_code},
            ).first()
            return membership is not None

    def list_projects(
        self,
        user_email: str | None = None,
        is_admin: bool = False,
    ) -> list[dict[str, Any]]:
        """Lấy danh sách tất cả các template/dự án từ database onboarding_template.
        - Admin: xem toàn bộ dự án.
        - Member: chỉ xem các dự án mà mình là thành viên (có trong user_checklists).
        """
        clean_email = user_email.strip().lower() if user_email else None
        with get_connection(self._url) as conn:
            if clean_email and not is_admin:
                u_row = conn.execute(
                    text(
                        """
                        SELECT u.user_id, COALESCE(system_role.key_role, 'MEMBER') AS access_key
                        FROM users u
                        LEFT JOIN roles system_role ON system_role.role_id = u.role_id
                        WHERE LOWER(u.email) = :email
                        """
                    ),
                    {"email": clean_email},
                ).mappings().first()
                if u_row:
                    user_perm = (u_row.get("access_key") or "").strip().upper()
                    if user_perm == PERMISSION_TEAM_LEAD:
                        is_admin = True

            if clean_email and not is_admin:
                sql = """
                    SELECT DISTINCT ot.template_id, ot.template_code, ot.template_name, ot.document_link,
                           ot.version, ot.is_active, ot.duration_days, ot.created_at,
                           uc.started_at AS member_started_at, uc.due_at AS member_due_at,
                           uc.status AS member_status,
                           COALESCE(project_role.key_role, 'MEMBER') AS member_permission,
                           COALESCE(u.job_title, '') AS member_job_title
                    FROM onboarding_template ot
                    JOIN user_checklists uc ON uc.template_id = ot.template_id
                    JOIN users u ON u.user_id = uc.user_id
                    LEFT JOIN roles project_role ON project_role.role_id = uc.project_role_id
                    WHERE LOWER(u.email) = :email
                    ORDER BY ot.template_code ASC
                """
                rows = conn.execute(text(sql), {"email": clean_email}).mappings().all()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT template_id, template_code, template_name, document_link,
                               version, is_active, duration_days, created_at,
                               NULL AS member_started_at, NULL AS member_due_at, NULL AS member_status,
                               NULL AS member_permission,
                               NULL AS member_job_title
                        FROM onboarding_template 
                        ORDER BY template_code ASC
                        """
                    )
                ).mappings().all()

            risk_summary_map: dict[int, dict[str, int]] = {}
            risk_rows = conn.execute(
                text(
                    """
                    SELECT template_id, status, progress, started_at, due_at, created_at
                    FROM user_checklists
                    """
                )
            ).mappings().all()
            duration_by_template = {
                int(row.get("template_id")): int(row.get("duration_days") or 20)
                for row in rows
                if row.get("template_id") is not None
            }
            for risk_row in risk_rows:
                risk_template_id = int(risk_row["template_id"])
                risk = _risk_metadata(
                    risk_row.get("started_at") or risk_row.get("created_at"),
                    risk_row.get("due_at"),
                    duration_by_template.get(risk_template_id, 20),
                    str(risk_row.get("status") or ""),
                    risk_row.get("progress"),
                )
                summary = risk_summary_map.setdefault(
                    risk_template_id,
                    {"member_count": 0, "risk_count": 0, "overdue_count": 0},
                )
                summary["member_count"] += 1
                if risk["risk_status"] == "at_risk":
                    summary["risk_count"] += 1
                elif risk["risk_status"] == "overdue":
                    summary["overdue_count"] += 1

            result = []
            for r in rows:
                tid = r.get("template_id")
                code = r.get("template_code") or ""
                name = r.get("template_name") or ""
                doc_link = r.get("document_link") or ""
                member_job_title = str(r.get("member_job_title") or "")
                member_permission = str(r.get("member_permission") or (PERMISSION_TEAM_LEAD if is_admin else "MEMBER"))
                can_manage_template = is_admin or has_management_permission(member_permission)
                risk_summary = risk_summary_map.get(
                    int(tid),
                    {"member_count": 0, "risk_count": 0, "overdue_count": 0},
                ) if tid is not None else {
                    "member_count": 0,
                    "risk_count": 0,
                    "overdue_count": 0,
                }
                result.append(
                    {
                        "template_id": tid,
                        "template_code": code,
                        "code": code,
                        "template_name": name,
                        "name": name,
                        "document_link": doc_link,
                        "doc_folder": doc_link,
                        "description": "",
                        "version": r.get("version", 1),
                        "is_active": bool(r.get("is_active", True)),
                        "duration_days": int(r.get("duration_days") or 20),
                        "member_job_title": member_job_title,
                        "access_level": member_permission,
                        "can_manage_template": can_manage_template,
                        **risk_summary,
                        **_deadline_metadata(
                            r.get("member_started_at"),
                            r.get("member_due_at"),
                            int(r.get("duration_days") or 20),
                            str(r.get("member_status") or ""),
                        ),
                        "role_ids": [],
                        "created_at": str(r.get("created_at") or ""),
                        "updated_at": str(r.get("created_at") or ""),
                    }
                )
            return result

    def list_templates(
        self,
        user_email: str | None = None,
        is_admin: bool = False,
    ) -> list[dict[str, Any]]:
        """Alias cho list_projects."""
        return self.list_projects(user_email=user_email, is_admin=is_admin)

    def get_project(self, code: str) -> dict[str, Any] | None:
        """Lấy thông tin một template/dự án theo template_code từ database."""
        with get_connection(self._url) as conn:
            row = conn.execute(
                text(
                    """
                    SELECT template_id, template_code, template_name, document_link,
                           version, is_active, duration_days, created_at
                    FROM onboarding_template 
                    WHERE template_code = :code
                    """
                ),
                {"code": code},
            ).mappings().first()
            if not row:
                return None
            tid = row.get("template_id")
            code_val = row.get("template_code") or ""
            name_val = row.get("template_name") or ""
            doc_link = row.get("document_link") or ""
            return {
                "template_id": tid,
                "template_code": code_val,
                "code": code_val,
                "template_name": name_val,
                "name": name_val,
                "document_link": doc_link,
                "doc_folder": doc_link,
                "description": "",
                "version": row.get("version", 1),
                "is_active": bool(row.get("is_active", True)),
                "duration_days": int(row.get("duration_days") or 20),
                "role_ids": [],
                "created_at": str(row.get("created_at") or ""),
                "updated_at": str(row.get("created_at") or ""),
            }

    def get_template(self, template_code: str) -> dict[str, Any] | None:
        """Alias cho get_project."""
        return self.get_project(template_code)

    def get_doc_folder(self, code: str) -> Path:
        """Trả về folder riêng của dự án và tạo folder nếu chưa tồn tại."""
        folder = self._canonical_doc_folder(code)
        if self.get_project(code) is None:
            raise KeyError(code)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def set_doc_folder(self, code: str, folder_path: str) -> bool:
        """Giữ API cũ nhưng luôn ép về folder canonical của project."""
        del folder_path
        self._canonical_doc_folder(code).mkdir(parents=True, exist_ok=True)
        with get_connection(self._url) as conn:
            res = conn.execute(
                text(
                    """
                    UPDATE onboarding_template 
                    SET document_link = :document_link 
                    WHERE template_code = :code
                    """
                ),
                {"code": code, "document_link": self._canonical_document_link(code)},
            )
            return res.rowcount > 0

    def set_document_link(self, template_code: str, document_link: str) -> bool:
        """Alias cho set_doc_folder."""
        return self.set_doc_folder(template_code, document_link)

    def upsert_project(
        self,
        code: str,
        name: str,
        description: str = "",
        doc_folder: str = "",
    ) -> None:
        """Thêm mới hoặc cập nhật template trong database."""
        now = datetime.now().isoformat()
        self._canonical_doc_folder(code).mkdir(parents=True, exist_ok=True)
        with get_connection(self._url) as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO onboarding_template (template_code, template_name, document_link, created_at)
                    VALUES (:template_code, :template_name, :document_link, :created_at)
                    ON CONFLICT (template_code) DO UPDATE SET
                        template_name = excluded.template_name,
                        document_link = excluded.document_link
                    """
                ),
                {
                    "template_code": code,
                    "template_name": name,
                    "document_link": self._canonical_document_link(code),
                    "created_at": now,
                },
            )

    def upsert_template(
        self,
        template_code: str,
        template_name: str,
        document_link: str = "",
        **kwargs: Any,
    ) -> None:
        """Alias cho upsert_project."""
        self.upsert_project(code=template_code, name=template_name, doc_folder=document_link)

    def create_project(
        self,
        code: str,
        name: str,
        description: str = "",
        role_name: str = "Developer",
        creator_email: str = "",
        duration_days: int = 20,
    ) -> dict[str, Any]:
        """Tạo dự án/onboarding template mới trong database và khởi tạo thư mục tài liệu."""
        normalized_code = code.strip().upper()
        if not _PROJECT_CODE_RE.fullmatch(normalized_code):
            raise ValueError(f"Mã dự án '{code}' không hợp lệ. Chỉ chấp nhận chữ cái, số, dấu '.', '_', '-'.")

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Tên dự án không được để trống.")
        if not isinstance(duration_days, int) or isinstance(duration_days, bool) or not 1 <= duration_days <= 3650:
            raise ValueError("Thời hạn hoàn thành phải từ 1 đến 3650 ngày.")

        now = datetime.now().isoformat()
        self._canonical_doc_folder(normalized_code).mkdir(parents=True, exist_ok=True)

        with get_connection(self._url) as conn:
            # Kiểm tra xem mã dự án đã tồn tại chưa
            existing = conn.execute(
                text("SELECT template_id FROM onboarding_template WHERE template_code = :code"),
                {"code": normalized_code},
            ).first()
            if existing:
                raise ValueError(f"Mã dự án '{normalized_code}' đã tồn tại trong hệ thống.")

            conn.execute(
                text(
                    """
                    INSERT INTO onboarding_template
                        (template_code, template_name, duration_days, document_link, created_at)
                    VALUES (:template_code, :template_name, :duration_days, :document_link, :created_at)
                    """
                ),
                {
                    "template_code": normalized_code,
                    "template_name": clean_name,
                    "duration_days": duration_days,
                    "document_link": self._canonical_document_link(normalized_code),
                    "created_at": now,
                },
            )

            # Nếu có creator_email, thêm người tạo vào dự án qua user_checklists
            if creator_email:
                try:
                    self._ensure_user_checklist_member(
                        conn,
                        project_code=normalized_code,
                        user_email=creator_email,
                        role_in_project=None,
                        project_role_key=PERMISSION_PROJECT_LEAD,
                        added_by=creator_email,
                        now=now,
                    )
                except Exception:
                    pass

        return self.get_project(normalized_code) or {
            "template_code": normalized_code,
            "code": normalized_code,
            "template_name": clean_name,
            "name": clean_name,
            "description": description,
            "duration_days": duration_days,
            "document_link": self._canonical_document_link(normalized_code),
            "doc_folder": self._canonical_document_link(normalized_code),
            "created_at": now,
        }

    def _ensure_user_checklist_member(
        self,
        conn,
        project_code: str,
        user_email: str,
        role_in_project: str | None = None,
        role_id: int | None = None,
        role_name: str | None = None,
        job_title: str | None = None,
        project_role_key: str = PERMISSION_MEMBER,
        added_by: str = "",
        user_name: str = "",
        department: str = "",
        now: str = "",
    ) -> dict[str, Any]:
        clean_code = project_code.strip()
        clean_email = user_email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise ValueError(f"Email '{user_email}' không hợp lệ.")

        if not now:
            now = datetime.now().isoformat()

        t_row = conn.execute(
            text("SELECT template_id, duration_days FROM onboarding_template WHERE template_code = :code"),
            {"code": clean_code},
        ).mappings().first()
        if not t_row:
            raise ValueError(f"Không tìm thấy dự án có mã '{clean_code}'.")
        template_id = t_row["template_id"]
        duration_days = int(t_row.get("duration_days") or 20)
        started_at = now
        due_at = (datetime.fromisoformat(now) + timedelta(days=duration_days)).isoformat()

        roles_by_id: dict[int, str] = {}
        role_ids_by_key: dict[str, int] = {}
        try:
            for r in conn.execute(text("SELECT role_id, role_name, key_role FROM roles")).all():
                roles_by_id[r[0]] = r[1].strip()
                role_ids_by_key[str(r[2] or "").strip().upper()] = r[0]
        except Exception:
            pass

        clean_project_role_key = (project_role_key or PERMISSION_MEMBER).strip().upper()
        if clean_project_role_key not in {PERMISSION_PROJECT_LEAD, PERMISSION_MEMBER}:
            raise ValueError("Quyền trong dự án chỉ có thể là PROJECT_LEAD hoặc MEMBER.")
        project_role_id = role_ids_by_key.get(clean_project_role_key)
        if project_role_id is None:
            raise ValueError(f"Không tìm thấy role key '{clean_project_role_key}'.")

        # Tra cứu hoặc tạo user
        u = conn.execute(
            text(
                """
                SELECT u.user_id, u.role_id, u.job_title, u.name, u.department,
                       COALESCE(system_role.key_role, 'MEMBER') AS access_key
                FROM users u
                LEFT JOIN roles system_role ON system_role.role_id = u.role_id
                WHERE LOWER(u.email) = :email
                """
            ),
            {"email": clean_email},
        ).mappings().first()

        if u:
            user_id = u["user_id"]
            user_role_id = u["role_id"]
            job_title = str(u.get("job_title") or "")
            user_name = user_name or u["name"]
            department = department or u["department"]
            user_level = u["access_key"] or "MEMBER"
        else:
            user_role_id = role_ids_by_key[PERMISSION_MEMBER]
            job_title = ""
            user_name = user_name or clean_email.split("@")[0]
            department = department or "Engineering"
            user_level = "MEMBER"
            conn.execute(
                text(
                    """
                    INSERT INTO users (name, email, role_id, job_title, department, password)
                    VALUES (:name, :email, :role_id, :job_title, :dept, '81dc9bdb52d04dc20036dbd8313ed055')
                    ON CONFLICT (email) DO NOTHING
                    """
                ),
                {
                    "name": user_name,
                    "email": clean_email,
                    "role_id": user_role_id,
                    "job_title": job_title,
                    "dept": department,
                },
            )
            u_new = conn.execute(
                text("SELECT user_id, role_id FROM users WHERE LOWER(email) = :email"),
                {"email": clean_email},
            ).mappings().first()
            user_id = u_new["user_id"]
            user_role_id = u_new["role_id"]

        # Thêm vào user_checklists với role_id
        conn.execute(
            text(
                """
                INSERT INTO user_checklists
                    (user_id, template_id, role_id, project_role_id, status, progress, started_at, due_at, created_at, updated_at)
                VALUES (:uid, :tid, :role_id, :project_role_id, 'NOT_STARTED', 0, :started_at, :due_at, :now, :now)
                ON CONFLICT (user_id, template_id) DO UPDATE SET
                    role_id = COALESCE(excluded.role_id, user_checklists.role_id),
                    project_role_id = excluded.project_role_id,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "uid": user_id,
                "tid": template_id,
                "role_id": project_role_id,
                "project_role_id": project_role_id,
                "started_at": started_at,
                "due_at": due_at,
                "now": now,
            },
        )

        cl_row = conn.execute(
            text(
                "SELECT checklist_id, role_id, project_role_id, status, progress, started_at, due_at, created_at "
                "FROM user_checklists WHERE user_id = :uid AND template_id = :tid"
            ),
            {"uid": user_id, "tid": template_id},
        ).mappings().first()
        checklist_id = cl_row["checklist_id"]
        actual_role_id = cl_row["project_role_id"]
        actual_role_name = roles_by_id.get(actual_role_id, clean_project_role_key)

        # Checklist mẫu dùng chung nên thành viên nhận toàn bộ task của dự án.
        task_rows = conn.execute(
            text(
                """
                SELECT template_task_id FROM onboarding_template_tasks
                WHERE template_id = :tid
                """
            ),
            {"tid": template_id},
        ).mappings().all()

        for tr in task_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO user_checklists_tasks (checklist_id, template_task_id, status, created_at, updated_at)
                    VALUES (:cid, :ttid, 'PENDING', :now, :now)
                    ON CONFLICT (checklist_id, template_task_id) DO NOTHING
                    """
                ),
                {"cid": checklist_id, "ttid": tr["template_task_id"], "now": now},
            )

        deadline = _deadline_metadata(
            cl_row.get("started_at") or cl_row.get("created_at"),
            cl_row.get("due_at"),
            duration_days,
            str(cl_row["status"]),
        )
        risk = _risk_metadata(
            cl_row.get("started_at") or cl_row.get("created_at"),
            cl_row.get("due_at"),
            duration_days,
            str(cl_row["status"]),
            cl_row.get("progress"),
        )
        return {
            "id": checklist_id,
            "project_code": clean_code,
            "user_email": clean_email,
            "user_name": user_name,
            "role_id": actual_role_id,
            "role_name": actual_role_name,
            "role_in_project": actual_role_name,
            "job_title": job_title,
            "department": department or "Engineering",
            "system_role_key": str(user_level).upper(),
            "user_level": user_level,
            "project_role_key": clean_project_role_key,
            "added_by": added_by or "system",
            "joined_at": str(cl_row["created_at"] or now),
            "duration_days": duration_days,
            **deadline,
            **risk,
            "status": cl_row["status"],
            "progress": cl_row["progress"],
        }

    def list_project_members(self, project_code: str, search: str | None = None) -> list[dict[str, Any]]:
        """Lấy danh sách thành viên của dự án từ user_checklists kèm tìm kiếm."""
        clean_code = project_code.strip()
        with get_connection(self._url) as conn:
            sql = """
                SELECT uc.checklist_id, uc.role_id as checklist_role_id, uc.status, uc.progress,
                       uc.started_at, uc.due_at, uc.created_at as joined_at,
                       u.user_id, u.name as user_name, u.email as user_email, u.job_title, u.department,
                       COALESCE(system_role.key_role, 'MEMBER') as system_role_key,
                       COALESCE(project_role.key_role, 'MEMBER') as project_role_key,
                       project_role.role_id as project_role_id, project_role.role_name as project_role_name,
                       ot.template_code as project_code, ot.duration_days
                FROM user_checklists uc
                JOIN users u ON u.user_id = uc.user_id
                LEFT JOIN roles system_role ON system_role.role_id = u.role_id
                LEFT JOIN roles project_role ON project_role.role_id = uc.project_role_id
                JOIN onboarding_template ot ON ot.template_id = uc.template_id
                WHERE ot.template_code = :code
                ORDER BY uc.checklist_id ASC
            """
            rows = conn.execute(text(sql), {"code": clean_code}).mappings().all()
            results = []
            for r in rows:
                member_role_id = r["project_role_id"]
                member_role_name = r["project_role_name"] or "Member"
                deadline = _deadline_metadata(
                    r.get("started_at") or r.get("joined_at"),
                    r.get("due_at"),
                    int(r.get("duration_days") or 20),
                    str(r["status"]),
                )
                risk = _risk_metadata(
                    r.get("started_at") or r.get("joined_at"),
                    r.get("due_at"),
                    int(r.get("duration_days") or 20),
                    str(r["status"]),
                    r.get("progress"),
                )
                item = {
                    "id": r["checklist_id"],
                    "project_code": r["project_code"],
                    "user_email": r["user_email"],
                    "user_name": r["user_name"] or r["user_email"].split("@")[0],
                    "role_id": member_role_id,
                    "role_name": member_role_name,
                    "role_in_project": member_role_name,
                    "job_title": r["job_title"] or "",
                    "department": r["department"] or "",
                    "system_role_key": r["system_role_key"] or "MEMBER",
                    "permission": r["project_role_key"] or "MEMBER",
                    "user_level": r["project_role_key"] or "MEMBER",
                    "project_role_key": r["project_role_key"] or "MEMBER",
                    "added_by": "system",
                    "joined_at": str(r["joined_at"] or ""),
                    "duration_days": int(r.get("duration_days") or 20),
                    **deadline,
                    **risk,
                    "status": r["status"],
                    "progress": r["progress"],
                }
                if search:
                    q = search.strip().lower()
                    if (
                        q not in item["user_name"].lower()
                        and q not in item["user_email"].lower()
                        and q not in item["role_name"].lower()
                        and q not in item["role_in_project"].lower()
                        and q not in item["department"].lower()
                    ):
                        continue
                results.append(item)
            return results

    def list_roles(self) -> list[dict[str, Any]]:
        """Lấy danh mục vai trò canonical, sắp xếp ổn định theo tên."""
        with get_connection(self._url) as conn:
            rows = conn.execute(
                text("SELECT role_id, key_role, role_name, description FROM roles ORDER BY role_name ASC")
            ).mappings().all()
            return [dict(r) for r in rows]

    def add_project_member(
        self,
        project_code: str,
        user_email: str,
        role_in_project: str | None = None,
        role_id: int | None = None,
        role_name: str | None = None,
        job_title: str | None = None,
        project_role_key: str = PERMISSION_MEMBER,
        added_by: str = "",
        user_name: str = "",
        department: str = "",
    ) -> dict[str, Any]:
        """Thêm thành viên vào dự án qua user_checklists."""
        with get_connection(self._url) as conn:
            return self._ensure_user_checklist_member(
                conn,
                project_code=project_code,
                user_email=user_email,
                role_in_project=role_in_project,
                role_id=role_id,
                role_name=role_name,
                job_title=job_title,
                project_role_key=project_role_key,
                added_by=added_by,
                user_name=user_name,
                department=department,
            )

    def add_project_members_batch(
        self,
        project_code: str,
        members: list[dict[str, Any]],
        added_by: str = "",
    ) -> list[dict[str, Any]]:
        """Thêm hàng loạt thành viên vào dự án trong cùng một transaction."""
        results: list[dict[str, Any]] = []
        now = datetime.now().isoformat()
        with get_connection(self._url) as conn:
            for it in members:
                u_email = (it.get("user_email") or it.get("email") or "").strip().lower()
                if not u_email:
                    continue
                res = self._ensure_user_checklist_member(
                    conn,
                    project_code=project_code,
                    user_email=u_email,
                    role_in_project=it.get("role_in_project") or it.get("role_name") or "Developer",
                    role_id=it.get("role_id"),
                    role_name=it.get("role_name"),
                    job_title=it.get("job_title"),
                    project_role_key=str(it.get("project_role_key") or PERMISSION_MEMBER),
                    added_by=added_by,
                    user_name=it.get("user_name") or it.get("name") or "",
                    department=it.get("department") or "",
                    now=now,
                )
                results.append(res)
        return results

    def remove_project_member(self, project_code: str, user_email: str) -> bool:
        """Xóa thành viên khỏi dự án (xóa khỏi user_checklists)."""
        clean_code = project_code.strip()
        clean_email = user_email.strip().lower()
        with get_connection(self._url) as conn:
            t = conn.execute(
                text("SELECT template_id FROM onboarding_template WHERE template_code = :code"),
                {"code": clean_code},
            ).mappings().first()
            u = conn.execute(
                text("SELECT user_id FROM users WHERE LOWER(email) = :email"),
                {"email": clean_email},
            ).mappings().first()
            if not t or not u:
                return False

            tid = t["template_id"]
            uid = u["user_id"]

            cl = conn.execute(
                text("SELECT checklist_id FROM user_checklists WHERE template_id = :tid AND user_id = :uid"),
                {"tid": tid, "uid": uid},
            ).mappings().first()
            if not cl:
                return False

            cid = cl["checklist_id"]
            conn.execute(
                text("DELETE FROM user_checklists_tasks WHERE checklist_id = :cid"),
                {"cid": cid},
            )
            res = conn.execute(
                text("DELETE FROM user_checklists WHERE checklist_id = :cid"),
                {"cid": cid},
            )
            return res.rowcount > 0


# Alias tương thích
OnboardingTemplateService = ProjectService

