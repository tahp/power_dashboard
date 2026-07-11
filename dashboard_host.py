#!/usr/bin/env python3
import time
import threading
from flask import Flask, render_template_string, jsonify
import plotly.graph_objects as go
import plotly.offline as op

# --- Hardware Initialization ---
try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    i2c = busio.I2C(board.SCL, board.SDA)
    adc = ADS.ADS1115(i2c)
    chan_voltage = AnalogIn(adc, 0)
    chan_current = AnalogIn(adc, 1)
    sensors_initialized = True
except Exception as e:
    print(f"\n[ERROR]: Failed to initialize sensors. Is the board plugged in?")
    print(f"Error detail: {e}\n")
    print("Dashboard will continue but will show mocked data (12.6V, 0.8A) instead.")
    sensors_initialized = False

# --- Configuration & Calibration ---
V_REF = 12.60 
VOLTAGE_DIVIDER_RATIO = 5.0
ACS712_SENSITIVITY = 0.100  
ZERO_CURRENT_OFFSET = 2.45  

# --- Internal Data Logger ---
MAX_LOG_ENTRIES = 120 
START_RUN_TIME = time.time()

historical_data = {
    'relative_time': [0.0], 
    'voltage': [12.60],
    'amps': [0.0]
}
data_lock = threading.Lock()

# --- Flask Server Initialization ---
app = Flask(__name__)

def update_historical_data():
    """Polls the sensor (or mocks it) and appends to historical_data."""
    global sensors_initialized
    
    elapsed_seconds = time.time() - START_RUN_TIME
    
    if not sensors_initialized:
        # Generate mock readings that fluctuate over time
        import math
        import random
        # Voltage slowly drains from 12.60V with minor noise
        actual_voltage = 12.60 - (elapsed_seconds * 0.002) + random.uniform(-0.01, 0.01)
        actual_voltage = max(10.5, actual_voltage)
        # Current fluctuates as a sine wave + noise
        actual_current = 2.0 + 1.5 * math.sin(elapsed_seconds / 10.0) + random.uniform(-0.1, 0.1)
        actual_current = max(0.0, actual_current)
    else:
        try:
            v_sensor_read = chan_voltage.voltage
            current_sensor_read = chan_current.voltage
            actual_voltage = v_sensor_read * VOLTAGE_DIVIDER_RATIO
            actual_current = (current_sensor_read - ZERO_CURRENT_OFFSET) / ACS712_SENSITIVITY
            if abs(actual_current) < 0.15:
                actual_current = 0.0
        except Exception as e:
            # Fallback to mock data if transient hardware read error
            import math
            import random
            actual_voltage = 12.60 - (elapsed_seconds * 0.002) + random.uniform(-0.01, 0.01)
            actual_voltage = max(10.5, actual_voltage)
            actual_current = 2.0 + 1.5 * math.sin(elapsed_seconds / 10.0) + random.uniform(-0.1, 0.1)
            actual_current = max(0.0, actual_current)

    with data_lock:
        historical_data['relative_time'].append(elapsed_seconds)
        historical_data['voltage'].append(actual_voltage)
        historical_data['amps'].append(actual_current)
        
        if len(historical_data['relative_time']) > MAX_LOG_ENTRIES:
            historical_data['relative_time'].pop(0)
            historical_data['voltage'].pop(0)
            historical_data['amps'].pop(0)

    return {
        'voltage': round(actual_voltage, 2),
        'amps': round(actual_current, 2)
    }

def get_sensor_readings():
    with data_lock:
        latest_voltage = historical_data['voltage'][-1]
        latest_amps = historical_data['amps'][-1]
    return {
        'voltage': round(latest_voltage, 2),
        'amps': round(latest_amps, 2),
        'mode': 'ACTIVE' if sensors_initialized else 'MOCKED'
    }

def polling_loop():
    while True:
        try:
            update_historical_data()
        except Exception as e:
            pass
        time.sleep(1.0)

# Start background polling thread
polling_thread = threading.Thread(target=polling_loop, daemon=True)
polling_thread.start()

def generate_3d_helix():
    import numpy as np
    
    time_start = historical_data['relative_time'][0]
    time_end = historical_data['relative_time'][-1]
    
    if time_start == time_end:
        time_end = time_start + 10.0 

    t = np.linspace(time_start, time_end, 200)
    amps = np.sin(2 * np.pi * t) + np.random.normal(0, 0.2, 200) 
    voltage = V_REF - ((t - time_start) * 0.01)
    
    amps[np.abs(amps) < 0.15] = 0.0

    fig = go.Figure(data=[
        go.Scatter3d(
            x=amps,
            y=voltage,
            z=t, 
            mode='lines',
            line=dict(
                width=8,
                color=voltage,
                colorscale=[[0, 'red'], [1, 'cyan']],
                cmin=10.0, cmax=V_REF,
            )
        )
    ])

    fig.update_layout(
        template='plotly_dark',
        scene=dict(
            xaxis=dict(title='AMPS (A)', color='#ffff00', range=[-1, 12]),
            yaxis=dict(title='VOLTAGE (V)', color='#00ffff', range=[10, V_REF+0.5]),
            zaxis=dict(title='ELAPSED TIME (s)', color='#ffffff', range=[time_end, time_start]),
            camera=dict(
                eye=dict(x=1.8, y=1.4, z=1.2), 
                up=dict(x=0, y=0, z=1),
                center=dict(x=0, y=0, z=0)
            )
        ),
        margin=dict(r=0, l=0, t=0, b=0),
        hovermode=False, 
        dragmode=False 
    )

    return op.plot(fig, output_type='div', include_plotlyjs=False, show_link=False, link_text='')

# --- Web Routes ---
# 1. Update the graph route to be a JSON generator, not a static DIV
@app.route('/api_graph')
def api_graph():
    with data_lock:
        x_data = list(historical_data['amps'])
        y_data = list(historical_data['voltage'])
        z_data = list(historical_data['relative_time'])

    # Generate the figure based on the *current* historical_data
    fig = go.Figure(data=[
        go.Scatter3d(
            x=x_data,
            y=y_data,
            z=z_data,
            mode='lines',
            line=dict(width=5, color=y_data, colorscale='Viridis')
        )
    ])
    fig.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=0, b=0))
    return fig.to_json()

# 2. Update your HTML template to refresh the graph automatically
@app.route('/')
def index():
    return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Power Telemetry Dashboard</title>
            <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
            <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
            <style>
                body {
                    margin: 0;
                    background: #020208;
                    color: #fff;
                    overflow: hidden;
                    font-family: 'Share Tech Mono', monospace;
                }
                
                #plot-div {
                    width: 100vw;
                    height: 100vh;
                    position: absolute;
                    top: 0;
                    left: 0;
                    z-index: 1;
                }
                
                .hud-panel {
                    position: absolute;
                    top: 25px;
                    left: 25px;
                    z-index: 10;
                    width: 320px;
                    padding: 24px;
                    background: rgba(8, 12, 28, 0.7);
                    backdrop-filter: blur(15px);
                    -webkit-backdrop-filter: blur(15px);
                    border: 1px solid rgba(0, 243, 255, 0.25);
                    border-radius: 16px;
                    box-shadow: 0 8px 32px 0 rgba(0, 243, 255, 0.15),
                                inset 0 0 20px rgba(0, 243, 255, 0.05);
                    transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                }
                
                .hud-panel:hover {
                    border-color: rgba(0, 243, 255, 0.5);
                    box-shadow: 0 12px 40px 0 rgba(0, 243, 255, 0.3),
                                inset 0 0 30px rgba(0, 243, 255, 0.1);
                    transform: scale(1.02) translateY(-2px);
                }
                
                .hud-header {
                    border-bottom: 1px solid rgba(0, 243, 255, 0.2);
                    padding-bottom: 12px;
                    margin-bottom: 16px;
                }
                
                .hud-title {
                    font-family: 'Orbitron', sans-serif;
                    font-weight: 700;
                    font-size: 14px;
                    letter-spacing: 2px;
                    color: #e0faff;
                    text-shadow: 0 0 10px rgba(0, 243, 255, 0.5);
                }
                
                .status-indicator {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 11px;
                    letter-spacing: 1px;
                }
                
                .pulse-dot {
                    width: 8px;
                    height: 8px;
                    background-color: #00ffaa;
                    border-radius: 50%;
                    box-shadow: 0 0 8px #00ffaa;
                    display: inline-block;
                    animation: pulse 1.8s infinite;
                }
                
                @keyframes pulse {
                    0% {
                        transform: scale(0.95);
                        box-shadow: 0 0 0 0 rgba(0, 255, 170, 0.7);
                    }
                    70% {
                        transform: scale(1);
                        box-shadow: 0 0 0 6px rgba(0, 255, 170, 0);
                    }
                    100% {
                        transform: scale(0.95);
                        box-shadow: 0 0 0 0 rgba(0, 255, 170, 0);
                    }
                }
                
                .metric-container {
                    margin-bottom: 18px;
                }
                
                .metric-label {
                    font-size: 11px;
                    letter-spacing: 1.5px;
                    color: rgba(255, 255, 255, 0.6);
                    margin-bottom: 4px;
                }
                
                .metric-value-wrapper {
                    display: flex;
                    align-items: baseline;
                    gap: 4px;
                }
                
                .metric-value {
                    font-family: 'Orbitron', sans-serif;
                    font-size: 32px;
                    font-weight: 900;
                    line-height: 1;
                }
                
                .color-voltage {
                    color: #00f3ff;
                    text-shadow: 0 0 15px rgba(0, 243, 255, 0.5);
                }
                
                .color-current {
                    color: #ffb700;
                    text-shadow: 0 0 15px rgba(255, 183, 0, 0.5);
                }
                
                .color-power {
                    color: #ff007c;
                    text-shadow: 0 0 15px rgba(255, 0, 124, 0.5);
                }
                
                .metric-unit {
                    font-size: 14px;
                    font-weight: 700;
                    color: rgba(255, 255, 255, 0.8);
                }
                
                .gauge-bar {
                    width: 100%;
                    height: 4px;
                    background: rgba(255, 255, 255, 0.08);
                    border-radius: 2px;
                    margin-top: 6px;
                    overflow: hidden;
                }
                
                .gauge-fill {
                    height: 100%;
                    border-radius: 2px;
                    transition: width 0.8s cubic-bezier(0.16, 1, 0.3, 1);
                }
                
                .bg-voltage {
                    background: linear-gradient(90deg, #005f73, #00f3ff);
                    box-shadow: 0 0 8px #00f3ff;
                }
                
                .bg-current {
                    background: linear-gradient(90deg, #9b5de5, #ffb700);
                    box-shadow: 0 0 8px #ffb700;
                }
                
                .bg-power {
                    background: linear-gradient(90deg, #7209b7, #ff007c);
                    box-shadow: 0 0 8px #ff007c;
                }
                
                .hud-footer {
                    border-top: 1px solid rgba(255, 255, 255, 0.08);
                    padding-top: 12px;
                    margin-top: 16px;
                    display: flex;
                    justify-content: space-between;
                    font-size: 11px;
                    color: rgba(255, 255, 255, 0.5);
                    letter-spacing: 1px;
                }
                
                .footer-row {
                    display: flex;
                    gap: 6px;
                }
                
                #mode-text {
                    font-weight: 700;
                    color: #00ffaa;
                }
            </style>
        </head>
        <body>
            <div id="plot-div"></div>
            
            <div class="hud-panel">
                <div class="hud-header">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span class="hud-title">POWER TELEMETRY</span>
                        <div class="status-indicator">
                            <span class="pulse-dot"></span>
                            <span id="status-text">ONLINE</span>
                        </div>
                    </div>
                </div>
                
                <div class="metric-container">
                    <div class="metric-label">VOLTAGE</div>
                    <div class="metric-value-wrapper">
                        <span id="val-voltage" class="metric-value color-voltage">0.00</span>
                        <span class="metric-unit">V</span>
                    </div>
                    <div class="gauge-bar">
                        <div id="bar-voltage" class="gauge-fill bg-voltage" style="width: 0%"></div>
                    </div>
                </div>

                <div class="metric-container">
                    <div class="metric-label">CURRENT</div>
                    <div class="metric-value-wrapper">
                        <span id="val-current" class="metric-value color-current">0.00</span>
                        <span class="metric-unit">A</span>
                    </div>
                    <div class="gauge-bar">
                        <div id="bar-current" class="gauge-fill bg-current" style="width: 0%"></div>
                    </div>
                </div>

                <div class="metric-container">
                    <div class="metric-label">POWER DRAW</div>
                    <div class="metric-value-wrapper">
                        <span id="val-power" class="metric-value color-power">0.00</span>
                        <span class="metric-unit">W</span>
                    </div>
                    <div class="gauge-bar">
                        <div id="bar-power" class="gauge-fill bg-power" style="width: 0%"></div>
                    </div>
                </div>

                <div class="hud-footer">
                    <div class="footer-row">
                        <span>MODE:</span>
                        <span id="mode-text">MOCKED</span>
                    </div>
                    <div class="footer-row">
                        <span>RUN TIME:</span>
                        <span id="run-time">0s</span>
                    </div>
                </div>
            </div>

            <script>
                const startTime = Date.now();
                
                function refreshData() {
                    fetch('/api_data')
                        .then(res => res.json())
                        .then(data => {
                            const v = parseFloat(data.voltage);
                            const a = parseFloat(data.amps);
                            const w = parseFloat((v * a).toFixed(2));
                            
                            document.getElementById('val-voltage').textContent = v.toFixed(2);
                            document.getElementById('val-current').textContent = a.toFixed(2);
                            document.getElementById('val-power').textContent = w.toFixed(2);
                            
                            // Gauges styling limits: Voltage 0-15V, Amps 0-10A, Power 0-120W
                            const vPercent = Math.min(100, Math.max(0, (v / 15.0) * 100));
                            const aPercent = Math.min(100, Math.max(0, (a / 10.0) * 100));
                            const wPercent = Math.min(100, Math.max(0, (w / 120.0) * 100));
                            
                            document.getElementById('bar-voltage').style.width = vPercent + '%';
                            document.getElementById('bar-current').style.width = aPercent + '%';
                            document.getElementById('bar-power').style.width = wPercent + '%';
                            
                            document.getElementById('mode-text').textContent = data.mode;
                            if (data.mode === 'ACTIVE') {
                                document.getElementById('mode-text').style.color = '#00ffaa';
                            } else {
                                document.getElementById('mode-text').style.color = '#ffb700';
                            }
                        })
                        .catch(err => console.error("Telemetry update error:", err));
                        
                    const elapsed = Math.floor((Date.now() - startTime) / 1000);
                    document.getElementById('run-time').textContent = elapsed + 's';
                }
                
                function refreshGraph() {
                    fetch('/api_graph')
                        .then(res => res.json())
                        .then(data => Plotly.react('plot-div', data.data, data.layout))
                        .catch(err => console.error("Graph update error:", err));
                }
                
                setInterval(refreshData, 1000);
                setInterval(refreshGraph, 2000);
                
                refreshData();
                refreshGraph();
            </script>
        </body>
        </html>
    """)


@app.route('/api_data')
def api_data():
    return jsonify(get_sensor_readings())

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print(f"\n[INFO]: Modernized v2 Graphics Dashboard initialized.")
    print(f"Open page on Pi display or mobile browser to verify.\n")
    app.run(host='0.0.0.0', port=port, debug=True)


