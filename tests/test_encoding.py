from __future__ import annotations

from types import SimpleNamespace

from shared.encoding import completed_output, decode_process_output


def test_decode_process_output_prefers_utf8() -> None:
    text = "Tiếng Việt 한글"
    assert decode_process_output(text.encode("utf-8")) == text


def test_decode_process_output_supports_native_code_page() -> None:
    assert decode_process_output("café".encode("cp437"), encodings=("utf-8", "cp437")) == "café"


def test_completed_output_accepts_bytes_and_test_strings() -> None:
    stdout, stderr = completed_output(
        SimpleNamespace(stdout="Đã xong".encode("utf-8"), stderr="Cảnh báo")
    )
    assert stdout == "Đã xong"
    assert stderr == "Cảnh báo"
