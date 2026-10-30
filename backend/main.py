"""Entrypoint chạy riêng backend khi phát triển."""
from __future__ import annotations

import logging
from pathlib import Path
import sys
import uvicorn

from shared.config import API_HOST, API_PORT
from shared.encoding import configure_utf8_stdio

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"


def main() -> None:
    configure_utf8_stdio()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        root_logger.addHandler(ch)
        try:
            fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
            fh.setFormatter(formatter)
            root_logger.addHandler(fh)
        except Exception:
            pass

    print(f"Dang khoi dong backend API tai http://{API_HOST}:{API_PORT} ...")
    uvicorn.run("backend.app:app", host=API_HOST, port=API_PORT, log_level="info", access_log=True)


if __name__ == "__main__":
    main()
