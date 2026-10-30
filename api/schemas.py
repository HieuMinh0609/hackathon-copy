"""Pydantic schemas cho giao tiếp JSON API giữa Frontend và Backend."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ==================== HEALTH ====================
class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    database: str
    database_ok: bool
    ollama_ok: bool = False


# ==================== TEMPLATES / PROJECTS ====================
class TemplateDto(BaseModel):
    template_id: int | None = None
    template_code: str
    code: str
    template_name: str
    name: str
    document_link: str = ""
    doc_folder: str = ""
    description: str = ""
    version: int = 1
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class UpsertTemplateRequest(BaseModel):
    template_code: str
    template_name: str
    document_link: str = ""
    description: str = ""


class DocFolderResponse(BaseModel):
    template_code: str
    doc_folder: str
    exists: bool


class SetDocFolderRequest(BaseModel):
    doc_folder: str


# ==================== CHECKLIST ====================
class ChecklistItemDto(BaseModel):
    key: str
    category: str
    title: str
    description: str = ""
    check_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    status: str = "pending"
    message: str = ""
    updated_at: str | None = None


class ChecklistProgressDto(BaseModel):
    total: int
    percent: int
    passed: int
    failed: int
    warning: int
    pending: int
    required_left: int


class SetManualDoneRequest(BaseModel):
    done: bool = True
    key: str | None = None
    user_id: int | None = None
    user_email: str | None = None
    project_code: str | None = None


class ImportChecklistRequest(BaseModel):
    content: str = Field(min_length=1, description="Nội dung CSV hoặc JSON của checklist")
    project_code: str | None = None
    user_email: str | None = None


# ==================== VERIFICATION ====================
class VerificationResultDto(BaseModel):
    key: str
    status: str
    message: str
    suggestion: str = ""


class InstallPlanDto(BaseModel):
    software: str
    manager: str
    command: list[str]
    description: str = ""


class RunInstallRequest(BaseModel):
    plan: InstallPlanDto
    key: str | None = None


class RunInstallResponse(BaseModel):
    ok: bool
    output: str


# ==================== AGENT / CHAT ====================
class ChatRequest(BaseModel):
    message: str
    project_code: str | None = None
    checklist_mode: bool = False


class AgentReplyDto(BaseModel):
    text: str
    sources: list[str] = Field(default_factory=list)
    pending_install: InstallPlanDto | None = None
    pending_key: str | None = None
    agent: str = "ai_buddy"
    install_ok: bool | None = None
    created_at: str | None = None


class ConfirmInstallRequest(BaseModel):
    plan: InstallPlanDto
    key: str | None = None


# ==================== KNOWLEDGE / RAG ====================
class DocumentDto(BaseModel):
    id: str | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchKnowledgeRequest(BaseModel):
    query: str
    k: int | None = None
    project_code: str | None = None


class SearchResultItemDto(BaseModel):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None


class IngestPathsRequest(BaseModel):
    paths: list[str]
    reset: bool = False
    project_code: str | None = None


class IngestReportDto(BaseModel):
    files: int
    chunks: int
    errors: list[str] = Field(default_factory=list)
    summary: str = ""


# ==================== APP CATALOG ====================
class AppCatalogDto(BaseModel):
    app_id: int | None = None
    app_code: str
    app_name: str
    category: str = "Công cụ chung"
    recommended_version: str | None = None
    installer_path: str | None = None
    check_command: str = ""
    version_args: str = "--version"
    install_args: str | None = None
    description: str | None = None
    is_required: bool = True
    is_installed: bool = False
    installed_version: str | None = None
    meets_min: bool = False
    status: str = "NOT_INSTALLED"
    has_installer_file: bool = False
    installer_file_size: int | None = None
    updated_at: str | None = None


class UpdateAppPathRequest(BaseModel):
    installer_path: str


class CreateAppRequest(BaseModel):
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


class UploadInstallerRequest(BaseModel):
    source_path: str | None = None
    filename: str | None = None
    version: str | None = None


class ExportInstallerRequest(BaseModel):
    destination_dir: str
    version: str | None = None

