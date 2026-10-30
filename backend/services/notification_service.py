"""Thông báo nội bộ (pub/sub) để UI hiển thị snackbar/toast."""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class Notification:
    level: str  # info | success | warning | error
    message: str
    created_at: datetime = field(default_factory=datetime.now)


class NotificationService:
    def __init__(self, history_size: int = 50) -> None:
        self._subscribers: list[Callable[[Notification], None]] = []
        self._lock = threading.Lock()
        self.history: deque[Notification] = deque(maxlen=history_size)

    def subscribe(self, callback: Callable[[Notification], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Notification], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def notify(self, level: str, message: str) -> Notification:
        note = Notification(level, message)
        self.history.append(note)
        with self._lock:
            subscribers = list(self._subscribers)
        for cb in subscribers:
            try:
                cb(note)
            except Exception:  # một subscriber lỗi không được làm hỏng luồng chính
                log.exception("Notification subscriber failed")
        return note

    def info(self, message: str) -> None:
        self.notify("info", message)

    def success(self, message: str) -> None:
        self.notify("success", message)

    def warning(self, message: str) -> None:
        self.notify("warning", message)

    def error(self, message: str) -> None:
        self.notify("error", message)
