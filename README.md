# Power Dashboard

A real-time 3D telemetry dashboard designed for Raspberry Pi hardware. It visualizes I2C sensor data (Voltage, Amps, Watts) using Flask and Plotly.

## Features
- Real-time 3D telemetry graphing.
- Optimized for Raspberry Pi (Bookworm/Wayfire/Labwc).
- Kiosk-mode browser interface.

## Setup
1. Clone this repo: `git clone https://github.com/tahp/power_dashboard.git`
2. Install dependencies using the Raspberry Pi instructions below.
3. Configure I2C: Ensure your user is in the `i2c` group (`sudo usermod -aG i2c $USER`).
4. Run the dashboard: `.venv/bin/python dashboard_host.py`

For development on a non-Pi computer, create a virtual environment and run
`pip install -r requirements.txt`. The application will automatically use
mock telemetry when Raspberry Pi I2C hardware is unavailable.

On Raspberry Pi OS, use the system camera packages and a virtual environment
that can see them:

```bash
sudo apt update
sudo apt install python3-flask python3-numpy python3-opencv python3-picamera2 python3-venv
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-pi.txt
```

## Deployment
This project is designed to run as a systemd service. Update the paths in `dashboard.service` to match your local installation directory.



## Embedded camera page

The left Camera icon switches the main content to a live CSI or USB camera
feed inside the dashboard. Home restores the telemetry graph and HUD. The
navigation stays visible; no separate window or fullscreen player is opened.
Pause/Resume controls viewing in this browser. Leaving Camera stops its stream;
sensor polling continues. Retry connection rescans hardware when the camera is unavailable.

### Run and test on the Raspberry Pi

1. Connect a Raspberry Pi CSI camera or a USB camera before starting the app.
   The application prefers Picamera2/libcamera for CSI cameras and falls back
   to OpenCV/V4L2 for USB cameras.
2. In the existing Python environment used by this project, run:
   ```bash
   cd ~/power-dashboard
   .venv/bin/python dashboard_host.py
   ```
   If a camera library is missing, install `python3-picamera2` for CSI cameras
   or `python3-opencv` for USB cameras. A virtual environment must be created
   with `--system-site-packages` to access these Raspberry Pi OS packages.
3. Open `http://localhost:5000` in the Pi's browser, or
   `http://<PI-IP>:5000` from another device. If `PORT` is set, use that port.
   Restart the existing service instead if it already owns the port, then
   refresh the browser to load the updated UI.
4. Confirm Home still updates voltage, current, power, runtime, and the graph.
   Select Camera: the feed should occupy the main panel, with the left dock
   still visible and the URL ending in `#camera`.
5. Test Pause, Resume, Home, and Camera repeatedly. Test browser Back/Forward
   and reload directly at `http://localhost:5000/#camera`. Resize the browser
   or test on the Pi touchscreen; the camera should fit without hiding the dock.
6. Stop with Ctrl+C, disconnect the camera, and restart. Camera should show
   connection instructions while Home still works. Reconnect and tap Retry
   connection to detect the camera without restarting the app.

Camera diagnostics: `curl http://localhost:5000/camera_status` should report
`"available": true` and a `picamera2` or `v4l2` backend when detection succeeds. The `/video_feed` endpoint
is the raw MJPEG stream; use the dashboard's Camera icon for normal viewing.
Sensor initialization failures retain the existing mocked telemetry fallback.

## Boot directly into Power Dashboard (this Pi)

The `kiosk/` configuration runs a dedicated Labwc + Chromium session without
loading the Raspberry Pi desktop panel, file manager, or desktop startup apps.
It retains LightDM for automatic login and runs the Python backend as a system
service. Chromium waits for the backend and restarts if the browser exits.
This configuration targets the existing `pugs` account and
`/home/pugs/power-dashboard`, on port 5000.

Install from a terminal on the Pi (enter your sudo password locally):

```bash
cd ~/power-dashboard
sudo bash kiosk/install.sh
sudo reboot
```

If the kiosk is already installed and `/var/backups/power-dashboard-kiosk`
exists, update only the boot/shutdown screen with:

```bash
sudo bash kiosk/install.sh --update-plymouth
sudo reboot
```

Installation backs up the existing LightDM configuration and dashboard service
under `/var/backups/power-dashboard-kiosk`. It takes effect on the next reboot;
it does not terminate the current desktop session. After reboot, confirm the
dashboard fills the display, the desktop panel is absent, telemetry updates,
and Camera/Home navigation works. Plotly is packaged under `static/vendor` and
the UI uses local system fonts, so the dashboard UI no longer needs internet
access.

The kiosk installer also replaces the Raspberry Pi/Plymouth boot splash with
the custom 800x480 boot artwork during startup and shutdown artwork during
poweroff. The custom Plymouth theme intentionally does not register a
status-message callback, and the installer removes the display console plus
systemd status output from the kernel command line, so verbose boot text is
not shown on the display. The original boot command line and Plymouth
configuration are backed up with the other kiosk files.

To restore normal desktop boot, use SSH or switch to a console with
Ctrl+Alt+F2, log in, and run:

```bash
cd ~/power-dashboard
sudo bash kiosk/restore.sh
sudo reboot
```

Diagnostics: `systemctl status dashboard.service`,
`journalctl -u dashboard.service -b`, and
`curl http://127.0.0.1:5000/api_data`.
Do not run another copy of `dashboard_host.py` while its service is running.

### Network and power-action security

The server binds to `127.0.0.1` by default, which is the safe setting for the
local Chromium kiosk. To intentionally allow telemetry and camera viewing from
another device, start it with `HOST=0.0.0.0`. Restart and shutdown requests are
still rejected unless they originate from the Pi itself, and the UI supplies a
per-process request token. Forwarded-address headers are not trusted.

Run the local smoke tests with:

```bash
DASHBOARD_SKIP_CAMERA_INIT=1 DASHBOARD_DISABLE_POLLING=1 \
  python3 -m unittest discover -s tests -v
```

If the kiosk was installed before the Power Options menu was added, install
its permission rule once without reinstalling the kiosk:

```bash
cd ~/power-dashboard
sudo bash kiosk/repair-power-permissions.sh
sudo systemctl restart dashboard.service
```

After pulling this security update onto an existing kiosk, refresh the service
definition so it uses loopback networking and the project environment:

```bash
cd ~/power-dashboard
sudo bash kiosk/update-service.sh
```
