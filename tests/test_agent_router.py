import pytest

from backend.core.agents.ai_buddy_agent import detect_intent


@pytest.mark.parametrize(
    "message,expected",
    [
        ("kiểm tra 192.168.1.10:5432", "networking"),
        ("telnet db.company.local 443", "networking"),
        ("ping 10.0.0.1", "networking"),
        ("kiểm tra port 8000 có bị trùng không", "networking"),
        ("kiểm tra môi trường của tôi", "checklist"),
        ("cài git giúp mình", "checklist"),
        ("check list còn thiếu gì", "checklist"),
        ("Quy trình xin cấp quyền IP là gì?", "knowledge"),
        ("Mục tiêu dự án là gì?", "knowledge"),
        ("đọc file readme.md", "knowledge"),
    ],
)
def test_detect_intent(message, expected):
    assert detect_intent(message) == expected


def test_checklist_mode_routing(settings):
    from backend.core.context import build_context

    ctx = build_context(settings)
    msg = "Mục tiêu dự án là gì?"
    assert detect_intent(msg) == "knowledge"

    # Khi bật checklist_mode=True, luôn ưu tiên ChecklistAgent (Qwen 2.5:7b)
    reply = ctx.agent.chat(msg, checklist_mode=True)
    assert reply.agent == "checklist"

