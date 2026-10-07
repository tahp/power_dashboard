#!/bin/sh
# Keep the single-purpose profile in tmpfs so Chromium does not read a large,
# stale profile from the microSD card during every boot.
runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
profile_dir="$runtime_dir/power-dashboard-chromium"
mkdir -p "$profile_dir"

while :; do
    until /usr/bin/curl --noproxy '*' --fail --silent --max-time 3 http://127.0.0.1:5000/api_data >/dev/null; do
        sleep 1
    done
    /usr/bin/chromium --ozone-platform=wayland --kiosk --no-first-run \
        --no-default-browser-check --noerrdialogs --disable-session-crashed-bubble \
        --disable-background-networking --disable-component-update --disable-default-apps \
        --disable-sync --disable-translate \
        --disable-features=MediaRouter,OptimizationHints,AutofillServerCommunication \
        --password-store=basic --user-data-dir="$profile_dir" \
        http://127.0.0.1:5000
    sleep 2
done
