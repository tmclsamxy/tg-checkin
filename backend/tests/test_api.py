"""End-to-end smoke tests for the REST API (no Telegram connection required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TMP_DATA = BACKEND_DIR.parent / ".pytest-data"
os.environ["DATA_DIR"] = str(TMP_DATA)
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-pass-12345"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "test-pass-12345"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_login_rejects_bad_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_requires_auth(client):
    assert client.get("/api/tasks").status_code == 401


def test_me(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_task_crud(client, auth_headers):
    payload = {
        "name": "测试机器人",
        "target_type": "bot",
        "bot_username": "test_bot",  # should be normalised to @test_bot
        "action_type": "message",
        "message": "/sign",
    }
    resp = client.post("/api/tasks", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["bot_username"] == "@test_bot"
    assert task["target"] == "@test_bot"
    assert task["auto_captcha"] is True  # on by default

    task_id = task["id"]
    assert client.get("/api/tasks", headers=auth_headers).json()

    resp = client.put(
        f"/api/tasks/{task_id}",
        json={**payload, "name": "改名后", "enabled": False, "auto_captcha": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名后"
    assert resp.json()["enabled"] is False
    assert resp.json()["auto_captcha"] is False

    resp = client.post(f"/api/tasks/{task_id}/toggle", headers=auth_headers)
    assert resp.json()["enabled"] is True

    assert client.delete(f"/api/tasks/{task_id}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/tasks/{task_id}", headers=auth_headers).status_code == 404


def test_task_validation(client, auth_headers):
    bad = {"target_type": "bot", "action_type": "message", "message": "x"}  # missing username
    assert client.post("/api/tasks", json=bad, headers=auth_headers).status_code == 400

    bad_group = {
        "target_type": "group",
        "group_id": "-100123",
        "action_type": "button",  # groups only support messages
        "button_type": "text",
        "button_text": "签到",
    }
    assert client.post("/api/tasks", json=bad_group, headers=auth_headers).status_code == 400


def test_settings_roundtrip(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["has_api_hash"] is False
    assert resp.json()["captcha_enabled"] is True
    assert resp.json()["captcha_max_rounds"] == 2

    resp = client.put(
        "/api/settings",
        json={
            "api_id": "123456",
            "api_hash": "abcdef0123456789",
            "schedule_time": "07:30",
            "timezone": "Asia/Shanghai",
            "captcha_enabled": False,
            "captcha_max_rounds": 3,
            "captcha_wait_seconds": 6,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["api_id"] == "123456"
    assert body["has_api_hash"] is True
    assert body["api_hash_masked"].endswith("6789")
    assert body["schedule_time"] == "07:30"
    assert body["captcha_enabled"] is False
    assert body["captcha_max_rounds"] == 3
    assert body["captcha_wait_seconds"] == 6

    # secrets are never returned in clear text
    assert "abcdef0123456789" not in str(body)

    assert client.put("/api/settings", json={"schedule_time": "25:99"}, headers=auth_headers).status_code == 422
    assert client.put("/api/settings", json={"captcha_max_rounds": 99}, headers=auth_headers).status_code == 422


def test_run_without_telegram_session(client, auth_headers):
    """Running a task without a Telegram session must fail gracefully."""
    resp = client.post(
        "/api/tasks",
        json={
            "name": "无会话任务",
            "target_type": "bot",
            "bot_username": "@no_session_bot",
            "action_type": "message",
            "message": "/sign",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    resp = client.post(f"/api/tasks/{task_id}/run", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    log = resp.json()
    assert log["status"] == "failed"
    assert log["error"]

    runs = client.get("/api/runs?limit=10", headers=auth_headers).json()
    assert any(r["task_id"] == task_id for r in runs)

    stats = client.get("/api/runs/stats", headers=auth_headers).json()
    assert stats["total"] >= 1

    client.delete(f"/api/tasks/{task_id}", headers=auth_headers)


def test_system_info(client, auth_headers):
    resp = client.get("/api/system/info", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "version" in body
    assert body["task_count"] >= 0


def test_change_password(client, auth_headers):
    resp = client.post(
        "/api/auth/password",
        json={"old_password": "wrong", "new_password": "another-pass-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    resp = client.post(
        "/api/auth/password",
        json={"old_password": "test-pass-12345", "new_password": "another-pass-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
