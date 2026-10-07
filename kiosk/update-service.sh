#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
if [ "$(id -u)" != 0 ]; then
    echo "Run with sudo bash kiosk/update-service.sh" >&2
    exit 1
fi

test -x /home/pugs/power-dashboard/.venv/bin/python
install -Dm755 browser.sh /usr/local/libexec/power-dashboard-browser
install -m644 dashboard.service /etc/systemd/system/dashboard.service
install -Dm440 power-dashboard-sudoers /etc/sudoers.d/power-dashboard
visudo -cf /etc/sudoers.d/power-dashboard
systemctl daemon-reload
systemctl restart dashboard.service
echo "Dashboard service and kiosk browser updated."
