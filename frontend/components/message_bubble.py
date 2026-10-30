"""Bong bóng tin nhắn (User / AI-Buddy) theo thiết kế React UI."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Callable

import flet as ft

from frontend import theme


def format_time_label(timestamp: str | datetime | None = None) -> tuple[str, str | None]:
    """Format thời gian ngắn gọn, tinh tế cho tin nhắn chat (VD: 10:45 hoặc 10:45 • 27/10).
    
    Returns:
        tuple[str, str | None]: (thời_gian_hiển_thị, tooltip_chi_tiết)
    """
    if timestamp is None:
        now = datetime.now()
        return now.strftime("%H:%M"), now.strftime("%d/%m/%Y %H:%M:%S")

    if isinstance(timestamp, datetime):
        now = datetime.now()
        tip = timestamp.strftime("%d/%m/%Y %H:%M:%S")
        if timestamp.date() == now.date():
            return timestamp.strftime("%H:%M"), tip
        return timestamp.strftime("%H:%M • %d/%m"), tip

    ts_str = str(timestamp).strip()
    if not ts_str:
        now = datetime.now()
        return now.strftime("%H:%M"), now.strftime("%d/%m/%Y %H:%M:%S")

    # Nếu ts_str đã có dạng HH:MM
    if len(ts_str) == 5 and ts_str[2] == ":":
        return ts_str, None

    try:
        clean_ts = ts_str.replace("Z", "+00:00").replace(" ", "T")
        dt = datetime.fromisoformat(clean_ts)
        tip = dt.strftime("%d/%m/%Y %H:%M:%S")
        return dt.strftime("%H:%M"), tip
    except Exception:
        match = re.search(r"(\d{2}:\d{2})", ts_str)
        if match:
            return match.group(1), ts_str
        return (ts_str[:5] if len(ts_str) >= 5 else ts_str), ts_str


def extract_runnable_commands(text: str) -> list[str]:
    """Trích xuất các khối lệnh terminal/shell được AI đề xuất trong văn bản markdown (cả code block và inline backtick)."""
    if not text:
        return []

    commands: list[str] = []

    # 1. Quét code block dạng triple-backticks
    block_pattern = r"```([a-zA-Z0-9_\-\+]*)[^\S\r\n]*\r?\n([\s\S]*?)\r?\n?[^\S\r\n]*```"
    matches = re.findall(block_pattern, text)

    non_cmd_tags = {
        "python", "py", "json", "yaml", "yml", "sql", "html", "css",
        "javascript", "js", "typescript", "ts", "dockerfile", "xml", "csv", "markdown", "md",
        "output", "stdout", "stderr", "log", "logs", "text", "txt"
    }

    cmd_tags = {"bash", "sh", "cmd", "powershell", "ps1", "shell", "bat", "pwsh", "zsh", "terminal"}

    def _clean_command_line(line: str) -> str:
        line = line.strip()
        # Bỏ dấu prompt thường gặp: '$ ', '> ', 'PS >', 'PS C:\...> '
        line = re.sub(r"^(?:PS\s+[A-Za-z]:\\[^>]*>\s*|PS\s*>\s*|\$\s*|>\s*)", "", line)
        return line.strip()

    def _is_runnable(cmd_str: str) -> bool:
        if not cmd_str or len(cmd_str) < 2 or len(cmd_str) > 300:
            return False
        # Loại bỏ các dòng comment
        if cmd_str.startswith(("#", "//", "REM ", "::", "/*", "'''", '"""')):
            return False
        # Loại bỏ cấu trúc code lập trình
        if any(cmd_str.startswith(k) for k in (
            "def ", "class ", "import ", "from ", "function ", "const ", "let ", "var ",
            "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "return ", "<?php", "<html", "<div"
        )):
            return False
        # Loại bỏ JSON/dict thuần
        if "{" in cmd_str and "}" in cmd_str and ":" in cmd_str:
            return False
        return True

    for tag, code in matches:
        tag_clean = (tag or "").strip().lower()
        if tag_clean in non_cmd_tags:
            continue

        code_clean = code.strip()
        if not code_clean:
            continue

        raw_lines = [line.strip() for line in code_clean.splitlines() if line.strip()]
        cleaned_lines: list[str] = []
        for l in raw_lines:
            c = _clean_command_line(l)
            if _is_runnable(c):
                cleaned_lines.append(c)

        if not cleaned_lines:
            continue

        if tag_clean in cmd_tags:
            for c in cleaned_lines:
                commands.append(c)
        else:
            # Tag trống hoặc khác: thêm nếu dòng trông giống lệnh terminal
            for c in cleaned_lines:
                commands.append(c)

    # 2. Quét các lệnh inline dạng `cmd` trong câu văn (VD: `netstat -ano | findstr :5432`, `python --version`, ...)
    text_without_blocks = re.sub(block_pattern, "", text)
    inline_pattern = r"(?<!`)`([^`\r\n]+)`(?!`)"
    inline_matches = re.findall(inline_pattern, text_without_blocks)

    known_cmd_starters = {
        "python", "python3", "py", "pip", "pip3", "pytest",
        "git", "docker", "docker-compose", "node", "npm", "npx", "yarn", "pnpm",
        "winget", "choco", "brew", "apt", "apt-get",
        "ollama", "netstat", "ping", "curl", "telnet", "ssh", "tracert", "traceroute",
        "ipconfig", "ifconfig", "netsh", "route", "tasklist", "taskkill", "wmic",
        "cat", "dir", "ls", "echo", "cd", "code", "psql", "dbeaver", "uvicorn", "fastapi"
    }

    for item in inline_matches:
        candidate = _clean_command_line(item)
        if not _is_runnable(candidate):
            continue

        tokens = candidate.split()
        if not tokens:
            continue
        first = tokens[0].lower().rstrip(".exe")
        is_known = first in known_cmd_starters
        is_ps_cmdlet = bool(re.match(r"^[A-Z][a-zA-Z0-9]+-[A-Z][a-zA-Z0-9]+", tokens[0]))
        has_flags = any(t.startswith(("-", "--", "/")) for t in tokens[1:])
        has_pipe = "|" in candidate

        if is_known or is_ps_cmdlet or (has_flags and not candidate.startswith(("{", "["))) or has_pipe:
            # Tránh đường dẫn tệp đơn thuần (VD: `config/settings.py`)
            if ("/" in candidate or "\\" in candidate) and not (" " in candidate or is_known or has_flags or has_pipe):
                continue
            commands.append(candidate)

    # Loại bỏ trùng lặp giữ nguyên thứ tự xuất hiện
    seen = set()
    unique_commands: list[str] = []
    for c in commands:
        if c not in seen:
            seen.add(c)
            unique_commands.append(c)

    return unique_commands


class MessageBubble(ft.Row):
    def __init__(
        self,
        text: str,
        is_user: bool,
        sources: list[str] | None = None,
        on_link=None,
        on_run_command: Callable[[str], None] | None = None,
        timestamp: str | datetime | None = None,
    ) -> None:
        self.on_run_command = on_run_command

        # Avatar vuông bo góc theo mẫu
        if is_user:
            avatar = ft.Container(
                width=34,
                height=34,
                bgcolor=theme.SURFACE_ALT,
                border=ft.border.all(1, theme.BORDER),
                border_radius=8,
                alignment=ft.alignment.center,
                content=ft.Icon(ft.Icons.PERSON, size=18, color=theme.TEXT_MUTED),
            )
        else:
            avatar = ft.Container(
                width=34,
                height=34,
                bgcolor=theme.PRIMARY,
                border_radius=8,
                alignment=ft.alignment.center,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=6,
                    color=ft.Colors.with_opacity(0.2, theme.PRIMARY),
                    offset=ft.Offset(0, 2),
                ),
                content=ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=18, color=theme.TEXT_WHITE),
            )

        sender_label = ft.Text(
            "Bạn" if is_user else "AI-Buddy",
            size=11,
            weight=ft.FontWeight.W_500,
            color=theme.TEXT_MUTED,
        )

        time_display, full_time_tip = format_time_label(timestamp)
        time_label = ft.Text(
            time_display,
            size=10,
            color=theme.TEXT_LIGHT,
            weight=ft.FontWeight.W_400,
            tooltip=full_time_tip,
        )

        sender_header = ft.Row(
            tight=True,
            spacing=6,
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                time_label,
                ft.Text("•", size=9, color=theme.BORDER),
                sender_label,
            ] if is_user else [
                sender_label,
                ft.Text("•", size=9, color=theme.BORDER),
                time_label,
            ],
        )

        if is_user:
            body: ft.Control = ft.Text(text, color=theme.TEXT_WHITE, selectable=True, size=14)
        else:
            body = ft.Markdown(
                text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme=ft.MarkdownCodeTheme.ATOM_ONE_LIGHT,
                on_tap_link=on_link,
            )

        bubble_elements: list[ft.Control] = [body]

        # Khối hiển thị các lệnh cmd được đề xuất kèm nút Run
        if not is_user:
            runnable_cmds = extract_runnable_commands(text)
            for cmd in runnable_cmds:
                bubble_elements.append(self._build_command_card(cmd, on_run_command))

        if sources:
            bubble_elements.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    controls=[
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=8, vertical=3),
                            border_radius=6,
                            bgcolor=theme.PRIMARY_BG,
                            border=ft.border.all(1, theme.PRIMARY_BORDER),
                            content=ft.Row(
                                tight=True,
                                spacing=4,
                                controls=[
                                    ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=13, color=theme.PRIMARY),
                                    ft.Text(s, size=11, color=theme.PRIMARY, weight=ft.FontWeight.W_500),
                                ],
                            ),
                        )
                        for s in sources
                    ],
                )
            )

        bubble_container = ft.Container(
            content=ft.Column(bubble_elements, spacing=8, tight=True),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            border_radius=ft.border_radius.only(
                top_left=16 if is_user else 4,
                top_right=4 if is_user else 16,
                bottom_left=16,
                bottom_right=16,
            ),
            bgcolor=theme.PRIMARY if is_user else theme.SURFACE,
            border=ft.border.all(1, theme.PRIMARY if is_user else theme.BORDER),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color=ft.Colors.with_opacity(0.04, "#000000"),
                offset=ft.Offset(0, 2),
            ) if not is_user else None,
        )

        msg_column = ft.Column(
            tight=True,
            spacing=3,
            horizontal_alignment=ft.CrossAxisAlignment.END if is_user else ft.CrossAxisAlignment.START,
            controls=[
                sender_header,
                bubble_container,
            ],
        )

        super().__init__(
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=10,
            controls=[avatar, ft.Container(content=msg_column, expand=True)] if not is_user else [ft.Container(content=msg_column, expand=True), avatar],
        )

    def _build_command_card(self, cmd: str, on_run: Callable[[str], None] | None) -> ft.Container:
        display_cmd = cmd if len(cmd) <= 80 else cmd[:77] + "..."
        return ft.Container(
            bgcolor=theme.SURFACE_ALT,
            border=ft.border.all(1, theme.BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=10, vertical=7),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        expand=True,
                        controls=[
                            ft.Container(
                                width=26,
                                height=26,
                                bgcolor=theme.PRIMARY_BG,
                                border_radius=6,
                                alignment=ft.alignment.center,
                                content=ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=15, color=theme.PRIMARY),
                            ),
                            ft.Column(
                                spacing=1,
                                tight=True,
                                expand=True,
                                controls=[
                                    ft.Text("Lệnh đề xuất:", size=10, weight=ft.FontWeight.W_600, color=theme.TEXT_MUTED),
                                    ft.Text(
                                        display_cmd,
                                        size=11,
                                        font_family="monospace",
                                        weight=ft.FontWeight.BOLD,
                                        color=theme.TEXT,
                                        selectable=True,
                                        tooltip=cmd if len(cmd) > 80 else None,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.IconButton(
                                ft.Icons.COPY_ROUNDED,
                                icon_size=15,
                                icon_color=theme.TEXT_MUTED,
                                tooltip="Sao chép lệnh",
                                on_click=lambda _, c=cmd: self._copy_command(c),
                            ),
                            ft.FilledButton(
                                "Run",
                                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                style=ft.ButtonStyle(
                                    bgcolor=theme.PRIMARY,
                                    color=theme.SURFACE,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                                tooltip="Chạy lệnh này trên máy tính",
                                on_click=lambda _, c=cmd: (on_run(c) if on_run else self._default_run(c)),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _copy_command(self, cmd: str) -> None:
        if self.page:
            self.page.set_clipboard(cmd)
            self.page.open(
                ft.SnackBar(
                    ft.Text(f"Đã sao chép lệnh: {cmd}"),
                    duration=2000,
                    open=True,
                )
            )

    def _default_run(self, cmd: str) -> None:
        import subprocess, os
        def work():
            try:
                if os.name == "nt":
                    proc = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", cmd],
                        capture_output=True,
                        timeout=120,
                    )
                else:
                    proc = subprocess.run(
                        ["bash", "-c", cmd],
                        capture_output=True,
                        timeout=120,
                    )
                status_str = "thành công (0)" if proc.returncode == 0 else f"lỗi ({proc.returncode})"
                if self.page:
                    self.page.open(
                        ft.SnackBar(
                            ft.Text(f"Lệnh hoàn tất: {status_str}"),
                            duration=3000,
                            open=True,
                        )
                    )
            except Exception as e:
                if self.page:
                    self.page.open(
                        ft.SnackBar(
                            ft.Text(f"Lỗi khi chạy lệnh: {e}"),
                            duration=3000,
                            open=True,
                        )
                    )
        if self.page:
            self.page.run_thread(work)
        else:
            work()
