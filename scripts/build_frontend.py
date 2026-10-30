"""Chuẩn bị source tối thiểu và đóng gói ứng dụng frontend-only bằng Flet CLI 0.28.3."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


TARGETS = ("windows", "linux", "macos", "web", "apk", "aab", "ipa")


def _default_target() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _validate_build_path(project_root: Path, path: Path) -> Path:
    resolved_root = project_root.resolve()
    resolved = path.resolve()
    build_root = (resolved_root / "build").resolve()
    if resolved == build_root or build_root not in resolved.parents:
        raise ValueError(f"Thư mục staging phải nằm bên trong {build_root}")
    return resolved


def prepare_stage(project_root: Path, stage_dir: Path) -> Path:
    """Tạo gói source frontend không chứa backend, dữ liệu runtime hoặc secret."""
    project_root = project_root.resolve()
    stage_dir = _validate_build_path(project_root, stage_dir)
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(project_root / "frontend", stage_dir / "frontend", ignore=ignore)
    shutil.copytree(project_root / "shared", stage_dir / "shared", ignore=ignore)
    shutil.copy2(project_root / "frontend_app.py", stage_dir / "main.py")
    shutil.copy2(project_root / "requirements-frontend.txt", stage_dir / "requirements.txt")
    return stage_dir


def _find_flet_cli() -> str:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [executable_dir / "flet.exe", executable_dir / "flet"]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    discovered = shutil.which("flet")
    if discovered:
        return discovered
    raise RuntimeError("Không tìm thấy Flet CLI. Hãy cài: pip install -r requirements-frontend.txt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ứng dụng AI Buddy frontend-only.")
    parser.add_argument("--target", choices=TARGETS, default=_default_target())
    parser.add_argument("--version", default="1.0.0", help="Phiên bản hiển thị, dạng x.y.z.")
    parser.add_argument("--build-number", default="1", help="Mã build nội bộ.")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Chỉ tạo staging để kiểm tra, không gọi Flet build.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    stage_dir = prepare_stage(project_root, project_root / "build" / "frontend-stage")
    print(f"Đã chuẩn bị frontend-only tại: {stage_dir}")
    if args.prepare_only:
        return 0

    output_dir = project_root / "dist" / "frontend" / args.target
    command = [
        _find_flet_cli(),
        "build",
        args.target,
        str(stage_dir),
        "--output",
        str(output_dir),
        "--project",
        "ai_buddy",
        "--product",
        "AI Buddy",
        "--org",
        "com.aibuddy",
        "--bundle-id",
        "com.aibuddy.desktop",
        "--description",
        "AI Buddy onboarding desktop client",
        "--build-version",
        args.version,
        "--build-number",
        args.build_number,
        "--compile-app",
        "--cleanup-app",
    ]
    if args.clear_cache:
        command.append("--clear-cache")
    print(f"Đang build frontend target '{args.target}'...")
    subprocess.run(command, cwd=project_root, check=True)
    print(f"Build hoàn tất: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
