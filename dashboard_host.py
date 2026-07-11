#!/usr/bin/env python3
import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from flask import Flask, render_template_string, jsonify
import plotly.graph_objects as go
import plotly.offline as op

# --- Hardware Initialization ---
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    adc = ADS.ADS1115(i2c)
    chan_voltage = AnalogIn(adc, 0)
    chan_current = AnalogIn(adc, 1)
except Exception as e:
    print(f"\n[ERROR]: Failed to initialize sensors. Is the board plugged in?")
    print(f"Error detail: {e}\n")
    print("Dashboard will continue but will show mocked data (12.6V, 0.8A) instead.")
    sensors_initialized = False
else:
    sensors_initialized = True

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

# --- Flask Server Initialization ---
app = Flask(__name__)

def get_sensor_readings():
    if not sensors_initialized:
        return {'voltage': 12.60, 'amps': 0.8} 

    try:
        v_sensor_read = chan_voltage.voltage
        current_sensor_read = chan_current.voltage
    except Exception as e:
        return {'voltage': 12.60, 'amps': 0.8} 

    actual_voltage = v_sensor_read * VOLTAGE_DIVIDER_RATIO
    actual_current = (current_sensor_read - ZERO_CURRENT_OFFSET) / ACS712_SENSITIVITY

    if abs(actual_current) < 0.15:
        actual_current = 0.0
    
    elapsed_seconds = time.time() - START_RUN_TIME
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
    # Generate the figure based on the *current* historical_data
    fig = go.Figure(data=[
        go.Scatter3d(
            x=historical_data['amps'],
            y=historical_data['voltage'],
            z=historical_data['relative_time'],
            mode='lines',
            line=dict(width=5, color=historical_data['voltage'], colorscale='Viridis')
        )
    ])
    fig.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=0, b=0))
    return fig.to_json()

# 2. Update your HTML template to refresh the graph automatically
@app.route('/')
def index():
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
            <style>body { margin: 0; background: #000; color: #fff; overflow: hidden; }</style>
        </head>
        <body>
            <div id="plot-div" style="width:100vw; height:100vh;"></div>
            <script>
                function refreshGraph() {
                    fetch('/api_graph')
                        .then(res => res.json())
                        .then(data => Plotly.react('plot-div', data.data, data.layout));
                }
                setInterval(refreshGraph, 2000); // Updates the 3D graph every 2 seconds
                refreshGraph();
            </script>
        </body>
        </html>
    """)


@app.route('/api_data')
def api_data():
    return jsonify(get_sensor_readings())

if __name__ == '__main__':
    print(f"\n[INFO]: Modernized v2 Graphics Dashboard initialized.")
    print(f"Open page on Pi display or mobile browser to verify.\n")
    app.run(host='0.0.0.0', port=5000, debug=True)

