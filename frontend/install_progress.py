"""Trạng thái từng bước cài đặt; không giả lập phần trăm tải gói."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InstallProgress:
    software: str = ""
    current: int = 0
    detail: str = ""
    states: list[str] = field(default_factory=lambda: ["pending"] * 4)

    def begin(self, software: str) -> None:
        self.software = software
        self.states = ["pending"] * 4
        self.advance(0, "Đang chuẩn bị lệnh cài đặt…")

    def advance(self, index: int, detail: str) -> None:
        self.current, self.detail = index, detail
        self.states = ["done" if i < index else "running" if i == index else "pending" for i in range(4)]

    def finish(self, detail: str) -> None:
        self.states = ["done"] * 4
        self.detail = detail

    def stop(self, detail: str, cancelled: bool = False) -> None:
        self.states[self.current] = "cancelled" if cancelled else "failed"
        for i in range(self.current + 1, 4):
            self.states[i] = "pending"
        self.detail = detail
