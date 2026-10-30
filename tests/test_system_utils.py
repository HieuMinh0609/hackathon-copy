import sys

from backend.core.utils import system_utils as su


def test_parse_and_compare_versions():
    assert su.parse_version("git version 2.43.0.windows.1") == (2, 43, 0)
    assert su.parse_version("Python 3.11.9") == (3, 11, 9)
    assert su.parse_version("no digits") is None
    assert su.version_gte("3.11.9", "3.11")
    assert su.version_gte("3.11", "3.11.0")
    assert not su.version_gte("3.10.12", "3.11")
    assert not su.version_gte(None, "1.0")
    assert su.version_gte(None, None)


def test_check_software_finds_current_python(monkeypatch):
    st = su.check_software("Python", sys.executable, min_version="3.11")
    # sys.executable là đường dẫn đầy đủ nên shutil.which tìm được
    assert st.installed and st.meets_min


def test_check_software_missing():
    st = su.check_software("Nope", "definitely-not-a-real-command-xyz")
    assert not st.installed and not st.meets_min
    assert "Chưa cài" in st.message


def test_build_install_plan(monkeypatch):
    monkeypatch.setattr(su, "detect_package_manager", lambda: "winget")
    plan = su.build_install_plan("Git", {"winget": "Git.Git"})
    assert plan and plan.command[:3] == ["winget", "install", "--id"]
    assert "Git.Git" in plan.display


def test_build_install_plan_rejects_unsafe_or_missing(monkeypatch):
    monkeypatch.setattr(su, "detect_package_manager", lambda: "winget")
    assert su.build_install_plan("X", {"winget": "evil; rm -rf /"}) is None
    assert su.build_install_plan("X", {"apt": "git"}) is None
    assert su.build_install_plan("X", None) is None
    monkeypatch.setattr(su, "detect_package_manager", lambda: None)
    assert su.build_install_plan("X", {"winget": "Git.Git"}) is None
