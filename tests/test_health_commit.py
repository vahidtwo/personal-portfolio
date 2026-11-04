import pytest
from fastapi.testclient import TestClient

from app.main import app

VARS = ("GIT_SHA", "SOURCE_COMMIT", "DOKPLOY_COMMIT_SHA", "DOKPLOY_COMMIT_HASH")


@pytest.fixture
def client(monkeypatch):
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
