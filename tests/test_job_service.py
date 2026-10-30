"""Test background job và contract progress dùng cho polling realtime."""
from __future__ import annotations

import time

from backend.services.job_service import JobService
from frontend.context import KnowledgeGateway


def _wait_for_terminal(service: JobService, job_id: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = service.get(job_id)
        if state and state["status"] in {"completed", "failed"}:
            return state
        time.sleep(0.01)
    raise AssertionError("Job không kết thúc đúng hạn")


def test_job_service_reports_progress_and_result() -> None:
    service = JobService(max_workers=1)

    def task(progress):
        progress(2, 4, "Đã nạp lô 1")
        progress(4, 4, "Đã nạp lô 2")
        return {"files": 2, "chunks": 4, "batches": 2, "errors": []}

    state = _wait_for_terminal(service, service.submit(task))
    assert state["status"] == "completed"
    assert state["percent"] == 100
    assert state["result"]["chunks"] == 4


def test_job_service_exposes_friendly_failure() -> None:
    service = JobService(max_workers=1)

    def task(_progress):
        raise RuntimeError("Ollama chưa chạy")

    state = _wait_for_terminal(service, service.submit(task))
    assert state["status"] == "failed"
    assert "Ollama" in state["error"]


def test_frontend_gateway_polls_until_completed(monkeypatch) -> None:
    class FakeClient:
        calls = 0

        def post(self, path, payload):
            assert path == "/api/v1/documents/ingest-jobs"
            return {"job_id": "job-1"}

        def get(self, path):
            assert path == "/api/v1/jobs/job-1"
            self.calls += 1
            if self.calls == 1:
                return {
                    "status": "running", "current": 5, "total": 10,
                    "message": "50%", "result": None, "error": None,
                }
            return {
                "status": "completed", "current": 10, "total": 10,
                "message": "Hoàn tất", "result": {"files": 1, "chunks": 10, "batches": 1, "errors": []},
                "error": None,
            }

    monkeypatch.setattr("frontend.context.time.sleep", lambda _seconds: None)
    updates = []
    report = KnowledgeGateway(FakeClient()).ingest_paths([], progress=lambda i, n, msg: updates.append((i, n, msg)))
    assert report.chunks == 10
    assert (5, 10, "50%") in updates
    assert (10, 10, "Hoàn tất") in updates

