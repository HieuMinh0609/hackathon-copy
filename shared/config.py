"""Cấu hình transport local giữa frontend và backend."""
from __future__ import annotations

import os


API_HOST = os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1"
API_PORT = int(os.getenv("LOCAL_API_PORT", "8765"))
API_BASE_URL = f"http://{API_HOST}:{API_PORT}"

