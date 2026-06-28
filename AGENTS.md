# AGENTS.md — GarminSyncWeight

Controlled local bridge: Withings Body Cardio → Garmin Connect.  
FastAPI + SQLite + static frontend. French UI, English code. Python ≥ 3.12, managed with `uv`.

## Quick start (dev)

```powershell
uv sync --group dev                      # installs deps + pytest + ruff
copy .env.example .env
# edit .env: WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, USER_HEIGHT_M
./scripts/dev.ps1                        # http://127.0.0.1:8010 (--reload)
```

The `PYTHONPATH` must include `backend/` — scripts set this automatically.  
When running manually: `uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010`

## Commands

| Purpose | Command |
|---|---|---|
| Install deps (prod) | `uv sync` |
| Install deps (dev) | `uv sync --group dev` |
| Lint | `uv run ruff check backend` |
| Test (all) | `uv run pytest` |
| Test (all, Windows fallback) | `$env:PYTHONPATH = "backend"; python -m pytest` |
| Test (one file) | `uv run pytest backend/tests/test_sync.py -v` |
| Test (filter) | `uv run pytest -k "test_run_sync" -v` |
| Run server (prod) | `./scripts/start.ps1` or `start.bat` |
| Run server (dev) | `./scripts/dev.ps1` (--reload) |
| CLI status | `uv run python -m backend.app.cli status` |
| CLI sync | `uv run python -m backend.app.cli sync --start-date 2026-06-21 --end-date 2026-06-21` |
| Docker build+run | `docker compose up --build` |
| CI check | `./scripts/test.ps1` (ruff + pytest) |
| Health check | `curl http://127.0.0.1:8010/api/healthz` |

> **Windows note**: `uv run pytest` may fail with "uv trampoline failed to canonicalize script path".
> The fallback `$env:PYTHONPATH = "backend"; python -m pytest` always works.

## Architecture

```
backend/app/
  main.py              ← FastAPI create_app(), mounts frontend, includes routers
  config.py             ← pydantic-settings from .env, frozen (immutable)
  logging_config.py     ← JSONL logs with secret redaction, per-subsystem files
  cache.py              ← In-memory TTL cache with stale-while-revalidate + @cached decorator
  cli.py                ← sync/status/check-config subcommands
  api/
    routes_status.py    ← GET /api/status (cached 60s)
    routes_auth.py      ← Withings OAuth2 flow + POST /api/withings/auth/config (writes .env)
    routes_garmin_auth.py ← Garmin auth via Taxuspt/garmin_mcp
    routes_sync.py      ← POST /api/sync/run + SSE streaming
    routes_logs.py      ← Log file viewer
    routes_measurements.py ← Measurement history/preview
  services/
    sync_engine.py      ← Orchestrator: check → read → dedupe → write → report
    withings_auth.py    ← OAuth2 client, refresh token rotation
    withings_client.py  ← POST /measure?action=getmeas
    withings_parser.py  ← Decode Withings value×10^unit, timezone-aware
    mapper.py           ← Withings fields → Garmin add_body_composition payload
    garmin_auth_service.py ← garmin-mcp-auth subprocess management
    garmin_client.py    ← garminconnect library wrapper (read weigh-ins, write body comp)
    deduplicator.py     ← Epsilon-based dedup (0.05kg duplicate, 0.2kg conflict)
    report_builder.py   ← JSON reports → runtime/reports/
  storage/
    db.py               ← SQLite schema init (8 tables: tokens, oauth_states, garmin_cache,
                           withings_measurements, sync_jobs, sync_candidates,
                           sync_decisions, schema_migrations)
    token_store.py      ← Withings OAuth tokens (single-store: withings_tokens table)
    sync_store.py       ← sync_jobs, sync_candidates, sync_decisions (idempotency + audit)
    measurement_store.py ← Cached Withings measurements
    garmin_cache.py     ← Cache Garmin reads (1h TTL)
  models/
    sync.py             ← SyncReport, SyncCandidate, StatusResponse (Pydantic)
    garmin.py           ← GarminBodyComposition, GarminWeighIn, GarminBodyCompositionCandidate
    auth.py, withings.py
  utils/
    redact.py           ← Secret redaction (tokens, emails, passwords)
frontend/out/           ← Static SPA (index.html + assets/app.js + assets/styles.css)
```

Database: single SQLite `data/withings_tokens.db` — everything in one file.
`token_store.py` opens it as `TOKEN_DB_FILENAME = "withings_tokens.db"` (constant in code).
All other stores construct the same path from `settings.resolved_data_dir / "withings_tokens.db"`.
Garmin tokens: `~/.garminconnect` (mounted as volume in Docker).

## Python import rules

All imports use `app.` prefix (not `backend.app.`):  
`from app.config import Settings`, `from app.services.sync_engine import SyncEngine`

This works because `pythonpath = ["backend"]` in `pyproject.toml` (`[tool.pytest.ini_options]`) or `PYTHONPATH=backend` env var.

## Frontend golden rule

> **The backend is the single source of truth. The frontend is display-only.**

- Never compute business logic in `frontend/out/assets/app.js` (BMI, dedup decisions, period math).
- Never call Garmin or Withings APIs directly from the frontend.
- Never store secrets (passwords, OTP) in `localStorage`.
- If the backend already computes a value (e.g. BMI in `mapper.py`), the frontend reads it from the API response — never recomputes it.

Full rules: `docs/ARCHITECTURE_FRONTEND_BACKEND.md`.

## Cache behavior (important for tests)

`cache.py` provides three layers:
- `TTLCache` — per-key TTL, singleton via `get_cache()`
- `stale_while_revalidate()` — serves stale data while refreshing in background
- `@cached(key, ttl_seconds)` — decorator for async functions

The `/api/status` endpoint uses `stale_while_revalidate` with `ttl=60, stale_ttl=300`.
Tests that exercise cached routes should call `get_cache().invalidate_all()` to reset state.

## Test structure

```
backend/tests/
  conftest.py          ← APP_ENV=test autouse fixture, Settings fixtures, helpers
  fixtures/            ← JSON files: withings_getmeas_*.json, garmin_*.json
  test_admin_api.py    ← Admin UI, Withings config save, Garmin auth disconnect
  test_cache.py        ← TTL cache, stale-while-revalidate
  test_dedup.py        ← Deduplicator epsilon logic
  test_garmin_api.py   ← GarminClient (uses test_data injection, NOT mocking)
  test_garmin_cache.py ← GarminCache SQLite TTL
  test_mapping.py      ← WithingsToGarminMapper field mapping
  test_measurement_store.py
  test_security.py     ← Redaction, env validation, host binding
  test_sync.py         ← Full sync engine integration
  test_units.py        ← Parser unit conversions, edge cases
```

Key conftest fixtures (available to all tests without import):
- `settings` — `Settings(**overrides)` with test paths and `user_height_m=1.75`
- `settings_no_height` — same but `user_height_m=None`
- `parser`, `parser_no_height` — `WithingsParser` instances
- `mapper`, `mapper_no_height` — `WithingsToGarminMapper` instances
- `sync_store` — `SyncStore` with temp directory, auto-closed on teardown
- `dedup` — `Deduplicator(settings, sync_store)`

Key helpers in conftest:
- `load_fixture(name)` → dict — load JSON from `backend/tests/fixtures/`
- `make_weigh_in(date_str, weight_kg)` → `GarminWeighIn`
- `make_body_composition(date_str, weight_kg)` → `GarminBodyComposition`
- `make_candidate(date_str, weight_kg, idempotency_key)` → `GarminBodyCompositionCandidate`

## Key constraints

- **Ruff:** `line-length = 100`, targets `py312`, rules `["E", "F", "I", "UP", "B", "SIM"]`, ignores `B008`.
- **Settings loads from both** `.env` and `config/.env` (latter for Docker). Constructor is frozen — use `Settings(**overrides)` for tests.
- **Never delete or modify Garmin data.**
- **Garmin client test injection.** `GarminClient` accepts `test_data` kwarg and `set_test_data()`. Tests inject fixtures directly — never mock at the garminconnect level.
- **Dedup idempotency.** `sync_candidates` table is the source of truth. Only `synced` and `skipped_existing` decisions block re-sync. `failed`, `skipped_conflict`, `invalid` do NOT block re-sync.
- **`sync_decisions` table** is a detailed audit log of each dedup decision (separate from `sync_candidates.decision`). Both tables must stay consistent.
- **Withings refresh tokens are rotative.** Each refresh response may return a new refresh token. Always persist the latest.
- **Log redaction is automatic.** Any `logging.getLogger("garminsync")` or subsystem logger passes through `RedactingJsonFormatter`. Don't add manual redaction.
- **Test logging isolation.** `APP_ENV=test` disables file logging. Tests only write to console. Set automatically by conftest autouse fixture.
- **Port binding.** Default `127.0.0.1:8010`. Never expose publicly without external auth.
- **Withings scope `user.metrics` is mandatory.** Reject configuration without it.
- **Per-day measurement strategy.** Controlled by `WITHINGS_PER_DAY_STRATEGY` env var: `latest_per_day` (default), `earliest_per_day`, or `all_if_distinct`.
- **Garmin OTP flow (2 steps).** `POST /api/garmin/auth/login` supports a two-step MFA flow:
  1. Send `email` + `password` → returns `needs_otp: true` + `auth_session_id`
  2. Send `auth_session_id` + `otp` → completes authentication
  The legacy single-call (`email` + `password` + `otp` in one request) still works for backward compatibility.
  Sessions are in-memory (TTL 5 min), not shared between workers.
  `POST /api/garmin/auth/verify` only checks token validity — never submits OTP.
- **Garmin lookback/forward windows.** Configurable via `GARMIN_LOOKBACK_DAYS` (default 7) and `GARMIN_LOOKAHEAD_DAYS` (default 1). Sync reads existing Garmin data within this window to detect duplicates/conflicts.
- **Docker binding nuance.** Dockerfile uvicorn binds `0.0.0.0:8010`, but docker-compose maps to `127.0.0.1:8010`. The compose mapping is the effective bind — never remove the `127.0.0.1` restriction in compose.

## Version note

`pyproject.toml` version 0.3.7 is canonical. Also hardcoded in `config.py` (`app_version`).
When bumping: update pyproject.toml, backend/app/config.py, README.md,
docs/DOCKER.md, and frontend/out/index.html (version badge).

## Docs

- `docs/README_GUIDE.md` — README maintenance rules
- `docs/architecture.md` — full component reference
- `docs/ARCHITECTURE_FRONTEND_BACKEND.md` — frontend/backend separation rules and OTP flow
- `docs/agent-workflow.md` — two-agent workflow (brainstorm → dev) using `agents/` directory
- `docs/security.md` — threat model and redaction rules
- `docs/mapping_withings_garmin.md` — field mapping decisions and rationale
- `docs/UI_STYLE_GUIDE.md` — frontend conventions
- `docs/DOCKER.md` — Docker deployment and healthcheck setup

## Utility scripts (non-runtime)

- `scripts/migrate_v1_to_v2.py` — v1 (JSON) → v2 (SQLite) migration
- `scripts/analyze_db.py` — inspect sync_candidates decisions/stats
- `scripts/fix_duplicate_jobs.py` — dedup duplicate sync_job entries
- `scripts/verify_migration.py` — validate migration completeness

## .sisyphus integration

Sisyphus plans live in `.sisyphus/plans/`. The project has no `opencode.json` or other agent instruction files.
