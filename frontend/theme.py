"""Design tokens cho giao diện Clean Modern Light Theme (theo thiết kế React Tailwind)."""
from __future__ import annotations

import flet as ft

# Palette màu sáng hiện đại (Tailwind-like)
BG = "#F9FAFB"            # gray-50
SURFACE = "#FFFFFF"       # white
SURFACE_ALT = "#F3F4F6"   # gray-100
SURFACE_HOVER = "#F8FAFC" # slate-50

BORDER = "#E5E7EB"        # gray-200
BORDER_LIGHT = "#F3F4F6"  # gray-100
BORDER_FOCUS = "#3B82F6"  # blue-500

# Primary colors (Blue)
PRIMARY = "#2563EB"       # blue-600
PRIMARY_HOVER = "#1D4ED8" # blue-700
PRIMARY_BG = "#EFF6FF"    # blue-50
PRIMARY_BORDER = "#BFDBFE"# blue-200
ACCENT = PRIMARY

# Accent & Functional colors
EMERALD = "#10B981"       # emerald-500
EMERALD_BG = "#ECFDF5"    # emerald-50
EMERALD_BORDER = "#A7F3D0"

SUCCESS = EMERALD
SUCCESS_BG = EMERALD_BG
SUCCESS_BORDER = EMERALD_BORDER

PURPLE = "#8B5CF6"        # purple-500
PURPLE_BG = "#F5F3FF"     # purple-50
PURPLE_BORDER = "#DDD6FE" # purple-200
ACCENT_2 = PURPLE

OK = "#10B981"            # green-500

# Warning colors (Amber)
WARN = "#F59E0B"          # amber-500
WARN_BG = "#FFFBEB"       # amber-50
WARN_BORDER = "#FDE68A"   # amber-200
WARNING = WARN
WARNING_BG = WARN_BG
WARNING_BORDER = WARN_BORDER

# Error / Danger colors (Red)
ERR = "#EF4444"           # red-500
ERR_BG = "#FEF2F2"        # red-50
ERR_BORDER = "#FECACA"    # red-200
ERROR = ERR
ERROR_BG = ERR_BG
ERROR_BORDER = ERR_BORDER
DANGER = ERR
DANGER_BG = ERR_BG
DANGER_BORDER = ERR_BORDER

# Typography colors
TEXT = "#111827"          # gray-900
TEXT_MUTED = "#6B7280"    # gray-500
TEXT_LIGHT = "#9CA3AF"    # gray-400
TEXT_WHITE = "#FFFFFF"
MUTED = TEXT_MUTED

# Mapping trạng thái checklist
STATUS_STYLE = {
    "passed": (ft.Icons.CHECK_CIRCLE, OK),
    "COMPLETED": (ft.Icons.CHECK_CIRCLE, OK),
    "failed": (ft.Icons.CANCEL, ERR),
    "BLOCKED": (ft.Icons.BLOCK, ERR),
    "warning": (ft.Icons.WARNING_AMBER_ROUNDED, WARN),
    "pending": (ft.Icons.RADIO_BUTTON_UNCHECKED, TEXT_LIGHT),
    "ACTIVE": (ft.Icons.RADIO_BUTTON_UNCHECKED, TEXT_LIGHT),
    "active": (ft.Icons.RADIO_BUTTON_UNCHECKED, TEXT_LIGHT),
    "IN_PROGRESS": (ft.Icons.ACCESS_TIME, PRIMARY),
}


def card_decoration(
    bg: str = SURFACE,
    border_color: str = BORDER,
    radius: int = 16,
    padding: int = 16,
    shadow: bool = True,
    **kwargs,
) -> dict:
    """Thuộc tính chung cho Container dạng Card nổi bật."""
    decor = dict(
        bgcolor=bg,
        border=ft.border.all(1, border_color),
        border_radius=radius,
        padding=padding,
        **kwargs,
    )
    if shadow:
        decor["shadow"] = ft.BoxShadow(
            spread_radius=0,
            blur_radius=8,
            color=ft.Colors.with_opacity(0.04, "#000000"),
            offset=ft.Offset(0, 2),
        )
    return decor
