"""Kiểm thử tính năng lưu trữ và truy vấn lịch sử chat AI (30 tin nhắn gần nhất theo user và project)."""
from __future__ import annotations

import hashlib
from fastapi.testclient import TestClient

from backend.app import app
from backend.core.context import build_context
from backend.services.chat_history_service import ChatHistoryService


def test_chat_history_service_crud_and_limits(settings) -> None:
    service = ChatHistoryService(settings.database_url)

    user1 = "alex.carter@example.com"
    user2 = "emma.wilson@example.com"
    proj1 = "project_onboarding"
    proj2 = "project_payments"

    # 1. Ban đầu lịch sử trống
    assert service.get_recent_messages(user1, proj1) == []
    assert service.count_messages(user1, proj1) == 0

    # 2. Lưu tin nhắn đơn
    msg1 = service.save_message(user1, proj1, sender="user", message="Xin chào AI Buddy!")
    assert msg1["sender"] == "user"
    assert msg1["message"] == "Xin chào AI Buddy!"

    reply1 = service.save_message(
        user1,
        proj1,
        sender="ai",
        message="Chào bạn! Tôi có thể giúp gì?",
        sources=["docs/readme.md"],
        metadata={"agent": "knowledge"},
    )
    assert reply1["sender"] == "ai"
    assert reply1["sources"] == ["docs/readme.md"]

    # 3. Lấy lại tin nhắn
    history = service.get_recent_messages(user1, proj1, limit=30)
    assert len(history) == 2
    assert history[0]["sender"] == "user"
    assert history[0]["message"] == "Xin chào AI Buddy!"
    assert history[1]["sender"] == "ai"
    assert history[1]["message"] == "Chào bạn! Tôi có thể giúp gì?"
    assert history[1]["sources"] == ["docs/readme.md"]
    assert history[1]["metadata"].get("agent") == "knowledge"

    # 4. Kiểm tra cô lập dữ liệu theo User và Project
    # user2 không thấy tin của user1
    assert service.get_recent_messages(user2, proj1) == []
    # user1 trong proj2 không thấy tin của proj1
    assert service.get_recent_messages(user1, proj2) == []

    # 5. Lưu 55 tin nhắn liên tiếp để kiểm tra giới hạn 50 tin
    for i in range(1, 56):
        service.save_message(user1, proj1, sender="user", message=f"Câu hỏi số {i}")

    # Tổng số tin hiện tại: 2 tin ban đầu + 55 = 57 tin
    assert service.count_messages(user1, proj1) == 57

    # Lấy với limit=50 mặc định
    recent_50 = service.get_recent_messages(user1, proj1)
    assert len(recent_50) == 50

    # 50 tin mới nhất phải gồm các câu hỏi từ 6 đến 55
    # Thứ tự phải tăng dần theo thời gian (từ cũ đến mới)
    assert recent_50[0]["message"] == "Câu hỏi số 6"
    assert recent_50[-1]["message"] == "Câu hỏi số 55"

    # Lấy với limit tùy biến (VD: limit=30)
    recent_30 = service.get_recent_messages(user1, proj1, limit=30)
    assert len(recent_30) == 30
    assert recent_30[0]["message"] == "Câu hỏi số 26"
    assert recent_30[-1]["message"] == "Câu hỏi số 55"

    # 6. Kiểm tra xóa lịch sử
    deleted = service.clear_history(user1, proj1)
    assert deleted == 57
    assert service.get_recent_messages(user1, proj1) == []


def test_api_chat_history_endpoints(settings, monkeypatch) -> None:
    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)

    client = TestClient(app)

    # 1. Đăng nhập để nhận session_key
    email = "alex.carter@example.com"
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "1234"})
    assert login_res.status_code == 200
    session_key = login_res.json()["data"]["session_key"]
    headers = {"X-Session-Key": session_key, "X-User-Email": email}

    project_code = "sample_test_proj"

    # 2. Xóa lịch sử cũ nếu có
    client.delete(f"/api/v1/chat/history?project_code={project_code}", headers=headers)

    # 3. Gửi tin nhắn qua /api/v1/chat
    chat_res = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"message": "Kiểm tra kết nối port 8080", "project_code": project_code},
    )
    assert chat_res.status_code == 200
    reply_data = chat_res.json()["data"]
    assert "text" in reply_data
    assert "created_at" in reply_data
    assert reply_data["created_at"] is not None

    # 4. Lưu log thực thi terminal qua POST /api/v1/chat/history
    term_log_res = client.post(
        "/api/v1/chat/history",
        headers=headers,
        json={
            "message": "💻 **Kết quả thực thi:** `python --version` (Thành công ✓)\n\n```output\nPython 3.11.9\n```",
            "project_code": project_code,
            "sender": "ai",
            "metadata": {"type": "terminal_execution", "command": "python --version", "exit_code": 0},
        },
    )
    assert term_log_res.status_code == 200
    assert term_log_res.json()["success"] is True

    # 5. Lấy lịch sử qua /api/v1/chat/history (mặc định lấy 50 tin)
    history_res = client.get(f"/api/v1/chat/history?project_code={project_code}", headers=headers)
    assert history_res.status_code == 200
    history = history_res.json()["data"]

    # Phải có ít nhất 3 tin nhắn: 1 của user, 1 của ai và 1 log terminal
    assert len(history) >= 3
    user_msgs = [m for m in history if m["sender"] == "user"]
    ai_msgs = [m for m in history if m["sender"] == "ai"]
    assert len(user_msgs) >= 1
    assert len(ai_msgs) >= 2
    assert user_msgs[0]["message"] == "Kiểm tra kết nối port 8080"
    term_msgs = [m for m in history if "Kết quả thực thi" in m["message"]]
    assert len(term_msgs) == 1
    assert term_msgs[0]["metadata"].get("type") == "terminal_execution"

    # 6. Xóa lịch sử qua /api/v1/chat/history
    del_res = client.delete(f"/api/v1/chat/history?project_code={project_code}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["cleared"] >= 3

    # Lấy lại lịch sử sau khi xóa -> rỗng
    after_del = client.get(f"/api/v1/chat/history?project_code={project_code}", headers=headers)
    assert after_del.status_code == 200
    assert after_del.json()["data"] == []


def test_cancelled_chat_response_is_not_saved(settings, monkeypatch) -> None:
    """Response hoàn tất sau tín hiệu hủy không được chen vào lịch sử hoặc UI lần sau."""
    from backend import app as app_module

    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)
    client = TestClient(app)
    email = "emma.wilson@example.com"
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "1234"})
    session_key = login.json()["data"]["session_key"]
    headers = {"X-Session-Key": session_key, "X-User-Email": email}
    project_code = "cancelled_chat_project"
    request_id = "request-cancelled-001"
    client.delete(f"/api/v1/chat/history?project_code={project_code}", headers=headers)

    app_module._mark_chat_cancelled(email, request_id)
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "Câu hỏi sẽ bị hủy",
            "project_code": project_code,
            "request_id": request_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["agent"] == "cancelled"
    history = client.get(
        f"/api/v1/chat/history?project_code={project_code}",
        headers=headers,
    ).json()["data"]
    assert [item["sender"] for item in history] == ["user"]
    assert history[0]["metadata"]["request_id"] == request_id


def test_cancel_chat_endpoint_persists_cancel_marker(settings, monkeypatch) -> None:
    from backend import app as app_module

    ctx = build_context(settings)
    monkeypatch.setattr("backend.app._context", lambda: ctx)
    client = TestClient(app)
    email = "emma.wilson@example.com"
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "1234"})
    session_key = login.json()["data"]["session_key"]
    headers = {"X-Session-Key": session_key, "X-User-Email": email}
    project_code = "cancel_marker_project"
    request_id = "request-cancel-marker-001"
    client.delete(f"/api/v1/chat/history?project_code={project_code}", headers=headers)

    response = client.post(
        "/api/v1/chat/cancel",
        headers=headers,
        json={"request_id": request_id, "project_code": project_code},
    )

    assert response.status_code == 200
    history = client.get(
        f"/api/v1/chat/history?project_code={project_code}",
        headers=headers,
    ).json()["data"]
    assert history[-1]["metadata"] == {"type": "chat_cancelled", "request_id": request_id}
    app_module._consume_chat_cancelled(email, request_id)
