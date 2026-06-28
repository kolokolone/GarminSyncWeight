"""Shared FastAPI dependencies (admin auth, settings)."""

from app.config import Settings, get_settings
from fastapi import Depends, HTTPException, Request, status


async def verify_admin_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Require ADMIN_API_TOKEN on protected routes.

    When ADMIN_API_TOKEN is empty (not configured), all requests pass through.
    When configured, the caller must provide the token via:
    - ``Authorization: Bearer <token>`` header, or
    - ``?token=<token>`` query parameter.
    """
    token = settings.admin_api_token
    if not token:
        return  # No token configured → open (backward compatibility)

    # Header Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
        if provided == token:
            return

    # Query param ?token=<token>
    provided = request.query_params.get("token", "")
    if provided == token:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token admin requis. Utilisez ?token=... ou Authorization: Bearer ...",
    )
