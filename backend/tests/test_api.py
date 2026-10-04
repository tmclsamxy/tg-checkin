"""End-to-end smoke tests for the REST API (no Telegram connection required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (env is prepared by conftest.py)


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
    assert resp.json()["captcha_enabled"] is True
    assert resp.json()["captcha_max_rounds"] == 2
    assert resp.json()["account_count"] == 0

    resp = client.put(
        "/api/settings",
        json={
            "schedule_time": "07:30",
            "timezone": "Asia/Shanghai",
            "notify_bot_token": "123456:AAabcdefghijklmnopqrstuvwxyz012345",
            "captcha_enabled": False,
            "captcha_max_rounds": 3,
            "captcha_wait_seconds": 6,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schedule_time"] == "07:30"
    assert body["has_notify_bot_token"] is True
    assert body["captcha_enabled"] is False
    assert body["captcha_max_rounds"] == 3
    assert body["captcha_wait_seconds"] == 6

    # secrets are never returned in clear text
    assert "AAabcdefghijklmnopqrstuvwxyz012345" not in str(body)

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
    assert body["account_count"] >= 0


# --------------------------------------------------------------------------- #
# accounts
# --------------------------------------------------------------------------- #
def _new_account(client, auth_headers, name="小号一", phone="+8613800138001"):
    resp = client.post(
        "/api/accounts",
        json={
            "name": name,
            "api_id": "123456",
            "api_hash": "0123456789abcdef0123456789abcdef",
            "phone": phone,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_account_crud(client, auth_headers):
    assert client.get("/api/accounts", headers=auth_headers).json() == []

    account = _new_account(client, auth_headers)
    assert account["name"] == "小号一"
    assert account["enabled"] is True
    assert account["has_api_hash"] is True
    assert account["has_session"] is False
    assert account["connected"] is False
    assert account["task_count"] == 0

    # the secret is masked, never returned raw
    assert account["api_hash_masked"].endswith("cdef")
    assert "0123456789abcdef0123456789abcdef" not in str(account)

    account_id = account["id"]
    listed = client.get("/api/accounts", headers=auth_headers).json()
    assert [item["id"] for item in listed] == [account_id]

    resp = client.put(
        f"/api/accounts/{account_id}",
        json={"name": "小号一改名", "enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "小号一改名"
    assert resp.json()["enabled"] is False

    # blank api_hash keeps the stored one
    resp = client.put(f"/api/accounts/{account_id}", json={"api_hash": ""}, headers=auth_headers)
    assert resp.json()["has_api_hash"] is True

    assert client.delete(f"/api/accounts/{account_id}", headers=auth_headers).status_code == 200
    assert client.get("/api/accounts", headers=auth_headers).json() == []


def test_accounts_are_ordered_independently(client, auth_headers):
    first = _new_account(client, auth_headers, name="甲", phone="+8613800138001")
    second = _new_account(client, auth_headers, name="乙", phone="+8613800138002")

    resp = client.post(
        "/api/accounts/reorder",
        json={"ids": [second["id"], first["id"]]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    names = [item["name"] for item in client.get("/api/accounts", headers=auth_headers).json()]
    assert names == ["乙", "甲"]

    for account in (first, second):
        client.delete(f"/api/accounts/{account['id']}", headers=auth_headers)


def test_account_login_requires_existing_account(client, auth_headers):
    creds = {"api_id": "1", "api_hash": "x", "phone": "+8613800138000"}
    resp = client.post("/api/accounts/9999/request-code", json=creds, headers=auth_headers)
    assert resp.status_code == 404
    assert client.post("/api/accounts/9999/connect", headers=auth_headers).status_code == 404
    assert client.post("/api/accounts/9999/logout", headers=auth_headers).status_code == 404
    assert client.put("/api/accounts/9999", json={"name": "x"}, headers=auth_headers).status_code == 404
    assert client.delete("/api/accounts/9999", headers=auth_headers).status_code == 404


def test_connect_without_api_hash_fails_clearly(client, auth_headers):
    """No credentials stored yet -> the error must explain what is missing."""
    resp = client.post(
        "/api/accounts",
        json={"name": "空账号", "api_id": "1", "api_hash": "x", "phone": "+8613800138003"},
        headers=auth_headers,
    )
    account_id = resp.json()["id"]
    resp = client.post(f"/api/accounts/{account_id}/connect", headers=auth_headers)
    assert resp.status_code == 400
    assert "登录" in resp.json()["detail"]

    client.delete(f"/api/accounts/{account_id}", headers=auth_headers)


def test_task_binds_to_an_account(client, auth_headers):
    account = _new_account(client, auth_headers, name="绑定测试")
    payload = {
        "name": "绑定任务",
        "target_type": "bot",
        "bot_username": "@bind_bot",
        "action_type": "message",
        "message": "/sign",
        "account_id": account["id"],
    }
    resp = client.post("/api/tasks", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["account_id"] == account["id"]

    # the account now reports the task count
    listed = client.get("/api/accounts", headers=auth_headers).json()
    assert listed[0]["task_count"] == 1

    # filtering by account
    assert len(client.get(f"/api/tasks?account_id={account['id']}", headers=auth_headers).json()) == 1
    assert client.get("/api/tasks?account_id=9999", headers=auth_headers).json() == []

    # an unknown account is rejected up front
    bad = client.post("/api/tasks", json={**payload, "account_id": 9999}, headers=auth_headers)
    assert bad.status_code == 400

    # deleting the account orphans the task instead of deleting it
    resp = client.delete(f"/api/accounts/{account['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert "关联任务" in resp.json()["message"]
    task = client.get(f"/api/tasks/{task['id']}", headers=auth_headers).json()
    assert task["account_id"] is None

    client.delete(f"/api/tasks/{task['id']}", headers=auth_headers)


def test_run_without_account_reports_clearly(client, auth_headers):
    resp = client.post(
        "/api/tasks",
        json={
            "name": "无账号任务",
            "target_type": "bot",
            "bot_username": "@no_account_bot",
            "action_type": "message",
            "message": "/sign",
        },
        headers=auth_headers,
    )
    task_id = resp.json()["id"]
    log = client.post(f"/api/tasks/{task_id}/run", headers=auth_headers).json()
    assert log["status"] == "failed"
    assert "账号" in log["error"]
    assert log["account_id"] is None

    client.delete(f"/api/tasks/{task_id}", headers=auth_headers)


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
