"""Kiểm tra Auto dùng lệnh chỉ đọc và phát tiến độ đúng lúc."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from backend.core.utils import network_utils as nu, system_utils as su
from frontend.context import VerificationGateway


@pytest.mark.parametrize("system,outputs,expected", [
    ("Windows", ["State : connected\n BSSID : 12:34:56:78:90:ab"], True),
    ("Windows", ["State : disconnected"], False),
    ("Linux", ["wifi:connected\nethernet:disconnected"], True),
    ("Linux", ["ethernet:connected\nwifi:disconnected"], False),
    ("Darwin", ["Hardware Port: Wi-Fi\nDevice: en0\n", "Current Wi-Fi Network: Office"], True),
    ("Darwin", ["Hardware Port: Wi-Fi\nDevice: en0\n", "You are not associated with an AirPort network."], False),
])
def test_wifi_local_readonly_commands(monkeypatch, system, outputs, expected):
    monkeypatch.setattr(nu.platform, "system", lambda: system)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        assert isinstance(command, list)
        assert not kwargs.get("shell")
        assert kwargs["timeout"] == 8
        return SimpleNamespace(returncode=0, stdout=outputs.pop(0))
    monkeypatch.setattr(nu.subprocess, "run", run)
    ok, message = nu.check_wifi()
    assert ok is expected
    assert message
    assert commands[0][0] in {"netsh", "nmcli", "networksetup"}
    if ok:
        assert "không xác nhận Internet" in message


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("netsh", 8), OSError("denied")])
def test_wifi_unavailable_does_not_crash(monkeypatch, error):
    monkeypatch.setattr(nu.platform, "system", lambda: "Windows")
    def run(*args, **kwargs):
        raise error
    monkeypatch.setattr(nu.subprocess, "run", run)
    assert nu.check_wifi()[0] is False


@pytest.mark.parametrize("code,output", [(1, "git version 9.0"), (0, "unknown")])
def test_version_check_cannot_pass_on_error(monkeypatch, code, output):
    monkeypatch.setattr(su.shutil, "which", lambda _: "/tools/git")
    monkeypatch.setattr(su.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code, stdout=output, stderr=""))
    status = su.check_software("Git", "git")
    assert not status.meets_min
    assert status.error


def test_version_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(su.shutil, "which", lambda _: "/tools/git")
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 10)
    monkeypatch.setattr(su.subprocess, "run", run)
    result = su.check_software("Git", "git")
    assert not result.meets_min
    assert "thời gian" in result.message


def test_gateway_stops_on_first_failure_and_keeps_project_filter():
    events = []
    class Client:
        def get(self, url):
            assert url == "/api/v1/checklist?project_code=PRJ_TEST"
            return {"items": [
                {"key": "1", "title": "Git", "check_type": "SOFTWARE"},
                {"key": "2", "title": "Read docs", "check_type": "MANUAL"},
                {"key": "3", "title": "Wi-Fi", "check_type": "WIFI"},
            ]}
        def post(self, url):
            key = url.split("/")[-2]
            events.append(("run", key))
            return {"key": key, "status": "failed" if key == "1" else "passed", "message": "result"}
    result = VerificationGateway(Client(), None).verify_all(
        project_code="PRJ_TEST",
        on_current=lambda i, n, item: events.append(("start", item["key"])),
        on_progress=lambda i, n, item: events.append(("done", item["key"])),
    )
    assert events == [("start", "1"), ("run", "1"), ("done", "1")]
    assert len(result) == 1


def test_version_checks_reject_executable_code(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Không được thực thi tham số ngoài danh sách kiểm tra")
    monkeypatch.setattr(su.subprocess, "run", unexpected)
    result = su.check_software("Python", "python", ["-c", "print('unsafe')"])
    assert not result.meets_min
    assert "Tham số" in result.message
