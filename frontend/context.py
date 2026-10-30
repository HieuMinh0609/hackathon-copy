"""Các gateway frontend gọi backend qua JSON, không import lớp nghiệp vụ backend."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable
from urllib.parse import quote

from frontend.api_client import ApiClient, ApiError
from frontend.models import AgentReply, AppItem, ChecklistItem, IngestReport, InstallPlan
from shared.config import API_BASE_URL


@dataclass
class Notification:
    level: str
    message: str


class NotificationService:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[Notification], None]] = []

    def subscribe(self, callback: Callable[[Notification], None]) -> None:
        self._subscribers.append(callback)

    def notify(self, level: str, message: str) -> None:
        for callback in list(self._subscribers):
            callback(Notification(level, message))

    def info(self, message: str) -> None: self.notify("info", message)
    def success(self, message: str) -> None: self.notify("success", message)
    def warning(self, message: str) -> None: self.notify("warning", message)
    def error(self, message: str) -> None: self.notify("error", message)


class FrontendSettings:
    def __init__(self, client: ApiClient, data: dict[str, Any] | None = None) -> None:
        self._client = client
        if data:
            self._apply(data)
        else:
            self._apply_defaults()

    def _apply_defaults(self) -> None:
        self.ollama_base_url = "http://127.0.0.1:11434"
        self.llm_model = "qwen2.5:7b"
        self.embedding_model = "bge-m3"
        self.user_role = "onboarding"
        self.roles = {
            "onboarding": "Thành viên mới (Onboarding)",
            "backend_developer": "Lập trình viên Backend",
            "frontend_developer": "Lập trình viên Frontend",
            "hr": "Nhân sự & Vận hành",
        }
        self.documents_dir = Path("documents")
        self.database_description = "PostgreSQL"

    def load(self) -> None:
        """Tải cấu hình từ backend khi đã xác thực."""
        try:
            data = self._client.get("/api/v1/settings")
            self._apply(data)
        except Exception:
            pass

    def _apply(self, data: dict[str, Any]) -> None:
        self.ollama_base_url = data.get("ollama_base_url", "http://127.0.0.1:11434")
        self.llm_model = data.get("llm_model", "qwen2.5:7b")
        self.embedding_model = data.get("embedding_model", "bge-m3")
        self.user_role = data.get("user_role", "onboarding")
        self.roles = dict(data.get("roles", {}))
        self.documents_dir = Path(data.get("documents_dir", "documents"))
        self.database_description = data.get("database_description", "")

    def save_user_overrides(self) -> None:
        data = self._client.put("/api/v1/settings", {
            "ollama_base_url": self.ollama_base_url,
            "llm_model": self.llm_model,
            "embedding_model": self.embedding_model,
            "user_role": self.user_role,
        })
        self._apply(data)


class AgentGateway:
    def __init__(self, client: ApiClient) -> None: self.client = client
    def chat(
        self,
        message: str,
        project_code: str | None = None,
        checklist_mode: bool = False,
        request_id: str | None = None,
    ) -> AgentReply:
        return AgentReply.from_dict(self.client.post("/api/v1/chat", {
            "message": message,
            "project_code": project_code,
            "checklist_mode": checklist_mode,
            "request_id": request_id,
        }))
    def cancel_chat(self, request_id: str, project_code: str | None = None) -> dict[str, Any]:
        return self.client.post("/api/v1/chat/cancel", {
            "request_id": request_id,
            "project_code": project_code or "general",
        })
    def confirm_install(self, plan: InstallPlan, key: str | None = None) -> AgentReply:
        return AgentReply.from_dict(self.client.post("/api/v1/install/execute", {
            "confirmation_token": plan.confirmation_token, "key": key,
        }))
    def get_history(self, project_code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        code = quote(project_code or "general")
        return self.client.get(f"/api/v1/chat/history?project_code={code}&limit={limit}")
    def save_message(
        self,
        message: str,
        project_code: str | None = None,
        sender: str = "ai",
        sources: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.client.post("/api/v1/chat/history", {
            "message": message,
            "project_code": project_code or "general",
            "sender": sender,
            "sources": sources or [],
            "metadata": metadata or {},
        })
    def clear_history(self, project_code: str | None = None) -> dict[str, Any]:
        code = quote(project_code or "general")
        return self.client.delete(f"/api/v1/chat/history?project_code={code}")


class ChecklistGateway:
    def __init__(self, client: ApiClient) -> None: self.client = client
    def _snapshot(self, project_code: str | None = None, user_email: str | None = None) -> dict[str, Any]:
        params = []
        if project_code:
            params.append(f"project_code={quote(project_code)}")
        email = user_email or getattr(self.client, "user_email", None)
        if email:
            params.append(f"user_email={quote(email)}")
        qs = f"?{'&'.join(params)}" if params else ""
        return self.client.get(f"/api/v1/checklist{qs}")
    def list_items(
        self,
        category: str | None = None,
        project_code: str | None = None,
        user_email: str | None = None,
    ) -> list[ChecklistItem]:
        items = [ChecklistItem.from_dict(row) for row in self._snapshot(project_code=project_code, user_email=user_email)["items"]]
        return [item for item in items if item.category == category] if category else items
    def get_item(self, key: str) -> ChecklistItem | None:
        try: return ChecklistItem.from_dict(self.client.get(f"/api/v1/checklist/{quote(key)}"))
        except Exception: return None
    def progress(self, project_code: str | None = None, user_email: str | None = None) -> dict[str, Any]:
        return self._snapshot(project_code=project_code, user_email=user_email)["progress"]
    def categories(self, project_code: str | None = None, user_email: str | None = None) -> list[str]:
        return list(dict.fromkeys(i.category for i in self.list_items(project_code=project_code, user_email=user_email)))
    def set_manual_done(
        self,
        key: str,
        done: bool,
        user_id: int | None = None,
        user_email: str | None = None,
        project_code: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"key": key, "done": done}
        if user_id:
            payload["user_id"] = user_id
        if user_email:
            payload["user_email"] = user_email
        if project_code:
            payload["project_code"] = project_code
        self.client.put(f"/api/v1/checklist/{quote(key)}/manual", payload)
    def reset(self) -> None: self.client.delete("/api/v1/checklist")
    def export_report(self) -> Path: return Path(self.client.post("/api/v1/checklist/export")["path"])
    def get_sample_template(self, project_code: str) -> dict[str, Any]:
        return self.client.get(f"/api/v1/checklist/template-sample?project_code={quote(project_code)}")
    def import_checklist(
        self,
        content: str,
        project_code: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content}
        if project_code:
            payload["project_code"] = project_code
        if user_email:
            payload["user_email"] = user_email
        return self.client.post("/api/v1/checklist/import", payload)


class VerificationGateway:
    def __init__(self, client: ApiClient, agent: AgentGateway) -> None: self.client, self.agent = client, agent
    def install_plan(self, item: ChecklistItem | None) -> InstallPlan | None:
        if item is None: return None
        data = self.client.post("/api/v1/install/plan", {"key": item.key})
        return InstallPlan.from_dict(data) if data else None
    def catalog_install_plan(self, app_code: str, key: str) -> InstallPlan:
        return InstallPlan.from_dict(self.client.post(
            f"/api/v1/apps/{quote(app_code, safe='')}/install-plan", {"key": key},
        ))

    def verify_all(
        self, on_progress: Any = None, project_code: str | None = None,
        on_current: Any = None,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        # Mỗi response là kết quả thật; UI cập nhật ngay, không phát lại tiến độ sau cùng.
        params = []
        if project_code:
            params.append(f"project_code={quote(project_code)}")
        email = user_email or getattr(self.client, "user_email", None)
        if email:
            params.append(f"user_email={quote(email)}")
        qs = f"?{'&'.join(params)}" if params else ""
        items = self.client.get(f"/api/v1/checklist{qs}")["items"]
        results = []
        for index, item in enumerate(items, 1):
            if item.get("status", "").lower() in {"passed", "completed"}:
                continue
            if (item.get("check_type") or "MANUAL").upper() == "MANUAL":
                break
            if on_current:
                on_current(index, len(items), item)
            result = self.verify_key(item["key"])
            results.append(result)
            if on_progress:
                on_progress(index, len(items), result)
            if result["status"] != "passed":
                break
        return results
    def verify_key(self, key: str) -> dict[str, Any]: return self.client.post(f"/api/v1/checklist/{quote(key)}/verify")
    def run_install(self, plan: InstallPlan, key: str | None = None) -> tuple[bool, str]:
        reply = self.agent.confirm_install(plan, key)
        return ("thành công" in reply.text.lower(), reply.text)


class ProjectGateway:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def list_projects(self, user_email: str | None = None) -> list[dict[str, Any]]:
        email = user_email or getattr(self.client, "user_email", None)
        qs = f"?user_email={quote(email)}" if email else ""
        return self.client.get(f"/api/v1/projects{qs}")
    def create_project(
        self,
        code: str,
        name: str,
        description: str = "",
        role_name: str = "Developer",
        duration_days: int = 20,
    ) -> dict[str, Any]:
        return self.client.post("/api/v1/projects", {
            "code": code,
            "name": name,
            "description": description,
            "role_name": role_name,
            "duration_days": duration_days,
        })
    def list_members(self, code: str, query: str | None = None) -> list[dict[str, Any]]:
        qs = f"?q={quote(query)}" if query else ""
        return self.client.get(f"/api/v1/projects/{quote(code)}/members{qs}")
    def add_member(
        self,
        code: str,
        user_email: str,
        project_role_key: str = "MEMBER",
        user_name: str = "",
        department: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user_email": user_email,
            "user_name": user_name,
            "department": department,
            "project_role_key": project_role_key,
        }
        return self.client.post(f"/api/v1/projects/{quote(code)}/members", payload)
    def add_members_batch(
        self,
        code: str,
        members: list[dict[str, Any]] | None = None,
        user_emails: list[str] | None = None,
        project_role_key: str = "MEMBER",
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {}
        if members:
            payload["members"] = members
        if user_emails:
            payload["user_emails"] = user_emails
        payload["project_role_key"] = project_role_key
        return self.client.post(f"/api/v1/projects/{quote(code)}/members/batch", payload)
    def list_roles(self) -> list[dict[str, Any]]:
        return self.client.get("/api/v1/roles")
    def remove_member(self, code: str, user_email: str) -> bool:
        res = self.client.delete(f"/api/v1/projects/{quote(code)}/members/{quote(user_email)}")
        return bool(res.get("removed", True))
    def get_doc_folder(self, code: str) -> Path:
        return Path(self.client.get(f"/api/v1/projects/{quote(code)}/document-folder")["path"])
    def list_documents(self, code: str) -> dict[str, Any]:
        return self.client.get(f"/api/v1/projects/{quote(code)}/documents")
    def copy_documents(self, code: str, paths: list[Path]) -> int:
        data = self.client.post(f"/api/v1/projects/{quote(code)}/documents", {"source_paths": [str(p) for p in paths]})
        return int(data["copied"])
    def delete_document(self, code: str, path: Path) -> None:
        self.client.delete(f"/api/v1/projects/{quote(code)}/documents", {"path": str(path)})
    def export_document(self, code: str, source: Path, destination: Path) -> Path:
        data = self.client.post(f"/api/v1/projects/{quote(code)}/documents/export", {
            "source_path": str(source), "destination_path": str(destination),
        })
        return Path(data["path"])


class KnowledgeGateway:
    def __init__(self, client: ApiClient) -> None: self.client = client
    def ingest_paths(self, paths: list[Path], reset: bool = False, progress: Any = None, project_code: str | None = None) -> IngestReport:
        if progress:
            progress(0, 1, "Đang tạo tiến trình nạp tài liệu…")
        started = self.client.post("/api/v1/documents/ingest-jobs", {
            "paths": [str(p) for p in paths], "reset": reset, "project_code": project_code,
        })
        job_id = started["job_id"]
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            state = self.client.get(f"/api/v1/jobs/{quote(job_id)}")
            if progress:
                progress(state["current"], state["total"], state["message"])
            if state["status"] == "completed":
                return IngestReport(**(state["result"] or {}))
            if state["status"] == "failed":
                raise ApiError(state["error"] or "Nạp tài liệu thất bại.")
            time.sleep(0.4)
        raise ApiError("Tiến trình nạp tài liệu quá thời gian 30 phút.")
    def ingest_all(self, reset: bool = False, progress: Any = None) -> IngestReport:
        return self.ingest_paths([], reset=reset, progress=progress)


class AppCatalogGateway:
    def __init__(self, client: ApiClient) -> None: self.client = client
    def list_apps(self, query: str | None = None, category: str | None = None) -> list[AppItem]:
        params = []
        if query: params.append(f"query={quote(query)}")
        if category and category != "Tất cả": params.append(f"category={quote(category)}")
        qs = f"?{'&'.join(params)}" if params else ""
        rows = self.client.get(f"/api/v1/apps{qs}")
        return [AppItem.from_dict(r) for r in rows]

    def categories(self) -> list[str]:
        return list(self.client.get("/api/v1/apps/categories"))

    def get_app(self, app_code: str) -> AppItem | None:
        try:
            return AppItem.from_dict(self.client.get(f"/api/v1/apps/{quote(app_code)}"))
        except Exception:
            return None

    def update_path(self, app_code: str, installer_path: str) -> AppItem:
        res = self.client.put(f"/api/v1/apps/{quote(app_code)}/path", {"installer_path": installer_path})
        return AppItem.from_dict(res)

    def update_app(self, app_code: str, data: dict[str, Any]) -> AppItem:
        res = self.client.put(f"/api/v1/apps/{quote(app_code)}", data)
        return AppItem.from_dict(res)

    def check_app(self, app_code: str) -> dict[str, Any]:
        return self.client.post(f"/api/v1/apps/{quote(app_code)}/check")

    def create_app(self, data: dict[str, Any]) -> AppItem:
        res = self.client.post("/api/v1/apps", data)
        return AppItem.from_dict(res)

    def upload_installer(
        self,
        app_code: str,
        source_path: str,
        filename: str | None = None,
        version: str | None = None,
    ) -> AppItem:
        payload: dict[str, Any] = {"source_path": source_path, "filename": filename}
        if version:
            payload["version"] = version
        res = self.client.post(
            f"/api/v1/apps/{quote(app_code)}/upload",
            payload,
        )
        return AppItem.from_dict(res)

    def download_installer(
        self,
        app_code: str,
        destination_path: Path | str,
        exact_path: bool = False,
        on_progress: Any = None,
    ) -> Path:
        return self.client.download_file(
            f"/api/v1/apps/{quote(app_code)}/download",
            destination_path,
            exact_path=exact_path,
            on_progress=on_progress,
        )

    def export_installer(self, app_code: str, destination_dir: str, version: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"destination_dir": destination_dir}
        if version:
            payload["version"] = version
        return self.client.post(f"/api/v1/apps/{quote(app_code)}/export", payload)

    def delete_app(self, app_code: str) -> bool:
        res = self.client.delete(f"/api/v1/apps/{quote(app_code)}")
        return bool(res.get("deleted", True)) if isinstance(res, dict) else bool(res)


@dataclass
class FrontendContext:
    client: ApiClient
    settings: FrontendSettings
    notifier: NotificationService
    agent: AgentGateway
    checklist: ChecklistGateway
    verification: VerificationGateway
    knowledge: KnowledgeGateway
    projects: ProjectGateway
    apps: AppCatalogGateway

    def ollama_status(self) -> dict[str, Any]: return self.client.get("/api/v1/status/ollama")
    def database_status(self) -> dict[str, Any]: return self.client.get("/api/v1/status/database")
    def login(self, email: str, password: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"email": email}
        if password is not None and password != "":
            payload["password"] = password
        data = self.client.post("/api/v1/auth/login", payload)
        self.client.set_user_email(data.get("email"))
        session_key = data.get("session_key")
        if session_key:
            self.client.set_session_key(session_key)
        self.settings.load()
        return data

    def logout(self) -> None:
        self.client.set_user_email(None)
        self.client.set_session_key(None)

    def list_users(self) -> list[dict[str, Any]]:
        return self.client.get("/api/v1/auth/users")


def build_frontend_context(base_url: str = API_BASE_URL) -> FrontendContext:
    client = ApiClient(base_url)
    settings = FrontendSettings(client, None)
    notifier = NotificationService()
    agent = AgentGateway(client)
    checklist = ChecklistGateway(client)
    apps = AppCatalogGateway(client)
    return FrontendContext(
        client, settings, notifier, agent, checklist, VerificationGateway(client, agent),
        KnowledgeGateway(client), ProjectGateway(client), apps,
    )
