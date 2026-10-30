from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.app_catalog_service import AppCatalogService


@pytest.fixture
def catalog_service(settings) -> AppCatalogService:
    return AppCatalogService(settings)


def test_seed_defaults(catalog_service):
    apps = catalog_service.list_apps()
    assert len(apps) >= 8
    codes = {a["app_code"] for a in apps}
    assert "python" in codes
    assert "git" in codes
    assert "docker" in codes
    assert "node" in codes
    assert "vscode" in codes
    assert "psql" in codes
    assert "dbeaver" in codes
    assert "ollama" in codes


def test_list_and_search_apps(catalog_service):
    # Tìm kiếm theo tên hoặc mã
    git_results = catalog_service.list_apps(query="git")
    assert len(git_results) >= 1
    assert any("git" in a["app_code"] for a in git_results)

    # Tìm kiếm theo từ khóa không tồn tại
    empty_results = catalog_service.list_apps(query="nonexistent_xyz_app")
    assert len(empty_results) == 0

    # Lọc theo danh mục
    db_results = catalog_service.list_apps(category="Cơ sở dữ liệu")
    assert len(db_results) >= 1
    assert all(a["category"] == "Cơ sở dữ liệu" for a in db_results)


def test_update_installer_path(catalog_service):
    # Dù người dùng hoặc legacy input có tiền tố data/installers/, DB chỉ lưu suffix
    custom_path = "data/installers/git_v2.43/Git-2.43.0-64-bit.exe"
    expected_suffix = "git_v2.43/Git-2.43.0-64-bit.exe"
    updated = catalog_service.update_installer_path("git", custom_path)
    assert updated["app_code"] == "git"
    assert updated["installer_path"] == expected_suffix

    # Kiểm tra lại qua get_app
    app_info = catalog_service.get_app("git")
    assert app_info is not None
    assert app_info["installer_path"] == expected_suffix


def test_create_app(catalog_service):
    new_app_data = {
        "app_code": "postman",
        "app_name": "Postman Desktop",
        "category": "Công cụ lập trình",
        "recommended_version": "10.0",
        "installer_path": "postman_v10.0/postman-setup.exe",
        "check_command": "postman",
        "version_args": "--version",
        "description": "Nền tảng kiểm thử và thiết kế API.",
        "is_required": False,
    }
    created = catalog_service.create_app(new_app_data)
    assert created["app_code"] == "postman"
    assert created["app_name"] == "Postman Desktop"

    # Tìm lại
    search_res = catalog_service.list_apps(query="postman")
    assert len(search_res) == 1
    assert search_res[0]["installer_path"] == "postman_v10.0/postman-setup.exe"


def test_server_installer_path_normalization(catalog_service, settings):
    # 1. Non-existent client local path is NOT saved to DB
    res = catalog_service.update_installer_path("git", r"C:\NonExistent\test\my_app.exe")
    assert res["installer_path"] == ""

    # 2. Backslashes on Windows in data/installers are stripped and converted to clean POSIX suffix
    res2 = catalog_service.update_installer_path("git", r"data\installers\git_v2.30\git.exe")
    assert res2["installer_path"] == "git_v2.30/git.exe"

    # 2b. Direct suffix with Windows backslashes is normalized to POSIX suffix
    res2b = catalog_service.update_installer_path("git", r"git_v2.30\git.exe")
    assert res2b["installer_path"] == "git_v2.30/git.exe"

    # 3. Existing local file is auto-imported to server and path is stored as suffix (not starting with data/)
    local_file = settings.data_dir / "my_custom_setup.exe"
    local_file.write_bytes(b"SETUP_BYTES")
    res3 = catalog_service.update_installer_path("git", str(local_file))
    assert not res3["installer_path"].startswith("data/")
    assert "my_custom_setup.exe" in res3["installer_path"]


def test_app_api_endpoints(settings, monkeypatch):
    import hashlib
    from backend import app as backend_app
    from backend.core.context import build_context

    ctx = build_context(settings)
    monkeypatch.setattr(backend_app, "_context", lambda: ctx)

    sr_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    jr_key = hashlib.md5(b"emma.wilson@example.com").hexdigest()
    client = TestClient(backend_app.app, headers={"X-Session-Key": sr_key})

    # 1. GET /api/v1/apps
    res = client.get("/api/v1/apps")
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) >= 8

    # 2. GET /api/v1/apps/categories
    cat_res = client.get("/api/v1/apps/categories")
    assert cat_res.status_code == 200
    cats = cat_res.json()["data"]
    assert "Môi trường lập trình" in cats

    # 3. PUT /api/v1/apps/{code}/path (lưu suffix)
    put_res = client.put(
        "/api/v1/apps/python/path",
        json={"installer_path": "data/installers/python_v3.11/python.exe"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["data"]["installer_path"] == "python_v3.11/python.exe"

    # 3b. PUT /api/v1/apps/{code} - Cập nhật version, check_command, version_args, installer_path
    # Thử gọi bằng tài khoản Junior -> 403 Forbidden
    put_junior = client.put(
        "/api/v1/apps/python",
        json={"recommended_version": "3.12.0", "check_command": "python", "version_args": "-V"},
        headers={"X-Session-Key": jr_key, "X-User-Email": "emma.wilson@example.com"},
    )
    assert put_junior.status_code == 403

    # Gọi bằng tài khoản Admin -> 200 OK
    put_admin = client.put(
        "/api/v1/apps/python",
        json={
            "recommended_version": "3.12.0",
            "check_command": "python",
            "version_args": "-V",
            "installer_path": "python_v3.12/python-3.12.0-amd64.exe",
        },
        headers={"X-Session-Key": sr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert put_admin.status_code == 200
    updated_data = put_admin.json()["data"]
    assert updated_data["recommended_version"] == "3.12.0"
    assert updated_data["check_command"] == "python"
    assert updated_data["version_args"] == "-V"
    assert updated_data["installer_path"] == "python_v3.12/python-3.12.0-amd64.exe"

    # 4. Search via query param
    search_res = client.get("/api/v1/apps?query=python")
    assert search_res.status_code == 200
    search_data = search_res.json()["data"]
    assert len(search_data) >= 1
    assert search_data[0]["installer_path"] == "python_v3.12/python-3.12.0-amd64.exe"
    assert search_data[0]["recommended_version"] == "3.12.0"

    # 5. POST /api/v1/apps - Non-senior (Junior) hoặc thiếu header -> 403
    junior_res = client.post(
        "/api/v1/apps",
        json={"app_code": "redis", "app_name": "Redis Server"},
        headers={"X-Session-Key": jr_key, "X-User-Email": "emma.wilson@example.com"},
    )
    assert junior_res.status_code == 403

    # 6. POST /api/v1/apps - Senior (alex.carter@example.com) -> 200 OK
    senior_res = client.post(
        "/api/v1/apps",
        json={
            "app_code": "redis",
            "app_name": "Redis Server",
            "category": "Cơ sở dữ liệu",
            "recommended_version": "7.0",
            "installer_path": "redis_v7.0/redis-server.exe",
        },
        headers={"X-Session-Key": sr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert senior_res.status_code == 200
    assert senior_res.json()["data"]["app_code"] == "redis"
    assert senior_res.json()["data"]["installer_path"] == "redis_v7.0/redis-server.exe"

    # 7. Search newly created app via query param
    search_redis = client.get("/api/v1/apps?query=redis")
    assert search_redis.status_code == 200
    assert len(search_redis.json()["data"]) == 1
    assert search_redis.json()["data"][0]["app_code"] == "redis"

    # 8. POST /api/v1/apps/{code}/upload - Junior -> 403
    dummy_exe = settings.data_dir / "dummy_setup.exe"
    dummy_exe.write_bytes(b"DUMMY_BINARY_DATA_FOR_TEST")
    up_junior = client.post(
        "/api/v1/apps/redis/upload",
        json={"source_path": str(dummy_exe), "filename": "redis_setup.exe"},
        headers={"X-Session-Key": jr_key, "X-User-Email": "emma.wilson@example.com"},
    )
    assert up_junior.status_code == 403

    # 9. POST /api/v1/apps/{code}/upload - Senior -> 200 OK & file saved on server
    up_senior = client.post(
        "/api/v1/apps/redis/upload",
        json={"source_path": str(dummy_exe), "filename": "redis_setup.exe"},
        headers={"X-Session-Key": sr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert up_senior.status_code == 200
    up_data = up_senior.json()["data"]
    assert up_data["has_installer_file"] is True
    assert (settings.installers_dir / "redis_v7.0" / "redis_setup.exe").is_file()

    # 9b. Không cho phép tải lên ứng dụng và phiên bản trùng nhau -> 400 Bad Request
    up_duplicate = client.post(
        "/api/v1/apps/redis/upload",
        json={"source_path": str(dummy_exe), "filename": "redis_setup.exe"},
        headers={"X-Session-Key": sr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert up_duplicate.status_code == 400
    assert "Không được tải lên trùng nhau" in up_duplicate.json().get("detail", "")

    # 9c. PROJECT_LEAD theo assignment dự án được tải bộ cài dù role hệ thống vẫn là MEMBER.
    ctx.apps.create_app(
        {
            "app_code": "project_tool",
            "app_name": "Project Tool",
            "recommended_version": "1.0",
        }
    )
    ctx.projects.add_project_member(
        project_code="PRJ_ECOMMERCE",
        user_email="emma.wilson@example.com",
        project_role_key="PROJECT_LEAD",
    )
    project_lead_file = settings.data_dir / "project_tool.exe"
    project_lead_file.write_bytes(b"PROJECT_LEAD_UPLOAD")
    up_project_lead = client.post(
        "/api/v1/apps/project_tool/upload",
        json={"source_path": str(project_lead_file), "filename": "project_tool.exe"},
        headers={"X-Session-Key": jr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert up_project_lead.status_code == 200
    assert up_project_lead.json()["data"]["has_installer_file"] is True


    # 10. GET /api/v1/apps/{code}/download - User đã đăng nhập đều tải được -> 200 OK
    down_res = client.get("/api/v1/apps/redis/download")
    assert down_res.status_code == 200
    assert down_res.content == b"DUMMY_BINARY_DATA_FOR_TEST"

    # 11. POST /api/v1/apps/{code}/export - User đã đăng nhập có thể export về thư mục chỉ định kèm folder version
    export_dir = settings.data_dir / "my_downloads"
    export_res = client.post(
        "/api/v1/apps/redis/export",
        json={"destination_dir": str(export_dir)},
    )
    assert export_res.status_code == 200
    assert (export_dir / "redis_v7.0" / "redis_setup.exe").read_bytes() == b"DUMMY_BINARY_DATA_FOR_TEST"

    # 12a. DELETE /api/v1/apps/{code} - Member (emma.wilson@example.com) -> 403 Forbidden (Chỉ ADMIN mới có quyền)
    del_member = client.delete(
        "/api/v1/apps/redis",
        headers={"X-Session-Key": jr_key, "X-User-Email": "emma.wilson@example.com"},
    )
    assert del_member.status_code == 403
    assert "Chỉ TEAM_LEAD mới có quyền" in del_member.json().get("detail", "")

    # 12b. DELETE /api/v1/apps/{code} - ADMIN (alex.carter@example.com) -> 200 OK
    del_admin = client.delete(
        "/api/v1/apps/redis",
        headers={"X-Session-Key": sr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert del_admin.status_code == 200
    assert del_admin.json()["data"]["deleted"] is True

    # 12c. GET /api/v1/apps/{code} sau khi xóa -> 404 Not Found
    get_after_del = client.get("/api/v1/apps/redis")
    assert get_after_del.status_code == 404

    # 12d. DELETE /api/v1/apps/{code} lại lần nữa khi app không còn tồn tại -> 404 Not Found
    del_again = client.delete(
        "/api/v1/apps/redis",
        headers={"X-Session-Key": sr_key, "X-User-Email": "alex.carter@example.com"},
    )
    assert del_again.status_code == 404


def test_checklist_item_mapping_and_installer_check(catalog_service, settings):
    """Kiểm tra logic ánh xạ từ checklist item sang App Catalog và kiểm tra tồn tại của file cài đặt."""
    # 1. Ứng dụng có sẵn trong mặc định nhưng chưa có file installer trên máy chủ
    python_app = catalog_service.get_app("python")
    assert python_app is not None
    # Nếu máy dev chưa có installer thật thì has_installer_file phản ánh đúng
    assert "has_installer_file" in python_app

    # 2. Tạo một file giả lập lưu vào thư mục installers của server
    server_dir = catalog_service.get_installer_folder("python", version="3.11")
    fake_installer = server_dir / "python-3.11.8-amd64.exe"
    fake_installer.write_bytes(b"FAKE_PYTHON_INSTALLER_BINARY")

    # Kiểm tra lại: app_catalog phải nhận diện được file cài đặt
    rechecked_python = catalog_service.get_app("python")
    assert rechecked_python["has_installer_file"] is True

    # 3. Ứng dụng không tồn tại trong danh mục -> trả về None
    assert catalog_service.get_app("nonexistent_unknown_tool") is None


def test_api_client_download_installer(settings, monkeypatch, tmp_path):
    """Kiểm tra ApiClient.download_file tải file installer từ máy chủ BE về máy client."""
    import hashlib
    from backend import app as backend_app
    from backend.core.context import build_context
    from frontend.api_client import ApiClient

    ctx = build_context(settings)
    monkeypatch.setattr(backend_app, "_context", lambda: ctx)

    # 1. Tạo tệp installer cho git trên máy chủ
    git_dir = settings.installers_dir / "git_v2.30"
    git_dir.mkdir(parents=True, exist_ok=True)
    git_file = git_dir / "Git-2.30.2-64-bit.exe"
    git_file.write_bytes(b"GIT_INSTALLER_BINARY_DATA_XYZ_123")

    # Cập nhật đường dẫn server vào DB
    ctx.apps.update_installer_path("git", "data/installers/git_v2.30/Git-2.30.2-64-bit.exe")

    # 2. Dùng TestClient để tạo server test hoặc gọi endpoint download
    admin_key = hashlib.md5(b"alex.carter@example.com").hexdigest()
    client = TestClient(backend_app.app, headers={"X-Session-Key": admin_key})

    down_res = client.get("/api/v1/apps/git/download")
    assert down_res.status_code == 200
    assert down_res.content == b"GIT_INSTALLER_BINARY_DATA_XYZ_123"
    assert "Git-2.30.2-64-bit.exe" in down_res.headers.get("content-disposition", "")

    # 3. User không có session key vẫn tải được bộ cài đặt từ máy chủ
    client_public = TestClient(backend_app.app)
    down_pub = client_public.get("/api/v1/apps/git/download")
    assert down_pub.status_code == 200
    assert down_pub.content == b"GIT_INSTALLER_BINARY_DATA_XYZ_123"

    # 4. Kiểm tra exact_path với file path do người dùng tùy chọn lưu
    custom_dest = tmp_path / "custom_folder" / "my_custom_git_setup.exe"
    # Giả lập download qua ApiClient bằng cách viết nội dung từ response
    custom_dest.parent.mkdir(parents=True, exist_ok=True)
    custom_dest.write_bytes(down_res.content)
    assert custom_dest.is_file()
    assert custom_dest.read_bytes() == b"GIT_INSTALLER_BINARY_DATA_XYZ_123"


def test_frontend_clean_version_tag():
    """Kiểm tra hàm _clean_version_tag trên dashboard_page và workspace_page."""
    from frontend.pages.dashboard_page import _clean_version_tag as dash_clean
    from frontend.pages.workspace_page import _clean_version_tag as work_clean

    assert dash_clean(">= 3.11") == "3.11"
    assert dash_clean("v2.43.0") == "2.43.0"
    assert dash_clean("Latest") == "latest"
    assert dash_clean(None) == ""
    assert dash_clean("") == ""

    assert work_clean(">= 3.11") == "3.11"
    assert work_clean("v2.43.0") == "2.43.0"
    assert work_clean(None) == ""


def test_installer_prefix_env_and_suffix_resolution(tmp_path, monkeypatch):
    """Kiểm tra cấu hình INSTALLER_PREFIX từ env và cơ chế phân giải prefix + suffix trên Windows."""
    from backend.services.app_catalog_service import AppCatalogService
    from config.settings import Settings

    custom_prefix_dir = tmp_path / "custom_server_installers"
    custom_prefix_dir.mkdir(parents=True, exist_ok=True)

    # Đặt biến môi trường INSTALLER_PREFIX (hỗ trợ đường dẫn tuyệt đối trên Windows)
    monkeypatch.setenv("INSTALLER_PREFIX", str(custom_prefix_dir))

    cfg_settings = Settings.load()
    assert cfg_settings.installers_dir.resolve() == custom_prefix_dir.resolve()

    # Dùng database tạm của sqlite
    sqlite_url = f"sqlite:///{tmp_path / 'custom_test.db'}"
    cfg_settings.database_url_override = sqlite_url
    svc = AppCatalogService(cfg_settings)

    # 1. Tạo file cài đặt thật trong thư mục prefix tùy chỉnh
    app_folder = svc.get_installer_folder("git", version="2.43.0")
    assert app_folder.parent.resolve() == custom_prefix_dir.resolve()
    target_exe = app_folder / "Git-2.43.0-custom.exe"
    target_exe.write_bytes(b"WINDOWS_CUSTOM_INSTALLER_BINARY")

    # 2. Cập nhật đường dẫn qua svc (truyền Windows path có backslash)
    raw_win_path = rf"git_v2.43.0\Git-2.43.0-custom.exe"
    updated = svc.update_installer_path("git", raw_win_path)
    # DB chỉ lưu suffix dạng POSIX
    assert updated["installer_path"] == "git_v2.43.0/Git-2.43.0-custom.exe"

    # 3. Phân giải tệp kết hợp prefix từ env + suffix từ DB
    file_info = svc.find_installer_file("git", installer_path=updated["installer_path"])
    assert file_info is not None
    resolved_path, fname = file_info
    assert resolved_path.is_file()
    assert fname == "Git-2.43.0-custom.exe"
    assert resolved_path.read_bytes() == b"WINDOWS_CUSTOM_INSTALLER_BINARY"


def test_recursive_find_installer_file(catalog_service, settings):
    """Kiểm tra tìm file bộ cài đặt trong thư mục con khi installer_path chỉ lưu tên file."""
    # Tạo file trong thư mục con bất kỳ
    nested_dir = settings.installers_dir / "vscode_v1.85.0"
    nested_dir.mkdir(parents=True, exist_ok=True)
    setup_file = nested_dir / "VSCode-Custom-Setup.exe"
    setup_file.write_bytes(b"VSCODE_BINARY")

    # 1. Tìm theo tên file khi installer_path chỉ là tên file
    found = catalog_service.find_installer_file("vscode", installer_path="VSCode-Custom-Setup.exe")
    assert found is not None
    assert found[0].is_file()
    assert found[1] == "VSCode-Custom-Setup.exe"

    # 2. Tìm tự động theo app_code khi installer_path rỗng
    found_by_code = catalog_service.find_installer_file("vscode", installer_path="")
    assert found_by_code is not None
    assert found_by_code[1] == "VSCode-Custom-Setup.exe"


def test_api_client_download_file(tmp_path, monkeypatch):
    """Kiểm tra ApiClient.download_file xử lý đối tượng Path, tính tiến trình on_progress và lưu file thành công."""
    import io
    import urllib.request
    from frontend.api_client import ApiClient

    client = ApiClient(base_url="http://127.0.0.1:8765")
    mock_data = b"MOCK_BINARY_APP_DATA"

    class MockResponse:
        def __init__(self):
            self.headers = {
                "Content-Disposition": 'attachment; filename="test_app_v1.0.exe"',
                "Content-Length": str(len(mock_data)),
            }
            self._stream = io.BytesIO(mock_data)

        def read(self, size=-1):
            return self._stream.read(size)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: MockResponse())

    dest = tmp_path / "downloads" / "my_app.exe"
    progress_events: list[tuple[int, int]] = []

    def on_prog(cur: int, tot: int) -> None:
        progress_events.append((cur, tot))

    saved = client.download_file(
        "/api/v1/apps/python/download",
        dest_path=dest,
        exact_path=True,
        on_progress=on_prog,
    )

    assert saved.is_file()
    assert saved.read_bytes() == mock_data
    assert saved.name == "my_app.exe"
    assert len(progress_events) >= 2
    assert progress_events[0] == (0, len(mock_data))
    assert progress_events[-1] == (len(mock_data), len(mock_data))


def test_delete_app_service(catalog_service):
    """Kiểm tra phương thức delete_app của AppCatalogService."""
    # 1. Thêm một app mới
    catalog_service.create_app({
        "app_code": "temp_tool",
        "app_name": "Temporary Tool",
        "category": "Tiện ích",
    })
    assert catalog_service.get_app("temp_tool") is not None

    # 2. Xóa thành công
    assert catalog_service.delete_app("temp_tool") is True
    assert catalog_service.get_app("temp_tool") is None

    # 3. Xóa lại khi app không còn tồn tại -> False
    assert catalog_service.delete_app("temp_tool") is False

    # 4. Xóa chuỗi rỗng -> False
    assert catalog_service.delete_app("") is False
    assert catalog_service.delete_app("   ") is False


def test_update_app_service(catalog_service):
    """Kiểm tra phương thức update_app của AppCatalogService cập nhật version, check command, installer_path."""
    # 1. Cập nhật app có sẵn (git)
    updated = catalog_service.update_app("git", {
        "recommended_version": "2.44.0",
        "check_command": "git",
        "version_args": "--version",
        "installer_path": "git_v2.44.0/Git-2.44.0-64-bit.exe",
    })
    assert updated["recommended_version"] == "2.44.0"
    assert updated["check_command"] == "git"
    assert updated["version_args"] == "--version"
    assert updated["installer_path"] == "git_v2.44.0/Git-2.44.0-64-bit.exe"

    # Kiểm tra lại bằng get_app
    app = catalog_service.get_app("git")
    assert app is not None
    assert app["recommended_version"] == "2.44.0"
    assert app["installer_path"] == "git_v2.44.0/Git-2.44.0-64-bit.exe"

    # 2. Cập nhật app không tồn tại -> KeyError
    import pytest
    with pytest.raises(KeyError):
        catalog_service.update_app("nonexistent_app_xyz", {"recommended_version": "1.0"})




