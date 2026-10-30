import dataclasses

from config.settings import get_settings
from backend.services.db import check_connection, describe


def _settings(**kw):
    base = dataclasses.replace(get_settings(), database_url_override="")
    return dataclasses.replace(base, **kw)


def test_defaults_to_postgres():
    s = _settings()
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.uses_postgres


def test_postgres_url_from_parts_escapes_password():
    s = _settings(pg_host="db.local", pg_port=5433, pg_database="ab", pg_user="u", pg_password="p@ss:w/rd")
    assert s.uses_postgres
    assert s.database_url.startswith("postgresql+psycopg://u:")
    assert "@db.local:5433/ab" in s.database_url
    assert "p@ss:w/rd" not in s.database_url  # đã được percent-encode


def test_database_url_override_wins():
    s = _settings(pg_host="x", database_url_override="postgresql+psycopg://a:b@h:1/d")
    assert s.database_url == "postgresql+psycopg://a:b@h:1/d"


def test_describe_masks_password():
    assert "secret" not in describe("postgresql+psycopg://u:secret@h:5432/d")


def test_check_connection_failure_is_friendly():
    ok, msg = check_connection("postgresql+psycopg://u:p@127.0.0.1:1/d")
    assert ok is False and "Không kết nối được" in msg and "p@" not in msg
