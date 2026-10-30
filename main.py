"""Launcher desktop: khởi động API local trước, sau đó mở Flet frontend."""
from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request

import flet as ft
import uvicorn

from frontend.main import ASSETS_DIR, main as frontend_main
from shared.config import API_BASE_URL, API_HOST, API_PORT
from shared.encoding import configure_utf8_stdio

configure_utf8_stdio()

API_URL = f"{API_BASE_URL}/api/v1/health/live"
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def _setup_logging() -> None:
    """Cấu hình logging đồng bộ ra console và file logs/app.log cho cả BE và FE."""
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception:
            pass


logger = logging.getLogger("aibuddy.launcher")


def _api_is_running() -> bool:
    try:
        with urllib.request.urlopen(API_URL, timeout=0.4):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _start_backend() -> None:
    if _api_is_running():
        logger.info("[BE] Backend API da san sang hoat dong tai %s:%s", API_HOST, API_PORT)
        return
    logger.info("[BE] Dang khoi dong Backend API tai http://%s:%s ...", API_HOST, API_PORT)
    config = uvicorn.Config(
        "backend.app:app",
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        access_log=True,
    )
    thread = threading.Thread(target=uvicorn.Server(config).run, name="aibuddy-api", daemon=True)
    thread.start()
    # Không chặn UI trong lúc Uvicorn khởi động. ConnectionScreen sẽ kiểm tra health,
    # báo timeout và cho phép đổi sang server khác nếu backend local không sẵn sàng.
    logger.info("[BE] Backend API dang khoi dong o background tai http://%s:%s", API_HOST, API_PORT)


if __name__ == "__main__":
    _setup_logging()
    logger.info("=== KHOI DONG HE THONG AI BUDDY (BE + FE) ===")
    logger.info("[LOG] File log: %s", LOG_FILE)
    _start_backend()
    logger.info("[FE] Dang khoi dong giao dien Desktop Flet...")
    ft.app(target=frontend_main, assets_dir=str(ASSETS_DIR))
