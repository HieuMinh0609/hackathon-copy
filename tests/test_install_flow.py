"""Kiểm thử luồng cấp phép bằng callback, không cài phần mềm trên máy chạy test."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.core.utils import system_utils as su
from backend.services.verification_service import VerificationResult, VerificationService


def test_preparing_install_does_not_execute(monkeypatch):
    monkeypatch.setattr(su, "detect_package_manager", lambda: "winget")
    def forbidden(*args, **kwargs):
        raise AssertionError("Tạo plan không được chạy subprocess")
    monkeypatch.setattr(su.subprocess, "run", forbidden)
    plan = su.build_install_plan("Git", {"winget": "Git.Git"})
    assert plan.command[:4] == ["winget", "install", "--id", "Git.Git"]
    assert su.build_install_plan("Git", {"winget": "Git.Git\n"}) is None


@pytest.mark.parametrize("error", [PermissionError("denied"), FileNotFoundError(), subprocess.TimeoutExpired("winget", 1)])
def test_install_os_errors_are_friendly(monkeypatch, error):
    def run(*args, **kwargs):
        assert not kwargs.get("shell")
        assert kwargs["stdin"] == subprocess.DEVNULL
        raise error
    monkeypatch.setattr(su.subprocess, "run", run)
    ok, message = su.run_install_plan(su.InstallPlan("Git", "winget", ["winget", "install", "Git.Git"]))
    assert not ok and message


@pytest.mark.parametrize("status,expected", [("passed", True), ("failed", False)])
def test_install_rechecks_and_only_reports_verified_success(monkeypatch, status, expected):
    service = VerificationService(SimpleNamespace())
    calls = []
    monkeypatch.setattr(su, "run_install_plan", lambda plan: (True, "Installed"))
    def verify(key):
        calls.append(key)
        return VerificationResult(key, status, "Version result")
    monkeypatch.setattr(service, "verify_key", verify)
    ok, _ = service.run_install(su.InstallPlan("Git", "winget", ["winget"]), "task_1")
    assert ok is expected and calls == ["task_1"]
    assert not service._install_lock.locked()


def test_install_lock_prevents_parallel_commands(monkeypatch):
    service = VerificationService(SimpleNamespace())
    def forbidden(plan):
        raise AssertionError("Không chạy song song")
    monkeypatch.setattr(su, "run_install_plan", forbidden)
    service._install_lock.acquire()
    try:
        ok, message = service.run_install(su.InstallPlan("Git", "winget", ["winget"]))
        assert not ok and "phần mềm khác" in message
    finally:
        service._install_lock.release()


@pytest.mark.parametrize("confirm", [False, True])
def test_confirmation_dialog_cancel_and_double_click(monkeypatch, confirm):
    # Chỉ giả lập control hiển thị; chạy callback thật để kiểm tra cổng xác nhận.
    def control(*args, **kwargs):
        return SimpleNamespace(**kwargs)
    ft = SimpleNamespace(
        AlertDialog=control, Text=control, Column=control, Container=control,
        TextButton=control, FilledButton=control,
        Icons=SimpleNamespace(CHECK="check"), border=SimpleNamespace(all=lambda *args: None),
    )
    theme = SimpleNamespace(TEXT_MUTED="", TEXT="", SURFACE_ALT="", BORDER="", PRIMARY="")
    monkeypatch.setitem(sys.modules, "flet", ft)
    import frontend
    monkeypatch.setattr(frontend, "theme", theme, raising=False)
    path = Path(__file__).resolve().parents[1] / "frontend/components/confirm_dialog.py"
    spec = importlib.util.spec_from_file_location("install_dialog_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dialogs, events = [], []
    page = SimpleNamespace(open=dialogs.append, close=lambda dlg: None)
    plan = SimpleNamespace(software="Git", display="winget install Git.Git")
    module.confirm_install_dialog(page, plan, lambda: events.append("install"), lambda: events.append("cancel"))
    assert events == []
    action = dialogs[0].actions[1 if confirm else 0]
    action.on_click()
    action.on_click()
    dialogs[0].actions[1].on_click()
    assert events == (["install"] if confirm else ["cancel"])


def test_install_progress_real_step_lifecycle():
    from frontend.install_progress import InstallProgress
    progress = InstallProgress()
    progress.begin("Git")
    assert progress.states == ["running", "pending", "pending", "pending"]
    progress.advance(1, "Chờ xác nhận")
    assert progress.states == ["done", "running", "pending", "pending"]
    progress.advance(2, "Đang cài")
    assert progress.states == ["done", "done", "running", "pending"]
    progress.advance(3, "Kiểm tra phiên bản")
    assert progress.states == ["done", "done", "done", "running"]
    progress.finish("Đạt")
    assert progress.states == ["done"] * 4


def test_progress_cancel_error_and_retry():
    from frontend.install_progress import InstallProgress
    progress = InstallProgress()
    progress.begin("Git")
    progress.advance(1, "Chờ")
    progress.stop("Hủy", cancelled=True)
    assert progress.states == ["done", "cancelled", "pending", "pending"]
    progress.begin("Git")
    progress.advance(2, "Đang cài")
    progress.stop("Thiếu quyền")
    assert progress.states == ["done", "done", "failed", "pending"]
    progress.begin("Python")
    assert progress.states == ["running", "pending", "pending", "pending"]
    assert progress.software == "Python"


def test_install_result_dto_keeps_structured_success():
    from frontend.models import AgentReply
    assert AgentReply.from_dict({"text": "Lỗi", "install_ok": False}).install_ok is False
    assert AgentReply.from_dict({"text": "OK", "install_ok": True}).install_ok is True
    assert AgentReply.from_dict({"text": "Chat thông thường"}).install_ok is None
