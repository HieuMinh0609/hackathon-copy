"""Chi tiết tiến trình một bước checklist dựa trên request/kết quả thật."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckRun:
    labels: list[str]
    states: list[str] = field(default_factory=lambda: ["done", "running", "pending"])
    message: str = ""

    @classmethod
    def start(cls, check_type: str, params: dict[str, Any]) -> CheckRun:
        kind = check_type.upper()
        action = {
            "WIFI": "Đọc trạng thái bộ điều hợp Wi-Fi",
            "HOST_REACHABLE": f"Kết nối TCP {params.get('host', '')}:{params.get('port', '')}",
            "PORT_FREE": f"Kiểm tra cổng {params.get('port', '')} trên máy",
            "MANUAL": "Lưu xác nhận của bạn",
        }.get(kind, "Chạy phép kiểm tra đã cấu hình")
        if kind == "SOFTWARE":
            command = str(params.get("command", ""))
            args = params.get("version_args", [] if " " in command else ["--version"])
            action = "Chạy: " + " ".join([command, *map(str, args)])
        return cls(["Đã chuẩn bị bước kiểm tra", action, "Đánh giá và ghi nhận kết quả"])

    def finish(self, result: dict[str, Any]) -> None:
        self.states = ["done", "done", "done" if result["status"].lower() in {"passed", "completed"} else "failed"]
        if result["status"] == "pending":
            self.states = ["done", "pending", "pending"]
        self.message = result.get("message", "")

    def fail(self, message: str) -> None:
        self.states = ["done", "failed", "pending"]
        self.message = message
