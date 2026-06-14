# zepp-sync-sidecar

A small, self-hosted sidecar (CLI: `bio-bridge`) that pulls your own health data from a
Zepp / Amazfit wearable, normalizes it, and forwards it to an HTTP endpoint of your choice.
It runs on a schedule via systemd and keeps incremental sync state in SQLite so it only
fetches what's new.

It's built for the case where you want your wearable data in *your* system (a personal
dashboard, a database, your own API) instead of locked inside a vendor app.

## What it does

- **Extracts** Zepp API credentials from a HAR capture of the official app (one-time setup).
- **Fetches** daily wellness metrics (sleep, steps, stress, HRV/readiness, SpO2, PAI, blood pressure) and strength-training sessions.
- **Normalizes** Zepp's raw, reverse-engineered response blobs into a stable JSON shape.
- **Forwards** the result to a configurable ingest endpoint (`INGEST_URL`) with a shared key.
- **Runs incrementally** on a systemd timer, with resumable historical backfill.

## Commands

```bash
bio-bridge init <path-to-har>          # Extract Zepp credentials from a HAR capture into config.json
bio-bridge sync                        # Run one incremental sync cycle
bio-bridge backfill --from --to        # Historical pull (rate-limited, resumable)
bio-bridge status                      # Show config and last sync time
```

## Setup

1. **Capture credentials.** Follow [`runbooks/01-har-capture.md`](runbooks/01-har-capture.md)
   to record a HAR file from the Zepp app, then:
   ```bash
   bio-bridge init ./capture.har        # writes config.json (chmod 600, gitignored)
   ```
2. **Configure the destination.** Set `INGEST_URL` and `INGEST_KEY` (env vars, or in `config.json`)
   to point at the endpoint that should receive the data.
3. **Run it.** `bio-bridge sync` for a one-off, or install the systemd timer (below) for scheduled syncs.

## Deploying as a service

On a Linux host (tested on Ubuntu):

```bash
git clone <this-repo> /opt/bio-bridge
cd /opt/bio-bridge
sudo ./install.sh                       # creates a service user, venv, env file, and systemd timer
sudo nano /etc/bio-bridge.env           # fill in ZEPP_* and INGEST_* values
```

`install.sh` is idempotent — re-run it for updates: `git pull && sudo ./install.sh`.
The systemd service runs hardened (non-root user, `NoNewPrivileges`, `ProtectSystem=strict`).

## Token refresh

Zepp app tokens expire; when `sync` starts returning 401s, re-capture and re-extract:

1. Re-do the HAR capture (see [`runbooks/01-har-capture.md`](runbooks/01-har-capture.md)).
2. `bio-bridge init ./capture.har`
3. `sudo systemctl restart bio-bridge.timer`
4. Securely delete the HAR file.

## Security notes

- Credentials live only in `config.json` (mode 600, gitignored) or environment variables — never committed.
- HAR captures contain a live token; shred them after extracting.
- The service runs as a dedicated non-root user with a hardened systemd unit.

## Attribution

The Zepp/Huami API client in [`src/bio_bridge/_zepp_client.py`](src/bio_bridge/_zepp_client.py)
is **vendored from [m4ary/zepp-health-cli](https://github.com/m4ary/zepp-health-cli)**
(pinned commit `a466dfa`) and retains its original authorship. See [NOTICE](NOTICE). Everything
else — the sync engine, normalizer, CLI, state tracking, and deployment tooling — is original.

Not affiliated with or endorsed by Zepp Health / Huami.

## License

[MIT](LICENSE) for the original code in this repository. The vendored client retains its upstream license; see [NOTICE](NOTICE).
