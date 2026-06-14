"""Config loading — env vars only, no on-disk secrets in prod.

Locally for testing, falls back to ./config.json (gitignored).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Config:
    zepp_app_token: str
    zepp_user_id: str
    zepp_host: str
    ingest_url: str
    ingest_key: str
    state_path: Path

    @classmethod
    def load(cls) -> "Config":
        # Local-dev fallback: read config.json if env vars are missing.
        local_cfg = {}
        local_path = Path("config.json")
        if local_path.exists():
            local_cfg = json.loads(local_path.read_text())

        def _get(env_key: str, json_key: Optional[str] = None, default: Optional[str] = None) -> str:
            v = os.getenv(env_key) or local_cfg.get(json_key or env_key.lower(), default)
            if not v:
                raise RuntimeError(f"Missing config: {env_key} (and not in config.json)")
            return v

        return cls(
            zepp_app_token=_get("ZEPP_APP_TOKEN", "app_token"),
            zepp_user_id=_get("ZEPP_USER_ID", "user_id"),
            zepp_host=_get("ZEPP_HOST", "host", default="api-mifit-us3.zepp.com"),
            ingest_url=_get("INGEST_URL", default="http://localhost:8000/ingest"),
            ingest_key=_get("INGEST_KEY"),
            state_path=Path(os.getenv("STATE_PATH", "/var/lib/bio-bridge/state.sqlite")),
        )
