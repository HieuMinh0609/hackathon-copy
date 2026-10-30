"""Script tự động build Custom Model 'aibuddy-checklist' từ Modelfile cho Ollama."""
from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from shared.encoding import completed_output, configure_utf8_stdio  # noqa: E402

configure_utf8_stdio()

MODELFILE_PATH = BASE_DIR / "config" / "Modelfile.checklist"
MODEL_NAME = "aibuddy-checklist"


def is_ollama_running(url: str = "http://localhost:11434/api/tags") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3.0):
            return True
    except Exception:
        return False


def main() -> int:
    print("=" * 70)
    print("   AI BUDDY - OLLAMA CUSTOM MODEL BUILDER")
    print(f"   Mô hình đích: {MODEL_NAME}")
    print(f"   Modelfile:    {MODELFILE_PATH}")
    print("=" * 70)

    if not MODELFILE_PATH.exists():
        print(f"❌ Không tìm thấy file {MODELFILE_PATH}")
        return 1

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        print("❌ Lệnh 'ollama' không tìm thấy trong PATH hệ thống.")
        print("💡 Hãy cài đặt Ollama từ: https://ollama.com hoặc 'winget install Ollama.Ollama'")
        return 1

    if not is_ollama_running():
        print("⚠️ Dịch vụ Ollama chưa chạy ngầm trên cổng 11434.")
        print("💡 Hãy mở Ollama hoặc chạy lệnh: 'ollama serve'")
        print(f"👉 Sau đó chạy lệnh sau để build thủ công:")
        print(f"   ollama create {MODEL_NAME} -f {MODELFILE_PATH}\n")
        return 1

    print(f"🚀 Đang tiến hành build model '{MODEL_NAME}' qua Ollama CLI...")
    cmd = [ollama_bin, "create", MODEL_NAME, "-f", str(MODELFILE_PATH)]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True)
        stdout, stderr = completed_output(proc)
        if proc.returncode == 0:
            print(f"✅ Build thành công mô hình '{MODEL_NAME}:latest' trong Ollama!")
            print(stdout)
            print("👉 Bây giờ bạn có thể chạy: ollama run aibuddy-checklist")
            print("👉 Hoặc bật switch Checklist trên app AI Buddy để sử dụng tự động.")
            return 0
        else:
            print(f"❌ Build thất bại với mã lỗi {proc.returncode}:")
            print(stderr or stdout)
            return proc.returncode
    except Exception as exc:
        print(f"❌ Lỗi khi thực thi: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
