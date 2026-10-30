"""Dịch vụ lưu trữ và truy vấn lịch sử hội thoại AI theo từng người dùng và từng dự án."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy import text

from backend.services.db import get_connection, init_schema


class ChatHistoryService:
    """Quản lý lịch sử chat của trợ lý AI Buddy theo cặp (user_email, project_code)."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        try:
            init_schema(database_url)
        except Exception:
            pass

    def save_message(
        self,
        user_email: str,
        project_code: str,
        sender: str,
        message: str,
        sources: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Lưu một tin nhắn (từ 'user' hoặc 'ai') vào cơ sở dữ liệu.
        
        Args:
            user_email: Email tài khoản người dùng gửi/nhận tin.
            project_code: Mã dự án hiện tại (hoặc 'general' nếu là chat chung).
            sender: Người gửi ('user' hoặc 'ai').
            message: Nội dung văn bản tin nhắn.
            sources: Danh sách tài liệu/nguồn RAG tham chiếu nếu có.
            metadata: Thông tin bổ sung (checklist_mode, intent, v.v.).
            
        Returns:
            dict chứa thông tin bản ghi vừa lưu.
        """
        clean_email = (user_email or "").strip().lower()
        clean_project = (project_code or "general").strip()
        clean_sender = (sender or "user").strip().lower()
        clean_message = (message or "").strip()
        
        sources_json = json.dumps(sources or [], ensure_ascii=False)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        sql = """
        INSERT INTO chat_history (user_email, project_code, sender, message, sources, metadata, created_at)
        VALUES (:email, :project_code, :sender, :message, :sources, :metadata, :created_at)
        """
        now = datetime.now()

        with get_connection(self.database_url) as conn:
            conn.execute(
                text(sql),
                {
                    "email": clean_email,
                    "project_code": clean_project,
                    "sender": clean_sender,
                    "message": clean_message,
                    "sources": sources_json,
                    "metadata": metadata_json,
                    "created_at": now,
                },
            )

        return {
            "user_email": clean_email,
            "project_code": clean_project,
            "sender": clean_sender,
            "message": clean_message,
            "sources": sources or [],
            "metadata": metadata or {},
            "created_at": now.isoformat(),
        }

    def get_recent_messages(
        self,
        user_email: str,
        project_code: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Lấy danh sách tin nhắn gần nhất (mặc định tối đa 50 tin) sắp xếp theo thứ tự thời gian tăng dần.
        
        Truy vấn lấy LIMIT tin nhắn mới nhất (DESC), sau đó đảo lại (ASC) để hiển thị lịch sử hội thoại tự nhiên từ trên xuống dưới.
        """
        clean_email = (user_email or "").strip().lower()
        clean_project = (project_code or "general").strip()
        limit = max(1, min(int(limit), 100))

        sql = """
        SELECT id, user_email, project_code, sender, message, sources, metadata, created_at
        FROM (
            SELECT id, user_email, project_code, sender, message, sources, metadata, created_at
            FROM chat_history
            WHERE LOWER(user_email) = LOWER(:email) AND project_code = :project_code
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
        ) sub
        ORDER BY created_at ASC, id ASC
        """

        with get_connection(self.database_url) as conn:
            rows = conn.execute(
                text(sql),
                {"email": clean_email, "project_code": clean_project, "limit": limit},
            ).mappings().all()

        results: list[dict[str, Any]] = []
        for r in rows:
            raw_sources = r["sources"]
            raw_metadata = r["metadata"]
            
            try:
                sources = json.loads(raw_sources) if isinstance(raw_sources, str) else (raw_sources or [])
            except Exception:
                sources = []

            try:
                meta = json.loads(raw_metadata) if isinstance(raw_metadata, str) else (raw_metadata or {})
            except Exception:
                meta = {}

            created = r["created_at"]
            created_str = created.isoformat() if hasattr(created, "isoformat") else str(created or "")

            results.append({
                "id": r["id"],
                "user_email": r["user_email"],
                "project_code": r["project_code"],
                "sender": r["sender"],
                "message": r["message"],
                "sources": sources,
                "metadata": meta,
                "created_at": created_str,
            })

        return results

    def clear_history(self, user_email: str, project_code: str) -> int:
        """Xóa toàn bộ lịch sử tin nhắn của một người dùng trong một dự án cụ thể.
        
        Returns:
            Số lượng bản ghi đã xóa.
        """
        clean_email = (user_email or "").strip().lower()
        clean_project = (project_code or "general").strip()

        sql = """
        DELETE FROM chat_history
        WHERE LOWER(user_email) = LOWER(:email) AND project_code = :project_code
        """

        with get_connection(self.database_url) as conn:
            result = conn.execute(
                text(sql),
                {"email": clean_email, "project_code": clean_project},
            )
            return getattr(result, "rowcount", 0) or 0

    def count_messages(self, user_email: str, project_code: str) -> int:
        """Đếm tổng số tin nhắn của người dùng trong một dự án."""
        clean_email = (user_email or "").strip().lower()
        clean_project = (project_code or "general").strip()

        sql = """
        SELECT COUNT(*) AS total
        FROM chat_history
        WHERE LOWER(user_email) = LOWER(:email) AND project_code = :project_code
        """

        with get_connection(self.database_url) as conn:
            row = conn.execute(
                text(sql),
                {"email": clean_email, "project_code": clean_project},
            ).mappings().first()
            return int(row["total"]) if row else 0
