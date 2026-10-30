"""HTTP client đồng bộ cho backend local; mọi payload đều là JSON."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any

from shared.config import API_BASE_URL

logger = logging.getLogger("frontend.api")


class ApiError(RuntimeError):
    """Backend không truy cập được hoặc trả về lỗi nghiệp vụ."""


class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL, timeout: float = 1800.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_email: str | None = None
        self.session_key: str | None = None

    def set_base_url(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        # Session của server cũ không được gửi sang server vừa đổi.
        self.set_user_email(None)
        self.set_session_key(None)

    def health_check(self, timeout: float = 2.0) -> bool:
        """Kiểm tra nhanh server mà không dùng timeout dài của các tác vụ LLM/ingest."""
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/health/live",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False
        data = result.get("data") if isinstance(result, dict) else None
        return bool(
            isinstance(result, dict)
            and result.get("success") is True
            and isinstance(data, dict)
            and data.get("status") == "ok"
        )

    def set_user_email(self, email: str | None) -> None:
        self.user_email = email.strip().lower() if email else None

    def set_session_key(self, session_key: str | None) -> None:
        self.session_key = session_key.strip() if session_key else None

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        logger.info("[FE -> BE] %s %s", method, path)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.session_key:
            headers["X-Session-Key"] = self.session_key
        if self.user_email:
            headers["X-User-Email"] = self.user_email
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                logger.info("[FE <- BE] %s %s -> %d OK", method, path, response.status)
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read().decode("utf-8"))
                detail = data.get("detail") or data.get("error") or str(exc)
            except (ValueError, UnicodeDecodeError):
                detail = str(exc)
            logger.error("[FE <- BE LOI] %s %s -> HTTP %d: %s", method, path, exc.code, detail)
            raise ApiError(str(detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.error("[FE <- BE LOI KET NOI] %s %s: %s", method, path, exc)
            raise ApiError(f"Không kết nối được backend local: {exc}") from exc
        if not result.get("success", False):
            err_msg = result.get("error") or "Backend trả về lỗi không xác định."
            logger.error("[FE <- BE LOI NGIEP VU] %s %s: %s", method, path, err_msg)
            raise ApiError(err_msg)
        return result.get("data")

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, payload or {})

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PUT", path, payload)

    def delete(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("DELETE", path, payload)

    def download_file(
        self,
        path: str,
        dest_path: Path | str,
        exact_path: bool = False,
        on_progress: Any = None,
    ) -> Path:
        import re
        from urllib.parse import unquote
        target = Path(dest_path)
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/octet-stream"}
        if self.session_key:
            headers["X-Session-Key"] = self.session_key
        if self.user_email:
            headers["X-User-Email"] = self.user_email
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content_disp = response.headers.get("Content-Disposition", "")
                real_filename = ""
                if "filename=" in content_disp or "filename*=" in content_disp:
                    m = re.search(r"filename\*?=(?:UTF-8\'\')?\"?([^;\"]+)\"?", content_disp, re.IGNORECASE)
                    if m:
                        real_filename = unquote(m.group(1).strip().strip('"').strip("'"))
                if target.is_dir():
                    fname = real_filename or "installer.exe"
                    target = target / fname
                elif not exact_path and real_filename and target.name.endswith("_installer.exe") and real_filename != target.name:
                    target = target.parent / real_filename
                elif real_filename and not target.suffix and Path(real_filename).suffix:
                    target = target.with_suffix(Path(real_filename).suffix)

                target.parent.mkdir(parents=True, exist_ok=True)

                # Lấy tổng dung lượng tệp từ header Content-Length
                length_hdr = response.headers.get("Content-Length")
                total_bytes = int(length_hdr) if length_hdr and length_hdr.isdigit() else 0
                downloaded_bytes = 0

                if on_progress:
                    try:
                        on_progress(0, total_bytes)
                    except Exception:
                        pass

                # Mở và ghi tệp (nếu file đang bị Windows khóa, tự động sinh tên thay thế an toàn)
                out_handle = None
                write_target = target
                for attempt in range(10):
                    try:
                        out_handle = open(write_target, "wb")
                        target = write_target
                        break
                    except PermissionError:
                        if attempt < 9:
                            suffix = target.suffix
                            stem = target.stem
                            write_target = target.parent / f"{stem} ({attempt + 1}){suffix}"
                        else:
                            raise

                with out_handle:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        out_handle.write(chunk)
                        downloaded_bytes += len(chunk)
                        if on_progress:
                            try:
                                on_progress(downloaded_bytes, total_bytes)
                            except Exception:
                                pass
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read().decode("utf-8"))
                detail = data.get("detail") or data.get("error") or str(exc)
            except (ValueError, UnicodeDecodeError):
                detail = str(exc)
            raise ApiError(str(detail)) from exc
        except PermissionError as exc:
            raise ApiError(f"Không thể ghi tệp vào '{target}'. Tệp đang bị khóa hoặc không có quyền ghi: {exc}") from exc
        except Exception as exc:
            raise ApiError(f"Lỗi khi tải tệp từ máy chủ: {exc}") from exc
        return target
