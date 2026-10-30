"""Smoke test cho contract API không phụ thuộc PostgreSQL/Ollama."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import pytest

pytest.importorskip("fastapi")

from backend import app as api
from backend.app import IngestRequest, liveness


def test_liveness_does_not_require_external_services() -> None:
    response = liveness()
    assert response.success is True
    assert response.data == {"status": "ok"}


def test_ingest_job_api_returns_progress_and_result(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "documents" / "projects" / "PRJ_TEST"
    project_root.mkdir(parents=True)
    source = project_root / "guide.md"
    source.write_text("Hướng dẫn", encoding="utf-8")

    @dataclass
    class Report:
        files: int = 1
        chunks: int = 3
        batches: int = 1
        errors: list[str] | None = None

    class Projects:
        def get_doc_folder(self, code: str) -> Path:
            assert code == "PRJ_TEST"
            return project_root

    class Knowledge:
        def ingest_paths(self, paths, reset, progress, project_code):
            assert paths == [source]
            progress(1, 3, "Đã nạp 1/3")
            progress(3, 3, "Đã nạp 3/3")
            return Report(errors=[])

    fake_context = type("FakeContext", (), {"projects": Projects(), "knowledge": Knowledge()})()
    monkeypatch.setattr(api, "_context", lambda: fake_context)

    response = api.start_ingest_job(IngestRequest(paths=[str(source)], project_code="PRJ_TEST"))
    job_id = response.data["job_id"]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = api.get_job(job_id).data
        if state["status"] == "completed":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("API job không hoàn tất")

    assert state["percent"] == 100
    assert state["result"]["chunks"] == 3


def test_install_token_owner_key_expiry_and_single_use(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.core.utils.system_utils import InstallPlan

    api._plans.clear()
    calls = []
    def confirm(plan, key):
        calls.append((plan, key))
        return SimpleNamespace(text="OK", sources=[], pending_install=None, pending_key=None, agent="checklist", install_ok=True)
    monkeypatch.setattr(api, "_context", lambda: SimpleNamespace(agent=SimpleNamespace(confirm_install=confirm), checklist=SimpleNamespace(step_blocker=lambda key: None)))
    monkeypatch.setattr(api.time, "monotonic", lambda: 100)
    plan = InstallPlan("Git", "winget", ["winget", "install", "Git.Git"])
    token = api._store_plan(plan, "task_1", "owner")["confirmation_token"]
    owner = SimpleNamespace(state=SimpleNamespace(user_email="owner"))
    other = SimpleNamespace(state=SimpleNamespace(user_email="other"))
    payload = api.ExecuteInstallRequest(confirmation_token=token, key="task_1")
    with pytest.raises(HTTPException) as exc:
        api.execute_install(payload, other)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        api.execute_install(api.ExecuteInstallRequest(confirmation_token=token, key="task_2"), owner)
    assert calls == []
    assert api.execute_install(payload, owner).data["install_ok"] is True
    with pytest.raises(HTTPException):
        api.execute_install(payload, owner)
    assert len(calls) == 1
    token = api._store_plan(plan, "task_1", "owner")["confirmation_token"]
    monkeypatch.setattr(api.time, "monotonic", lambda: 701)
    with pytest.raises(HTTPException):
        api.execute_install(api.ExecuteInstallRequest(confirmation_token=token, key="task_1"), owner)
    assert len(calls) == 1
    api._plans.clear()


def test_manual_api_rejects_locked_step_before_writes(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException

    ctx = SimpleNamespace(
        checklist=SimpleNamespace(
            step_blocker=lambda key, user_email=None: "Cần hoàn thành bước 1 trước."
        )
    )
    monkeypatch.setattr(api, "_context", lambda: ctx)
    with pytest.raises(HTTPException) as exc:
        api.manual(
            "task_2",
            api.ManualRequest(key="task_2", done=True),
            SimpleNamespace(state=SimpleNamespace(user_email="emma.wilson@example.com")),
        )
    assert exc.value.status_code == 409
    assert "bước 1" in exc.value.detail
