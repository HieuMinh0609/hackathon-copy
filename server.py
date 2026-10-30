"""Chạy Backend REST API server (FastAPI + Uvicorn).

Lệnh chạy:
    python server.py
    python server.py --port 8000 --reload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import get_settings


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Chạy AI Buddy Backend REST API")
    parser.add_argument("--host", default="127.0.0.1", help="Địa chỉ host lắng nghe (mặc định: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Cổng lắng nghe (mặc định: 8000)")
    parser.add_argument("--reload", action="store_true", help="Bật chế độ auto-reload khi code thay đổi")
    args = parser.parse_args()

    print(f"🚀 Đang khởi động AI Buddy Backend API tại: http://{args.host}:{args.port}")
    print(f"📖 OpenAPI Swagger docs: http://{args.host}:{args.port}/docs")
    print(f"📌 Database: {settings.database_url}")

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
