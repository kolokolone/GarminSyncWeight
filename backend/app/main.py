"""GarminSyncWeight — FastAPI application entry point.

Safe dry-run bridge between Withings Body Cardio and Garmin Connect.

Usage:
    uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
"""


from pathlib import Path

from app.api import routes_auth, routes_garmin_auth, routes_logs, routes_status, routes_sync
from app.config import get_settings
from app.logging_config import setup_logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_directories()

    # ── Logging ───────────────────────────────────────────────
    setup_logging(
        log_dir=settings.resolved_log_dir,
        level=settings.log_level,
        fmt=settings.log_format,
    )

    app = FastAPI(
        title="GarminSyncWeight",
        version=settings.app_version,
        description="Withings → Garmin Connect bridge — safe dry-run pipeline",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://127.0.0.1:{settings.app_port}",
            f"http://localhost:{settings.app_port}",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ── Routes ────────────────────────────────────────────────
    app.include_router(routes_status.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_garmin_auth.router)
    app.include_router(routes_sync.router)
    app.include_router(routes_logs.router)

    frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "out"
    assets_dir = frontend_dir / "assets"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False, response_model=None)
    def root():
        index = frontend_dir / "index.html"
        if index.exists():
            return FileResponse(index)
        return {
            "app": "GarminSyncWeight",
            "version": settings.app_version,
            "status": "/api/status",
            "docs": "/docs",
        }

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def frontend_fallback(path: str):
        index = frontend_dir / "index.html"
        if index.exists() and not path.startswith("api/"):
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not found")

    return app


app = create_app()
