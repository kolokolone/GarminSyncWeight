"""Sync report persistence and retrieval."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models.sync import SyncReport

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("sync")
    return _logger


class ReportBuilder:
    """Handles serialisation and retrieval of sync reports."""

    def __init__(self, settings: Settings) -> None:
        self._reports_dir = settings.reports_dir

    def save(self, report: SyncReport) -> Path:
        """Save a sync report to disk as JSON.

        Returns: the file path of the saved report.
        """
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        filename = f"sync-{now.strftime('%Y%m%d-%H%M%S')}.json"
        filepath = self._reports_dir / filename

        data = report.model_dump(mode="json")
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _log().info("Report saved → %s", filepath)
        return filepath

    def latest_report_path(self) -> Path | None:
        """Return the path of the most recent report, or None."""
        files = sorted(self._reports_dir.glob("sync-*.json"), reverse=True)
        return files[0] if files else None

    def load_latest(self) -> dict[str, Any] | None:
        """Load and return the latest report as a dict, or None."""
        path = self.latest_report_path()
        if path is None:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_reports(self) -> list[dict[str, Any]]:
        """Return metadata about all available reports."""
        reports: list[dict[str, Any]] = []
        for path in sorted(self._reports_dir.glob("sync-*.json"), reverse=True)[:20]:
            reports.append({
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            })
        return reports
