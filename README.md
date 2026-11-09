# AgentOps Backend

FastAPI backend for the AgentOps observability platform. Stores traces and steps in SQLite.

## Run

```bash
# Depuis le dossier agent_ops (recommandé) :
cd /home/terry/Bureau/PERSO/agent_ops
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# OU depuis le dossier parent (PERSO) :
cd /home/terry/Bureau/PERSO
uvicorn agent_ops.main:app --reload --port 8001
```

Dashboard: http://localhost:8001/dashboard

## API

- `GET /health`
- `POST /api/trace` {session_name, metadata}
- `POST /api/log` {trace_id, thought, action, observation, state_snapshot}
- `POST /api/trace/{id}/end` {status}
- `GET /api/traces?limit=&offset=`
- `GET /api/traces/{id}`
- `DELETE /api/traces/{id}`

Auth via `X-API-Key` header when `AGENT_OPS_API_KEY` is set.

## Tests

```bash
pytest agent_ops/tests
```