"""Log reading routes (read-only, redacted).

Endpoints:
  GET /api/logs/{service}  — retrieve recent log lines for a service
"""


from app.config import Settings, get_settings
from app.dependencies import verify_admin_token
from app.models.sync import LogResult
from app.utils.redact import redact_lines
from fastapi import APIRouter, Depends, HTTPException, Query

ALLOWED_SERVICES = frozenset({"backend", "withings", "garmin", "sync", "security"})

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/{service}", response_model=LogResult)
def get_logs(
    service: str,
    lines: int = Query(default=200, ge=1, le=1000),
    settings: Settings = Depends(get_settings),
    _admin: None = Depends(verify_admin_token),
) -> LogResult:
    """Return redacted log lines for a given service."""
    if service not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown log service '{service}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_SERVICES))}"
            ),
        )
    log_file = settings.resolved_log_dir / f"{service}.log"
    if not log_file.exists():
        return LogResult(service=service, lines=["No log entries yet."], truncated=False)

    all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    # Filter out lines that escaped from pytest worker directories
    filtered = [ln for ln in all_lines if "pytest-of-" not in ln]
    selected = filtered[-lines:]
    safe = redact_lines(selected)
    return LogResult(service=service, lines=safe, truncated=len(all_lines) > lines)
