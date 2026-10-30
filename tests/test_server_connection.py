"""Kiểm tra cấu hình server và health check trước màn hình đăng nhập."""
from __future__ import annotations

import json

import pytest

from frontend.api_client import ApiClient
from frontend.server_config import ServerConfigStore, normalize_server_url, probe_until_connected


def test_normalize_server_url_accepts_host_and_rejects_api_path() -> None:
    assert normalize_server_url(" 192.168.1.20:8765/ ") == "http://192.168.1.20:8765"
    assert normalize_server_url("https://server.internal") == "https://server.internal"

    with pytest.raises(ValueError, match="địa chỉ gốc"):
        normalize_server_url("http://localhost:8765/api/v1")
    with pytest.raises(ValueError, match="http hoặc https"):
        normalize_server_url("ftp://localhost:8765")
    with pytest.raises(ValueError, match="mật khẩu"):
        normalize_server_url("http://user:secret@localhost:8765")


def test_server_config_store_round_trip_and_invalid_fallback(tmp_path) -> None:
    path = tmp_path / "server_settings.json"
    store = ServerConfigStore(path=path, default_url="http://127.0.0.1:8765")

    assert store.load() == "http://127.0.0.1:8765"
    assert store.save("server.local:9000") == "http://server.local:9000"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "server_url": "http://server.local:9000",
    }
    assert store.load() == "http://server.local:9000"

    path.write_text("{invalid", encoding="utf-8")
    assert store.load() == "http://127.0.0.1:8765"


def test_probe_until_connected_retries_then_succeeds() -> None:
    checks = iter([False, False, True])
    clock = [0.0]

    result = probe_until_connected(
        check=lambda: next(checks),
        timeout_seconds=10,
        retry_interval=1,
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert result.connected is True
    assert result.attempts == 3
    assert result.elapsed_seconds == 2


def test_probe_until_connected_reports_timeout() -> None:
    clock = [0.0]
    remaining: list[float] = []

    result = probe_until_connected(
        check=lambda: False,
        timeout_seconds=2,
        retry_interval=1,
        on_retry=remaining.append,
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert result.connected is False
    assert result.attempts == 3
    assert result.elapsed_seconds == 2
    assert remaining == [2, 1, 0]


def test_api_client_health_check_uses_short_timeout(monkeypatch) -> None:
    calls: list[tuple[str, float]] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return b'{"success": true, "data": {"status": "ok"}}'

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr("frontend.api_client.urllib.request.urlopen", fake_urlopen)
    client = ApiClient("http://server.local:8765", timeout=1800)

    assert client.health_check(timeout=1.5) is True
    assert calls == [("http://server.local:8765/api/v1/health/live", 1.5)]


def test_changing_server_clears_previous_session() -> None:
    client = ApiClient("http://old-server:8765")
    client.set_user_email("user@example.com")
    client.set_session_key("old-session")

    client.set_base_url("http://new-server:8765/")

    assert client.base_url == "http://new-server:8765"
    assert client.user_email is None
    assert client.session_key is None


def test_launcher_starts_backend_without_blocking_ui(monkeypatch) -> None:
    import main as launcher

    started: list[bool] = []

    class FakeServer:
        def __init__(self, _config) -> None:
            pass

        def run(self) -> None:
            pass

    class FakeThread:
        def __init__(self, **kwargs) -> None:
            assert kwargs["name"] == "aibuddy-api"
            assert kwargs["daemon"] is True

        def start(self) -> None:
            started.append(True)

    monkeypatch.setattr(launcher, "_api_is_running", lambda: False)
    monkeypatch.setattr(launcher.uvicorn, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(launcher.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(launcher.threading, "Thread", FakeThread)

    launcher._start_backend()

    assert started == [True]
