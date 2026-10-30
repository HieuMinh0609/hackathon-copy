"""Nạp tài liệu vào ChromaDB.

Ví dụ:
    python scripts/ingest_document.py                 # nạp toàn bộ thư mục documents/
    python scripts/ingest_document.py --reset         # xoá rồi nạp lại
    python scripts/ingest_document.py --file documents/hr/policy.pdf
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings  # noqa: E402
from backend.rag import ingest  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Nạp tài liệu vào kho tri thức (ChromaDB)")
    parser.add_argument("--dir", type=Path, help="Thư mục tài liệu (mặc định: documents/)")
    parser.add_argument("--file", type=Path, action="append", help="Chỉ nạp file này (lặp được nhiều lần)")
    parser.add_argument("--reset", action="store_true", help="Xoá collection trước khi nạp")
    args = parser.parse_args()

    settings = get_settings()

    def progress(i: int, n: int, name: str) -> None:
        print(f"[{i}/{n}] {name}")

    if args.file:
        report = ingest.ingest_files(settings, [f.resolve() for f in args.file], reset=args.reset, progress=progress)
    else:
        report = ingest.ingest_directory(settings, args.dir, reset=args.reset, progress=progress)

    print(report.summary())
    for err in report.errors:
        print("  !", err)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
