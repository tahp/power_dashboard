#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
if [ "$(id -u)" != 0 ]; then
    echo "Run with sudo bash kiosk/repair-power-permissions.sh" >&2
    exit 1
fi

install -Dm440 power-dashboard-sudoers /etc/sudoers.d/power-dashboard
visudo -cf /etc/sudoers.d/power-dashboard
echo "Power-dashboard restart/shutdown permissions installed."
