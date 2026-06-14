"""bio-bridge CLI entry points."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import click

from . import _zepp_client as zc
from .config import Config
from .ingest import IngestClient
from .normalizer import normalize_daily, normalize_strength_session
from .state import State

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bio-bridge")


@click.group()
def main() -> None:
    """bio-bridge — Zepp/Amazfit health-data sync sidecar."""


@main.command()
@click.argument("har_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def init(har_path: Path) -> None:
    """Extract Zepp credentials from a HAR capture file into config.json."""
    creds = _extract_from_har(har_path)
    if not creds:
        click.echo("ERROR: could not extract Zepp credentials from HAR.", err=True)
        sys.exit(1)
    click.echo(f"Extracted: app_token={creds['app_token'][:8]}…, user_id={creds['user_id']}, host={creds['host']}")

    Path("config.json").write_text(json.dumps(creds, indent=2))
    Path("config.json").chmod(0o600)
    click.echo("Wrote config.json (chmod 600). For deployment, set the same values as environment variables instead.")


@main.command()
def sync() -> None:
    """Run one incremental sync cycle."""
    cfg = Config.load()
    state = State(cfg.state_path)
    client = zc.ZeppClient(apptoken=cfg.zepp_app_token, user_id=cfg.zepp_user_id, host=cfg.zepp_host)
    ingest = IngestClient(url=cfg.ingest_url, key=cfg.ingest_key, zepp_user_id=cfg.zepp_user_id)

    today = date.today()
    last = state.get_last_sync("daily") or (datetime.now(timezone.utc) - timedelta(days=2))
    start = max(last.date() - timedelta(days=1), today - timedelta(days=7))

    wellness_rows = []
    for day in _daterange(start, today):
        try:
            responses = _fetch_day(client, day)
            wellness_rows.append(normalize_daily(responses, day))
        except Exception as e:
            logger.warning(f"skipping {day}: {e}")

    activity_rows: list[dict] = []
    try:
        history = client.sport_history("strength_training", 0, 0)
        for session in (history.get("data", {}).get("sessions", []) or [])[:50]:
            norm = normalize_strength_session(session)
            if norm:
                activity_rows.append(norm)
    except Exception as e:
        logger.warning(f"strength history fetch failed: {e}")

    result = ingest.post(wellness_daily=wellness_rows or None, activities=activity_rows or None)
    state.set_last_sync("daily", datetime.now(timezone.utc))
    logger.info(f"sync complete: {result}")


@main.command()
@click.option("--from", "from_date", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
@click.option("--to", "to_date", type=click.DateTime(formats=["%Y-%m-%d"]), required=True)
def backfill(from_date: datetime, to_date: datetime) -> None:
    """Historical pull. Rate-limited, resumable via state.sqlite."""
    import time
    cfg = Config.load()
    state = State(cfg.state_path)
    client = zc.ZeppClient(apptoken=cfg.zepp_app_token, user_id=cfg.zepp_user_id, host=cfg.zepp_host)
    ingest = IngestClient(url=cfg.ingest_url, key=cfg.ingest_key, zepp_user_id=cfg.zepp_user_id)

    days = list(_daterange(from_date.date(), to_date.date()))
    logger.info(f"backfilling {len(days)} days from {from_date.date()} to {to_date.date()}")
    rows: list[dict] = []
    for i, day in enumerate(days, 1):
        marker = (day.isoformat(), day.isoformat())
        if state.is_window_done("daily", *marker):
            continue
        try:
            responses = _fetch_day(client, day)
            rows.append(normalize_daily(responses, day))
            state.mark_backfill_window("daily", *marker)
        except Exception as e:
            logger.warning(f"backfill skip {day}: {e}")
        if i % 7 == 0:
            ingest.post(wellness_daily=rows)
            rows = []
            logger.info(f"backfill progress: {i}/{len(days)}")
        time.sleep(1.0)  # rate limit
    if rows:
        ingest.post(wellness_daily=rows)
    logger.info("backfill complete")


@main.command()
def status() -> None:
    """Show sync state."""
    cfg = Config.load()
    state = State(cfg.state_path)
    last = state.get_last_sync("daily")
    click.echo(f"Config:")
    click.echo(f"  zepp_user_id:      {cfg.zepp_user_id}")
    click.echo(f"  zepp_host:         {cfg.zepp_host}")
    click.echo(f"  ingest_url:        {cfg.ingest_url}")
    click.echo(f"  state_path:        {cfg.state_path}")
    click.echo(f"Last daily sync: {last}")


# --- helpers ---

def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _fetch_day(client, day: date) -> dict:
    """Fetch all per-day Zepp endpoints for one calendar date.

    Wraps each endpoint in try/except: if Zepp's response shape or path differs
    from what we expect, we log and skip — sync still completes for the other
    metrics. Refine these calls as we learn the real response shapes.
    """
    from_ms = _ms(day)
    to_ms = _ms(day + timedelta(days=1))
    out: dict = {}

    # Readiness / watch_score — skin temp, HRV status, readiness/recovery scores
    try:
        out["readiness_watch_score"] = client.events_user(
            "readiness", from_ms, to_ms, sub_type="watch_score"
        )
    except Exception as e:
        logger.warning(f"{day} readiness fetch failed: {e}")

    # Band data — sleep + steps blob
    try:
        out["band_data"] = client.band_data(day, day, query_type="summary")
    except Exception as e:
        logger.warning(f"{day} band_data fetch failed: {e}")

    # Event-stream metrics
    try:
        out.setdefault("events", {})["all_day_stress"] = client.events_user(
            "all-day-stress", from_ms, to_ms
        )
    except Exception as e:
        logger.warning(f"{day} stress fetch failed: {e}")
    try:
        out.setdefault("events", {})["pai"] = client.events_user("pai", from_ms, to_ms)
    except Exception as e:
        logger.warning(f"{day} pai fetch failed: {e}")
    try:
        out.setdefault("events", {})["spo2"] = client.events_user("spo2", from_ms, to_ms)
    except Exception as e:
        logger.warning(f"{day} spo2 fetch failed: {e}")

    # Blood pressure
    try:
        out["blood_pressure"] = client.blood_pressure_me(days=1, to_date=day)
    except Exception as e:
        logger.warning(f"{day} bp fetch failed: {e}")

    return out


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


_USER_ID_RE = re.compile(r"/users/(\d+)/")


def _extract_from_har(har_path: Path) -> Optional[dict]:
    """Pull app_token, user_id, host from a HAR / JSON session export."""
    raw = har_path.read_text()
    data = json.loads(raw)
    entries = data.get("log", {}).get("entries", []) if isinstance(data, dict) else data

    app_token = None
    user_id = None
    host = None
    for entry in entries:
        req = entry.get("request", {}) if isinstance(entry, dict) else {}
        url = req.get("url", "")
        if "api-mifit" not in url:
            continue
        for h in req.get("headers", []):
            if h.get("name", "").lower() == "apptoken":
                app_token = h.get("value")
        m = _USER_ID_RE.search(url)
        if m:
            user_id = m.group(1)
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname and "api-mifit" in parsed.hostname:
            host = parsed.hostname
        if app_token and user_id and host:
            break

    if not (app_token and user_id and host):
        return None
    return {"app_token": app_token, "user_id": user_id, "host": host}


if __name__ == "__main__":
    main()
