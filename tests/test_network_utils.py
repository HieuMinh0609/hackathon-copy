import socket

from backend.core.utils import network_utils as nu


def test_parse_host_port():
    assert nu.parse_host_port("kiểm tra 192.168.1.10:5432 giúp") == [("192.168.1.10", 5432)]
    assert nu.parse_host_port("telnet db.company.local:443") == [("db.company.local", 443)]
    assert nu.parse_host_port("ping 10.0.0.1") == [("10.0.0.1", None)]
    assert nu.parse_host_port("localhost:8000") == [("localhost", 8000)]


def test_parse_host_port_ignores_noise():
    assert nu.parse_host_port("đọc file readme.md và project_rules.md") == []
    assert nu.parse_host_port("ip 999.1.1.1:80") == []
    assert nu.parse_host_port("host 10.0.0.1:99999") == []


def test_tcp_connect_and_port_in_use():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        res = nu.tcp_connect("127.0.0.1", port)
        assert res.ok and res.latency_ms is not None
        assert nu.is_port_in_use(port) is True
    finally:
        server.close()
    assert nu.tcp_connect("127.0.0.1", port, timeout=0.5).ok is False
    assert nu.is_port_in_use(port) is False


def test_generate_check_script_is_valid_python():
    code = nu.generate_check_script("127.0.0.1", 8000)
    compile(code, "<generated>", "exec")


def test_analyze_unresolvable_host():
    report = nu.analyze_connectivity("host.invalid", 80)
    assert report.dns_ok is False
    assert "DNS" in report.diagnosis
