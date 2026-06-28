# AGENTS.md — GarminSyncWeight

Controlled local bridge: Withings Body Cardio → Garmin Connect.  
FastAPI + SQLite + static frontend. French UI, English code.

## Quick start (dev)

```powershell
uv sync
copy .env.example .env
# edit .env with WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET
./scripts/dev.ps1     # http://127.0.0.1:8010 (--reload)
```

The `PYTHONPATH` must include `backend/` — scripts set this automatically.  
When running manually: `uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010`

## Commands

| Purpose | Command |
|---|---|
| Install deps | `uv sync` |
| Lint | `uv run ruff check backend` |
| Test (all) | `uv run pytest` |
| Test (one file) | `uv run pytest backend/tests/test_sync.py -v` |
| Test (filter) | `uv run pytest -k "test_run_sync" -v` |
| Run server | `./scripts/start.ps1` (prod) or `./scripts/dev.ps1` (dev --reload) |
| CLI status | `uv run python -m backend.app.cli status` |
| CLI sync | `uv run python -m backend.app.cli sync --start-date 2026-06-21 --end-date 2026-06-21` |
| Garmin auth | `uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth` |
| Garmin verify | `uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth --verify` |
| Docker | `docker compose up --build` |
| CI check | `./scripts/test.ps1` (ruff + pytest) |

## Architecture

```
backend/app/
  main.py              ← FastAPI create_app(), mounts frontend, includes routers
  config.py             ← pydantic-settings from .env, frozen (immutable)
  logging_config.py     ← JSONL logs with secret redaction, per-subsystem files
  cache.py              ← Simple in-memory TTL cache (used for /api/status)
  cli.py                ← sync/status/check-config subcommands
  api/
    routes_status.py    ← GET /api/status (cached 60s)
    routes_auth.py      ← Withings OAuth2 flow
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
    db.py               ← SQLite schema init
    token_store.py      ← Withings OAuth tokens
    sync_store.py       ← sync_jobs, sync_candidates (idempotency + audit)
    measurement_store.py ← Cached Withings measurements
    garmin_cache.py     ← Cache Garmin reads (1h TTL)
  models/
    sync.py             ← SyncReport, SyncCandidate, StatusResponse (Pydantic)
    garmin.py           ← GarminBodyComposition, GarminWeighIn
    auth.py, withings.py
  utils/
    redact.py           ← Secret redaction (tokens, emails, passwords)
frontend/out/           ← Static SPA (index.html + assets/app.js + assets/styles.css)
```

Database: single SQLite `data/withings_tokens.db` — everything in one file.  
Garmin tokens: `~/.garminconnect` (mounted as volume in Docker).

## Python import rules

All imports use `app.` prefix (not `backend.app.`):  
`from app.config import Settings`, `from app.services.sync_engine import SyncEngine`

This works because `pythonpath = ["backend"]` in pyproject.toml or `PYTHONPATH=backend`.

## Key constraints

- **Never delete or modify Garmin data.** This app only writes new `add_body_composition` calls.
- **Settings is frozen.** `config.Settings` has `frozen=True`. For tests, construct `Settings(**overrides)`.
- **Garmin client test injection.** `GarminClient` accepts `test_data` kwarg and `set_test_data()`. Tests inject fixtures directly — never mock at the garminconnect level.
- **Dedup idempotency.** `sync_candidates` table is the source of truth. Only `synced` and `skipped_existing` decisions block re-sync. `failed`, `skipped_conflict`, `invalid` do NOT block re-sync.
- **Withings refresh tokens are rotative.** Each refresh response may return a new refresh token. Always persist the latest.
- **Log redaction is automatic.** Any `logging.getLogger("garminsync")` or subsystem logger passes through `RedactingJsonFormatter`. Don't add manual redaction.
- **Test logging isolation.** `APP_ENV=test` disables file logging. Tests only write to console. Set automatically by conftest.py.
- **Port binding.** Default `127.0.0.1:8010`. Never expose publicly without external auth.
- **Withings scope `user.metrics` is mandatory.** Reject configuration without it.

## Version note

`pyproject.toml` says 0.3.1 (canonical). `README.md` header says 0.2.10 (stale).  
Update README version when bumping pyproject.toml.

## Docs

- `docs/architecture.md` — full component reference
- `docs/security.md` — threat model and redaction rules
- `docs/mapping_withings_garmin.md` — field mapping decisions and rationale
- `docs/UI_STYLE_GUIDE.md` — frontend conventions
- `AUDIT_GARMINSYNCWEIGHT.md` — historical context from v0.1.1 audit (problems found, fixes applied)

## .sisyphus integration

Sisyphus plans live in `.sisyphus/plans/`. The project has no `opencode.json` or other agent instruction files.
