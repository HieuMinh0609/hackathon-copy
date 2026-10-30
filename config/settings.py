"""Cấu hình trung tâm của AI Buddy.

Thứ tự ưu tiên: llm_config.yaml < biến môi trường (.env) < data/user_settings.json
(do người dùng chỉnh trong trang Cài đặt).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

ROLES: dict[str, str] = {
    "backend_developer": "Backend Developer",
    "frontend_developer": "Frontend Developer",
    "hr": "HR",
}

# Các field người dùng được phép ghi đè qua trang Cài đặt
_OVERRIDABLE = ("ollama_base_url", "llm_model", "embedding_model", "user_role")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@dataclass
class Settings:
    base_dir: Path
    data_dir: Path
    documents_dir: Path
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    embedding_model: str = "bge-m3"
    temperature: float = 0.2
    num_ctx: int = 2048
    num_predict: int = 512
    num_thread: int = 8
    request_timeout: int = 120
    chunk_size: int = 1500
    chunk_overlap: int = 150
    top_k: int = 4
    collection_name: str = "aibuddy_docs"
    user_role: str = "backend_developer"
    app_name: str = "AI Buddy"
    # Database: Sử dụng PostgreSQL
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "aibuddy"
    pg_user: str = "aibuddy"
    pg_password: str = field(default="aibuddy", repr=False)
    database_url_override: str = ""  # DATABASE_URL đầy đủ, ưu tiên cao nhất
    installer_prefix: str = "data/installers"  # Prefix thư mục bộ cài đặt trên server, cấu hình qua INSTALLER_PREFIX
    roles: dict[str, str] = field(default_factory=lambda: dict(ROLES))

    # ---- đường dẫn dẫn xuất từ data_dir (để test có thể thay data_dir) ----
    @property
    def config_dir(self) -> Path:
        return self.base_dir / "config"

    @property
    def uses_postgres(self) -> bool:
        return True

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL: DATABASE_URL hoặc cấu hình PostgreSQL (POSTGRES_*)."""
        if self.database_url_override:
            return self.database_url_override
        return URL.create(
            "postgresql+psycopg",
            username=self.pg_user or "aibuddy",
            password=self.pg_password or None,
            host=self.pg_host or "localhost",
            port=self.pg_port or 5432,
            database=self.pg_database or "aibuddy",
        ).render_as_string(hide_password=False)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "database" / "aibuddy.db"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chromadb"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def installers_dir(self) -> Path:
        """Thư mục lưu trữ bộ cài đặt trên máy chủ: prefix từ env (tuyệt đối hoặc tương đối qua data_dir)."""
        prefix = (getattr(self, "installer_prefix", "") or "").strip() or "data/installers"
        p = Path(prefix)
        if p.is_absolute():
            return p
        if len(p.parts) > 0 and p.parts[0] == "data":
            return self.data_dir / Path(*p.parts[1:])
        return self.data_dir / p

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def user_settings_path(self) -> Path:
        return self.data_dir / "user_settings.json"

    def ensure_dirs(self) -> None:
        for p in (self.chroma_dir, self.uploads_dir, self.exports_dir, self.installers_dir, self.downloads_dir):
            p.mkdir(parents=True, exist_ok=True)

    # ---- load / save ----
    @classmethod
    def load(cls) -> "Settings":
        cfg = _load_yaml(BASE_DIR / "config" / "llm_config.yaml")
        ollama, llm = cfg.get("ollama", {}), cfg.get("llm", {})
        emb, rag = cfg.get("embedding", {}), cfg.get("rag", {})

        data_dir = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
        s = cls(
            base_dir=BASE_DIR,
            data_dir=data_dir,
            documents_dir=BASE_DIR / "documents",
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", ollama.get("base_url", "http://localhost:11434")),
            llm_model=os.getenv("LLM_MODEL", llm.get("model", "qwen2.5:7b")),
            embedding_model=os.getenv("EMBEDDING_MODEL", emb.get("model", "bge-m3")),
            temperature=float(llm.get("temperature", 0.2)),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", llm.get("num_ctx", 2048))),
            num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", llm.get("num_predict", 512))),
            num_thread=int(os.getenv("OLLAMA_NUM_THREAD", llm.get("num_thread", 8))),
            request_timeout=int(llm.get("request_timeout", 120)),
            chunk_size=int(rag.get("chunk_size", 1500)),
            chunk_overlap=int(rag.get("chunk_overlap", 150)),
            top_k=int(rag.get("top_k", 4)),
            collection_name=rag.get("collection", "aibuddy_docs"),
            user_role=os.getenv("USER_ROLE", "backend_developer"),
            pg_host=os.getenv("POSTGRES_HOST", "localhost").strip() or "localhost",
            pg_port=int(os.getenv("POSTGRES_PORT", "5432") or 5432),
            pg_database=os.getenv("POSTGRES_DB", "aibuddy"),
            pg_user=os.getenv("POSTGRES_USER", "aibuddy"),
            pg_password=os.getenv("POSTGRES_PASSWORD", "aibuddy"),
            database_url_override=os.getenv("DATABASE_URL", "").strip(),
            installer_prefix=os.getenv("INSTALLER_PREFIX", "data/installers").strip() or "data/installers",
        )
        s._apply_user_overrides()
        return s

    def _apply_user_overrides(self) -> None:
        path = self.user_settings_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key in _OVERRIDABLE:
            if data.get(key):
                setattr(self, key, data[key])

    def save_user_overrides(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {k: getattr(self, k) for k in _OVERRIDABLE}
        self.user_settings_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @property
    def role_filter(self) -> list[str]:
        """Thư mục tài liệu được phép truy xuất: onboarding luôn có + role hiện tại."""
        return ["onboarding", self.user_role]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.load()
    settings.ensure_dirs()
    return settings


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, str]:
    return _load_yaml(BASE_DIR / "config" / "prompt_templates.yaml")


def get_prompt(name: str, **kwargs: Any) -> str:
    """Lấy prompt theo tên và điền biến {placeholder}."""
    template = load_prompts()[name]
    return template.format(**kwargs) if kwargs else template
