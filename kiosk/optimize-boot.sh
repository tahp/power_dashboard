#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
if [ "$(id -u)" != 0 ]; then
    echo "Run with sudo bash kiosk/optimize-boot.sh" >&2
    exit 1
fi

backup=/var/backups/power-dashboard-boot-optimization
units=(docker.service docker.socket containerd.service)

if [ "${1:-}" = "--restore" ]; then
    test -d "$backup"
    systemctl disable power-dashboard-docker-delay.timer 2>/dev/null || true
    rm -f /etc/systemd/system/power-dashboard-docker-delay.service
    rm -f /etc/systemd/system/power-dashboard-docker-delay.timer
    while read -r unit state; do
        if [ "$state" = enabled ]; then
            systemctl enable "$unit"
        fi
    done < "$backup/unit-states"
    systemctl daemon-reload
    mv "$backup" "$backup.restored-$(date +%Y%m%d-%H%M%S)"
    echo "Restored normal Docker startup."
    exit 0
fi

if [ ! -d "$backup" ]; then
    mkdir -p "$backup"
    for unit in "${units[@]}"; do
        printf '%s ' "$unit" >> "$backup/unit-states"
        systemctl is-enabled "$unit" 2>/dev/null >> "$backup/unit-states" || true
    done
fi

install -m644 power-dashboard-docker-delay.service /etc/systemd/system/power-dashboard-docker-delay.service
install -m644 power-dashboard-docker-delay.timer /etc/systemd/system/power-dashboard-docker-delay.timer
systemctl daemon-reload
systemctl disable "${units[@]}"
systemctl enable power-dashboard-docker-delay.timer
echo "Docker will start 45 seconds after boot; the currently running Docker service was not stopped."
