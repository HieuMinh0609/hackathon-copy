"""Kiểm tra cấu hình Docker backend và staging frontend-only."""
from __future__ import annotations

from pathlib import Path

import yaml

from scripts.build_frontend import prepare_stage


def test_compose_backend_is_private_by_default() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    backend = compose["services"]["backend"]

    assert backend["build"]["dockerfile"] == "Dockerfile.backend"
    assert backend["environment"]["API_HOST"] == "0.0.0.0"
    assert backend["ports"] == ["${BACKEND_PUBLISH_HOST:-127.0.0.1}:${BACKEND_PORT:-8765}:8765"]
    assert backend["depends_on"]["db"]["condition"] == "service_healthy"
    assert "backend_documents:/app/documents" in backend["volumes"]
    assert compose["services"]["db"]["ports"] == [
        "${POSTGRES_PUBLISH_HOST:-127.0.0.1}:${POSTGRES_PORT:-5432}:5432"
    ]


def test_frontend_stage_excludes_backend_and_secrets(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "frontend" / "assets").mkdir(parents=True)
    (project_root / "shared").mkdir()
    (project_root / "backend").mkdir()
    (project_root / "frontend" / "main.py").write_text("APP = True\n", encoding="utf-8")
    (project_root / "frontend" / "assets" / "font.ttf").write_bytes(b"font")
    (project_root / "shared" / "config.py").write_text("PORT = 8765\n", encoding="utf-8")
    (project_root / "backend" / "app.py").write_text("SECRET = True\n", encoding="utf-8")
    (project_root / "frontend_app.py").write_text("print('frontend')\n", encoding="utf-8")
    (project_root / "requirements-frontend.txt").write_text("flet==0.28.3\n", encoding="utf-8")
    (project_root / ".env").write_text("PASSWORD=secret\n", encoding="utf-8")

    stage = prepare_stage(project_root, project_root / "build" / "frontend-stage")

    assert (stage / "main.py").is_file()
    assert (stage / "frontend" / "assets" / "font.ttf").is_file()
    assert (stage / "shared" / "config.py").is_file()
    assert (stage / "requirements.txt").read_text(encoding="utf-8") == "flet==0.28.3\n"
    assert not (stage / "backend").exists()
    assert not (stage / ".env").exists()


def test_frontend_stage_rejects_paths_outside_build(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    try:
        prepare_stage(project_root, tmp_path / "unsafe-stage")
    except ValueError as exc:
        assert "bên trong" in str(exc)
    else:
        raise AssertionError("Staging ngoài thư mục build phải bị từ chối")
