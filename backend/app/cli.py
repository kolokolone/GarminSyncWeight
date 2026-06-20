"""GarminSyncWeight command-line interface.

Usage:
    python -m backend.app.cli dry-run --start-date 2026-06-01 --end-date 2026-06-19
    python -m backend.app.cli status
    python -m backend.app.cli check-config
"""

import argparse
import asyncio
import json
import sys

from app.config import Settings, get_settings
from app.logging_config import setup_logging
from app.services.deduplicator import Deduplicator
from app.services.garmin_client import GarminClient
from app.services.mapper import WithingsToGarminMapper
from app.services.report_builder import ReportBuilder
from app.services.sync_engine import SyncEngine
from app.services.withings_auth import WithingsAuthService
from app.services.withings_client import WithingsClient
from app.services.withings_parser import WithingsParser
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    settings = get_settings()
    settings.ensure_directories()
    setup_logging(
        log_dir=settings.resolved_log_dir,
        level=settings.log_level,
        fmt=settings.log_format,
    )

    if args.command == "status":
        _cmd_status(settings)
    elif args.command == "check-config":
        _cmd_check_config(settings)
    elif args.command == "dry-run":
        asyncio.run(_cmd_dry_run(settings, args))
    else:
        parser.print_help()
        sys.exit(1)


# ── Commands ────────────────────────────────────────────────────


def _cmd_status(settings: "Settings") -> None:
    token_store = TokenStore(settings.resolved_data_dir)
    auth = WithingsAuthService(settings, token_store)
    sync_store = SyncStore(settings.resolved_data_dir)
    report_builder = ReportBuilder(settings)

    print("╔══════════════════════════════════════════╗")
    print("║        GarminSyncWeight Status           ║")
    print("╚══════════════════════════════════════════╝")
    print(f"  Version:          {settings.app_version}")
    print(f"  Dry-run default:  {settings.dry_run_default}")
    print(f"  Writes enabled:   {settings.enable_garmin_writes}")
    print(f"  Withings config:  {'✓' if auth.is_configured() else '✗'}")
    print(f"  Withings token:   {'✓' if auth.has_token() else '✗'}")
    print(f"  Last sync:        {sync_store.last_sync_time() or 'never'}")
    print(f"  Latest report:    {report_builder.latest_report_path() or 'none'}")


def _cmd_check_config(settings: "Settings") -> None:
    print("╔══════════════════════════════════════════╗")
    print("║      GarminSyncWeight Configuration      ║")
    print("╚══════════════════════════════════════════╝")
    print(f"  APP_HOST:            {settings.app_host}")
    print(f"  APP_PORT:            {settings.app_port}")
    print(f"  APP_TIMEZONE:        {settings.app_timezone}")
    print(f"  USER_HEIGHT_M:       {settings.user_height_m or 'not set'}")
    print(f"  DRY_RUN_DEFAULT:     {settings.dry_run_default}")
    print(f"  ENABLE_GARMIN_WRITES: {settings.enable_garmin_writes}")
    print(f"  WITHINGS_SCOPE:      {settings.withings_scope}")
    print(f"  DATA_DIR:            {settings.resolved_data_dir}")
    print(f"  LOG_DIR:             {settings.resolved_log_dir}")
    print(f"  RUNTIME_DIR:         {settings.resolved_runtime_dir}")
    print()
    print("  Dedup thresholds:")
    print(f"    WEIGHT_DUPLICATE_EPSILON_KG: {settings.weight_duplicate_epsilon_kg}")
    print(f"    WEIGHT_CONFLICT_EPSILON_KG:  {settings.weight_conflict_epsilon_kg}")
    print(f"    GARMIN_LOOKBACK_DAYS:        {settings.garmin_lookback_days}")
    print(f"    GARMIN_LOOKAHEAD_DAYS:       {settings.garmin_lookahead_days}")
    print(f"    PER_DAY_STRATEGY:            {settings.withings_per_day_strategy}")


async def _cmd_dry_run(settings: "Settings", args: argparse.Namespace) -> None:
    token_store = TokenStore(settings.resolved_data_dir)
    sync_store = SyncStore(settings.resolved_data_dir)
    auth = WithingsAuthService(settings, token_store)
    wclient = WithingsClient(auth, settings)
    parser = WithingsParser(settings)
    mapper = WithingsToGarminMapper(settings)
    garmin = GarminClient(settings, use_mcp=False)
    dedup = Deduplicator(settings, sync_store)
    report_builder = ReportBuilder(settings)

    engine = SyncEngine(
        settings, auth, wclient, parser, mapper, garmin, dedup, sync_store, report_builder,
    )

    start_date = args.start_date
    end_date = args.end_date

    print("Mode: DRY-RUN")
    print(f"Période: {start_date} → {end_date}")
    print()

    report = await engine.run_dry_run(start_date, end_date, settings.app_timezone)

    s = report.summary
    print(f"Withings: {report.withings.get('raw_groups_count', 0)} groupes de mesures récupérés, "
          f"{report.withings.get('parsed_measurements_count', 0)} mesures exploitables")
    print(f"Garmin: {len(report.garmin.get('daily_weigh_ins', []))} weigh-ins existants, "
          f"{len(report.garmin.get('body_composition', []))} compositions existantes")
    print(f"Nouveaux candidats: {s.would_write_count}")
    print(f"Doublons: {s.skipped_duplicates_count}")
    print(f"Doublons probables: {s.possible_duplicates_count}")
    print(f"Conflits: {s.conflicts_count}")
    print(f"Invalides: {s.invalid_count}")
    print("Écritures Garmin exécutées: 0")
    print()

    report_path = report_builder.latest_report_path()
    if report_path:
        print(f"Rapport: {report_path}")
    print()
    print("Rapport détaillé:")
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garminsyncweight", description="GarminSyncWeight CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # dry-run
    dry = sub.add_parser("dry-run", help="Run the sync pipeline in dry-run mode (no writes)")
    dry.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    dry.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")

    # status
    sub.add_parser("status", help="Show application status")

    # check-config
    sub.add_parser("check-config", help="Show configuration values")

    return parser


if __name__ == "__main__":
    main()
