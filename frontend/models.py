"""DTO phía frontend, độc lập hoàn toàn với class nội bộ của backend."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class InstallPlan:
    software: str
    manager: str
    command: list[str]
    description: str = ""
    confirmation_token: str = ""
    display_text: str = ""

    @property
    def display(self) -> str:
        return self.display_text or " ".join(self.command)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstallPlan":
        return cls(
            software=data["software"], manager=data["manager"], command=list(data["command"]),
            description=data.get("description", ""), confirmation_token=data.get("confirmation_token", ""),
            display_text=data.get("display", ""),
        )


@dataclass
class AgentReply:
    text: str
    sources: list[str] = field(default_factory=list)
    pending_install: InstallPlan | None = None
    pending_key: str | None = None
    agent: str = "ai_buddy"
    install_ok: bool | None = None
    created_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentReply":
        raw_plan = data.get("pending_install")
        return cls(
            text=data["text"], sources=list(data.get("sources", [])),
            pending_install=InstallPlan.from_dict(raw_plan) if raw_plan else None,
            pending_key=data.get("pending_key"), agent=data.get("agent", "ai_buddy"),
            install_ok=data.get("install_ok"),
            created_at=data.get("created_at"),
        )


@dataclass
class ChecklistItem:
    key: str
    category: str
    title: str
    description: str
    check_type: str
    params: dict[str, Any] = field(default_factory=dict)
    required: bool = True
    status: str = "pending"
    message: str = ""
    updated_at: str | None = None
    template_task_id: int | None = None
    template_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChecklistItem":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})



@dataclass
class IngestReport:
    files: int = 0
    chunks: int = 0
    batches: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        suffix = f"; {len(self.errors)} lỗi" if self.errors else ""
        return f"Đã nạp {self.files} tệp, {self.chunks} chunks{suffix}."


@dataclass
class AppItem:
    app_code: str
    app_name: str
    category: str = "Công cụ chung"
    recommended_version: str = ""
    installer_path: str = ""
    check_command: str = ""
    version_args: str = "--version"
    install_args: str = ""
    description: str = ""
    is_required: bool = True
    is_installed: bool = False
    installed_version: str | None = None
    meets_min: bool = False
    status: str = "NOT_INSTALLED"
    has_installer_file: bool = False
    installer_file_size: int | None = None
    app_id: int | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppItem":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

