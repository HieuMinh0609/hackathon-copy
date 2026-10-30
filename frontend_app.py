"""Entrypoint đóng gói frontend desktop; không khởi động backend local."""
from __future__ import annotations

import flet as ft

from frontend.main import ASSETS_DIR, main


if __name__ == "__main__":
    ft.app(target=main, assets_dir=str(ASSETS_DIR))
