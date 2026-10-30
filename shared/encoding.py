"""Chuẩn hóa UTF-8 cho console và output của tiến trình con."""
from __future__ import annotations

import locale
import os
import sys
from collections.abc import Iterable
from typing import Any


def configure_utf8_stdio() -> None:
    """Ép stdout/stderr dùng UTF-8 để Windows không lỗi khi in tiếng Việt/Hangul."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Một số runner đã đóng hoặc thay stream bằng object chỉ đọc.
            continue


def decode_process_output(
    value: bytes | str | None,
    encodings: Iterable[str] | None = None,
) -> str:
    """Giải mã output, ưu tiên UTF-8 rồi code page OEM trên Windows.

    Native Windows tools có thể trả OEM trong khi PowerShell hiện đại trả UTF-8.
    Thử strict theo thứ tự giúp tránh biến UTF-8 hợp lệ thành mojibake cp1252.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value

    candidates = list(encodings or ())
    if not candidates:
        candidates.append("utf-8")
        if os.name == "nt":
            candidates.append("oem")
        candidates.append(locale.getpreferredencoding(False))

    seen: set[str] = set()
    for encoding in candidates:
        normalized = (encoding or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return value.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue

    fallback = "utf-8" if "utf-8" in seen else next(iter(seen), "utf-8")
    try:
        return value.decode(fallback, errors="replace")
    except LookupError:
        return value.decode("utf-8", errors="replace")


def completed_output(process: Any, encodings: Iterable[str] | None = None) -> tuple[str, str]:
    """Lấy stdout/stderr đã giải mã từ CompletedProcess hoặc test double."""
    return (
        decode_process_output(getattr(process, "stdout", None), encodings),
        decode_process_output(getattr(process, "stderr", None), encodings),
    )
