"""Quản lý danh mục các ứng dụng cần cài đặt và đường dẫn bộ cài (App Catalog)."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from sqlalchemy import text

from backend.core.utils.system_utils import InstallPlan, build_file_install_plan, check_software
from backend.services.db import get_connection, init_schema
from config.settings import Settings


def clean_version_tag(ver_str: str | None) -> str:
    """Chuẩn hóa chuỗi phiên bản để tạo tên thư mục hoặc tên tệp (ví dụ '>= 3.11' -> '3.11')."""
    if not ver_str:
        return ""
    v = ver_str.strip()
    v = re.sub(r"^[><=^~vV\s]+", "", v)
    v = re.sub(r'[\\/:*?"<>|\s]', "_", v)
    v = v.strip("._-")
    return v.lower()

DEFAULT_APPS = [
    {
        "app_code": "python",
        "app_name": "Python 3.11",
        "category": "Môi trường lập trình",
        "recommended_version": "3.11",
        "installer_path": "",
        "check_command": "python",
        "version_args": "--version",
        "install_args": '{"winget": "Python.Python.3.11", "choco": "python311"}',
        "description": "Ngôn ngữ chính chạy backend AI Buddy, dịch vụ RAG và các script tự động hóa.",
        "is_required": True,
    },
    {
        "app_code": "git",
        "app_name": "Git SCM",
        "category": "Quản lý mã nguồn",
        "recommended_version": "2.43.0",
        "installer_path": "",
        "check_command": "git",
        "version_args": "--version",
        "install_args": '{"winget": "Git.Git", "choco": "git"}',
        "description": "Hệ thống quản lý phiên bản phân tán bắt buộc cho toàn bộ dự án công ty.",
        "is_required": True,
    },
    {
        "app_code": "docker",
        "app_name": "Docker Desktop",
        "category": "Container & Hạ tầng",
        "recommended_version": "24.0",
        "installer_path": "",
        "check_command": "docker",
        "version_args": "--version",
        "install_args": '{"winget": "Docker.DockerDesktop", "choco": "docker-desktop"}',
        "description": "Quản lý container, khởi chạy PostgreSQL database local và các microservices.",
        "is_required": True,
    },
    {
        "app_code": "node",
        "app_name": "Node.js (LTS)",
        "category": "Môi trường Web & Tooling",
        "recommended_version": "18.0",
        "installer_path": "",
        "check_command": "node",
        "version_args": "--version",
        "install_args": '{"winget": "OpenJS.NodeJS.LTS", "choco": "nodejs-lts"}',
        "description": "Runtime JavaScript phục vụ build frontend và chạy các tooling dự án.",
        "is_required": False,
    },
    {
        "app_code": "vscode",
        "app_name": "Visual Studio Code",
        "category": "Công cụ lập trình",
        "recommended_version": "1.85.0",
        "installer_path": "",
        "check_command": "code",
        "version_args": "--version",
        "install_args": '{"winget": "Microsoft.VisualStudioCode", "choco": "vscode"}',
        "description": "IDE lập trình tiêu chuẩn kèm các extension hỗ trợ pair programming.",
        "is_required": False,
    },
    {
        "app_code": "psql",
        "app_name": "PostgreSQL Client (psql)",
        "category": "Cơ sở dữ liệu",
        "recommended_version": "16.0",
        "installer_path": "",
        "check_command": "psql",
        "version_args": "--version",
        "install_args": '{"winget": "PostgreSQL.PostgreSQL", "choco": "postgresql"}',
        "description": "Công cụ dòng lệnh psql kết nối và kiểm tra truy vấn tới database dev.",
        "is_required": True,
    },
    {
        "app_code": "dbeaver",
        "app_name": "DBeaver Community",
        "category": "Cơ sở dữ liệu",
        "recommended_version": "23.3.0",
        "installer_path": "",
        "check_command": "dbeaver",
        "version_args": "-version",
        "install_args": '{"winget": "dbeaver.dbeaver", "choco": "dbeaver"}',
        "description": "Trình quản trị CSDL trực quan, xem schema ERD và thao tác dữ liệu bảng.",
        "is_required": False,
    },
    {
        "app_code": "ollama",
        "app_name": "Ollama Local LLM",
        "category": "Trí tuệ nhân tạo",
        "recommended_version": "0.5.0",
        "installer_path": "",
        "check_command": "ollama",
        "version_args": "--version",
        "install_args": '{"winget": "Ollama.Ollama"}',
        "description": "Máy chủ AI cục bộ chạy mô hình Qwen 2.5 và bge-m3 hoàn toàn offline.",
        "is_required": True,
    },
]


class AppCatalogService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        init_schema(settings.database_url)
        self.seed_defaults()

    @property
    def _url(self) -> str:
        return self.settings.database_url

    def seed_defaults(self) -> int:
        now_str = datetime.now().isoformat(timespec="seconds")
        with get_connection(self._url) as conn:
            for it in DEFAULT_APPS:
                conn.execute(
                    text(
                        """
                        INSERT INTO app_catalog
                            (app_code, app_name, category, recommended_version, installer_path, check_command, version_args, install_args, description, is_required, created_at, updated_at)
                        VALUES
                            (:app_code, :app_name, :category, :recommended_version, :installer_path, :check_command, :version_args, :install_args, :description, :is_required, :now, :now)
                        ON CONFLICT (app_code) DO UPDATE SET
                            recommended_version = excluded.recommended_version
                        """
                    ),
                    {
                        "app_code": it["app_code"],
                        "app_name": it["app_name"],
                        "category": it["category"],
                        "recommended_version": it["recommended_version"],
                        "installer_path": it["installer_path"],
                        "check_command": it["check_command"],
                        "version_args": it["version_args"],
                        "install_args": it["install_args"],
                        "description": it["description"],
                        "is_required": it["is_required"],
                        "now": now_str,
                    },
                )
            # Dọn dẹp và chuẩn hóa bảng app_catalog: CHỈ lưu SUFFIX (subpath tương đối) của file cài đặt
            # Prefix thư mục được lưu trong env (INSTALLER_PREFIX)
            rows = conn.execute(text("SELECT app_code, recommended_version, installer_path FROM app_catalog")).mappings().all()
            for r in rows:
                code = r["app_code"]
                curr_p = (r["installer_path"] or "").strip()
                if not curr_p:
                    found = self.find_installer_file(code, recommended_version=r["recommended_version"] or "")
                    if found:
                        found_path = found[0]
                        try:
                            suffix = found_path.resolve().relative_to(self.settings.installers_dir.resolve()).as_posix()
                        except ValueError:
                            suffix = f"{found_path.parent.name}/{found_path.name}"
                        conn.execute(
                            text("UPDATE app_catalog SET installer_path = :path, updated_at = :now WHERE app_code = :code"),
                            {"path": suffix, "now": now_str, "code": code},
                        )
                else:
                    norm = curr_p.replace("\\", "/")
                    # Xóa triệt để các đường dẫn cục bộ máy client (C:\..., D:\..., /Users/..., /home/...)
                    if any(norm.lower().startswith(x) for x in ["c:", "d:", "e:", "/users/", "/home/"]):
                        conn.execute(
                            text("UPDATE app_catalog SET installer_path = '', updated_at = :now WHERE app_code = :code"),
                            {"now": now_str, "code": code},
                        )
                        continue
                    # Bóc tách tiền tố cũ nếu còn lưu dạng 'data/installers/...' hoặc 'installers/...'
                    clean_suffix = norm
                    for pfx in ["data/installers/", "installers/", "/data/installers/"]:
                        if clean_suffix.lower().startswith(pfx):
                            clean_suffix = clean_suffix[len(pfx):].lstrip("/")
                            break
                    if clean_suffix != curr_p:
                        conn.execute(
                            text("UPDATE app_catalog SET installer_path = :path, updated_at = :now WHERE app_code = :code"),
                            {"path": clean_suffix, "now": now_str, "code": code},
                        )
        return len(DEFAULT_APPS)

    def check_app_status(self, app: dict[str, Any]) -> dict[str, Any]:
        """Kiểm tra trạng thái cài đặt thực tế của ứng dụng trên máy người dùng."""
        cmd = app.get("check_command") or app.get("app_code") or ""
        raw_v_args = app.get("version_args") or "--version"
        v_args = [x.strip() for x in raw_v_args.split()] if raw_v_args else ["--version"]
        min_v = app.get("recommended_version") or None
        if min_v and min_v.startswith(">="):
            min_v = min_v[2:].strip()
        elif min_v and min_v.lower() == "latest":
            min_v = None

        status = check_software(app.get("app_name", cmd), cmd, version_args=v_args, min_version=min_v, timeout=2.5)
        is_installed = status.installed
        installed_version = status.version
        meets_min = status.meets_min

        # Kiểm tra file bộ cài có sẵn trên máy chủ BE để người dùng tải xuống
        has_file = False
        file_size = None
        installer_p = app.get("installer_path") or ""
        installer_file = self.find_installer_file(
            app_code=app.get("app_code") or "",
            installer_path=installer_p,
            recommended_version=app.get("recommended_version") or "",
        )
        if installer_file:
            has_file = True
            try:
                file_size = installer_file[0].stat().st_size
            except OSError:
                pass

        return {
            "is_installed": is_installed,
            "installed_version": installed_version,
            "meets_min": meets_min,
            "status": "INSTALLED" if is_installed else "NOT_INSTALLED",
            "has_installer_file": has_file,
            "installer_file_size": file_size,
        }

    def _get_raw_app_row(self, app_code: str) -> dict[str, Any] | None:
        """Lấy bản ghi thô từ cơ sở dữ liệu (không kiểm tra trạng thái máy)."""
        with get_connection(self._url) as conn:
            row = conn.execute(
                text("SELECT * FROM app_catalog WHERE app_code = :code LIMIT 1"),
                {"code": app_code.strip().lower()},
            ).mappings().first()
            return dict(row) if row else None

    def normalize_server_installer_path(
        self,
        raw_path: str | None,
        app_code: str = "",
        version: str = "",
    ) -> str:
        """Chuẩn hóa đường dẫn bộ cài đặt để CHỈ lưu SUFFIX (sub-path tương đối) trên Server BE.

        - Prefix thư mục lưu trữ được cấu hình qua biến môi trường INSTALLER_PREFIX (mặc định data/installers).
        - Bảng app_catalog chỉ lưu suffix, ví dụ: 'git_v2.43.0/Git-2.43.0-64-bit.exe' hoặc 'python_v3.11/python.exe'.
        - Hỗ trợ đầy đủ Windows (gạch chéo ngược \\, ký tự ổ đĩa C:, D:).
        """
        if not raw_path:
            return ""
        p_str = str(raw_path).strip().replace("\\", "/")
        if not p_str:
            return ""

        installers_dir_resolved = self.settings.installers_dir.resolve()
        base_dir_resolved = self.settings.base_dir.resolve()
        data_dir_resolved = self.settings.data_dir.resolve()
        configured_prefix = (getattr(self.settings, "installer_prefix", "data/installers") or "data/installers").replace("\\", "/").strip().strip("/")

        # Kiểm tra nếu là đường dẫn tuyệt đối (trên Windows: C:/..., D:/..., hoặc unix /...)
        try:
            expanded = Path(os.path.expandvars(os.path.expanduser(str(raw_path).strip())))
            if expanded.is_absolute():
                expanded_resolved = expanded.resolve()
                # 1. Nằm trong installers_dir của server BE
                try:
                    rel = expanded_resolved.relative_to(installers_dir_resolved)
                    return rel.as_posix()
                except ValueError:
                    pass

                # 2. Nằm trong base_dir của server BE
                try:
                    rel_base = expanded_resolved.relative_to(base_dir_resolved).as_posix()
                    for pfx in [f"{configured_prefix}/", "data/installers/", "installers/"]:
                        if rel_base.lower().startswith(pfx.lower()):
                            return rel_base[len(pfx):].lstrip("/")
                except ValueError:
                    pass

                # 3. Nằm trong data_dir của server BE
                try:
                    rel_data = expanded_resolved.relative_to(data_dir_resolved).as_posix()
                    if rel_data.lower().startswith("installers/"):
                        return rel_data[11:].lstrip("/")
                except ValueError:
                    pass

                # 4. Nếu là file tồn tại trên máy client (người dùng chọn file từ máy Windows):
                # Tự động nạp file này vào kho lưu trữ server BE và trả về suffix!
                if expanded.is_file() and app_code:
                    updated = self.save_installer_file(
                        app_code=app_code,
                        source_path=expanded,
                        version=version,
                    )
                    return updated.get("installer_path", "")

                # Đường dẫn tuyệt đối nhưng không tồn tại và không thuộc server -> không lưu
                return ""
        except Exception:
            pass

        # 5. Nếu có tiền tố prefix cũ hoặc prefix cấu hình, bóc tách lấy suffix
        for pfx in [f"{configured_prefix}/", "data/installers/", "installers/", "/data/installers/"]:
            if p_str.lower().startswith(pfx.lower()):
                p_str = p_str[len(pfx):].lstrip("/")
                break

        # Kiểm tra tính an toàn: không cho phép directory traversal (..)
        clean_suffix = p_str.lstrip("/")
        parts = clean_suffix.split("/")
        if ".." in parts:
            return ""

        return clean_suffix

    def find_installer_file(
        self,
        app_code: str,
        installer_path: str = "",
        recommended_version: str = "",
    ) -> tuple[Path, str] | None:
        """Lấy đường dẫn tệp bộ cài đặt trên server nếu có (quét cả thư mục có version).

        Bảng app_catalog lưu suffix (subpath). Server ghép prefix (installers_dir) + suffix.
        """
        code = app_code.strip().lower()
        if installer_path and installer_path.strip():
            raw_p = installer_path.strip().replace("\\", "/")
            suffix = raw_p
            for pfx in ["data/installers/", "installers/", "/data/installers/"]:
                if suffix.lower().startswith(pfx):
                    suffix = suffix[len(pfx):].lstrip("/")
                    break

            # 1. Ghép prefix (installers_dir) + suffix (Trường hợp chuẩn)
            try:
                candidate_inst = (self.settings.installers_dir / suffix).resolve()
                if candidate_inst.is_file():
                    return (candidate_inst, candidate_inst.name)
            except Exception:
                pass

            # 2. Tìm theo tên file trong installers_dir và các thư mục con
            try:
                fname = Path(suffix).name
                if fname:
                    candidate_file = (self.settings.installers_dir / fname).resolve()
                    if candidate_file.is_file():
                        return (candidate_file, candidate_file.name)
                    if self.settings.installers_dir.is_dir():
                        matches = [p for p in self.settings.installers_dir.rglob(fname) if p.is_file()]
                        if matches:
                            newest = max(matches, key=lambda x: x.stat().st_mtime)
                            return (newest, newest.name)
            except Exception:
                pass

            # 3. Tương thích ngược: nếu installer_path là đường dẫn so với base_dir
            try:
                candidate_base = (self.settings.base_dir / raw_p).resolve()
                if candidate_base.is_file():
                    return (candidate_base, candidate_base.name)
            except Exception:
                pass

            # 4. Tương thích ngược: nếu là đường dẫn tuyệt đối
            try:
                expanded = Path(os.path.expandvars(os.path.expanduser(raw_p)))
                if expanded.is_file():
                    return (expanded.resolve(), expanded.name)
            except Exception:
                pass

        # Quét các thư mục con theo phiên bản trong installers_dir
        clean_ver = clean_version_tag(recommended_version)
        candidate_folders: list[Path] = []
        if clean_ver:
            candidate_folders.append(self.settings.installers_dir / f"{code}_v{clean_ver}")
            candidate_folders.append(self.settings.installers_dir / f"{code}_{clean_ver}")
            candidate_folders.append(self.settings.installers_dir / code / f"v{clean_ver}")
            candidate_folders.append(self.settings.installers_dir / code / clean_ver)
        candidate_folders.append(self.settings.installers_dir / code)

        for folder in candidate_folders:
            if folder.is_dir():
                files = [f for f in folder.iterdir() if f.is_file() and f.name != ".gitkeep"]
                if files:
                    newest = max(files, key=lambda x: x.stat().st_mtime)
                    return (newest, newest.name)

        # Quét mọi folder bắt đầu bằng code trong installers_dir
        if self.settings.installers_dir.is_dir():
            matching_folders = [
                d for d in self.settings.installers_dir.iterdir()
                if d.is_dir() and (d.name == code or d.name.startswith(f"{code}_") or d.name.startswith(f"{code}-"))
            ]
            for folder in sorted(matching_folders, key=lambda x: x.stat().st_mtime, reverse=True):
                files = [f for f in folder.iterdir() if f.is_file() and f.name != ".gitkeep"]
                if files:
                    newest = max(files, key=lambda x: x.stat().st_mtime)
                    return (newest, newest.name)

            # Quét trực tiếp các tệp trong installers_dir có tên bắt đầu bằng code
            matching_files = [
                f for f in self.settings.installers_dir.iterdir()
                if f.is_file() and f.name != ".gitkeep" and (
                    f.stem.lower() == code or f.stem.lower().startswith(f"{code}_") or f.stem.lower().startswith(f"{code}-")
                )
            ]
            if matching_files:
                newest = max(matching_files, key=lambda x: x.stat().st_mtime)
                return (newest, newest.name)

            # Quét đệ quy rglob cho các file có chứa code
            deep_matching = [
                f for f in self.settings.installers_dir.rglob("*")
                if f.is_file() and f.name != ".gitkeep" and (
                    code in f.stem.lower() or code in f.parent.name.lower()
                )
            ]
            if deep_matching:
                newest = max(deep_matching, key=lambda x: x.stat().st_mtime)
                return (newest, newest.name)

        return None

    def get_installer_folder(self, app_code: str, version: str | None = None) -> Path:
        """Thư mục lưu trữ bộ cài đặt trên server kèm version: data/installers/<app_code>_v<version>/"""
        code = app_code.strip().lower()
        clean_ver = clean_version_tag(version)
        if not clean_ver:
            raw = self._get_raw_app_row(code)
            if raw:
                clean_ver = clean_version_tag(raw.get("recommended_version"))

        folder_name = f"{code}_v{clean_ver}" if clean_ver else code
        folder = self.settings.installers_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def save_installer_file(
        self,
        app_code: str,
        source_path: str | Path | None = None,
        file_bytes: bytes | None = None,
        filename: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Lưu trữ tệp bộ cài đặt lên thư mục server có kèm version (data/installers/<app_code>_v<version>/)."""
        raw = self._get_raw_app_row(app_code)
        if not raw:
            raise KeyError(f"Không tìm thấy ứng dụng với mã '{app_code}'.")

        clean_ver = clean_version_tag(version or raw.get("recommended_version"))
        folder = self.get_installer_folder(app_code, version=clean_ver)

        # Không cho phép tải lên ứng dụng và phiên bản trùng nhau
        if folder.is_dir():
            existing_files = [f for f in folder.iterdir() if f.is_file()]
            if existing_files:
                raise ValueError(
                    f"Ứng dụng '{raw.get('app_name', app_code)}' với phiên bản '{clean_ver or 'cố định'}' "
                    f"đã có tệp bộ cài đặt trên máy chủ ({existing_files[0].name}). Không được tải lên trùng nhau."
                )

        dest_filename = filename

        if source_path:
            src = Path(source_path)
            if not src.is_file():
                raise FileNotFoundError(f"Tệp nguồn '{source_path}' không tồn tại trên máy.")
            dest_filename = dest_filename or src.name
            dest_path = folder / dest_filename
            shutil.copy2(src, dest_path)
        elif file_bytes is not None:
            ver_part = f"_v{clean_ver}" if clean_ver else ""
            dest_filename = dest_filename or f"{app_code}{ver_part}_installer.exe"
            dest_path = folder / dest_filename
            dest_path.write_bytes(file_bytes)
        else:
            raise ValueError("Cần cung cấp 'source_path' hoặc 'file_bytes'.")

        # Lưu SUFFIX (subpath tương đối) trên server BE: <folder_name>/<dest_filename>
        # Prefix thư mục lưu trữ được quản lý qua biến môi trường INSTALLER_PREFIX
        try:
            rel_suffix = dest_path.resolve().relative_to(self.settings.installers_dir.resolve()).as_posix()
        except ValueError:
            rel_suffix = f"{folder.name}/{dest_filename}"

        # Cập nhật suffix của file cài đặt vào database
        updated_app = self.update_installer_path(app_code, rel_suffix)
        return updated_app

    def installer_plan(self, app_code: str) -> InstallPlan:
        """Ưu tiên đúng tệp được lưu, không tự chọn một bộ cài khác nếu đường dẫn lỗi."""
        app = self._get_raw_app_row(app_code)
        if not app:
            raise ValueError("Không tìm thấy ứng dụng trong App Catalog.")
        saved = str(app.get("installer_path") or "").strip()
        if not saved:
            raise ValueError("Ứng dụng chưa có đường dẫn bộ cài. Vui lòng cập nhật App Catalog.")
        saved = os.path.expandvars(os.path.expanduser(saved)).replace("\\", "/")
        for prefix in ("data/installers/", "installers/"):
            if saved.startswith(prefix):
                saved = saved[len(prefix):]
                break
        path = Path(saved)
        if not path.is_absolute():
            path = self.settings.installers_dir / path
        return build_file_install_plan(app["app_name"], path, str(app.get("install_args") or ""))

    def get_installer_file(self, app_code: str) -> tuple[Path, str] | None:
        """Lấy đường dẫn tệp bộ cài đặt trên server nếu có (quét cả thư mục có version)."""
        raw = self._get_raw_app_row(app_code)
        if not raw:
            return None
        return self.find_installer_file(
            app_code=app_code,
            installer_path=raw.get("installer_path") or "",
            recommended_version=raw.get("recommended_version") or "",
        )

    def list_apps(self, query: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
        """Lấy danh sách ứng dụng, có hỗ trợ tìm kiếm và lọc danh mục."""
        sql = "SELECT * FROM app_catalog"
        wheres: list[str] = []
        params: dict[str, Any] = {}

        if category and category != "Tất cả":
            wheres.append("category = :category")
            params["category"] = category

        if query and query.strip():
            q = f"%{query.strip().lower()}%"
            wheres.append(
                "(LOWER(app_name) LIKE :q OR LOWER(app_code) LIKE :q OR LOWER(category) LIKE :q OR LOWER(installer_path) LIKE :q OR LOWER(description) LIKE :q)"
            )
            params["q"] = q

        if wheres:
            sql += " WHERE " + " AND ".join(wheres)

        sql += " ORDER BY is_required DESC, app_id ASC"

        with get_connection(self._url) as conn:
            rows = [dict(r) for r in conn.execute(text(sql), params).mappings()]

        if rows:
            from concurrent.futures import ThreadPoolExecutor

            def _check_one(r: dict[str, Any]) -> dict[str, Any]:
                st = self.check_app_status(r)
                r.update(st)
                return r

            with ThreadPoolExecutor(max_workers=min(len(rows), 8)) as executor:
                rows = list(executor.map(_check_one, rows))

        return rows

    def get_app(self, app_code: str) -> dict[str, Any] | None:
        """Lấy thông tin một ứng dụng theo mã app_code."""
        with get_connection(self._url) as conn:
            row = conn.execute(
                text("SELECT * FROM app_catalog WHERE app_code = :code LIMIT 1"),
                {"code": app_code},
            ).mappings().first()
            if not row:
                return None
            res = dict(row)
            st = self.check_app_status(res)
            res.update(st)
            return res

    def update_installer_path(self, app_code: str, installer_path: str) -> dict[str, Any]:
        """Cập nhật đường dẫn bộ cài đặt của ứng dụng (chỉ lưu đường dẫn trên server BE)."""
        code = app_code.strip().lower()
        raw = self._get_raw_app_row(code)
        rec_ver = raw.get("recommended_version", "") if raw else ""
        norm_path = self.normalize_server_installer_path(installer_path, app_code=code, version=rec_ver)

        now_str = datetime.now().isoformat(timespec="seconds")
        with get_connection(self._url) as conn:
            conn.execute(
                text(
                    """
                    UPDATE app_catalog
                    SET installer_path = :path, updated_at = :now
                    WHERE app_code = :code
                    """
                ),
                {"path": norm_path, "code": code, "now": now_str},
            )
        app = self.get_app(code)
        if app is None:
            raise KeyError(f"Không tìm thấy ứng dụng với mã '{code}'.")
        return app

    def update_app(self, app_code: str, data: dict[str, Any]) -> dict[str, Any]:
        """Cập nhật thông tin ứng dụng trong app_catalog: version, check_command, version_args, installer_path, app_name, v.v."""
        code = app_code.strip().lower()
        raw = self._get_raw_app_row(code)
        if raw is None:
            raise KeyError(f"Không tìm thấy ứng dụng với mã '{code}'.")

        rec_ver = str(data.get("recommended_version", raw.get("recommended_version", ""))).strip()
        app_name = str(data.get("app_name", raw.get("app_name", ""))).strip() or raw.get("app_name", "")
        category = str(data.get("category", raw.get("category", "Công cụ chung"))).strip()
        check_command = str(data.get("check_command", raw.get("check_command", ""))).strip()
        version_args = str(data.get("version_args", raw.get("version_args", "--version"))).strip()
        install_args = str(data.get("install_args", raw.get("install_args", ""))).strip()
        description = str(data.get("description", raw.get("description", ""))).strip()

        if "installer_path" in data and data["installer_path"] is not None:
            raw_path = str(data["installer_path"]).strip()
            norm_path = self.normalize_server_installer_path(raw_path, app_code=code, version=rec_ver)
        else:
            norm_path = raw.get("installer_path", "")

        now_str = datetime.now().isoformat(timespec="seconds")
        with get_connection(self._url) as conn:
            conn.execute(
                text(
                    """
                    UPDATE app_catalog
                    SET
                        app_name = :app_name,
                        category = :category,
                        recommended_version = :rec_ver,
                        installer_path = :installer_path,
                        check_command = :check_command,
                        version_args = :version_args,
                        install_args = :install_args,
                        description = :description,
                        updated_at = :now
                    WHERE app_code = :code
                    """
                ),
                {
                    "app_name": app_name,
                    "category": category,
                    "rec_ver": rec_ver,
                    "installer_path": norm_path,
                    "check_command": check_command,
                    "version_args": version_args,
                    "install_args": install_args,
                    "description": description,
                    "now": now_str,
                    "code": code,
                },
            )
        app = self.get_app(code)
        if app is None:
            raise KeyError(f"Không tìm thấy ứng dụng với mã '{code}'.")
        return app

    def create_app(self, data: dict[str, Any]) -> dict[str, Any]:
        """Tạo mới một ứng dụng vào danh mục (đường dẫn bộ cài được chuẩn hóa về server BE)."""
        app_code = str(data.get("app_code", "")).strip().lower()
        if not app_code:
            raise ValueError("Mã ứng dụng (app_code) không được để trống.")
        app_name = str(data.get("app_name", "")).strip()
        if not app_name:
            raise ValueError("Tên ứng dụng (app_name) không được để trống.")

        raw_installer_p = str(data.get("installer_path", "")).strip()
        rec_ver = str(data.get("recommended_version", "")).strip()
        norm_path = self.normalize_server_installer_path(raw_installer_p, app_code=app_code, version=rec_ver)

        now_str = datetime.now().isoformat(timespec="seconds")
        with get_connection(self._url) as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO app_catalog
                        (app_code, app_name, category, recommended_version, installer_path, check_command, version_args, install_args, description, is_required, created_at, updated_at)
                    VALUES
                        (:app_code, :app_name, :category, :recommended_version, :installer_path, :check_command, :version_args, :install_args, :description, :is_required, :now, :now)
                    ON CONFLICT (app_code) DO UPDATE SET
                        app_name = excluded.app_name,
                        category = excluded.category,
                        recommended_version = excluded.recommended_version,
                        installer_path = excluded.installer_path,
                        check_command = excluded.check_command,
                        version_args = excluded.version_args,
                        install_args = excluded.install_args,
                        description = excluded.description,
                        is_required = excluded.is_required,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "app_code": app_code,
                    "app_name": app_name,
                    "category": str(data.get("category", "Công cụ chung")).strip(),
                    "recommended_version": rec_ver,
                    "installer_path": norm_path,
                    "check_command": str(data.get("check_command", "")).strip(),
                    "version_args": str(data.get("version_args", "--version")).strip(),
                    "install_args": str(data.get("install_args", "")).strip(),
                    "description": str(data.get("description", "")).strip(),
                    "is_required": bool(data.get("is_required", True)),
                    "now": now_str,
                },
            )
        return self.get_app(app_code) or {}

    def categories(self) -> list[str]:
        """Lấy danh sách các danh mục ứng dụng."""
        with get_connection(self._url) as conn:
            rows = conn.execute(text("SELECT DISTINCT category FROM app_catalog ORDER BY category")).all()
            return [r[0] for r in rows if r[0]]

    def delete_app(self, app_code: str) -> bool:
        """Xóa một ứng dụng khỏi danh mục app_catalog (Chỉ Admin)."""
        code = str(app_code).strip().lower()
        if not code:
            return False
        with get_connection(self._url) as conn:
            existing = conn.execute(
                text("SELECT app_id FROM app_catalog WHERE app_code = :code"),
                {"code": code},
            ).first()
            if not existing:
                return False
            conn.execute(
                text("DELETE FROM app_catalog WHERE app_code = :code"),
                {"code": code},
            )
            return True
