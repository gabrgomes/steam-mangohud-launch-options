#!/usr/bin/env bash
# Installs the systemd --user service that keeps every installed Steam
# game's MangoHud launch options up to date automatically (see README.md).
# Safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "-- Python virtual environment --"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
echo "Done."

echo "-- systemd --user service --"
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
cp steam-mangohud-autoconfig.service "$SERVICE_DIR/steam-mangohud-autoconfig.service"
systemctl --user daemon-reload
systemctl --user enable --now steam-mangohud-autoconfig.service
echo "Installed and started."
echo
echo "== Done =="
echo "Status:  systemctl --user status steam-mangohud-autoconfig"
echo "Logs:    journalctl --user -u steam-mangohud-autoconfig -f"
echo
echo "It watches for Steam to close and re-applies the MangoHud launch"
echo "options wrapper at that point - no more running add_mangohud.py by hand."
