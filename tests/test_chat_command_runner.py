from __future__ import annotations

import pytest

from frontend.components.message_bubble import MessageBubble, extract_runnable_commands


def test_extract_runnable_commands_various_blocks():
    text = (
        "Chào bạn, dưới đây là cách kiểm tra môi trường:\n\n"
        "```bash\npython --version\n```\n\n"
        "Và lệnh kiểm tra cổng:\n"
        "```cmd\nnetstat -ano | findstr :5432\n```\n\n"
        "Lệnh PowerShell:\n"
        "```powershell\nGet-Service -Name postgresql\n```\n\n"
        "Code Python mẫu (không phải lệnh chạy cmd):\n"
        "```python\ndef foo():\n    return 42\n```\n"
    )

    cmds = extract_runnable_commands(text)
    assert len(cmds) == 3
    assert "python --version" in cmds
    assert "netstat -ano | findstr :5432" in cmds
    assert "Get-Service -Name postgresql" in cmds
    assert not any("def foo" in c for c in cmds)


def test_extract_runnable_commands_ignores_json_and_sql():
    text = (
        "Cấu hình JSON:\n```json\n{\n  \"key\": \"value\"\n}\n```\n\n"
        "Truy vấn SQL:\n```sql\nSELECT * FROM app_catalog;\n```\n"
    )
    cmds = extract_runnable_commands(text)
    assert len(cmds) == 0


def test_extract_runnable_commands_empty():
    assert extract_runnable_commands("") == []
    assert extract_runnable_commands("Không có code block nào") == []


def test_message_bubble_creates_cards_for_commands():
    calls = []
    text = "Chạy lệnh này:\n```bash\necho 'hello buddy'\n```"
    bubble = MessageBubble(
        text=text,
        is_user=False,
        on_run_command=lambda c: calls.append(c),
    )
    # Kiểm tra bubble được tạo thành công
    assert bubble is not None
    assert bubble.on_run_command is not None


def test_extract_runnable_commands_inline_and_prompts():
    text = (
        "Bạn hãy chạy lệnh `netstat -ano | findstr :5432` để kiểm tra cổng kết nối.\n"
        "Sau đó chạy `python --version` và `Test-NetConnection -ComputerName 127.0.0.1 -Port 5432`.\n"
        "Lệnh khác: `ollama serve` hoặc xem `docker ps`.\n"
        "Bỏ qua tên file: `config/settings.py` và giá trị `true`."
    )
    cmds = extract_runnable_commands(text)
    assert "netstat -ano | findstr :5432" in cmds
    assert "python --version" in cmds
    assert "Test-NetConnection -ComputerName 127.0.0.1 -Port 5432" in cmds
    assert "ollama serve" in cmds
    assert "docker ps" in cmds
    assert "config/settings.py" not in cmds
    assert "true" not in cmds


def test_extract_runnable_commands_strips_prompts_and_crlf():
    text = (
        "```bash\r\n"
        "$ python -m pip install -r requirements.txt\r\n"
        "```\r\n\r\n"
        "```powershell\r\n"
        "PS > Get-Service postgresql\r\n"
        "```"
    )
    cmds = extract_runnable_commands(text)
    assert len(cmds) == 2
    assert "python -m pip install -r requirements.txt" in cmds
    assert "Get-Service postgresql" in cmds


def test_format_time_label():
    from datetime import datetime, timedelta
    from frontend.components.message_bubble import format_time_label

    # 1. Timestamp None -> lấy giờ phút hiện tại
    now = datetime.now()
    disp, _ = format_time_label(None)
    assert disp == now.strftime("%H:%M")

    # 2. Timestamp là datetime hôm nay
    dt_today = datetime(now.year, now.month, now.day, 14, 25, 30)
    disp, tip = format_time_label(dt_today)
    assert disp == "14:25"
    assert "14:25:30" in tip

    # 3. Timestamp là datetime ngày khác
    dt_past = dt_today - timedelta(days=2)
    disp_past, tip_past = format_time_label(dt_past)
    assert "14:25 • " in disp_past

    # 4. Timestamp là chuỗi ISO
    disp_iso, _ = format_time_label("2026-10-27T08:15:00")
    assert "08:15" in disp_iso


def test_message_bubble_displays_timestamp():
    from frontend.components.message_bubble import MessageBubble
    import flet as ft

    # User message
    user_bubble = MessageBubble(
        text="Xin chào AI Buddy",
        is_user=True,
        timestamp="2026-10-27T10:45:00",
    )
    assert user_bubble is not None
    # Kiểm tra time label nằm trong controls
    msg_col = user_bubble.controls[0].content
    header_row = msg_col.controls[0]
    time_ctrl = header_row.controls[0]
    assert isinstance(time_ctrl, ft.Text)
    assert time_ctrl.value == "10:45"

    # AI message
    ai_bubble = MessageBubble(
        text="Tôi có thể hỗ trợ gì cho bạn?",
        is_user=False,
        timestamp="2026-10-27T10:46:00",
    )
    assert ai_bubble is not None
    ai_col = ai_bubble.controls[1].content
    ai_header_row = ai_col.controls[0]
    ai_time_ctrl = ai_header_row.controls[2]
    assert isinstance(ai_time_ctrl, ft.Text)
    assert ai_time_ctrl.value == "10:46"


