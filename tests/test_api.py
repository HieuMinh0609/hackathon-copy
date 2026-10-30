"""Unit tests cho AI Buddy Backend REST API & ApiClient."""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.dependencies import set_app_context
from api.main import app
from core.api_client import ApiClient
from backend.core.context import build_context


@pytest.fixture()
def client(settings):
    # Cấu hình API sử dụng SQLite test database
    ctx = build_context(settings)
    set_app_context(ctx)
    with TestClient(app) as c:
        yield c


def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert data["app_name"] == "AI Buddy"
    assert "database" in data


def test_api_templates_crud(client, tmp_path: Path):
    admin_headers = {"X-Session-Key": hashlib.md5(b"alex.carter@example.com").hexdigest()}
    # 1. List templates
    res = client.get("/api/templates")
    assert res.status_code == 200
    templates = res.json()
    assert len(templates) >= 3
    codes = [t["template_code"] for t in templates]
    assert "PRJ_ECOMMERCE" in codes
    assert "PRJ_AI_BUDDY" in codes

    # 2. Get single template
    res = client.get("/api/templates/PRJ_ECOMMERCE")
    assert res.status_code == 200
    item = res.json()
    assert item["template_code"] == "PRJ_ECOMMERCE"
    assert item["code"] == "PRJ_ECOMMERCE"
    assert "Microservices" in item["template_name"]

    # 3. Get doc-folder
    res = client.get("/api/templates/PRJ_ECOMMERCE/doc-folder")
    assert res.status_code == 200
    data = res.json()
    assert "doc_folder" in data

    # 4. Update doc-folder
    custom_dir = tmp_path / "custom_doc_api"
    custom_dir.mkdir(parents=True, exist_ok=True)
    res = client.put(
        "/api/templates/PRJ_ECOMMERCE/doc-folder",
        headers=admin_headers,
        json={"doc_folder": str(custom_dir)},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 5. Upsert new template
    res = client.post(
        "/api/templates",
        headers=admin_headers,
        json={
            "template_code": "PRJ_NEW_API",
            "template_name": "New API Template",
            "document_link": "documents/new_api",
            "description": "Test template",
        },
    )
    assert res.status_code == 200
    res = client.get("/api/templates/PRJ_NEW_API")
    assert res.status_code == 200
    assert res.json()["template_name"] == "New API Template"


def test_api_checklist_flow(client):
    admin_headers = {"X-Session-Key": hashlib.md5(b"alex.carter@example.com").hexdigest()}
    # 1. List items
    res = client.get("/api/checklist/items")
    assert res.status_code == 200
    items = res.json()
    assert len(items) > 0

    first_key = items[0]["key"]

    # 2. Get single item
    res = client.get(f"/api/checklist/items/{first_key}")
    assert res.status_code == 200
    assert res.json()["key"] == first_key

    # 3. Progress
    res = client.get("/api/checklist/progress")
    assert res.status_code == 200
    prog = res.json()
    assert "total" in prog
    assert "percent" in prog

    # 4. Set manual done
    res = client.post(f"/api/checklist/items/{first_key}/manual", json={"done": True})
    assert res.status_code == 200

    # 5. Reset
    res = client.post("/api/checklist/reset?project_code=PRJ_ECOMMERCE", headers=admin_headers)
    assert res.status_code == 200
    res = client.get(f"/api/checklist/items/{first_key}")
    assert res.json()["status"] in ("pending", "ACTIVE")

    # 6. Template sample & import
    res_sample = client.get(
        "/api/checklist/template-sample?project_code=PRJ_ECOMMERCE",
        headers=admin_headers,
    )
    assert res_sample.status_code == 200
    assert "task_name" in res_sample.json()["content"]

    csv_data = """task_name,category,check_type,mandatory,owner_team,instructions,params,sort_order
Kiểm tra Grafana Monitor,Mạng nội bộ,HOST_REACHABLE,false,DevOps,Kiểm tra Grafana dashboard,"{""port"": 3000}",50
"""
    res_import = client.post(
        "/api/checklist/import",
        headers={**admin_headers, "X-User-Email": "alex.carter@example.com"},
        json={"content": csv_data, "project_code": "PRJ_ECOMMERCE"},
    )
    assert res_import.status_code == 200
    assert res_import.json()["imported_count"] == 1



def test_api_verification(client):
    res = client.post("/api/verification/verify-all")
    assert res.status_code == 200
    results = res.json()
    assert isinstance(results, list)
    assert len(results) > 0


def test_api_agent_chat(client):
    # Test networking intent router without requiring Ollama running
    res = client.post("/api/agent/chat", json={"message": "telnet 127.0.0.1 8080"})
    assert res.status_code == 200
    data = res.json()
    assert "text" in data
    assert data["agent"] in ("networking", "ai_buddy")


def test_api_agent_chat_checklist_mode(client):
    # Test gửi yêu cầu có checklist_mode=True
    res = client.post("/api/agent/chat", json={
        "message": "làm sao để cài nvm cho nodejs?",
        "checklist_mode": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert "text" in data
    assert data["agent"] == "checklist"


def test_api_client_adapter(client):
    # Test rằng ApiClient gọi qua backend REST API hoạt động đúng như interface dịch vụ
    api_client = ApiClient(http_client=client)

    # 1. Test templates/projects adapter
    projects = api_client.projects.list_projects()
    assert len(projects) >= 3

    tmpl = api_client.projects.get_project("PRJ_ECOMMERCE")
    assert tmpl is not None
    assert tmpl["template_code"] == "PRJ_ECOMMERCE"

    # 2. Test checklist adapter
    items = api_client.checklist.list_items()
    assert len(items) > 0
    p = api_client.checklist.progress()
    assert p["total"] == len(items)

    # 3. Test agent adapter
    reply = api_client.agent.chat("ping 127.0.0.1")
    assert reply.text != ""


def test_api_update_user_task(client):
    # Test cập nhật task theo user_id qua endpoint API manual
    res = client.post("/api/checklist/items/app_python/manual", json={"done": True, "user_id": 1})
    assert res.status_code == 200
    data = res.json()
    assert data["done"] is True

    # Test endpoint chuyên biệt /checklist/user-task
    res2 = client.post("/api/checklist/user-task", json={"key": "app_git", "done": True, "user_id": 1})
    assert res2.status_code == 200
    assert res2.json()["task_status"] == "COMPLETED"
