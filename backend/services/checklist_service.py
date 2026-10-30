"""Logic nghiệp vụ cho checklist: lưu trạng thái trong PostgreSQL, tính tiến độ, xuất báo cáo."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

from config.settings import Settings
from backend.services.db import get_connection, init_schema
from backend.services.notification_service import NotificationService

STATUSES = ("ACTIVE", "active", "pending", "passed", "failed", "warning", "COMPLETED", "IN_PROGRESS", "BLOCKED")


@dataclass
class ChecklistItem:
    key: str
    category: str
    title: str
    description: str
    check_type: str
    params: dict[str, Any] = field(default_factory=dict)
    required: bool = True
    status: str = "ACTIVE"
    message: str = ""
    updated_at: str | None = None
    template_task_id: int | None = None
    template_id: int | None = None


LEGACY_KEY_TO_NAME: dict[str, str] = {
    "app_python": "Python >= 3.11",
    "app_git": "Git >= 2.30",
    "app_node": "Node.js >= 18",
    "app_docker": "Docker >= 24",
    "app_ollama": "Ollama",
    "net_wifi": "Kết nối Wi-Fi",
    "net_ollama": "Ollama service (localhost:11434)",
    "net_git_server": "Git server nội bộ (git.company.local:443)",
    "net_db_dev": "Database dev (db.company.local:5432)",
    "port_8000": "Port 8000 còn trống (Backend API)",
    "port_3000": "Port 3000 còn trống (Frontend dev server)",
    "port_8080": "Port 8080 còn trống (API Gateway)",
    "train_goal": "Đã nắm mục tiêu dự án",
    "train_team": "Đã biết thông tin thành viên",
    "train_timeline": "Đã xem Timeline dự án",
    "train_rules": "Đã đọc rule dự án",
    "train_ip_process": "Đã biết quy trình xin cấp quyền IP",
    "train_arch": "Đã xem mô hình kiến trúc (Microservices)",
    "train_ask_first": "Đã hiểu nguyên tắc \"hỏi trước khi thực thi\"",
}


class ChecklistService:
    def __init__(self, settings: Settings, notifier: NotificationService | None = None) -> None:
        self.settings = settings
        self.notifier = notifier
        init_schema(settings.database_url)
        self.seed_defaults()

    @property
    def _url(self) -> str:
        return self.settings.database_url

    # ---------- seed ----------
    def seed_defaults(self) -> int:
        path = self.settings.config_dir / "checklist_items.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = data.get("items", [])
        with get_connection(self._url) as conn:
            # Lấy template_id mặc định từ onboarding_template
            row = conn.execute(
                text("SELECT template_id FROM onboarding_template ORDER BY template_id LIMIT 1")
            ).first()
            if row:
                template_id = row[0]
            else:
                conn.execute(
                    text(
                        "INSERT INTO onboarding_template (template_code, template_name, document_link) "
                        "VALUES ('PRJ_ECOMMERCE', 'Backend Developer Onboarding', 'documents/projects/PRJ_ECOMMERCE') "
                        "ON CONFLICT (template_code) DO NOTHING"
                    )
                )
                template_id = conn.execute(
                    text("SELECT template_id FROM onboarding_template WHERE template_code='PRJ_ECOMMERCE'")
                ).first()[0]

            for order, it in enumerate(items):
                task_name = it.get("title") or it.get("task_name") or ""
                check_type = str(it.get("check_type", "MANUAL")).upper()
                mandatory_val = it.get("mandatory") if it.get("mandatory") is not None else it.get("required", True)
                instructions = it.get("description") or it.get("instructions", "")
                params_str = json.dumps(it.get("params", {}), ensure_ascii=False)
                conn.execute(
                    text(
                        """
                        INSERT INTO onboarding_template_tasks
                            (template_id, task_name, category, mandatory, instructions, sort_order, check_type, params, status)
                        VALUES
                            (:template_id, :task_name, :category, :mandatory, :instructions, :sort_order, :check_type, :params, 'ACTIVE')
                        ON CONFLICT (template_id, task_name) DO UPDATE SET
                            category = excluded.category,
                            mandatory = excluded.mandatory,
                            instructions = excluded.instructions,
                            sort_order = excluded.sort_order,
                            check_type = excluded.check_type,
                            params = excluded.params
                        """
                    ),
                    {
                        "template_id": template_id,
                        "task_name": task_name,
                        "category": it.get("category", ""),
                        "mandatory": bool(mandatory_val),
                        "instructions": instructions,
                        "sort_order": order,
                        "check_type": check_type,
                        "params": params_str,
                    },
                )
        return len(items)

    # ---------- query ----------
    @staticmethod
    def _row_to_item(row) -> ChecklistItem:
        # Nếu có template_task_id, dùng task_<id> hoặc task_name làm key duy nhất
        key = row.get("key") or (f"task_{row.get('template_task_id')}" if row.get("template_task_id") is not None else (row.get("task_name") or ""))
        title = row.get("task_name") or row.get("title") or ""
        description = row.get("instructions") or row.get("description") or ""
        check_type = str(row.get("check_type") or "MANUAL").upper()
        raw_params = row.get("params") or "{}"
        if isinstance(raw_params, str):
            try:
                params = json.loads(raw_params)
            except Exception:
                params = {}
        else:
            params = dict(raw_params) if raw_params else {}

        mandatory = row.get("mandatory")
        if mandatory is None:
            mandatory = row.get("required", 1)
        required = bool(mandatory)

        status = row.get("user_status") or row.get("status") or "ACTIVE"
        message = ""  # Cột message đã bỏ khỏi schema, message chỉ tồn tại runtime
        updated_at = row.get("updated_at")

        return ChecklistItem(
            key=key,
            category=row.get("category", ""),
            title=title,
            description=description,
            check_type=check_type,
            params=params,
            required=required,
            status=status,
            message=message,
            updated_at=updated_at,
            template_task_id=row.get("template_task_id"),
            template_id=row.get("template_id"),
        )

    def list_items(
        self,
        category: str | None = None,
        template_code: str | None = None,
        user_email: str | None = None,
    ) -> list[ChecklistItem]:
        args: dict[str, Any] = {}
        wheres: list[str] = []

        with get_connection(self._url) as conn:
            sql = """SELECT ott.*"""
            if user_email:
                sql += """
                    , CASE
                        WHEN user_task.status = 'COMPLETED' THEN 'passed'
                        WHEN user_task.status = 'BLOCKED' THEN 'failed'
                        WHEN user_task.status = 'IN_PROGRESS' THEN 'pending'
                        ELSE 'ACTIVE'
                      END AS user_status
                """
            sql += """
                FROM onboarding_template_tasks ott
            """
            if user_email:
                sql += """
                    LEFT JOIN user_checklists member_checklist
                        ON member_checklist.template_id = ott.template_id
                       AND member_checklist.user_id = (
                           SELECT user_id FROM users WHERE LOWER(email) = :user_email
                       )
                    LEFT JOIN user_checklists_tasks user_task
                        ON user_task.checklist_id = member_checklist.checklist_id
                       AND user_task.template_task_id = ott.template_task_id
                """
                args["user_email"] = user_email.strip().lower()
            if template_code:
                sql += " JOIN onboarding_template t ON t.template_id = ott.template_id"
                wheres.append("t.template_code = :template_code")
                args["template_code"] = template_code

            if category:
                wheres.append("ott.category = :category")
                args["category"] = category

            if wheres:
                sql += " WHERE " + " AND ".join(wheres)

            sql += " ORDER BY ott.sort_order, ott.template_task_id"
            return [self._row_to_item(r) for r in conn.execute(text(sql), args).mappings()]

    def step_blocker(self, key: str, user_email: str | None = None) -> str | None:
        """Thứ tự theo template; warning cũng chưa phải hoàn thành một bước."""
        item = self.get_item(key)
        if item is None:
            raise KeyError(key)
        items = [
            row
            for row in self.list_items(user_email=user_email)
            if row.template_id == item.template_id
        ]
        for index, previous in enumerate(items, 1):
            if previous.key == item.key:
                return None
            if previous.status.lower() not in {"passed", "completed"}:
                return f"Cần hoàn thành bước {index}: {previous.title} trước."
        raise KeyError(key)

    def get_item(self, key: str) -> ChecklistItem | None:
        lookup_name = LEGACY_KEY_TO_NAME.get(key, key)
        with get_connection(self._url) as conn:
            row = None
            select_item = "SELECT ott.* FROM onboarding_template_tasks ott"
            if key.isdigit():
                row = conn.execute(
                    text(select_item + " WHERE ott.template_task_id = :tid"),
                    {"tid": int(key)},
                ).mappings().first()
            elif key.startswith("task_") and key[5:].isdigit():
                row = conn.execute(
                    text(select_item + " WHERE ott.template_task_id = :tid"),
                    {"tid": int(key[5:])},
                ).mappings().first()
            else:
                row = conn.execute(
                    text(select_item + " WHERE ott.task_name = :key"),
                    {"key": lookup_name},
                ).mappings().first()
                if not row:
                    row = conn.execute(
                        text(select_item + " WHERE ott.task_name LIKE :key_like"),
                        {"key_like": f"{lookup_name}%"},
                    ).mappings().first()
                if not row:
                    try:
                        row = conn.execute(
                            text(select_item + " WHERE ott.key = :key"),
                            {"key": key},
                        ).mappings().first()
                    except Exception:
                        pass
        return self._row_to_item(row) if row else None

    def categories(self) -> list[str]:
        seen: list[str] = []
        for item in self.list_items():
            if item.category not in seen:
                seen.append(item.category)
        return seen

    # ---------- update ----------
    def update_status(self, key: str, status: str, message: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"Trạng thái không hợp lệ: {status}")
        lookup_name = LEGACY_KEY_TO_NAME.get(key, key)
        now_str = datetime.now().isoformat(timespec="seconds")
        with get_connection(self._url) as conn:
            cur = None
            if key.isdigit():
                cur = conn.execute(
                    text(
                        "UPDATE onboarding_template_tasks SET status=:status, "
                        "updated_at=:updated_at WHERE template_task_id=:tid"
                    ),
                    {"status": status, "tid": int(key), "updated_at": now_str},
                )
            elif key.startswith("task_") and key[5:].isdigit():
                cur = conn.execute(
                    text(
                        "UPDATE onboarding_template_tasks SET status=:status, "
                        "updated_at=:updated_at WHERE template_task_id=:tid"
                    ),
                    {"status": status, "tid": int(key[5:]), "updated_at": now_str},
                )
            else:
                cur = conn.execute(
                    text(
                        "UPDATE onboarding_template_tasks SET status=:status, "
                        "updated_at=:updated_at WHERE task_name=:key"
                    ),
                    {"status": status, "key": lookup_name, "updated_at": now_str},
                )
                if cur.rowcount == 0:
                    cur = conn.execute(
                        text(
                            "UPDATE onboarding_template_tasks SET status=:status, "
                            "updated_at=:updated_at WHERE task_name LIKE :key_like"
                        ),
                        {"status": status, "key_like": f"{lookup_name}%", "updated_at": now_str},
                    )
                if cur.rowcount == 0:
                    try:
                        cur = conn.execute(
                            text(
                                "UPDATE onboarding_template_tasks SET status=:status, "
                                "updated_at=:updated_at WHERE key=:key"
                            ),
                            {"status": status, "key": key, "updated_at": now_str},
                        )
                    except Exception:
                        pass
            if cur is None or cur.rowcount == 0:
                raise KeyError(key)

    def set_manual_done(self, key: str, done: bool) -> None:
        self.update_status(key, "passed" if done else "ACTIVE", "Đã xác nhận thủ công" if done else "")
        if done and self.notifier and self.progress()["percent"] == 100:
            self.notifier.success("🎉 Bạn đã hoàn thành toàn bộ checklist! Sẵn sàng join dự án.")

    def update_user_task_status(
        self,
        user_id: int,
        key: str,
        done: bool,
        note: str = "",
        template_code: str | None = None,
        sync_template_status: bool = True,
    ) -> dict[str, Any]:
        """Cập nhật trạng thái một checklist item trong user_checklists_tasks theo user_id."""
        item = self.get_item(key)
        if not item:
            raise KeyError(f"Không tìm thấy mục checklist: {key}")

        template_task_id = item.template_task_id
        template_id = item.template_id

        with get_connection(self._url) as conn:
            # Nếu chưa có template_task_id hoặc template_id, truy vấn từ DB
            if not template_task_id or not template_id:
                lookup_name = LEGACY_KEY_TO_NAME.get(key, key)
                row = conn.execute(
                    text("SELECT template_task_id, template_id FROM onboarding_template_tasks WHERE task_name = :tn LIMIT 1"),
                    {"tn": lookup_name},
                ).mappings().first()
                if row:
                    template_task_id = row["template_task_id"]
                    template_id = row["template_id"]

            if not template_id:
                t_row = conn.execute(
                    text("SELECT template_id FROM onboarding_template WHERE template_code = :tc LIMIT 1"),
                    {"tc": template_code or "PRJ_ECOMMERCE"},
                ).mappings().first()
                if t_row:
                    template_id = t_row["template_id"]

            if not template_task_id:
                raise KeyError(f"Không tìm thấy template_task_id cho: {key}")

            # 1. Tìm hoặc tạo user_checklists
            c_row = conn.execute(
                text("SELECT checklist_id FROM user_checklists WHERE user_id = :uid AND template_id = :tid"),
                {"uid": user_id, "tid": template_id},
            ).mappings().first()

            if c_row:
                checklist_id = c_row["checklist_id"]
            else:
                now_str = datetime.now().isoformat(timespec="seconds")
                try:
                    conn.execute(
                        text(
                            "INSERT INTO user_checklists (user_id, template_id, status, progress, created_at, updated_at) "
                            "VALUES (:uid, :tid, 'IN_PROGRESS', 0, :now, :now)"
                        ),
                        {"uid": user_id, "tid": template_id, "now": now_str},
                    )
                    c_row = conn.execute(
                        text("SELECT checklist_id FROM user_checklists WHERE user_id = :uid AND template_id = :tid"),
                        {"uid": user_id, "tid": template_id},
                    ).mappings().first()
                    checklist_id = c_row["checklist_id"] if c_row else 1
                except Exception:
                    c_row = conn.execute(
                        text("SELECT checklist_id FROM user_checklists WHERE user_id = :uid AND template_id = :tid"),
                        {"uid": user_id, "tid": template_id},
                    ).mappings().first()
                    checklist_id = c_row["checklist_id"] if c_row else 1

            # 2. Cập nhật user_checklists_tasks
            new_status = "COMPLETED" if done else "PENDING"
            now_str = datetime.now().isoformat(timespec="seconds")
            completed_at_val = now_str if done else None

            upd = conn.execute(
                text(
                    "UPDATE user_checklists_tasks "
                    "SET status = :status, completed_at = :cat, note = :note, updated_at = :now "
                    "WHERE checklist_id = :cid AND template_task_id = :ttid"
                ),
                {
                    "status": new_status,
                    "cat": completed_at_val,
                    "note": note,
                    "now": now_str,
                    "cid": checklist_id,
                    "ttid": template_task_id,
                },
            )

            if upd.rowcount == 0:
                conn.execute(
                    text(
                        "INSERT INTO user_checklists_tasks (checklist_id, template_task_id, status, completed_at, note, created_at, updated_at) "
                        "VALUES (:cid, :ttid, :status, :cat, :note, :now, :now)"
                    ),
                    {
                        "cid": checklist_id,
                        "ttid": template_task_id,
                        "status": new_status,
                        "cat": completed_at_val,
                        "note": note,
                        "now": now_str,
                    },
                )

            # 3. Tính lại progress & status cho user_checklists
            cnt_row = conn.execute(
                text(
                    "SELECT COUNT(*) as total, "
                    "COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed, "
                    "COUNT(CASE WHEN status = 'BLOCKED' THEN 1 END) as blocked "
                    "FROM user_checklists_tasks WHERE checklist_id = :cid"
                ),
                {"cid": checklist_id},
            ).mappings().first()

            total = cnt_row["total"] if cnt_row else 0
            completed = cnt_row["completed"] if cnt_row else 0
            blocked = cnt_row["blocked"] if cnt_row else 0
            progress_pct = int(round(100.0 * completed / total)) if total > 0 else 0

            list_status = "NOT_STARTED"
            if blocked > 0:
                list_status = "BLOCKED"
            elif total > 0 and completed == total:
                list_status = "COMPLETED"
            elif completed > 0:
                list_status = "IN_PROGRESS"

            conn.execute(
                text(
                    "UPDATE user_checklists SET progress = :prog, status = :st, updated_at = :now "
                    "WHERE checklist_id = :cid"
                ),
                {"prog": progress_pct, "st": list_status, "now": now_str, "cid": checklist_id},
            )

        # Bước manual cần đồng bộ trạng thái hiển thị của task mẫu. Kết quả verify đã
        # tự cập nhật trạng thái chi tiết (passed/failed/warning), nên không ghi đè.
        if sync_template_status:
            self.set_manual_done(key, done)

        return {
            "status": "ok",
            "user_id": user_id,
            "checklist_id": checklist_id,
            "template_task_id": template_task_id,
            "key": key,
            "done": done,
            "task_status": new_status,
            "checklist_progress": progress_pct,
            "checklist_status": list_status,
        }

    def reset(self) -> None:
        with get_connection(self._url) as conn:
            conn.execute(
                text("UPDATE onboarding_template_tasks SET status='ACTIVE', updated_at=NULL")
            )

    # ---------- progress / report ----------
    def progress(
        self,
        template_code: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any]:
        items = self.list_items(template_code=template_code, user_email=user_email)
        total = len(items)
        passed_count = sum(1 for i in items if i.status in ("passed", "COMPLETED"))
        failed_count = sum(1 for i in items if i.status in ("failed", "BLOCKED"))
        warning_count = sum(1 for i in items if i.status == "warning")
        pending_count = sum(1 for i in items if i.status in ("ACTIVE", "active", "pending", "IN_PROGRESS"))
        required = [i for i in items if i.required]
        required_passed = sum(1 for i in required if i.status in ("passed", "COMPLETED"))
        return {
            "total": total,
            "passed": passed_count,
            "failed": failed_count,
            "warning": warning_count,
            "pending": pending_count,
            "ACTIVE": pending_count,
            "required_total": len(required),
            "required_passed": required_passed,
            "percent": round(100 * passed_count / total) if total else 0,
            "ready": bool(required) and required_passed == len(required),
        }

    def export_report(self, path: Path | None = None) -> Path:
        icons = {
            "passed": "✅",
            "COMPLETED": "✅",
            "failed": "❌",
            "warning": "⚠️",
            "pending": "⏳",
            "ACTIVE": "⏳",
            "active": "⏳",
            "IN_PROGRESS": "⏳",
            "BLOCKED": "🚫",
        }
        prog = self.progress()
        lines = [
            "# Báo cáo checklist onboarding",
            f"_Tạo lúc {datetime.now():%Y-%m-%d %H:%M}_",
            "",
            f"**Tiến độ:** {prog['passed']}/{prog['total']} ({prog['percent']}%) - "
            f"{'SẴN SÀNG' if prog['ready'] else 'CHƯA SẴN SÀNG'} để join dự án",
        ]
        for cat in self.categories():
            lines += ["", f"## {cat}"]
            for it in self.list_items(cat):
                req = "" if it.required else " _(tuỳ chọn)_"
                msg = f" - {it.message}" if it.message else ""
                icon = icons.get(it.status, "⏳")
                lines.append(f"- {icon} {it.title}{req}{msg}")
        out = path or self.settings.exports_dir / f"checklist_{datetime.now():%Y%m%d_%H%M%S}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    # ---------- template sample & import ----------
    def get_sample_template_csv(self) -> str:
        """Trả về nội dung template CSV mẫu chuẩn UTF-8 (kèm BOM để mở trực tiếp trong Excel tiếng Việt không lỗi font)."""
        rows = [
            ["task_name", "category", "check_type", "mandatory", "owner_team", "instructions", "params", "sort_order"],
            ["Cài đặt Git", "Môi trường", "SOFTWARE", "true", "DevOps", "Cài đặt Git phiên bản >= 2.30", '{"name": "Git", "command": "git", "version_args": ["--version"], "min_version": "2.30", "install": {"winget": "Git.Git", "brew": "git", "apt": "git"}}', "1"],
            ["Cài đặt Python 3.11", "Môi trường", "SOFTWARE", "true", "DevOps", "Cài đặt Python 3.11 trở lên phục vụ chạy service", '{"name": "Python", "command": "python", "version_args": ["--version"], "min_version": "3.11", "install": {"winget": "Python.Python.3.11", "brew": "python@3.11", "apt": "python3.11"}}', "2"],
            ["Cài đặt Docker Desktop", "Môi trường", "SOFTWARE", "false", "DevOps", "Cài đặt Docker Desktop phục vụ khởi chạy container", '{"name": "Docker", "command": "docker", "version_args": ["--version"], "min_version": "24.0", "install": {"winget": "Docker.DockerDesktop", "brew": "docker", "apt": "docker.io"}}', "3"],
            ["Kiểm tra kết nối Git Server", "Mạng nội bộ", "HOST_REACHABLE", "true", "IT Helpdesk", "Kiểm tra kết nối IP/domain Git server nội bộ", '{"host": "git.company.local", "port": 443}', "4"],
            ["Kiểm tra kết nối CSDL Dev", "Mạng nội bộ", "HOST_REACHABLE", "true", "IT Helpdesk", "Kiểm tra kết nối tới cơ sở dữ liệu dev", '{"host": "db.company.local", "port": 5432}', "5"],
            ["Kiểm tra Port 8000 API", "Mạng nội bộ", "PORT_FREE", "true", "DevOps", "Kiểm tra cổng 8000 còn trống cho Backend API", '{"port": 8000}', "6"],
            ["Kiểm tra Wi-Fi", "Mạng nội bộ", "WIFI", "false", "IT", "Kiểm tra kết nối Wi-Fi cục bộ; không yêu cầu Internet", "{}", "7"],
            ["Đọc tài liệu Quy trình Onboarding", "Tài liệu", "MANUAL", "true", "PROJECT_LEAD", "Đọc kỹ quy trình tiếp nhận dự án và xin quyền truy cập", "{}", "8"],
            ["Nắm rõ quy tắc bảo mật & hỏi trước khi thực thi", "Tài liệu", "MANUAL", "true", "PROJECT_LEAD", "Tuyệt đối không chạy lệnh hệ thống khi chưa có xác nhận", "{}", "9"],
        ]
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\r\n")
        for r in rows:
            writer.writerow(r)
        return "\ufeff" + output.getvalue()

    def _get_or_create_template_id(self, conn, project_code: str | None = None) -> int:
        code = (project_code or "PRJ_ECOMMERCE").strip()
        row = conn.execute(
            text("SELECT template_id FROM onboarding_template WHERE template_code = :code LIMIT 1"),
            {"code": code},
        ).mappings().first()
        if row:
            return row["template_id"]

        template_name = f"Checklist Onboarding - {code}"
        doc_link = f"documents/projects/{code}"
        conn.execute(
            text(
                """
                INSERT INTO onboarding_template (template_code, template_name, document_link)
                VALUES (:code, :name, :doc_link)
                ON CONFLICT (template_code) DO NOTHING
                """
            ),
            {"code": code, "name": template_name, "doc_link": doc_link},
        )
        row = conn.execute(
            text("SELECT template_id FROM onboarding_template WHERE template_code = :code LIMIT 1"),
            {"code": code},
        ).mappings().first()
        if row:
            return row["template_id"]

        first_row = conn.execute(
            text("SELECT template_id FROM onboarding_template ORDER BY template_id LIMIT 1")
        ).mappings().first()
        return first_row["template_id"] if first_row else 1

    def import_tasks_from_csv(self, content: str, project_code: str | None = None) -> dict[str, Any]:
        """Nhập danh sách checklist dùng chung từ nội dung CSV hoặc JSON."""
        raw_text = content.lstrip("\ufeff").strip()
        if not raw_text:
            raise ValueError("Nội dung checklist rỗng.")

        items_to_insert: list[dict[str, Any]] = []

        # 1. Hỗ trợ JSON nếu bắt đầu bằng '[' hoặc '{'
        if raw_text.startswith("[") or raw_text.startswith("{"):
            try:
                parsed_json = json.loads(raw_text)
                if isinstance(parsed_json, dict):
                    parsed_json = parsed_json.get("items") or parsed_json.get("tasks") or [parsed_json]
                if isinstance(parsed_json, list):
                    for idx, row in enumerate(parsed_json):
                        if not isinstance(row, dict):
                            continue
                        name = row.get("task_name") or row.get("title") or row.get("name")
                        if not name:
                            continue
                        cat = row.get("category") or "Môi trường"
                        ctype = str(row.get("check_type") or "MANUAL").strip().upper()
                        if ctype not in {"SOFTWARE", "HOST_REACHABLE", "PORT_FREE", "WIFI", "MANUAL"}:
                            ctype = "MANUAL"
                        mand = row.get("mandatory") if row.get("mandatory") is not None else row.get("required", True)
                        mand_bool = True if str(mand).lower() in ("true", "1", "yes", "có") else False
                        team = str(row.get("owner_team") or "")
                        inst = str(row.get("instructions") or row.get("description") or "")
                        p = row.get("params") or {}
                        p_str = json.dumps(p, ensure_ascii=False) if isinstance(p, dict) else str(p)
                        sort_o = int(row.get("sort_order") or (idx + 1))
                        items_to_insert.append({
                            "task_name": str(name).strip(),
                            "category": str(cat).strip(),
                            "check_type": ctype,
                            "mandatory": mand_bool,
                            "owner_team": team,
                            "instructions": inst,
                            "params": p_str,
                            "sort_order": sort_o,
                        })
            except json.JSONDecodeError:
                pass

        # 2. Nếu chưa parse được qua JSON thì parse qua CSV
        if not items_to_insert:
            sample = raw_text[:2048]
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            reader = csv.DictReader(io.StringIO(raw_text), delimiter=delimiter)

            for idx, r in enumerate(reader):
                normalized = {k.strip().lower(): (v.strip() if v else "") for k, v in r.items() if k}
                name = (
                    normalized.get("task_name")
                    or normalized.get("taskname")
                    or normalized.get("title")
                    or normalized.get("tên tác vụ")
                    or normalized.get("tên công việc")
                    or normalized.get("tên")
                    or normalized.get("name")
                )
                if not name:
                    continue

                cat = (
                    normalized.get("category")
                    or normalized.get("danh mục")
                    or normalized.get("nhóm")
                    or "Môi trường"
                )
                ctype = (
                    normalized.get("check_type")
                    or normalized.get("loại")
                    or normalized.get("loại kiểm tra")
                    or "MANUAL"
                ).upper()
                if ctype not in {"SOFTWARE", "HOST_REACHABLE", "PORT_FREE", "WIFI", "MANUAL"}:
                    ctype = "MANUAL"

                mand_raw = (
                    normalized.get("mandatory")
                    or normalized.get("required")
                    or normalized.get("bắt buộc")
                    or "true"
                ).lower()
                mand_bool = mand_raw in ("true", "1", "yes", "có")

                team = (
                    normalized.get("owner_team")
                    or normalized.get("đội phụ trách")
                    or normalized.get("nhóm phụ trách")
                    or ""
                )
                inst = (
                    normalized.get("instructions")
                    or normalized.get("description")
                    or normalized.get("hướng dẫn")
                    or normalized.get("mô tả")
                    or ""
                )
                raw_p = (
                    normalized.get("params")
                    or normalized.get("tham số")
                    or "{}"
                ).strip()
                if raw_p.startswith('"') and raw_p.endswith('"') and len(raw_p) > 2:
                    raw_p = raw_p[1:-1].strip()
                raw_p = raw_p.replace('\\"', '"')
                try:
                    p_obj = json.loads(raw_p) if raw_p else {}
                    if not isinstance(p_obj, dict):
                        p_obj = {}
                    params_str = json.dumps(p_obj, ensure_ascii=False)
                except Exception:
                    try:
                        import ast
                        p_obj = ast.literal_eval(raw_p)
                        params_str = json.dumps(p_obj, ensure_ascii=False) if isinstance(p_obj, dict) else "{}"
                    except Exception:
                        params_str = "{}"

                sort_raw = normalized.get("sort_order") or normalized.get("thứ tự")
                try:
                    sort_o = int(sort_raw) if sort_raw else (idx + 1)
                except ValueError:
                    sort_o = idx + 1

                items_to_insert.append({
                    "task_name": name,
                    "category": cat,
                    "check_type": ctype,
                    "mandatory": mand_bool,
                    "owner_team": team,
                    "instructions": inst,
                    "params": params_str,
                    "sort_order": sort_o,
                })

        if not items_to_insert:
            raise ValueError("Không tìm thấy mục checklist hợp lệ nào trong file (yêu cầu cột 'task_name').")

        now_str = datetime.now().isoformat(timespec="seconds")
        with get_connection(self._url) as conn:
            template_id = self._get_or_create_template_id(conn, project_code)

            # Xoá liên kết user_checklists_tasks trước do ràng buộc FK ON DELETE RESTRICT
            conn.execute(
                text(
                    """
                    DELETE FROM user_checklists_tasks
                    WHERE template_task_id IN (
                        SELECT template_task_id FROM onboarding_template_tasks WHERE template_id = :tid
                    )
                    """
                ),
                {"tid": template_id},
            )
            # Xoá toàn bộ tasks cũ của template này để thay thế hoàn toàn
            conn.execute(
                text("DELETE FROM onboarding_template_tasks WHERE template_id = :tid"),
                {"tid": template_id},
            )
            # Reset tiến độ các user_checklists liên kết với template này
            conn.execute(
                text(
                    """
                    UPDATE user_checklists
                    SET status = 'NOT_STARTED', progress = 0, updated_at = :now
                    WHERE template_id = :tid
                    """
                ),
                {"tid": template_id, "now": now_str},
            )

            for it in items_to_insert:
                conn.execute(
                    text(
                        """
                        INSERT INTO onboarding_template_tasks
                            (template_id, task_name, category, mandatory, instructions, owner_team, sort_order, check_type, params, status, updated_at)
                        VALUES
                            (:template_id, :task_name, :category, :mandatory, :instructions, :owner_team, :sort_order, :check_type, :params, 'ACTIVE', :updated_at)
                        """
                    ),
                    {
                        "template_id": template_id,
                        "task_name": it["task_name"],
                        "category": it["category"],
                        "mandatory": bool(it["mandatory"]),
                        "instructions": it["instructions"],
                        "owner_team": it["owner_team"],
                        "sort_order": it["sort_order"],
                        "check_type": it["check_type"],
                        "params": it["params"],
                        "updated_at": now_str,
                    },
                )

            # Checklist mẫu dùng chung nên mỗi thành viên nhận toàn bộ task của dự án.
            task_rows = conn.execute(
                text("SELECT template_task_id FROM onboarding_template_tasks WHERE template_id = :tid"),
                {"tid": template_id},
            ).mappings().all()

            user_cl_rows = conn.execute(
                text(
                    """
                    SELECT uc.checklist_id
                    FROM user_checklists uc
                    JOIN users u ON u.user_id = uc.user_id
                    WHERE uc.template_id = :tid
                    """
                ),
                {"tid": template_id},
            ).mappings().all()

            for cl in user_cl_rows:
                cid = cl["checklist_id"]
                for tr in task_rows:
                    conn.execute(
                        text(
                            """
                            INSERT INTO user_checklists_tasks
                                (checklist_id, template_task_id, status, created_at, updated_at)
                            VALUES
                                (:cid, :ttid, 'PENDING', :now, :now)
                            ON CONFLICT (checklist_id, template_task_id) DO NOTHING
                            """
                        ),
                        {"cid": cid, "ttid": tr["template_task_id"], "now": now_str},
                    )

        return {
            "status": "ok",
            "imported_count": len(items_to_insert),
            "template_id": template_id,
            "project_code": project_code or "PRJ_ECOMMERCE",
            "message": f"Đã nhập thành công {len(items_to_insert)} mục checklist vào dự án [{project_code or 'PRJ_ECOMMERCE'}].",
            "task_names": [i["task_name"] for i in items_to_insert],
        }
