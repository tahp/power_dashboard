#!/usr/bin/env python3
import time
import threading
import cv2
import numpy as np
from flask import Flask, render_template_string, jsonify, Response, request
import plotly.graph_objects as go
import random
import math
import os
import subprocess
import sys

# --- Camera Detection with Proper Handling ---
camera = None
camera_available = False
camera_lock = threading.Lock()
camera_process = None

def find_available_camera():
    """Find first working camera without triggering GUI windows"""
    for i in range(5):  # Check /dev/video0 through /dev/video4
        try:
            # Use a different backend to avoid GUI popups
            cap = cv2.VideoCapture(i, cv2.CAP_V4L2)  # Linux V4L2 backend
            if cap.isOpened():
                # Test read
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    cap.release()
                    print(f"✅ Camera found on /dev/video{i}")
                    return i
            cap.release()
        except Exception as e:
            print(f"⚠️ Camera {i} error: {e}")
            continue
    return None

def init_camera():
    """Initialize USB camera with proper handling"""
    global camera, camera_available
    
    try:
        camera_available = False
        if camera is not None:
            camera.release()
            camera = None
        
        camera_index = find_available_camera()
        if camera_index is not None:
            # Open with proper backend
            cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            if cap.isOpened():
                # Set properties for stability
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce latency
                
                # Test capture
                ret, frame = cap.read()
                if ret and frame is not None:
                    camera = cap
                    camera_available = True
                    print(f"✅ Camera initialized successfully")
                    return True
                cap.release()
        
        print("❌ No usable camera found")
        return False
    except Exception as e:
        print(f"❌ Camera initialization error: {e}")
        return False

def kill_camera_processes():
    """Kill processes that might be using the camera"""
    try:
        # Kill common camera hogging processes
        for proc in ['mpv', 'ffplay', 'vlc', 'cheese', 'guvcview']:
            try:
                subprocess.run(['pkill', '-f', proc], 
                             stderr=subprocess.DEVNULL, 
                             stdout=subprocess.DEVNULL)
            except:
                pass
        time.sleep(0.5)  # Wait for processes to release
    except:
        pass

# Try to initialize camera
init_camera()

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
ZERO_CURRENT_OFFSET = 2.60  

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
        actual_voltage = 12.60 - (elapsed_seconds * 0.002) + random.uniform(-0.01, 0.01)
        actual_voltage = max(10.5, actual_voltage)
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

# --- CAMERA STREAM GENERATOR (Thread-Safe) ---
def generate_frames():
    """Generator function for camera feed with sci-fi overlay"""
    global camera, camera_available
    
    while camera_available and camera is not None:
        try:
            with camera_lock:
                success, frame = camera.read()
                if not success or frame is None:
                    camera_available = False
                    camera.release()
                    camera = None
                    break
                
                # Add sci-fi overlay effects
                frame = add_scifi_overlay(frame)
                
                # Encode as JPEG with high quality
                ret, buffer = cv2.imencode('.jpg', frame, 
                    [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ret:
                    frame_bytes = buffer.tobytes()
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
        except Exception as e:
            print(f"⚠️ Camera frame error: {e}")
            time.sleep(0.1)
            continue
        
        time.sleep(0.03)  # ~30 FPS

def add_scifi_overlay(frame):
    """Add sci-fi HUD overlay to camera feed"""
    try:
        height, width = frame.shape[:2]
        
        # 2. Add corner brackets
        bracket_size = 25
        color = (0, 255, 255)  # Cyan
        thickness = 2
        
        # Top-left
        cv2.line(frame, (10, 10 + bracket_size), (10, 10), color, thickness)
        cv2.line(frame, (10, 10), (10 + bracket_size, 10), color, thickness)
        
        # Top-right
        cv2.line(frame, (width - 10, 10 + bracket_size), (width - 10, 10), color, thickness)
        cv2.line(frame, (width - 10, 10), (width - 10 - bracket_size, 10), color, thickness)
        
        # Bottom-left
        cv2.line(frame, (10, height - 10 - bracket_size), (10, height - 10), color, thickness)
        cv2.line(frame, (10, height - 10), (10 + bracket_size, height - 10), color, thickness)
        
        # Bottom-right
        cv2.line(frame, (width - 10, height - 10 - bracket_size), (width - 10, height - 10), color, thickness)
        cv2.line(frame, (width - 10, height - 10), (width - 10 - bracket_size, height - 10), color, thickness)
        
        # 3. Add HUD text
        cv2.putText(frame, "SURVEILLANCE FEED", (20, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
        # 4. Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (width - 200, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        
        # 5. Add FPS counter
        cv2.putText(frame, f"{int(30)} FPS", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        
        # 7. Subtle vignette effect
        mask = np.zeros((height, width), np.uint8)
        cv2.ellipse(mask, (width//2, height//2), 
                   (width//2 - 50, height//2 - 50), 0, 0, 360, 255, -1)
        mask = cv2.GaussianBlur(mask, (21, 21), 0)
        mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) / 255.0
        frame = (frame * (0.8 + 0.2 * mask)).astype(np.uint8)
        
        return frame
    except Exception as e:
        print(f"⚠️ Overlay error: {e}")
        return frame

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    if not camera_available:
        return "Camera not available", 404
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api_graph')
def api_graph():
    """Returns the raw data for JavaScript to render"""
    with data_lock:
        return {
            'time': historical_data['relative_time'],
            'voltage': historical_data['voltage'],
            'amps': historical_data['amps']
        }

@app.route('/api_data')
def api_data():
    return jsonify(get_sensor_readings())

@app.route('/camera_status')
def camera_status():
    """Check the camera, retrying detection if it was unavailable at startup."""
    with camera_lock:
        if not camera_available:
            init_camera()
    return jsonify({
        'available': camera_available,
        'stream_url': '/video_feed' if camera_available else None
    })

@app.route('/camera/toggle')
def toggle_camera():
    """Toggle camera on/off"""
    global camera_available
    camera_available = not camera_available
    return jsonify({'available': camera_available})

@app.route('/api/power', methods=['POST'])
def power_action():
    """Run one of the two explicit system power actions from the dashboard."""
    payload = request.get_json(silent=True) or {}
    action = payload.get('action')
    commands = {
        'restart': ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'reboot'],
        'shutdown': ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'poweroff'],
    }
    command = commands.get(action)
    if command is None:
        return jsonify({'error': 'Unsupported power action'}), 400

    try:
        # Check the authorization result before replying, otherwise the UI can
        # say "Shutting down" forever when systemd rejects the request.
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"[ERROR]: Unable to {action}: {error}", flush=True)
        return jsonify({'error': f'Unable to {action}'}), 500
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        print(f"[ERROR]: Unable to {action}: {detail}", flush=True)
        return jsonify({'error': f'Unable to {action}'}), 500

    return jsonify({'status': 'accepted', 'action': action})

# --- MAIN DASHBOARD HTML ---
@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>⚡ Holographic Power Monitor</title>
        <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
        <style>
            /* ... (same styles as before, keep all) ... */
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background: #020812;
                color: #ffffff;
                overflow: hidden;
                font-family: 'Share Tech Mono', monospace;
                height: 100vh;
                width: 100vw;
            }
            
            #plot-div {
                width: 100vw;
                height: 100vh;
                position: fixed;
                top: 0;
                left: 0;
                z-index: 1;
            }
            
            [hidden] { display: none !important; }
            #camera-player {
                position: absolute; inset: 0; overflow: hidden;
                border-radius: inherit;
            }
            #camera-feed {
                position: absolute; inset: 0; display: block;
                width: 100%; height: 100%; object-fit: cover; object-position: center;
            }
            .camera-controls {
                display: flex; flex-wrap: wrap; flex-shrink: 0;
                position: relative; z-index: 1;
                gap: 12px; margin-top: auto; padding-top: 12px;
            }
            .camera-controls button {
                background: #051220; color: #00eeff; border: 1px solid #00eeff45;
                border-radius: 8px; padding: 12px 16px; cursor: pointer; font: inherit;
            }
            .camera-controls button:focus-visible { outline: 2px solid #00eeff; }
            .camera-controls button:disabled { opacity: .4; cursor: default; }

            @keyframes pulse-dot {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.3; transform: scale(0.8); }
            }
            
            /* ---------- HUD (existing) ---------- */
            .hud-container {
                position: fixed;
                bottom: 30px;
                left: 30px;
                right: 30px;
                z-index: 10;
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
                gap: 15px;
                pointer-events: none;
            }
            
            .hud-panel {
                background: rgba(2, 8, 18, 0.75);
                backdrop-filter: blur(20px) saturate(1.5);
                -webkit-backdrop-filter: blur(20px) saturate(1.5);
                border: 1px solid rgba(0, 238, 255, 0.15);
                border-radius: 12px;
                padding: 16px 20px;
                pointer-events: auto;
                flex: 1;
                min-width: 150px;
                box-shadow: 
                    0 0 30px rgba(0, 238, 255, 0.03),
                    inset 0 0 30px rgba(0, 238, 255, 0.03);
                transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            }
            
            .hud-panel:hover {
                border-color: rgba(0, 238, 255, 0.4);
                box-shadow: 
                    0 0 50px rgba(0, 238, 255, 0.08),
                    inset 0 0 50px rgba(0, 238, 255, 0.05);
                transform: translateY(-3px);
            }
            
            .hud-title {
                font-family: 'Orbitron', sans-serif;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 3px;
                color: rgba(0, 238, 255, 0.5);
                text-transform: uppercase;
                margin-bottom: 8px;
                text-shadow: 0 0 20px rgba(0, 238, 255, 0.1);
            }
            
            .hud-title .glow {
                color: #00ffff;
                text-shadow: 0 0 20px rgba(0, 238, 255, 0.3);
            }
            
            .metric-container {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
            }
            
            .metric-label {
                font-size: 10px;
                color: rgba(255, 255, 255, 0.4);
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            
            .metric-value {
                font-family: 'Orbitron', sans-serif;
                font-size: 22px;
                font-weight: 900;
                letter-spacing: 1px;
                transition: all 0.3s ease;
            }
            
            .metric-unit {
                font-size: 12px;
                font-weight: 700;
                color: rgba(255, 255, 255, 0.5);
                margin-left: 2px;
            }
            
            .color-voltage { color: #ff8800; text-shadow: 0 0 20px rgba(255, 136, 0, 0.3); }
            .color-current { color: #00ffff; text-shadow: 0 0 20px rgba(0, 238, 255, 0.3); }
            .color-power { color: #ff00ff; text-shadow: 0 0 20px rgba(255, 0, 255, 0.3); }
            
            .bar-container {
                margin-top: 6px;
                height: 2px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 2px;
                overflow: hidden;
                position: relative;
            }
            
            .bar-fill {
                height: 100%;
                border-radius: 2px;
                transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1);
                position: relative;
            }
            
            .bar-voltage { background: linear-gradient(90deg, #ff4400, #ff8800, #ffcc00); }
            .bar-current { background: linear-gradient(90deg, #0044ff, #00ffff, #00ff88); }
            .bar-power { background: linear-gradient(90deg, #ff00ff, #ff00aa, #ff4400); }
            
            .bar-fill::after {
                content: '';
                position: absolute;
                top: -2px;
                bottom: -2px;
                left: 0;
                right: 0;
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
                animation: shimmer 2s infinite;
            }
            
            @keyframes shimmer {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(100%); }
            }
            
            .status-container {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-top: 10px;
                padding-top: 10px;
                border-top: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            .status-dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: #00ff88;
                box-shadow: 0 0 15px rgba(0, 255, 136, 0.5);
                animation: pulse-dot 2s infinite;
            }
            
            .status-dot.mocked {
                background: #ff8800;
                box-shadow: 0 0 15px rgba(255, 136, 0, 0.5);
            }
            
            .status-text {
                font-size: 9px;
                letter-spacing: 2px;
                color: rgba(255, 255, 255, 0.3);
            }
            
            .status-text .highlight {
                color: #00ff88;
                font-weight: 700;
            }
            
            .status-text .highlight.mocked {
                color: #ff8800;
            }
            
            .runtime {
                font-size: 9px;
                color: rgba(255, 255, 255, 0.2);
                letter-spacing: 1px;
                margin-left: auto;
                font-family: 'Orbitron', sans-serif;
            }
            
            @media (max-width: 850px), (max-height: 600px) {
                
                .hud-container {
                    bottom: 15px;
                    left: 15px;
                    right: 15px;
                    flex-wrap: wrap;
                    gap: 8px;
                }
                
                .hud-panel {
                    padding: 10px 14px;
                    min-width: 100px;
                    flex: 1;
                }
                
                .metric-value {
                    font-size: 16px;
                }
                
                .hud-title {
                    font-size: 7px;
                    margin-bottom: 4px;
                }
                
                .metric-label {
                    font-size: 8px;
                }
                
                .metric-unit {
                    font-size: 10px;
                }
                
                .status-container {
                    margin-top: 6px;
                    padding-top: 6px;
                }
                
                .status-text {
                    font-size: 7px;
                }
            }
            
            @media (max-width: 500px) {
                .hud-container {
                    flex-direction: column;
                    bottom: 10px;
                    left: 10px;
                    right: 10px;
                }
                
                .hud-panel {
                    width: 100%;
                }
                
            }
            :root { --dock-space: 88px; }
            .app-dock {
                position: fixed; left: 12px; top: 50%; transform: translateY(-50%);
                z-index: 50; display: flex; flex-direction: column; gap: 10px;
                padding: 10px; background: rgba(5, 18, 32, .94);
                border: 1px solid rgba(0, 238, 255, .25); border-radius: 20px;
                box-shadow: 0 12px 40px #0008;
            }
            .dock-item {
                display: grid; place-items: center; width: 44px; height: 48px;
                border: 1px solid transparent; border-radius: 12px;
                background: transparent; color: #8aa4b8; cursor: pointer;
            }
            .dock-item svg { width: 23px; height: 23px; }
            .dock-item:hover, .dock-item[aria-current="page"] {
                color: #00eeff; background: #00eeff14; border-color: #00eeff45;
            }
            .dock-item.power-item { color: #ff6688; }
            .dock-item.power-item:hover { color: #ff6688; background: #ff668814; border-color: #ff668845; }
            .dock-item:focus-visible { outline: 2px solid #00eeff; outline-offset: 3px; }
            .dock-item:disabled { opacity: .3; cursor: default; background: none; border-color: transparent; }
            #plot-div { left: var(--dock-space); width: calc(100vw - var(--dock-space)); }
            .hud-container { left: calc(var(--dock-space) + 12px); }
            #camera-view {
                position: fixed; inset: 24px 24px 24px calc(var(--dock-space) + 12px);
                padding: 24px; border: 1px solid #00eeff30; border-radius: 18px;
                background: #051220; display: flex; flex-direction: column; z-index: 2;
            }
            #camera-view h1, #camera-message {
                position: relative; z-index: 1; align-self: flex-start;
                background: #051220e6; padding: 6px 10px; border-radius: 6px;
            }
            #camera-view h1 { flex-shrink: 0; font-family: 'Orbitron', sans-serif; font-size: 18px; color: #00eeff; }
            #camera-message { flex-shrink: 0; margin: 12px 0; color: #8aa4b8; line-height: 1.6; }
            body[data-view="camera"] #plot-div,
            body[data-view="camera"] .hud-container { visibility: hidden; pointer-events: none; }
            @media (max-width: 500px) {
                :root { --dock-space: 72px; }
                .app-dock { left: 6px; padding: 6px; gap: 8px; }
                #camera-view { inset: 12px 12px 12px calc(var(--dock-space) + 6px); padding: 16px; }
            }

            .power-modal[hidden] { display: none; }
            .power-modal {
                position: fixed; inset: 0; z-index: 100; display: grid; place-items: center;
                padding: 24px; background: rgba(0, 0, 0, .62); backdrop-filter: blur(6px);
            }
            .power-dialog {
                width: min(360px, 100%); padding: 24px; border: 1px solid #ff668866;
                border-radius: 16px; background: #071321f5; box-shadow: 0 18px 60px #000b;
                text-align: center;
            }
            .power-dialog h2 {
                color: #ff6688; font: 700 18px 'Orbitron', sans-serif;
                letter-spacing: 2px; margin-bottom: 10px;
            }
            .power-dialog p { color: #9bb0bf; font-size: 12px; margin-bottom: 20px; }
            .power-actions { display: grid; gap: 10px; }
            .power-actions button {
                min-height: 44px; border: 1px solid #ff668866; border-radius: 8px;
                background: #ff668812; color: #ffb3c4; cursor: pointer; font: inherit;
            }
            .power-actions button:hover, .power-actions button:focus-visible {
                background: #ff66882b; border-color: #ff6688; outline: none;
            }
            .power-actions .cancel { color: #9bb0bf; border-color: #9bb0bf44; background: transparent; }
            .power-actions .cancel:hover, .power-actions .cancel:focus-visible { border-color: #9bb0bf; background: #9bb0bf12; }
            .power-status { min-height: 16px; margin: 14px 0 0; color: #ffb3c4; font-size: 11px; }
        </style>
    </head>
    <body data-view="home">
        <nav class="app-dock" aria-label="Main navigation">
            <a class="dock-item" href="#home" aria-label="Home" title="Home" aria-current="page" data-view="home">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9"/></svg>
            </a>
            <a class="dock-item" href="#camera" aria-label="Camera" title="Camera" data-view="camera">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M3 7h4l2-3h6l2 3h4v13H3z"/><circle cx="12" cy="13" r="4"/></svg>
            </a>
            <button class="dock-item" disabled aria-label="Apps — coming soon" title="Apps — coming soon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            </button>
            <button class="dock-item power-item" type="button" aria-label="Power options" title="Power options" onclick="openPowerMenu()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M12 3v8"/><path d="M6.2 6.2a8 8 0 1 0 11.6 0"/></svg>
            </button>
        </nav>
        <div id="power-modal" class="power-modal" role="presentation" hidden>
            <div class="power-dialog" role="dialog" aria-modal="true" aria-labelledby="power-heading">
                <h2 id="power-heading">POWER OPTIONS</h2>
                <p>Choose an action for this system.</p>
                <div class="power-actions">
                    <button type="button" onclick="runPowerAction('restart')">Restart</button>
                    <button type="button" onclick="runPowerAction('shutdown')">Shutdown</button>
                    <button type="button" class="cancel" onclick="closePowerMenu()">Cancel</button>
                </div>
                <p id="power-status" class="power-status" role="status" aria-live="polite"></p>
            </div>
        </div>
        <section id="camera-view" aria-labelledby="camera-heading" hidden>
            <h1 id="camera-heading">Camera</h1>
            <p id="camera-message" role="status">Select Camera to start the live view.</p>
            <div id="camera-player" hidden>
                <img id="camera-feed" alt="Live camera feed">
            </div>
            <div class="camera-controls">
                <button id="camera-pause" type="button" onclick="toggleCamera()" disabled>Pause</button>
                <button type="button" onclick="initCamera()">Retry connection</button>
            </div>
        </section>
        <!-- 3D Visualization -->
        <div id="plot-div"></div>
        
        <!-- HUD (existing) -->
        <div class="hud-container">
            <div class="hud-panel">
                <div class="hud-title">⚡ <span class="glow">VOLTAGE</span></div>
                <div class="metric-container">
                    <span class="metric-label">SYSTEM</span>
                    <span>
                        <span id="val-voltage" class="metric-value color-voltage">0.00</span>
                        <span class="metric-unit">V</span>
                    </span>
                </div>
                <div class="bar-container">
                    <div id="bar-voltage" class="bar-fill bar-voltage" style="width: 0%"></div>
                </div>
            </div>
            
            <div class="hud-panel">
                <div class="hud-title">⚡ <span class="glow">CURRENT</span></div>
                <div class="metric-container">
                    <span class="metric-label">FLOW</span>
                    <span>
                        <span id="val-current" class="metric-value color-current">0.00</span>
                        <span class="metric-unit">A</span>
                    </span>
                </div>
                <div class="bar-container">
                    <div id="bar-current" class="bar-fill bar-current" style="width: 0%"></div>
                </div>
            </div>
            
            <div class="hud-panel">
                <div class="hud-title">⚡ <span class="glow">POWER</span></div>
                <div class="metric-container">
                    <span class="metric-label">DRAW</span>
                    <span>
                        <span id="val-power" class="metric-value color-power">0.00</span>
                        <span class="metric-unit">W</span>
                    </span>
                </div>
                <div class="bar-container">
                    <div id="bar-power" class="bar-fill bar-power" style="width: 0%"></div>
                </div>
                
                <div class="status-container">
                    <div id="status-dot" class="status-dot"></div>
                    <span class="status-text">
                        MODE: <span id="mode-text" class="highlight">MOCKED</span>
                    </span>
                    <span class="runtime" id="run-time">00:00</span>
                </div>
            </div>
        </div>

        <script>
            const startTime = Date.now();
            let graphDiv = document.getElementById('plot-div');
            let currentData = { time: [], voltage: [], amps: [] };
            let cameraActive = false;
            let cameraRequest = 0;
            const powerModal = document.getElementById('power-modal');
            const powerStatus = document.getElementById('power-status');
            
            // --- SCI-FI COLORS ---
            const colors = {
                voltage: [
                    [0, '#ff0055'],
                    [0.3, '#ff4400'],
                    [0.5, '#ffaa00'],
                    [0.7, '#00ff88'],
                    [1, '#00eeff']
                ],
                glow: [
                    [0, 'rgba(255,0,85,0.05)'],
                    [0.5, 'rgba(0,255,136,0.08)'],
                    [1, 'rgba(0,238,255,0.05)']
                ],
                particles: [
                    [0, '#ff0055'],
                    [0.5, '#ff8800'],
                    [1, '#00ffff']
                ]
            };
            
            function navigate() {
                const view = location.hash === '#camera' ? 'camera' : 'home';
                document.body.dataset.view = view;
                document.getElementById('camera-view').hidden = view !== 'camera';
                document.querySelectorAll('.dock-item[data-view]').forEach(item => {
                    if (item.dataset.view === view) item.setAttribute('aria-current', 'page');
                    else item.removeAttribute('aria-current');
                });
                stopCamera();
                if (view === 'camera') initCamera();
                if (view === 'home' && window.Plotly && graphDiv.data) {
                    requestAnimationFrame(() => Plotly.Plots.resize(graphDiv));
                }
            }
            window.addEventListener('hashchange', navigate);

            function openPowerMenu() {
                powerStatus.textContent = '';
                powerModal.hidden = false;
                powerModal.querySelector('button').focus();
            }

            function closePowerMenu() {
                powerModal.hidden = true;
            }

            powerModal.addEventListener('click', (event) => {
                if (event.target === powerModal) closePowerMenu();
            });
            document.addEventListener('keydown', (event) => {
                if (event.key === 'Escape' && !powerModal.hidden) closePowerMenu();
            });

            async function runPowerAction(action) {
                const buttons = powerModal.querySelectorAll('button');
                buttons.forEach(button => button.disabled = true);
                powerStatus.textContent = action === 'restart' ? 'Restarting system…' : 'Shutting down system…';
                try {
                    const response = await fetch('/api/power', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({action})
                    });
                    if (!response.ok) throw new Error('Power action failed');
                } catch (error) {
                    buttons.forEach(button => button.disabled = false);
                    powerStatus.textContent = `Unable to ${action}. Check system permissions.`;
                }
            }

            // --- CAMERA FUNCTIONS ---
            function stopCamera() {
                cameraRequest++;
                cameraActive = false;
                document.getElementById('camera-feed').removeAttribute('src');
                document.getElementById('camera-player').hidden = true;
                document.getElementById('camera-pause').disabled = true;
            }

            function cameraError(message) {
                stopCamera();
                document.getElementById('camera-message').textContent = message;
            }

            async function initCamera() {
                stopCamera();
                const request = cameraRequest;
                document.getElementById('camera-message').textContent = 'Checking camera connection…';
                try {
                    const response = await fetch('/camera_status', {cache: 'no-store'});
                    if (!response.ok) throw new Error('Camera status failed');
                    const data = await response.json();
                    if (request !== cameraRequest || document.body.dataset.view !== 'camera') return;
                    if (!data.available) {
                        cameraError('Camera unavailable. Check the USB connection, then tap Retry connection.');
                        return;
                    }
                    cameraActive = true;
                    document.getElementById('camera-player').hidden = false;
                    document.getElementById('camera-pause').disabled = false;
                    document.getElementById('camera-pause').textContent = 'Pause';
                    document.getElementById('camera-message').textContent = 'Streaming camera';
                    document.getElementById('camera-feed').src = '/video_feed';
                } catch (error) {
                    if (request !== cameraRequest || document.body.dataset.view !== 'camera') return;
                    cameraError('Unable to check the camera. Use Retry connection to try again.');
                }
            }

            document.getElementById('camera-feed').addEventListener('error', () => {
                if (cameraActive) cameraError('Camera stream interrupted. Use Retry connection to try again.');
            });

            function toggleCamera() {
                if (!cameraActive) {
                    initCamera();
                    return;
                }
                stopCamera();
                document.getElementById('camera-message').textContent = 'Camera paused';
                document.getElementById('camera-pause').disabled = false;
                document.getElementById('camera-pause').textContent = 'Resume';
            }

            // --- CREATE GRAPH ---
            function createGraph(timeData, voltageData, currentData) {
                function smooth(data, window = 3) {
                    const result = [];
                    for (let i = 0; i < data.length; i++) {
                        let start = Math.max(0, i - window);
                        let end = Math.min(data.length, i + window + 1);
                        let sum = 0;
                        for (let j = start; j < end; j++) {
                            sum += data[j];
                        }
                        result.push(sum / (end - start));
                    }
                    return result;
                }
                
                const shimmer = timeData.map(t => 0.02 * Math.sin(t * 2.0));
                const vSmooth = smooth(voltageData, 2);
                const iSmooth = smooth(currentData, 2);
                const vGlow = vSmooth.map((v, i) => v + shimmer[i] * 0.1);
                const iGlow = iSmooth.map((i, idx) => i + shimmer[idx] * 0.05);
                
                const mainTrace = {
                    x: iGlow,
                    y: vGlow,
                    z: timeData,
                    mode: 'lines',
                    type: 'scatter3d',
                    line: {
                        width: 8,
                        color: vGlow,
                        colorscale: colors.voltage,
                        cmin: 10.0,
                        cmax: 12.6,
                        showscale: true,
                        colorbar: {
                            title: 'VOLTAGE',
                            titleside: 'right',
                            titlefont: { color: '#00ffff', size: 10, family: 'Orbitron' },
                            tickfont: { color: '#00ffff', size: 8 },
                            bgcolor: 'rgba(0,0,0,0)',
                            thickness: 12,
                            len: 0.7,
                            x: 1.02
                        }
                    },
                    name: 'Energy Stream'
                };
                
                const glowTrace = {
                    x: iGlow,
                    y: vGlow,
                    z: timeData,
                    mode: 'lines',
                    type: 'scatter3d',
                    line: {
                        width: 25,
                        color: vGlow,
                        colorscale: colors.glow,
                        cmin: 10.0,
                        cmax: 12.6,
                        showscale: false
                    },
                    opacity: 0.3,
                    name: 'Energy Glow'
                };
                
                const particleTrace = {
                    x: iGlow.map((v, i) => v + (Math.random() - 0.5) * 0.04),
                    y: vGlow.map((v, i) => v + (Math.random() - 0.5) * 0.04),
                    z: timeData.map((v, i) => v + (Math.random() - 0.5) * 0.2),
                    mode: 'markers',
                    type: 'scatter3d',
                    marker: {
                        size: 3 + Math.random() * 2,
                        color: vGlow,
                        colorscale: colors.particles,
                        cmin: 10.0,
                        cmax: 12.6,
                        showscale: false,
                        opacity: 0.5,
                        symbol: 'circle'
                    },
                    name: 'Particles'
                };
                
                const currentPos = {
                    x: [iGlow[iGlow.length - 1]],
                    y: [vGlow[vGlow.length - 1]],
                    z: [timeData[timeData.length - 1]],
                    mode: 'markers',
                    type: 'scatter3d',
                    marker: {
                        size: 25,
                        color: '#ffffff',
                        symbol: 'circle',
                        line: {
                            color: '#00ffff',
                            width: 4
                        },
                        opacity: 0.9
                    },
                    name: 'Current Position'
                };
                
                const outerGlow = {
                    x: [iGlow[iGlow.length - 1]],
                    y: [vGlow[vGlow.length - 1]],
                    z: [timeData[timeData.length - 1]],
                    mode: 'markers',
                    type: 'scatter3d',
                    marker: {
                        size: 50,
                        color: 'rgba(0, 238, 255, 0.12)',
                        symbol: 'circle',
                        line: {
                            color: 'rgba(0, 238, 255, 0.2)',
                            width: 2
                        },
                        opacity: 0.4
                    },
                    name: 'Energy Field'
                };
                
                return {
                    data: [mainTrace, glowTrace, particleTrace, currentPos, outerGlow],
                    layout: {
                        template: 'plotly_dark',
                        scene: {
                            xaxis: {
                                title: '<b>AMPERAGE</b> (A)',
                                titlefont: { color: '#00ffff', size: 12, family: 'Orbitron' },
                                tickfont: { color: '#00ffff', size: 9, family: 'Share Tech Mono' },
                                gridcolor: 'rgba(0, 238, 255, 0.08)',
                                gridwidth: 1,
                                zerolinecolor: 'rgba(0, 238, 255, 0.15)',
                                zerolinewidth: 1,
                                showbackground: true,
                                backgroundcolor: 'rgba(2, 8, 18, 0.9)',
                                color: '#00ffff',
                                range: [-2, 12]
                            },
                            yaxis: {
                                title: '<b>VOLTAGE</b> (V)',
                                titlefont: { color: '#ff8800', size: 12, family: 'Orbitron' },
                                tickfont: { color: '#ff8800', size: 9, family: 'Share Tech Mono' },
                                gridcolor: 'rgba(255, 136, 0, 0.08)',
                                gridwidth: 1,
                                zerolinecolor: 'rgba(255, 136, 0, 0.15)',
                                zerolinewidth: 1,
                                showbackground: true,
                                backgroundcolor: 'rgba(2, 8, 18, 0.9)',
                                color: '#ff8800',
                                range: [9.5, 13.5]
                            },
                            zaxis: {
                                title: '<b>TIME</b> (s)',
                                titlefont: { color: '#ffffff', size: 12, family: 'Orbitron' },
                                tickfont: { color: '#ffffff', size: 9, family: 'Share Tech Mono' },
                                gridcolor: 'rgba(255, 255, 255, 0.05)',
                                gridwidth: 1,
                                showbackground: true,
                                backgroundcolor: 'rgba(2, 8, 18, 0.9)',
                                color: '#ffffff',
                                range: [Math.max(...timeData) + 1, Math.min(...timeData) - 1]
                            },
                            camera: {
                                eye: { x: 1.8, y: 1.4, z: 1.2 },
                                up: { x: 0, y: 0, z: 1 },
                                center: { x: 0, y: 0, z: 0 }
                            },
                            lighting: {
                                ambient: 0.8,
                                diffuse: 0.3,
                                roughness: 0.2,
                                fresnel: 0.5
                            }
                        },
                        paper_bgcolor: 'rgba(2, 8, 18, 1)',
                        plot_bgcolor: 'rgba(2, 8, 18, 1)',
                        margin: { l: 0, r: 0, t: 0, b: 0 },
                        legend: {
                            font: { color: '#00ffff', family: 'Share Tech Mono', size: 9 },
                            bgcolor: 'rgba(2, 8, 18, 0.7)',
                            borderwidth: 1,
                            bordercolor: 'rgba(0, 238, 255, 0.2)'
                        },
                        hovermode: 'closest'
                    }
                };
            }
            
            // --- UPDATE GRAPH ---
            function updateGraph() {
                fetch('/api_graph')
                    .then(res => res.json())
                    .then(data => {
                        if (data.time && data.time.length > 2) {
                            currentData = data;
                            const graphData = createGraph(data.time, data.voltage, data.amps);
                            Plotly.react('plot-div', graphData.data, graphData.layout);
                        }
                    })
                    .catch(err => console.error('Graph error:', err));
            }
            
            // --- UPDATE HUD ---
            function updateHUD() {
                fetch('/api_data')
                    .then(res => res.json())
                    .then(data => {
                        const v = parseFloat(data.voltage);
                        const a = parseFloat(data.amps);
                        const w = parseFloat((v * a).toFixed(2));
                        
                        document.getElementById('val-voltage').textContent = v.toFixed(2);
                        document.getElementById('val-current').textContent = a.toFixed(2);
                        document.getElementById('val-power').textContent = w.toFixed(2);
                        
                        const vPercent = Math.min(100, Math.max(0, (v / 15.0) * 100));
                        const aPercent = Math.min(100, Math.max(0, (a / 10.0) * 100));
                        const wPercent = Math.min(100, Math.max(0, (w / 120.0) * 100));
                        
                        document.getElementById('bar-voltage').style.width = vPercent + '%';
                        document.getElementById('bar-current').style.width = aPercent + '%';
                        document.getElementById('bar-power').style.width = wPercent + '%';
                        
                        const modeText = document.getElementById('mode-text');
                        const statusDot = document.getElementById('status-dot');
                        
                        if (data.mode === 'ACTIVE') {
                            modeText.textContent = 'ACTIVE';
                            modeText.className = 'highlight';
                            statusDot.className = 'status-dot';
                        } else {
                            modeText.textContent = 'MOCKED';
                            modeText.className = 'highlight mocked';
                            statusDot.className = 'status-dot mocked';
                        }
                        
                        const elapsed = Math.floor((Date.now() - startTime) / 1000);
                        const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
                        const s = String(elapsed % 60).padStart(2, '0');
                        document.getElementById('run-time').textContent = m + ':' + s;
                    })
                    .catch(err => console.error('HUD error:', err));
            }
            
            // --- INITIALIZE ---
            navigate();
            updateGraph();
            updateHUD();
            
            // --- POLLING ---
            setInterval(updateHUD, 1000);
            setInterval(updateGraph, 2000);
            
            // --- RESIZE ---
            window.addEventListener('resize', () => {
                if (document.body.dataset.view === 'home' && window.Plotly && graphDiv.data) {
                    Plotly.Plots.resize(graphDiv);
                }
            });
            
            console.log('⚡ Holographic Dashboard with Embedded Camera initialized');
        </script>
    </body>
    </html>
    """)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n[INFO]: ⚡ Sci-Fi Holographic Dashboard with Embedded Camera")
    print(f"Dashboard running at: http://localhost:{port}")
    
    if camera_available:
        print(f"📹 Camera feed: http://localhost:{port}/video_feed")
        print("   Select Camera in the left navigation to view the embedded feed.")
    else:
        print(f"📹 No camera detected - Camera page will show connection instructions")
        print("   To use camera: plug in USB camera and restart")
    
    print("\nPress Ctrl+C to stop\n")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        if camera is not None:
            camera.release()
        print("✅ Camera released")
