#!/bin/sh
# Use a dedicated profile so other Chromium windows cannot absorb kiosk launches.
while :; do
    until /usr/bin/curl --noproxy '*' --fail --silent --max-time 3 http://127.0.0.1:5000/api_data >/dev/null; do
        sleep 1
    done
    /usr/bin/chromium --ozone-platform=wayland --kiosk --no-first-run \
        --no-default-browser-check --noerrdialogs --disable-session-crashed-bubble \
        --password-store=basic --user-data-dir="$HOME/.local/share/power-dashboard-chromium" \
        http://127.0.0.1:5000
    sleep 2
done
