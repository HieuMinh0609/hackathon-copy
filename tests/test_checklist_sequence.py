"""Thứ tự checklist: dừng tại lỗi/thủ công, chi tiết phản ánh request thật."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.verification_service import VerificationService, VerificationResult
from frontend.checklist_steps import CheckRun
from frontend.context import VerificationGateway


@pytest.mark.parametrize("first_kind,first_status,expected", [
    ("MANUAL", "pending", []),
    ("MANUAL", "COMPLETED", ["2"]),
    ("SOFTWARE", "passed", ["2"]),
    ("SOFTWARE", "failed", ["1", "2"]),
])
def test_gateway_resumes_first_incomplete_and_waits_for_manual(first_kind, first_status, expected):
    calls = []
    class Client:
        def get(self, path):
            return {"items": [
                {"key": "1", "check_type": first_kind, "status": first_status},
                {"key": "2", "check_type": "SOFTWARE", "status": "pending"},
            ]}
        def post(self, path):
            key = path.split("/")[-2]
            calls.append(key)
            return {"key": key, "status": "passed", "message": "OK"}
    VerificationGateway(Client(), None).verify_all()
    assert calls == expected


def test_backend_rejects_locked_step_without_running_command(monkeypatch):
    item = SimpleNamespace(key="2")
    checklist = SimpleNamespace(get_item=lambda key: item, step_blocker=lambda key: "Hoàn thành bước 1 trước")
    service = VerificationService(checklist)
    def forbidden(item):
        raise AssertionError("Bước khóa không được thực thi")
    monkeypatch.setattr(service, "verify_item", forbidden)
    result = service.verify_key("2")
    assert result.status == "pending"
    assert "bước 1" in result.message


@pytest.mark.parametrize("status", ["failed", "warning", "pending"])
def test_backend_auto_stops_at_unsuccessful_step(monkeypatch, status):
    items = [SimpleNamespace(key=str(i), status="pending", check_type="SOFTWARE") for i in range(3)]
    service = VerificationService(SimpleNamespace(list_items=lambda **kwargs: items))
    calls = []
    def verify(key):
        calls.append(key)
        return VerificationResult(key, status, "Không đạt")
    monkeypatch.setattr(service, "verify_key", verify)
    assert len(service.verify_all()) == 1
    assert calls == ["0"]


def test_details_cover_run_result_transport_error_and_locked_step():
    run = CheckRun.start("SOFTWARE", {"command": "git", "version_args": ["--version"]})
    assert run.labels[1] == "Chạy: git --version"
    assert run.states == ["done", "running", "pending"]
    run.finish({"status": "passed", "message": "Git 2.51"})
    assert run.states == ["done"] * 3
    assert run.message == "Git 2.51"
    run = CheckRun.start("MANUAL", {})
    run.fail("Mất kết nối")
    assert run.states == ["done", "failed", "pending"]
    run.finish({"status": "pending", "message": "Bước trước chưa đạt"})
    assert run.states == ["done", "pending", "pending"]
