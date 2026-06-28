# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS runtime
WORKDIR /app

# ── System dependencies ────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install uv ─────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── Install dependencies from lockfile ─────────────────────
# Copy only dependency files first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Install garmin_mcp pinned ──────────────────────────────
# ARG can be overridden at build time: --build-arg GARMIN_MCP_REF=<commit-sha>
ARG GARMIN_MCP_REF=main
RUN uv pip install --system \
    "garmin_mcp @ git+https://github.com/Taxuspt/garmin_mcp@${GARMIN_MCP_REF}"

# ── Copy application code ──────────────────────────────────
COPY backend ./backend
COPY frontend ./frontend

# ── Runtime setup ──────────────────────────────────────────
RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data /app/logs /app/runtime/reports /app/config \
    && chown -R app:app /app /home/app

USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8010

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", \
     "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8010"]
