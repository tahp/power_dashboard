#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(id -u)" != 0 ]; then
    echo "Run with sudo bash kiosk/install.sh" >&2
    exit 1
fi
backup=/var/backups/power-dashboard-kiosk

if [ "${1:-}" = "--update-plymouth" ]; then
    install -Dm644 plymouth/power-dashboard/power-dashboard.plymouth \
        /usr/share/plymouth/themes/power-dashboard/power-dashboard.plymouth
    install -Dm644 plymouth/power-dashboard/power-dashboard.script \
        /usr/share/plymouth/themes/power-dashboard/power-dashboard.script
    install -Dm644 plymouth/power-dashboard/boot.png \
        /usr/share/plymouth/themes/power-dashboard/boot.png
    install -Dm644 plymouth/power-dashboard/shutdown.png \
        /usr/share/plymouth/themes/power-dashboard/shutdown.png
    install -Dm644 plymouth/power-dashboard/splash.png \
        /usr/share/plymouth/themes/power-dashboard/splash.png
    plymouth-set-default-theme power-dashboard
    update-initramfs -u -k all
    echo "Updated Plymouth loading/shutdown screen. Reboot when ready."
    exit 0
fi

if [ -e "$backup" ]; then
    echo "Backup already exists at $backup; restore before reinstalling." >&2
    exit 1
fi
for binary in /usr/bin/labwc /usr/bin/chromium /usr/bin/curl; do test -x "$binary"; done
test -f /etc/systemd/system/dashboard.service
test -f /etc/lightdm/lightdm.conf
mkdir -p "$backup"
cp -a /etc/lightdm/lightdm.conf "$backup/lightdm.conf"
cp -a /etc/systemd/system/dashboard.service "$backup/dashboard.service"
cp -a /boot/firmware/cmdline.txt "$backup/cmdline.txt"
cp -a /etc/plymouth/plymouthd.conf "$backup/plymouthd.conf"
systemctl is-enabled dashboard.service > "$backup/dashboard.enabled" || true
install -Dm755 session.sh /usr/local/libexec/power-dashboard-session
install -Dm755 browser.sh /usr/local/libexec/power-dashboard-browser
install -Dm644 labwc/rc.xml /usr/local/share/power-dashboard/labwc/rc.xml
install -Dm755 labwc/autostart /usr/local/share/power-dashboard/labwc/autostart
install -Dm644 power-dashboard.desktop /usr/share/wayland-sessions/power-dashboard.desktop
install -Dm644 plymouth/power-dashboard/power-dashboard.plymouth /usr/share/plymouth/themes/power-dashboard/power-dashboard.plymouth
install -Dm644 plymouth/power-dashboard/power-dashboard.script /usr/share/plymouth/themes/power-dashboard/power-dashboard.script
install -Dm644 plymouth/power-dashboard/boot.png /usr/share/plymouth/themes/power-dashboard/boot.png
install -Dm644 plymouth/power-dashboard/shutdown.png /usr/share/plymouth/themes/power-dashboard/shutdown.png
install -Dm644 plymouth/power-dashboard/splash.png /usr/share/plymouth/themes/power-dashboard/splash.png
install -m644 dashboard.service /etc/systemd/system/dashboard.service
install -Dm440 power-dashboard-sudoers /etc/sudoers.d/power-dashboard
visudo -cf /etc/sudoers.d/power-dashboard
plymouth-set-default-theme power-dashboard
python3 - <<'PY'
from pathlib import Path
p = Path('/boot/firmware/cmdline.txt')
tokens = p.read_text().split()
hidden = {'console=serial0,115200', 'console=tty1', 'plymouth.ignore-serial-consoles'}
tokens = [token for token in tokens if token not in hidden]
for token in ('quiet', 'splash', 'loglevel=0', 'systemd.show_status=false', 'rd.systemd.show_status=false', 'vt.global_cursor_default=0'):
    if token not in tokens:
        tokens.append(token)
p.write_text(' '.join(tokens) + '\n')
PY
update-initramfs -u -k all
python3 - <<'PY'
from pathlib import Path
p = Path('/etc/lightdm/lightdm.conf')
lines = p.read_text().splitlines()
seat = False
keys = {'user-session': 'power-dashboard', 'autologin-session': 'power-dashboard', 'autologin-user': 'pugs'}
seen = set()
for i, line in enumerate(lines):
    if line.startswith('['):
        seat = line.strip() == '[Seat:*]'
    if seat and '=' in line and not line.lstrip().startswith('#'):
        key = line.split('=', 1)[0].strip()
        if key in keys:
            lines[i] = key + '=' + keys[key]
            seen.add(key)
assert seen == set(keys), 'Expected existing Pi autologin settings; configuration was not changed'
p.write_text('\n'.join(lines) + '\n')
PY
systemctl daemon-reload
systemctl reenable dashboard.service
echo "Installed. Reboot when ready. Existing desktop session has not been stopped."
