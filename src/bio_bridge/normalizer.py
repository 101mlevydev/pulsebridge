"""Zepp API responses → bio-bridge canonical payloads.

Normalizes raw Zepp/Huami responses into a stable `wellness_daily` / `activities`
shape that the ingest endpoint consumes. Keep the receiving side in sync.

Field reference (from Huami's reverse-engineered band_data summary blob):
  stp.ttl  = total steps          stp.dis = distance (m)        stp.cal = calories
  slp.st   = sleep start (unix)   slp.ed  = sleep end (unix)
  slp.dp   = deep sleep minutes   slp.lt  = light sleep minutes
  slp.dt   = total sleep time?    slp.ss  = sleep score?
  slp.rhr  = resting HR           slp.wk  = wake count
  hr.maxHr.hr = max HR for day
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _decode_band_summary(item: dict[str, Any]) -> dict[str, Any]:
    """Decode the base64-encoded `summary` field on a band_data row."""
    blob = item.get("summary")
    if not blob:
        return {}
    try:
        return json.loads(base64.b64decode(blob))
    except Exception as e:
        logger.warning(f"band_data summary decode failed: {e}")
        return {}


def _band_row_for_date(band_response: dict[str, Any], target_date: date) -> dict[str, Any]:
    """Find the band_data row matching target_date and return its decoded summary."""
    iso = target_date.isoformat()
    for item in band_response.get("data", []) or []:
        if item.get("date_time") == iso:
            return _decode_band_summary(item)
    return {}


def normalize_daily(zepp_responses: dict[str, Any], target_date: date) -> dict[str, Any]:
    """Collapse multiple per-endpoint responses for one date into one payload.

    Most useful metrics come from the band_data summary blob (base64-decoded).
    The events/readiness endpoints currently return empty for this account —
    those fields will populate once the strap has data to report.
    """
    band_decoded = _band_row_for_date(zepp_responses.get("band_data", {}) or {}, target_date)
    slp = band_decoded.get("slp", {}) or {}
    stp = band_decoded.get("stp", {}) or {}
    hr = band_decoded.get("hr", {}) or {}
    max_hr = hr.get("maxHr", {}) or {}

    events = zepp_responses.get("events", {}) or {}
    stress_events = (events.get("all_day_stress") or {}).get("items", [])
    stress_levels = [
        e.get("data", {}).get("value")
        for e in stress_events
        if isinstance(e, dict) and isinstance(e.get("data"), dict)
    ]
    stress_avg = round(sum(v for v in stress_levels if v is not None) / len(stress_levels)) if stress_levels else None

    bp = zepp_responses.get("blood_pressure") or {}
    bp_items = (bp.get("data") or {}).get("items") or [] if isinstance(bp.get("data"), dict) else []

    # Sleep duration in hours from start/end unix timestamps when both present
    sleep_h = None
    st, ed = slp.get("st"), slp.get("ed")
    if st and ed and ed > st:
        sleep_h = round((ed - st) / 3600.0, 2)

    return {
        "date": target_date.isoformat(),
        "primary_device": "amazfit_helio_strap",

        # From decoded band_data summary blob
        "resting_hr": slp.get("rhr") or None,
        "sleep_duration_h": sleep_h,
        "sleep_deep_minutes": slp.get("dp") or None,
        "sleep_light_minutes": slp.get("lt") or None,
        "sleep_awake_minutes": slp.get("wk") or None,
        "steps": stp.get("ttl") or None,

        # Stress from events
        "stress_level": stress_avg,

        # BP — first reading of the day if any
        "bp_systolic": (bp_items[0] if bp_items else {}).get("systolic"),
        "bp_diastolic": (bp_items[0] if bp_items else {}).get("diastolic"),

        # Zepp-only — preserved in meta jsonb
        "calories": stp.get("cal") or None,
        "distance_m": stp.get("dis") or None,
        "max_hr": max_hr.get("hr") or None,
        "step_goal": band_decoded.get("goal"),
        "device_serial": band_decoded.get("sn"),
        "tz_offset_s": band_decoded.get("tz"),
        "sleep_start_ts": slp.get("st"),
        "sleep_end_ts": slp.get("ed"),

        # Stub fields — will populate when the events endpoints return data
        "hrv_rmssd": None,
        "hrv_status": None,
        "sleep_quality_score": None,
        "sleep_rem_minutes": None,
        "readiness_score": None,
        "recovery_score": None,
        "recovery_time_hours": None,
        "body_battery_low": None,
        "body_battery_high": None,
        "body_battery_end": None,
        "spo2_avg": None,
        "respiration_rate": None,
        "training_status": None,
        "body_weight_kg": None,
        "skin_temp_delta_c": None,
        "pai_score": None,
        "vo2_max": None,
        "training_load": None,
        "training_effect_aerobic": None,
        "training_effect_anaerobic": None,

        "raw_response": zepp_responses,
    }


STRENGTH_SPORTS = {"strength_training", "hyrox", "strength"}


def normalize_strength_session(session: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a Zepp strength/HYROX session into the activities payload shape.

    Returns None if the session is an endurance type we deliberately skip.
    """
    sport_raw = (session.get("sport") or session.get("type") or "").lower()
    if sport_raw not in STRENGTH_SPORTS:
        return None

    return {
        "zepp_session_id": session.get("trackid") or session.get("id"),
        "sport": sport_raw if sport_raw in STRENGTH_SPORTS else "strength_training",
        "name": session.get("name"),
        "start_time": session.get("start_time") or session.get("trackid_iso"),
        "duration_s": session.get("duration_s") or session.get("end_time_seconds"),
        "calories": session.get("calories") or session.get("calorie"),
        "avg_hr": session.get("avg_hr"),
        "max_hr": session.get("max_hr"),
        "movements": session.get("movements", []),
        "total_sets": session.get("total_sets"),
        "total_reps": session.get("total_reps"),
        "rest_periods_s": session.get("rest_periods_s"),
        "raw_response": session,
    }
