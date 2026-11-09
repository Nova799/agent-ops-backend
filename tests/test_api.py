import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore", message=".*starlette.testclient.*")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi.testclient import TestClient

# Use a temp sqlite db
fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["AGENT_OPS_DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["AGENT_OPS_API_KEY"] = "test-key"

from agent_ops.main import app  # noqa: E402
from agent_ops.database import init_db  # noqa: E402

init_db()
client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_required():
    r = client.get("/api/traces")
    assert r.status_code == 401


def test_create_trace_and_log():
    r = client.post("/api/trace", json={"session_name": "s1", "metadata": {"a": 1}}, headers=HEADERS)
    assert r.status_code == 201
    trace = r.json()
    tid = trace["id"]
    assert trace["session_name"] == "s1"
    assert trace["step_count"] == 0

    r2 = client.post("/api/log", json={"trace_id": tid, "thought": "t", "action": "act", "observation": "obs", "state_snapshot": {"x": 2}}, headers=HEADERS)
    assert r2.status_code == 201
    step = r2.json()
    assert step["step_index"] == 0
    assert step["thought"] == "t"

    r3 = client.get(f"/api/traces/{tid}", headers=HEADERS)
    assert r3.status_code == 200
    detail = r3.json()
    assert detail["step_count"] == 1
    assert len(detail["steps"]) == 1

    r4 = client.post(f"/api/trace/{tid}/end", json={"status": "completed"}, headers=HEADERS)
    assert r4.status_code == 200
    assert r4.json()["status"] == "completed"


def test_log_unknown_trace():
    r = client.post("/api/log", json={"trace_id": "nope", "thought": "t"}, headers=HEADERS)
    assert r.status_code == 404


def test_list_and_delete():
    r = client.post("/api/trace", json={"session_name": "s2"}, headers=HEADERS)
    tid = r.json()["id"]
    rlist = client.get("/api/traces", headers=HEADERS)
    assert rlist.status_code == 200
    assert any(t["id"] == tid for t in rlist.json())
    rdel = client.delete(f"/api/traces/{tid}", headers=HEADERS)
    assert rdel.status_code == 204
    rget = client.get(f"/api/traces/{tid}", headers=HEADERS)
    assert rget.status_code == 404