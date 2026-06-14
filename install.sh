#!/usr/bin/env bash
# install.sh — idempotent systemd installer for bio-bridge.
# Re-running is safe; it only applies what has drifted.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "must run as root"; exit 1; }

REPO_DIR="/opt/bio-bridge"
STATE_DIR="/var/lib/bio-bridge"
ENV_FILE="/etc/bio-bridge.env"
USER="bio-bridge"

echo "[install] 1/8 user"
id "$USER" &>/dev/null || useradd --system --home "$REPO_DIR" --shell /usr/sbin/nologin "$USER"

echo "[install] 2/8 directories"
mkdir -p "$STATE_DIR"
chown -R "$USER:$USER" "$REPO_DIR" "$STATE_DIR"

echo "[install] 3/8 uv"
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
# Make uv globally PATH-visible so `sudo -u bio-bridge uv ...` works. The
# installer drops it in /root/.local/bin (mode 700), which non-root users
# can't traverse, so copy the binary into /usr/local/bin instead.
if [[ -x /root/.local/bin/uv ]]; then
    install -m 755 /root/.local/bin/uv  /usr/local/bin/uv
    install -m 755 /root/.local/bin/uvx /usr/local/bin/uvx 2>/dev/null || true
fi

echo "[install] 4/8 python env"
cd "$REPO_DIR"
if [[ ! -x "$REPO_DIR/.venv/bin/python" ]]; then
    sudo -u "$USER" uv venv "$REPO_DIR/.venv" --python 3.11
else
    echo "  venv already exists — reusing"
fi
sudo -u "$USER" uv pip install --python "$REPO_DIR/.venv/bin/python" -e "$REPO_DIR"

echo "[install] 5/8 credentials (optional)"
# If you captured a HAR on this machine, extract credentials into config.json.
# Otherwise, populate the env file in the next step.
if [[ -f /tmp/capture.har ]]; then
    echo "  found /tmp/capture.har — extracting credentials to config.json"
    sudo -u "$USER" "$REPO_DIR/.venv/bin/bio-bridge" init /tmp/capture.har || true
    shred -u /tmp/capture.har 2>/dev/null || rm -f /tmp/capture.har
fi

echo "[install] 6/8 env file"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" <<'EOF'
# bio-bridge configuration. Fill in the Zepp credentials (from a HAR capture)
# and the endpoint you want the data forwarded to. Do not commit this file.
ZEPP_APP_TOKEN=
ZEPP_USER_ID=
ZEPP_HOST=api-mifit-us3.zepp.com
INGEST_URL=http://localhost:8000/ingest
INGEST_KEY=
STATE_PATH=/var/lib/bio-bridge/state.sqlite
EOF
    chmod 600 "$ENV_FILE"
    echo "  created $ENV_FILE (template) — edit it and fill in the values"
else
    echo "  $ENV_FILE already exists — leaving it untouched"
fi

echo "[install] 7/8 systemd units"
install -m 644 "$REPO_DIR/deploy/bio-bridge.service" /etc/systemd/system/
install -m 644 "$REPO_DIR/deploy/bio-bridge.timer"   /etc/systemd/system/
systemctl daemon-reload

echo "[install] 8/8 enable timer"
# Make the env file group-readable by the service user so manual one-off
# commands (e.g. a backfill) can source it. systemd reads it as root before
# switching user, so this does not loosen anything for the service itself.
if id "$USER" &>/dev/null && [[ -f "$ENV_FILE" ]]; then
    chgrp "$USER" "$ENV_FILE"
    chmod 640 "$ENV_FILE"
fi
systemctl enable --now bio-bridge.timer

echo "[install] OK. Next run:"
systemctl list-timers bio-bridge.timer --no-pager 2>/dev/null | grep bio-bridge || true
