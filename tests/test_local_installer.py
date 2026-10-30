"""Bộ cài từ đường dẫn lưu: chỉ tạo plan, xử lý đúng định dạng và chờ kết quả."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.utils import system_utils as su
from frontend.context import VerificationGateway


@pytest.mark.parametrize("system,suffix,prefix", [
    ("windows", ".exe", []),
    ("windows", ".msi", ["msiexec.exe", "/i"]),
    ("darwin", ".pkg", ["/usr/bin/open", "-W"]),
    ("linux", ".deb", ["dpkg", "-i"]),
])
def test_saved_installer_path_with_spaces_is_one_argument(tmp_path, monkeypatch, system, suffix, prefix):
    installer = tmp_path / ("Bộ cài Git 2.51" + suffix)
    installer.touch()
    monkeypatch.setattr(su, "get_os_name", lambda: system)
    monkeypatch.setattr(su.os, "geteuid", lambda: 0, raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Tạo kế hoạch không được chạy bộ cài")
    monkeypatch.setattr(su.subprocess, "run", forbidden)
    plan = su.build_file_install_plan("Git", installer)
    assert plan.command == [*prefix, str(installer.resolve())]
    assert plan.manager == "local-installer"


def test_install_args_preserved_without_shell(tmp_path, monkeypatch):
    installer = tmp_path / "setup.exe"
    installer.touch()
    monkeypatch.setattr(su, "get_os_name", lambda: "windows")
    plan = su.build_file_install_plan("App", installer, '/quiet "two words"')
    assert plan.command == [str(installer), "/quiet", "two words"]


def test_missing_or_wrong_platform_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "get_os_name", lambda: "darwin")
    with pytest.raises(ValueError, match="Không tìm thấy"):
        su.build_file_install_plan("Git", tmp_path / "missing.pkg")
    installer = tmp_path / "setup.exe"
    installer.touch()
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        su.build_file_install_plan("Git", installer)


def test_windows_installer_uses_uac_runner_and_returns_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(su, "get_os_name", lambda: "windows")
    def elevated(command, timeout):
        calls.append((command, timeout))
        return False, "Bạn đã hủy UAC"
    monkeypatch.setattr(su, "_run_windows_installer", elevated)
    plan = su.InstallPlan("Git", "local-installer", ["C:/Installer Files/git.exe"])
    assert su.run_install_plan(plan, timeout=12) == (False, "Bạn đã hủy UAC")
    assert calls == [(plan.command, 12)]


def test_gateway_only_requests_plan_from_catalog():
    calls = []
    class Client:
        def post(self, path, data):
            calls.append((path, data))
            return {"software": "Git", "manager": "local-installer", "command": ["setup.exe"], "confirmation_token": "single-use"}
    plan = VerificationGateway(Client(), None).catalog_install_plan("git", "task_1")
    assert calls == [("/api/v1/apps/git/install-plan", {"key": "task_1"})]
    assert plan.confirmation_token == "single-use"
