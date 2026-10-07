#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(id -u)" != 0 ]; then
    echo "Run with sudo bash kiosk/restore.sh" >&2
    exit 1
fi
backup=/var/backups/power-dashboard-kiosk
if systemctl is-enabled power-dashboard-docker-delay.timer >/dev/null 2>&1; then
    bash optimize-boot.sh --restore
fi
test -f "$backup/lightdm.conf"
test -f "$backup/dashboard.service"
test -f "$backup/cmdline.txt"
test -f "$backup/plymouthd.conf"
systemctl disable dashboard.service
cp -a "$backup/lightdm.conf" /etc/lightdm/lightdm.conf
cp -a "$backup/dashboard.service" /etc/systemd/system/dashboard.service
cp -a "$backup/cmdline.txt" /boot/firmware/cmdline.txt
cp -a "$backup/plymouthd.conf" /etc/plymouth/plymouthd.conf
plymouth-set-default-theme pix
update-initramfs -u -k all
systemctl daemon-reload
if grep -qx enabled "$backup/dashboard.enabled"; then systemctl enable dashboard.service; fi
mv "$backup" "$backup.restored-$(date +%Y%m%d-%H%M%S)"
echo "Original desktop boot restored. Reboot when ready."
