"""Ghép đúng prefix/suffix đã lưu, không chọn nhầm bộ cài khác."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.app_catalog_service import AppCatalogService
from backend.core.utils import system_utils


def test_plan_uses_exact_saved_path(tmp_path, monkeypatch):
    root = tmp_path / "installers"
    path = root / "git_v2" / "Git Setup.exe"
    path.parent.mkdir(parents=True)
    path.touch()
    service = object.__new__(AppCatalogService)
    service.settings = SimpleNamespace(installers_dir=root)
    monkeypatch.setattr(service, "_get_raw_app_row", lambda code: {
        "app_name": "Git", "installer_path": "git_v2\\Git Setup.exe", "install_args": "/quiet",
    })
    monkeypatch.setattr(system_utils, "get_os_name", lambda: "windows")
    assert service.installer_plan("git").command == [str(path), "/quiet"]
    path.unlink()
    (root / "other.exe").touch()
    with pytest.raises(ValueError, match="Không tìm thấy"):
        service.installer_plan("git")
