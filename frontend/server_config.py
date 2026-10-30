"""Cấu hình kết nối frontend tới backend, lưu cục bộ và không chứa bí mật."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Callable
from urllib.parse import urlsplit

from shared.config import API_BASE_URL


SERVER_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "server_settings.json"


def normalize_server_url(value: str) -> str:
    """Chuẩn hóa URL gốc để mọi API path được ghép nhất quán và an toàn."""
    raw = value.strip()
    if not raw:
        raise ValueError("Vui lòng nhập địa chỉ máy chủ.")
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Địa chỉ máy chủ chỉ hỗ trợ giao thức http hoặc https.")
    if not parsed.hostname:
        raise ValueError("Địa chỉ máy chủ không hợp lệ.")
    if parsed.username or parsed.password:
        raise ValueError("Không nhập tài khoản hoặc mật khẩu trong địa chỉ máy chủ.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Chỉ nhập địa chỉ gốc, ví dụ http://192.168.1.20:8765.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Cổng máy chủ không hợp lệ.") from exc

    return f"{parsed.scheme.lower()}://{parsed.netloc}".rstrip("/")


class ServerConfigStore:
    def __init__(self, path: Path = SERVER_SETTINGS_PATH, default_url: str = API_BASE_URL) -> None:
        self.path = path
        self.default_url = normalize_server_url(default_url)

    def load(self) -> str:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return normalize_server_url(str(data.get("server_url", "")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self.default_url

    def save(self, server_url: str) -> str:
        normalized = normalize_server_url(server_url)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"server_url": normalized}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized


@dataclass(frozen=True)
class ConnectionProbeResult:
    connected: bool
    attempts: int
    elapsed_seconds: float


def probe_until_connected(
    check: Callable[[], bool],
    timeout_seconds: float,
    retry_interval: float = 1.0,
    should_stop: Callable[[], bool] | None = None,
    on_retry: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> ConnectionProbeResult:
    """Thử kết nối tuần tự tới hết hạn; hàm thuần để luồng UI dễ kiểm thử."""
    started = monotonic()
    deadline = started + max(0.0, timeout_seconds)
    attempts = 0

    while True:
        if should_stop and should_stop():
            return ConnectionProbeResult(False, attempts, max(0.0, monotonic() - started))
        attempts += 1
        if check():
            return ConnectionProbeResult(True, attempts, max(0.0, monotonic() - started))

        now = monotonic()
        remaining = max(0.0, deadline - now)
        if on_retry:
            on_retry(remaining)
        if remaining <= 0:
            return ConnectionProbeResult(False, attempts, max(0.0, now - started))
        sleep(min(max(0.0, retry_interval), remaining))
