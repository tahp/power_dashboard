#!/bin/sh
# A separate configuration prevents Raspberry Pi desktop autostart programs.
exec /usr/bin/labwc -C /usr/local/share/power-dashboard/labwc -S /usr/local/libexec/power-dashboard-browser
