"""Dependency container: dựng một lần, truyền cho UI."""
from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings, get_settings
from backend.core.agents.ai_buddy_agent import AiBuddyAgent
from backend.core.agents.checklist_agent import ChecklistAgent
from backend.core.agents.knowledge_agent import KnowledgeAgent
from backend.core.agents.networking_agent import NetworkingAgent
from backend.core.llm import LLMClient
from backend.services.app_catalog_service import AppCatalogService
from backend.services.chat_history_service import ChatHistoryService
from backend.services.checklist_service import ChecklistService
from backend.services.knowledge_service import KnowledgeService
from backend.services.notification_service import NotificationService
from backend.services.project_service import ProjectService
from backend.services.user_service import UserService
from backend.services.verification_service import VerificationService


@dataclass
class AppContext:
    settings: Settings
    notifier: NotificationService
    checklist: ChecklistService
    verification: VerificationService
    knowledge: KnowledgeService
    projects: ProjectService
    users: UserService
    llm: LLMClient
    agent: AiBuddyAgent
    apps: AppCatalogService
    chat_history: ChatHistoryService


def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or get_settings()
    settings.ensure_dirs()
    notifier = NotificationService()
    checklist = ChecklistService(settings, notifier)
    verification = VerificationService(checklist, notifier)
    knowledge = KnowledgeService(settings)
    users = UserService(settings)
    projects = ProjectService(settings)
    apps = AppCatalogService(settings)
    chat_history = ChatHistoryService(settings.database_url)
    llm = LLMClient(settings)
    agent = AiBuddyAgent(
        KnowledgeAgent(knowledge, llm),
        ChecklistAgent(checklist, verification, llm, settings=settings, knowledge=knowledge),
        NetworkingAgent(llm),
    )
    return AppContext(
        settings,
        notifier,
        checklist,
        verification,
        knowledge,
        projects,
        users,
        llm,
        agent,
        apps,
        chat_history,
    )

