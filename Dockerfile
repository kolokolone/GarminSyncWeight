# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system . \
    && uv pip install --system "git+https://github.com/Taxuspt/garmin_mcp"

COPY backend ./backend
COPY frontend ./frontend

RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data /app/logs /app/runtime/reports /home/app/.garminconnect \
    && chown -R app:app /app /home/app/.garminconnect

USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/status', timeout=5)"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8010"]
