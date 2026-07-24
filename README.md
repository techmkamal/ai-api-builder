# AI API Builder

Describe an API in plain English; the agent generates a production-ready FastAPI project and returns it as a downloadable ZIP.

## How it works (Phase 2)

A LangGraph agent runs a specialized pipeline

```
request → planner → architecture → backend → database → testing → reviewer → package → ZIP
                ↑ ______________________ retry with feedback ______________ ↓
```

- **planner** (`nodes/planner.py`) parses the request into a build spec `{project_name, database, auth, entities}` using the LLM, with a deterministic regex fallback when no LLM is reachable.
- **architecture** (`nodes/architecture.py`) normalizes the spec into the shared render context and lays down the project skeleton (README, Dockerfile, docker-compose, requirements, dotfiles).
- **backend** (`nodes/backend.py`) renders the application code — core app modules, one router per entity, auth when JWT is requested.
- **database** (`nodes/database.py`) renders the persistence layer (engine/session setup, SQLAlchemy models).
- **testing** (`nodes/testing.py`) renders the generated project's test suite.
- **reviewer** (`nodes/reviewer.py`) validates the result — required files, every entity wired end-to-end (model → schemas → router → mounted in main), matching DB driver, every `.py` parses. On failure it loops back to the planner with its problem report so the spec can be corrected (one retry); only after that does it fail the build.
- **package** (`nodes/package.py`) zips the file map.

All rendering is templates-first from Jinja templates in `agents/api_builder_agent/templates/fastapi/` — deterministic, always-valid Python.

## Project layout

```
src/
├── server.py                     # FastAPI entry point
├── llm.py                        # OpenAI-compatible LLM accessor (Ollama / vLLM, qwen2.5:1.5b)
├── config/settings.py
├── controllers/
│   ├── health.py
│   └── api_builder.py            # POST /api/build → ZIP
└── agents/api_builder_agent/
    ├── graph.py                  # planner → architecture → backend → database → testing → reviewer → package
    ├── state.py
    ├── interpreter/prompts.py
    ├── generators/renderer.py
    ├── nodes/{planner,architecture,backend,database,testing,reviewer,package}.py
    └── templates/fastapi/*.jinja
tests/
```

## Run the model locally (Ollama in Docker)

The LLM runs locally via [Ollama](https://ollama.com). The whole stack (Ollama + the
builder API) comes up with Docker Compose:

```bash
docker compose up --build -d
# One-time: pull the model into the Ollama container
docker compose exec ollama ollama pull qwen2.5:1.5b
```

The API is then on http://localhost:8080 and reaches Ollama at `http://ollama:11434/v1`.

**Model sizing:** `qwen2.5:1.5b` (~1 GB) runs inside a default ~3.5 GB Docker Desktop VM.
`qwen2.5:3b` / `phi3:3.8b` need ~6–8 GB allocated to Docker — on smaller machines the model
never finishes loading and requests stall. Set `LLM_MODEL` to switch.

## Run the API without Docker

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
cd src && ../venv/Scripts/uvicorn server:app --reload --port 8080
```

This talks to an Ollama server on the host (`http://localhost:11434/v1`). Install Ollama,
then `ollama pull qwen2.5:3b`. See `.env.example` to point at a different endpoint (e.g. vLLM).

## Generate a project

```bash
curl -X POST http://localhost:8080/api/build \
  -H "Content-Type: application/json" \
  -d '{"request": "Create a Book Management API with JWT auth, CRUD Books and Authors, PostgreSQL, Docker"}' \
  --output book-api.zip
```

The LLM is optional for a first run: without a reachable endpoint the planner falls back to
heuristics, so generation still works.

## Build history (Phase 3 — Postgres)

When `DATABASE_URL` is set, every build run is recorded — request, spec, attempts,
status, error, and the ZIP itself (inline for now; moves to S3 later in Phase 3):

- `GET /api/builds` — recent runs, newest first (503 when persistence is not configured)
- `GET /api/builds/{id}/download` — re-download a past build's ZIP
- `POST /api/build` responds with an `X-Build-Id` header when the run was recorded

Persistence is opt-in and best-effort: without `DATABASE_URL`, or with the database
down, builds keep working — they just aren't recorded. Docker Compose ships a
`postgres:16` service wired in automatically; for bare local dev use SQLite
(`DATABASE_URL=sqlite:///./builds.db`) or leave it empty.

## Build cache (Phase 3 — Redis)

When `REDIS_URL` is set, a successful build is cached keyed on the (normalized)
request text. An identical request within `BUILD_CACHE_TTL` (default 1 h) returns
the cached ZIP instantly — no LLM run — marked with an `X-Cache: hit` header and
not re-recorded in history. Same opt-in/best-effort rules as the database: no
Redis, or Redis down, and every request simply builds fresh. Docker Compose
ships a `redis:7` service wired in automatically.

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR: **ruff** lint → **pytest** (hermetic — no
LLM needed) → **docker build**. The docker-build job only runs if lint and tests pass.

## Tests

```bash
venv/Scripts/pytest
```

## Roadmap

- **Phase 1 (done):** single-agent templates-first generator → ZIP.
- **Phase 2 (done):** split into planner → architecture → backend → database → testing → reviewer nodes.
- **Phase 3 (in progress):** AWS backing — Postgres build history ✔, Redis build cache ✔; vLLM on EC2 GPU, S3 next.
- **Phase 4–7:** GitHub push, Docker verify, CI/CD generation, ECS deploy agent.
