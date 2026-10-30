"""Tiện ích mạng - dùng socket/subprocess thay cho lệnh telnet (Windows thường tắt sẵn Telnet)."""
from __future__ import annotations

import platform
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass

from shared.encoding import decode_process_output

_IPV4 = r"(?:\d{1,3}\.){3}\d{1,3}"
_HOSTNAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)+"
_TARGET_RE = re.compile(
    rf"(?<![\w.@/])(?P<host>{_IPV4}|localhost|{_HOSTNAME})(?::(?P<port>\d{{1,5}}))?(?![\w.])"
)


def check_wifi() -> tuple[bool, str]:
    """Chỉ đọc trạng thái Wi-Fi từ máy, không gửi request Internet hay đổi cấu hình."""
    def run(command: list[str]) -> str:
        proc = subprocess.run(
            command, capture_output=True, timeout=8,
            check=False, env={**os.environ, "LC_ALL": "C"},
        )
        if proc.returncode:
            raise OSError("Không đọc được trạng thái bộ điều hợp Wi-Fi.")
        return decode_process_output(proc.stdout)

    try:
        system = platform.system().lower()
        if system == "windows":
            output = run(["netsh", "wlan", "show", "interfaces"])
            # BSSID có định dạng ổn định kể cả khi Windows dùng ngôn ngữ khác.
            connected = bool(re.search(r"(?im)^\s*BSSID\s*:\s*(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", output))
            if not connected and ("location" in output.lower() or "access is denied" in output.lower()):
                return False, "Không đọc được Wi-Fi: kiểm tra quyền vị trí/truy cập của hệ điều hành."
        elif system == "darwin":
            ports = run(["networksetup", "-listallhardwareports"])
            devices = re.findall(r"Hardware Port: (?:Wi-Fi|AirPort)\s+Device: (\S+)", ports)
            if not devices:
                return False, "Không tìm thấy bộ điều hợp Wi-Fi."
            connected = False
            for device in devices:
                output = run(["networksetup", "-getairportnetwork", device])
                if "Current Wi-Fi Network:" in output:
                    connected = True
                    break
            if not connected:
                return False, "Chưa xác nhận được kết nối Wi-Fi; kiểm tra Wi-Fi và quyền truy cập của macOS."
        elif system == "linux":
            output = run(["nmcli", "-t", "-f", "TYPE,STATE", "device", "status"])
            connected = any(line.strip() == "wifi:connected" for line in output.splitlines())
        else:
            return False, "Hệ điều hành chưa hỗ trợ kiểm tra Wi-Fi tự động."
    except FileNotFoundError:
        return False, "Không có công cụ kiểm tra Wi-Fi trên máy (netsh/networksetup/nmcli)."
    except subprocess.TimeoutExpired:
        return False, "Kiểm tra Wi-Fi quá thời gian chờ."
    except OSError as exc:
        return False, f"Không thể kiểm tra Wi-Fi: {exc}"
    if connected:
        return True, "Wi-Fi đã kết nối. Trạng thái này không xác nhận Internet hoặc VPN."
    return False, "Wi-Fi chưa kết nối hoặc không có bộ điều hợp; máy có thể đang dùng mạng dây."


@dataclass
class TcpResult:
    ok: bool
    latency_ms: float | None = None
    error: str = ""


@dataclass
class ConnectivityReport:
    host: str
    port: int | None
    resolved_ip: str | None
    dns_ok: bool
    ping_ok: bool
    tcp: TcpResult | None
    diagnosis: str

    def to_markdown(self) -> str:
        def mark(v: bool) -> str:
            return "✅" if v else "❌"

        target = f"{self.host}:{self.port}" if self.port else self.host
        lines = [
            f"**Kết quả kiểm tra `{target}`**",
            f"- DNS/IP: {mark(self.dns_ok)} {self.resolved_ip or 'không phân giải được'}",
            f"- Ping (ICMP): {mark(self.ping_ok)}",
        ]
        if self.tcp is not None:
            detail = f"{self.tcp.latency_ms:.0f} ms" if self.tcp.ok else self.tcp.error
            lines.append(f"- TCP port {self.port}: {mark(self.tcp.ok)} {detail}")
        lines.append(f"- Chẩn đoán: {self.diagnosis}")
        return "\n".join(lines)


def _valid_ipv4(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def parse_host_port(text: str) -> list[tuple[str, int | None]]:
    """Trích các mục tiêu mạng từ câu chat.

    Nhận: IPv4 (có/không port), localhost, hostname **có kèm port** (tránh nhầm với tên file).
    """
    targets: list[tuple[str, int | None]] = []
    for m in _TARGET_RE.finditer(text):
        host, port_s = m.group("host"), m.group("port")
        is_ip = bool(re.fullmatch(_IPV4, host))
        if is_ip and not _valid_ipv4(host):
            continue
        port = int(port_s) if port_s else None
        if port is not None and not (1 <= port <= 65535):
            continue
        if port is None and not is_ip and host != "localhost":
            continue
        if (host, port) not in targets:
            targets.append((host, port))
    return targets


def tcp_connect(host: str, port: int, timeout: float = 3.0) -> TcpResult:
    """Thay thế `telnet host port`: thử mở kết nối TCP."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return TcpResult(True, (time.perf_counter() - start) * 1000)
    except socket.timeout:
        return TcpResult(False, error="timeout (nhiều khả năng bị firewall chặn)")
    except ConnectionRefusedError:
        return TcpResult(False, error="bị từ chối (port đóng hoặc chưa có service lắng nghe)")
    except socket.gaierror:
        return TcpResult(False, error="không phân giải được tên miền")
    except OSError as exc:
        return TcpResult(False, error=str(exc))


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """True nếu port đang bị tiến trình khác chiếm trên máy local."""
    if tcp_connect(host, port, timeout=0.5).ok:
        return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def resolve_host(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return None


def ping(host: str, timeout_s: int = 2) -> bool:
    """Gọi lệnh ping của hệ điều hành bằng subprocess (không qua shell)."""
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_s * 1000), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout_s), host]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s + 3, check=False)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def get_local_ips() -> list[str]:
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    try:  # IP của interface đi ra ngoài (không gửi gói tin thật)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def analyze_connectivity(host: str, port: int | None = None) -> ConnectivityReport:
    resolved = resolve_host(host)
    dns_ok = resolved is not None
    ping_ok = ping(host) if dns_ok else False
    tcp = tcp_connect(host, port) if (port and dns_ok) else None

    if not dns_ok:
        diagnosis = "Không phân giải được tên miền - kiểm tra DNS/VPN hoặc gõ sai host."
    elif tcp is not None and tcp.ok:
        diagnosis = "Kết nối OK, bạn có quyền truy cập."
    elif tcp is not None and ping_ok:
        diagnosis = f"Host hoạt động nhưng port {port} không mở được: {tcp.error}. Cần xin mở port/cấp quyền IP."
    elif tcp is not None:
        diagnosis = "Không tới được host (ICMP và TCP đều lỗi): có thể IP của bạn bị chặn hoặc chưa bật VPN."
    elif ping_ok:
        diagnosis = "Host phản hồi ping. Cung cấp thêm port để kiểm tra dịch vụ."
    else:
        diagnosis = "Host không phản hồi ping (có thể do firewall chặn ICMP). Hãy thử kèm port, ví dụ host:443."
    return ConnectivityReport(host, port, resolved, dns_ok, ping_ok, tcp, diagnosis)


def generate_check_script(host: str, port: int) -> str:
    """Sinh script Python chuẩn (socket) để người dùng tự kiểm tra kết nối."""
    return f'''import socket
import time

HOST, PORT, TIMEOUT = "{host}", {port}, 3.0

start = time.perf_counter()
try:
    with socket.create_connection((HOST, PORT), timeout=TIMEOUT):
        elapsed = (time.perf_counter() - start) * 1000
        print(f"OK: {{HOST}}:{{PORT}} ({{elapsed:.0f}} ms)")
except socket.timeout:
    print("TIMEOUT: nhiều khả năng bị firewall chặn")
except ConnectionRefusedError:
    print("REFUSED: port đóng hoặc chưa có service")
except OSError as exc:
    print(f"ERROR: {{exc}}")
'''
