import pytest
from fastapi.testclient import TestClient

from app.main import app

def _patch_commit_file(monkeypatch, path):
    # Patch the globals the served /health uses; other tests may reload app.main.
    endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/health")
    monkeypatch.setitem(endpoint.__globals__, "_COMMIT_FILE", path)


VARS = ("GIT_SHA", "SOURCE_COMMIT", "DOKPLOY_COMMIT_SHA", "DOKPLOY_COMMIT_HASH")


@pytest.fixture
def client(monkeypatch, tmp_path):
    _patch_commit_file(monkeypatch, tmp_path / "GIT_SHA")
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    return TestClient(app)


def test_commit_set_is_cut_to_seven(client, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "0BDAD2F1234567890abcdef1234567890abcdef0")
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True, "commit": "0bdad2f"}


def test_commit_from_source_commit(client, monkeypatch):
    monkeypatch.setenv("SOURCE_COMMIT", "abc1234")
    assert client.get("/health").json()["commit"] == "abc1234"


def test_commit_unset_is_unknown(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True, "commit": "unknown"}


@pytest.mark.parametrize("bad", ["not-a-sha", "abc12", "g123456", "abc1234; rm -rf /", "$(id)", "a" * 41])
def test_invalid_commit_is_not_shown(client, monkeypatch, bad):
    monkeypatch.setenv("GIT_SHA", bad)
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True, "commit": "unknown"}
    assert bad not in r.text


@pytest.fixture
def sha_file(tmp_path, monkeypatch):
    path = tmp_path / "GIT_SHA"
    _patch_commit_file(monkeypatch, path)
    return path


def test_build_file_used_when_env_unset(client, sha_file):
    sha_file.write_text("0BDAD2F46ad97d5a0964b26b3d4460d116741ceb\n")
    assert client.get("/health").json() == {"ok": True, "commit": "0bdad2f"}


def test_env_wins_over_build_file(client, sha_file, monkeypatch):
    sha_file.write_text("0bdad2f46ad97d5a0964b26b3d4460d116741ceb\n")
    monkeypatch.setenv("GIT_SHA", "abc1234def")
    assert client.get("/health").json()["commit"] == "abc1234"


@pytest.mark.parametrize("content", [None, "", "unknown\n", "ref: refs/heads/main\n", "zz" * 20, "$(id)"])
def test_missing_or_invalid_build_file_is_unknown(client, sha_file, content):
    if content is not None:
        sha_file.write_text(content)
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True, "commit": "unknown"}
