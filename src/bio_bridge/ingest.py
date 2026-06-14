"""HTTP client that posts normalized health data to a configurable ingest endpoint."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class IngestClient:
    def __init__(self, url: str, key: str, zepp_user_id: str, timeout: float = 30.0):
        self.url = url
        self.headers = {"X-Internal-Key": key, "Content-Type": "application/json"}
        self.zepp_user_id = zepp_user_id
        self.timeout = timeout

    def post(self, wellness_daily: list[dict[str, Any]] | None = None,
             activities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": "zepp",
            "provider_user_id": self.zepp_user_id,
        }
        if wellness_daily:
            payload["wellness_daily"] = wellness_daily
        if activities:
            payload["activities"] = activities
        if "wellness_daily" not in payload and "activities" not in payload:
            return {"status": "noop", "counts": {"wellness_daily": 0, "activities": 0}}

        r = httpx.post(self.url, json=payload, headers=self.headers, timeout=self.timeout)
        if r.status_code != 200:
            logger.error(f"ingest failed: {r.status_code} {r.text}")
        r.raise_for_status()
        return r.json()
