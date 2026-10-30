"""Kiểm tra & cài đặt phần mềm tự động.

Nguyên tắc an toàn: hàm `build_install_plan` chỉ TẠO KẾ HOẠCH (lệnh sẽ chạy).
Chỉ `run_install_plan` mới thực thi, và UI/Agent phải hỏi xác nhận người dùng trước.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import shlex
from pathlib import Path
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence

from shared.encoding import completed_output

_VERSION_RE = re.compile(r"(\d+(?:\.\d+){0,3})")
_PKG_ID_RE = re.compile(r"^[A-Za-z0-9._+@-]+$")


@dataclass
class SoftwareStatus:
    name: str
    command: str
    installed: bool
    version: str | None = None
    meets_min: bool = False
    min_version: str | None = None
    path: str | None = None
    error: str = ""

    @property
    def message(self) -> str:
        if self.error:
            return f"{self.name}: {self.error}"
        if not self.installed:
            return f"Chưa cài đặt {self.name}."
        need = f" (yêu cầu >= {self.min_version})" if self.min_version else ""
        if self.meets_min:
            return f"{self.name} {self.version} ✓{need}"
        return f"{self.name} {self.version or '?'} quá cũ{need}."


@dataclass
class InstallPlan:
    software: str
    manager: str
    command: list[str]
    description: str = ""

    @property
    def display(self) -> str:
        return subprocess.list2cmdline(self.command)


def get_os_name() -> str:
    return platform.system().lower()  # windows | linux | darwin


def parse_version(text: str) -> tuple[int, ...] | None:
    m = _VERSION_RE.search(text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def version_gte(installed: str | tuple[int, ...] | None, minimum: str | tuple[int, ...] | None) -> bool:
    if minimum is None:
        return True
    if installed is None:
        return False
    a = parse_version(installed) if isinstance(installed, str) else installed
    b = parse_version(minimum) if isinstance(minimum, str) else minimum
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return tuple(a) + (0,) * (n - len(a)) >= tuple(b) + (0,) * (n - len(b))


def check_software(
    name: str,
    command: str,
    version_args: Sequence[str] = ("--version",),
    min_version: str | None = None,
    timeout: float = 10.0,
) -> SoftwareStatus:
    if tuple(version_args) not in {("--version",), ("-version",), ("-V",), ("version",)}:
        return SoftwareStatus(name, command, False, min_version=min_version,
                              error="Tham số kiểm tra chỉ được dùng --version, -version, -V hoặc version.")
    path = shutil.which(command)
    if not path:
        return SoftwareStatus(name, command, False, min_version=min_version)
    try:
        proc = subprocess.run(
            [path, *version_args], capture_output=True, timeout=timeout, check=False
        )
        stdout, stderr = completed_output(proc)
        if proc.returncode != 0:
            return SoftwareStatus(name, command, True, min_version=min_version, path=path,
                                  error=f"Lệnh kiểm tra phiên bản thất bại (mã {proc.returncode}).")
        raw = f"{stdout}\n{stderr}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return SoftwareStatus(name, command, True, min_version=min_version, path=path,
                              error="Lệnh kiểm tra quá thời gian chờ." if isinstance(exc, subprocess.TimeoutExpired)
                              else "Không chạy được lệnh kiểm tra phiên bản.")
    parsed = parse_version(raw)
    version = ".".join(map(str, parsed)) if parsed else None
    return SoftwareStatus(
        name=name,
        command=command,
        installed=True,
        version=version,
        meets_min=version_gte(version, min_version) if version else False,
        min_version=min_version,
        path=path,
        error="Không đọc được phiên bản từ kết quả lệnh." if version is None else "",
    )


def detect_package_manager() -> str | None:
    osname = get_os_name()
    if osname == "windows":
        candidates = ("winget", "choco")
    elif osname == "darwin":
        candidates = ("brew",)
    else:
        candidates = ("apt-get",)
    return next((c for c in candidates if shutil.which(c)), None)


def build_install_plan(software: str, install_spec: dict[str, Any] | None) -> InstallPlan | None:
    """Tạo kế hoạch cài đặt từ spec {winget|choco|apt|brew: package_id}. KHÔNG thực thi."""
    if not install_spec:
        return None
    manager = detect_package_manager()
    if manager is None:
        return None
    key = {"apt-get": "apt"}.get(manager, manager)
    pkg = install_spec.get(key)
    if not isinstance(pkg, str) or not _PKG_ID_RE.fullmatch(pkg):
        return None

    if manager == "winget":
        cmd = ["winget", "install", "--id", pkg, "-e", "--silent",
               "--accept-package-agreements", "--accept-source-agreements"]
    elif manager == "choco":
        cmd = ["choco", "install", pkg, "-y"]
    elif manager == "brew":
        cmd = ["brew", "install", pkg]
    else:
        cmd = ["apt-get", "install", "-y", pkg]
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            cmd[0:0] = ["sudo", "-n"]
    return InstallPlan(software, manager, cmd, f"Cài {software} bằng {manager}")


def build_file_install_plan(software: str, path: Path, install_args: str = "") -> InstallPlan:
    """Tạo argv từ tệp đã lưu; không chạy lệnh hay thay đổi quyền tệp khi xem plan."""
    path = path.resolve()
    if not path.is_file():
        raise ValueError("Không tìm thấy bộ cài tại đường dẫn đã lưu trong App Catalog.")
    system = get_os_name()
    args = shlex.split(install_args, posix=system != "windows")
    if system == "windows":
        args = [arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in ("'", '"') else arg for arg in args]
    suffix = path.suffix.lower()
    if system == "windows" and suffix == ".exe":
        command = [str(path), *args]
    elif system == "windows" and suffix == ".msi":
        command = ["msiexec.exe", "/i", str(path), *args]
    elif system == "darwin" and suffix == ".pkg":
        if args:
            raise ValueError("Bộ cài .pkg qua Installer không hỗ trợ install_args. Hãy bỏ tham số này trong App Catalog.")
        command = ["/usr/bin/open", "-W", str(path)]
    elif system == "linux" and suffix == ".deb":
        command = ["dpkg", "-i", str(path), *args]
        if os.geteuid() != 0:
            command[0:0] = ["sudo", "-n"]
    else:
        raise ValueError(f"Bộ cài {suffix or '(không có phần mở rộng)'} không được hỗ trợ trên {system}. Dùng .exe/.msi cho Windows, .pkg cho macOS hoặc .deb cho Linux.")
    return InstallPlan(software, "local-installer", command, f"Cài từ bộ cài đã lưu: {path}")


def _run_windows_installer(command: list[str], timeout: float) -> tuple[bool, str]:
    """Mở UAC và chờ tiến trình thật; truyền file/arguments riêng, không qua cmd.exe."""
    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100  # Giữ process handle và đợi ShellExecute hoàn tất khởi chạy.
    info.lpVerb = "runas"
    info.lpFile = command[0]
    info.lpParameters = subprocess.list2cmdline(command[1:])
    info.nShow = 1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.get_last_error()
        return False, "Bạn đã hủy yêu cầu cấp quyền UAC." if code == 1223 else f"Không mở được bộ cài (mã Windows {code})."
    if not info.hProcess:
        return False, "Không theo dõi được tiến trình cài đặt. Hãy kiểm tra lại phần mềm trước khi thử lại."
    try:
        wait = kernel.WaitForSingleObject(info.hProcess, int(timeout * 1000))
        if wait == 258:
            return False, "Hết thời gian chờ; bộ cài có thể vẫn đang chạy. Hãy kiểm tra cửa sổ cài đặt trước khi thử lại."
        if wait != 0:
            return False, "Không đọc được trạng thái tiến trình cài đặt."
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            return False, "Không đọc được mã kết thúc của bộ cài."
        if code.value in (1641, 3010):
            return True, f"Bộ cài yêu cầu khởi động lại máy (mã {code.value}); ứng dụng không tự khởi động lại."
        return code.value == 0, f"Bộ cài đã kết thúc với mã {code.value}."
    finally:
        kernel.CloseHandle(info.hProcess)


def run_install_plan(plan: InstallPlan, timeout: float = 1800.0) -> tuple[bool, str]:
    """Thực thi kế hoạch cài đặt. CHỈ gọi sau khi người dùng đã xác nhận."""
    if plan.manager == "local-installer" and get_os_name() == "windows":
        return _run_windows_installer(plan.command, timeout)
    try:
        proc = subprocess.run(
            plan.command, capture_output=True,
            stdin=subprocess.DEVNULL, timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return False, f"Không tìm thấy công cụ '{plan.command[0]}'."
    except subprocess.TimeoutExpired:
        return False, "Cài đặt quá thời gian chờ."
    except OSError as exc:
        return False, f"Không chạy được lệnh cài đặt; kiểm tra quyền hệ điều hành: {exc}"
    stdout, stderr = completed_output(proc)
    output = (stdout + "\n" + stderr).strip()
    if proc.returncode != 0 and plan.command[:2] == ["sudo", "-n"]:
        output += "\nChưa có quyền sudo không tương tác. Hãy nhờ IT cấp quyền hoặc chạy lệnh đã duyệt trong terminal; ứng dụng không nhận mật khẩu quản trị."
    return proc.returncode == 0, output[-1500:]
