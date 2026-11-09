import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore", message=".*starlette.testclient.*")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault("AGENT_OPS_DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
os.environ.setdefault("AGENT_OPS_API_KEY", "test-key")
os.environ.setdefault("AGENT_OPS_JWT_SECRET", "test-secret-that-is-long-enough-for-hmac-sha256-signing")

import pytest
from fastapi.testclient import TestClient

from agent_ops.database import init_db
from agent_ops.main import app

init_db()
client = TestClient(app)


def test_register_login_and_key():
    r = client.post("/auth/register", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r2 = client.get("/auth/me", headers=h)
    assert r2.status_code == 200
    assert r2.json()["email"] == "a@b.com"

    r3 = client.post("/auth/keys", json={"name": "sdk", "scopes": "read,write"}, headers=h)
    assert r3.status_code == 201
    raw_key = r3.json()["key"]
    assert raw_key.startswith("ak_")

    # use api key
    r4 = client.post("/api/trace", json={"session_name": "t"}, headers={"X-API-Key": raw_key})
    assert r4.status_code == 201

    # list & revoke
    r5 = client.get("/auth/keys", headers=h)
    assert len(r5.json()) == 1
    kid = r5.json()[0]["id"]
    r6 = client.delete(f"/auth/keys/{kid}", headers=h)
    assert r6.status_code == 204

    r7 = client.post("/api/trace", json={"session_name": "t2"}, headers={"X-API-Key": raw_key})
    assert r7.status_code == 401


def test_login_invalid():
    client.post("/auth/register", json={"email": "x@y.com", "password": "password123"})
    r = client.post("/auth/login", json={"email": "x@y.com", "password": "wrong"})
    assert r.status_code == 401