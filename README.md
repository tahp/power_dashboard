# Power Dashboard

A real-time 3D telemetry dashboard designed for Raspberry Pi hardware. It visualizes I2C sensor data (Voltage, Amps, Watts) using Flask and Plotly.

## Features
- Real-time 3D telemetry graphing.
- Optimized for Raspberry Pi (Bookworm/Wayfire/Labwc).
- Kiosk-mode browser interface.

## Setup
1. Clone this repo: `git clone https://github.com/tahp/power-dashboard.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Configure I2C: Ensure your user is in the `i2c` group (`sudo usermod -aG i2c $USER`).
4. Run the dashboard: `python3 dashboard_host.py`

## Deployment
This project is designed to run as a systemd service. Update the paths in `dashboard.service` to match your local installation directory.


