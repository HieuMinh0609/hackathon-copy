"""Ràng buộc biên frontend/backend để tránh import ngược khi phát triển tiếp."""
from __future__ import annotations

import ast
from pathlib import Path

from frontend.models import AgentReply, InstallPlan


FORBIDDEN_FRONTEND_ROOTS = {"backend", "core", "services", "rag", "sqlalchemy", "chromadb"}


def test_frontend_does_not_import_backend_implementation() -> None:
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    violations: list[str] = []
    for path in frontend.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in FORBIDDEN_FRONTEND_ROOTS:
                    violations.append(f"{path.relative_to(frontend)}: {name}")
    assert violations == []


def test_frontend_agent_reply_is_built_from_json_dto() -> None:
    reply = AgentReply.from_dict({
        "text": "OK",
        "sources": ["guide.md"],
        "pending_install": {
            "software": "Git", "manager": "winget", "command": ["winget", "install", "Git.Git"],
            "confirmation_token": "one-time-token", "display": "winget install Git.Git",
        },
        "pending_key": "sw_git",
        "agent": "checklist",
    })
    assert isinstance(reply.pending_install, InstallPlan)
    assert reply.pending_install.confirmation_token == "one-time-token"
    assert reply.pending_install.display == "winget install Git.Git"

