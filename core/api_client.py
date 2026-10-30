"""HTTP JSON API Client cho Frontend: giao tiếp với Backend FastAPI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import httpx
from langchain_core.documents import Document

from backend.core.agents.base import AgentReply
from backend.core.utils.system_utils import InstallPlan
from backend.rag.ingest import IngestReport
from backend.services.checklist_service import ChecklistItem
from backend.services.verification_service import VerificationResult


class ApiClientAgent:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def chat(self, message: str, project_code: str | None = None, checklist_mode: bool = False) -> AgentReply:
        payload = {"message": message, "project_code": project_code, "checklist_mode": checklist_mode}
        res = self.client.post("/api/agent/chat", json=payload)
        res.raise_for_status()
        data = res.json()

        plan = None
        if data.get("pending_install"):
            p_data = data["pending_install"]
            plan = InstallPlan(
                software=p_data["software"],
                manager=p_data["manager"],
                command=p_data["command"],
                description=p_data.get("description", ""),
            )

        return AgentReply(
            text=data.get("text", ""),
            sources=data.get("sources", []),
            pending_install=plan,
            pending_key=data.get("pending_key"),
            agent=data.get("agent", "ai_buddy"),
        )

    def confirm_install(self, plan: InstallPlan, key: str | None = None) -> AgentReply:
        payload = {
            "plan": {
                "software": plan.software,
                "manager": plan.manager,
                "command": plan.command,
                "description": plan.description,
            },
            "key": key,
        }
        res = self.client.post("/api/agent/confirm-install", json=payload)
        res.raise_for_status()
        data = res.json()
        return AgentReply(
            text=data.get("text", ""),
            sources=data.get("sources", []),
            agent=data.get("agent", "ai_buddy"),
        )


class ApiClientChecklist:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def list_items(self, category: str | None = None) -> list[ChecklistItem]:
        params = {"category": category} if category else {}
        res = self.client.get("/api/checklist/items", params=params)
        res.raise_for_status()
        items = []
        for d in res.json():
            items.append(
                ChecklistItem(
                    key=d["key"],
                    category=d["category"],
                    title=d["title"],
                    description=d.get("description", ""),
                    check_type=d["check_type"],
                    params=d.get("params", {}),
                    required=d.get("required", True),
                    status=d.get("status", "pending"),
                    message=d.get("message", ""),
                    updated_at=d.get("updated_at"),
                )
            )
        return items

    def get_item(self, key: str) -> ChecklistItem | None:
        res = self.client.get(f"/api/checklist/items/{key}")
        if res.status_code == 404:
            return None
        res.raise_for_status()
        d = res.json()
        return ChecklistItem(
            key=d["key"],
            category=d["category"],
            title=d["title"],
            description=d.get("description", ""),
            check_type=d["check_type"],
            params=d.get("params", {}),
            required=d.get("required", True),
            status=d.get("status", "pending"),
            message=d.get("message", ""),
            updated_at=d.get("updated_at"),
        )

    def progress(self) -> dict[str, Any]:
        res = self.client.get("/api/checklist/progress")
        res.raise_for_status()
        return res.json()

    def set_manual_done(self, key: str, done: bool) -> None:
        res = self.client.post(f"/api/checklist/items/{key}/manual", json={"done": done})
        res.raise_for_status()

    def reset(self) -> None:
        res = self.client.post("/api/checklist/reset")
        res.raise_for_status()

    def export_report(self) -> Path:
        res = self.client.post("/api/checklist/export")
        res.raise_for_status()
        return Path(res.json().get("export_path", ""))


class ApiClientVerification:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def verify_key(self, key: str) -> VerificationResult:
        res = self.client.post("/api/verification/verify-key", params={"key": key})
        res.raise_for_status()
        d = res.json()
        return VerificationResult(
            key=d["key"],
            status=d["status"],
            message=d["message"],
            suggestion=d.get("suggestion", ""),
        )

    def verify_all(
        self, on_progress: Callable[[int, int, VerificationResult], None] | None = None
    ) -> list[VerificationResult]:
        res = self.client.post("/api/verification/verify-all")
        res.raise_for_status()
        results = [
            VerificationResult(
                key=d["key"],
                status=d["status"],
                message=d["message"],
                suggestion=d.get("suggestion", ""),
            )
            for d in res.json()
        ]
        if on_progress and results:
            for idx, r in enumerate(results, start=1):
                on_progress(idx, len(results), r)
        return results

    def install_plan(self, item: ChecklistItem) -> InstallPlan | None:
        res = self.client.get(f"/api/verification/install-plan/{item.key}")
        if res.status_code == 404:
            return None
        res.raise_for_status()
        d = res.json()
        if not d:
            return None
        return InstallPlan(
            software=d["software"],
            manager=d["manager"],
            command=d["command"],
            description=d.get("description", ""),
        )

    def run_install(self, plan: InstallPlan, key: str | None = None) -> tuple[bool, str]:
        payload = {
            "plan": {
                "software": plan.software,
                "manager": plan.manager,
                "command": plan.command,
                "description": plan.description,
            },
            "key": key,
        }
        res = self.client.post("/api/verification/run-install", json=payload)
        res.raise_for_status()
        d = res.json()
        return bool(d.get("ok")), d.get("output", "")


class ApiClientProjects:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def list_projects(self) -> list[dict[str, Any]]:
        res = self.client.get("/api/templates")
        res.raise_for_status()
        return res.json()

    def list_templates(self) -> list[dict[str, Any]]:
        return self.list_projects()

    def get_project(self, code: str) -> dict[str, Any] | None:
        res = self.client.get(f"/api/templates/{code}")
        if res.status_code == 404:
            return None
        res.raise_for_status()
        return res.json()

    def get_template(self, code: str) -> dict[str, Any] | None:
        return self.get_project(code)

    def get_doc_folder(self, code: str) -> Path:
        res = self.client.get(f"/api/templates/{code}/doc-folder")
        if res.status_code == 404:
            return Path("documents")
        res.raise_for_status()
        return Path(res.json().get("doc_folder", "documents"))

    def set_doc_folder(self, code: str, folder_path: str) -> bool:
        res = self.client.put(f"/api/templates/{code}/doc-folder", json={"doc_folder": folder_path})
        return res.status_code == 200

    def set_document_link(self, code: str, document_link: str) -> bool:
        return self.set_doc_folder(code, document_link)

    def upsert_project(
        self, code: str, name: str, description: str = "", doc_folder: str = ""
    ) -> None:
        payload = {
            "template_code": code,
            "template_name": name,
            "document_link": doc_folder,
            "description": description,
        }
        res = self.client.post("/api/templates", json=payload)
        res.raise_for_status()

    def upsert_template(
        self, template_code: str, template_name: str, document_link: str = "", **kwargs: Any
    ) -> None:
        self.upsert_project(template_code, template_name, doc_folder=document_link)


class ApiClientKnowledge:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def list_projects(self) -> list[str]:
        res = self.client.get("/api/knowledge/projects")
        res.raise_for_status()
        return res.json()

    def get_project_docs(self, project_code: str) -> list[Document]:
        res = self.client.get("/api/knowledge/documents", params={"project_code": project_code})
        res.raise_for_status()
        docs = []
        for d in res.json():
            docs.append(Document(page_content=d.get("content", ""), metadata=d.get("metadata", {})))
        return docs

    def ingest_paths(
        self,
        paths: list[Path],
        reset: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        batch_size: int = 48,
        max_workers: int = 3,
        project_code: str | None = None,
    ) -> IngestReport:
        payload = {
            "paths": [str(p) for p in paths],
            "reset": reset,
            "project_code": project_code,
        }
        res = self.client.post("/api/knowledge/ingest-paths", json=payload)
        res.raise_for_status()
        d = res.json()
        report = IngestReport(
            files=d.get("files", 0),
            chunks=d.get("chunks", 0),
            errors=d.get("errors", []),
        )
        if progress:
            progress(report.files, report.files, f"Hoàn tất: {report.chunks} chunks")
        return report

    def ingest_all(
        self,
        reset: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        batch_size: int = 48,
        max_workers: int = 3,
        project_code: str | None = None,
    ) -> IngestReport:
        params: dict[str, Any] = {"reset": reset}
        if project_code:
            params["project_code"] = project_code
        res = self.client.post("/api/knowledge/ingest-all", params=params)
        res.raise_for_status()
        d = res.json()
        report = IngestReport(
            files=d.get("files", 0),
            chunks=d.get("chunks", 0),
            errors=d.get("errors", []),
        )
        if progress:
            progress(report.files, report.files, f"Hoàn tất: {report.chunks} chunks")
        return report


class ApiClient:
    """Client tổng hợp kết nối tới AI Buddy Backend REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 120.0,
        http_client: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http_client or httpx.Client(base_url=self.base_url, timeout=timeout)

        self.agent = ApiClientAgent(self.http)
        self.checklist = ApiClientChecklist(self.http)
        self.verification = ApiClientVerification(self.http)
        self.projects = ApiClientProjects(self.http)
        self.templates = self.projects
        self.knowledge = ApiClientKnowledge(self.http)

    def ping(self) -> bool:
        try:
            res = self.http.get("/api/health", timeout=3.0)
            return res.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        self.http.close()
