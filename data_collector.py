# -*- coding: utf-8 -*-
"""
ESP32-CAM + Sensor + Full Base64 Image Collector + Flask Dashboard
--------------------------------------------------------------------
Features:
 - Collects temperature, humidity, gas, and Base64 images over MQTT
 - Saves data to esp32_data.csv
 - Stores images in /images/
 - Displays the latest records and images via a Flask dashboard
"""
import cv2
import numpy as np
from flask import Flask, jsonify, send_from_directory
import threading
import paho.mqtt.client as mqtt
import pandas as pd
import base64
import os
import time
import threading

from banana_detector import detect_banana_and_avg_color

# -------------------------------
# Configuration
# -------------------------------
DATA_FILE = "esp32_data.csv"
IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "fruiture/#"  # subscribe to all topics under fruiture

# -------------------------------
# Prepare CSV file
# -------------------------------
if not os.path.exists(DATA_FILE):
    pd.DataFrame(columns=["timestamp", "temperature", "humidity", "gas", "image_path"]).to_csv(DATA_FILE, index=False)

# -------------------------------
# Temporary storage for current entry
# -------------------------------
current_entry = {
    "timestamp": None,
    "temperature": None,
    "humidity": None,
    "gas": None,
    "image_path": None
}
entry_lock = threading.Lock()

# -------------------------------
# MQTT Callbacks
# -------------------------------
def on_connect(client, userdata, flags, rc):
    print("✅ Connected to MQTT broker with result code:", rc)
    client.subscribe(MQTT_TOPIC)
    print(f"📡 Subscribed to topic: {MQTT_TOPIC}")

# -------------------------------
# MQTT on_message (update fields under lock)
# -------------------------------
def on_message(client, userdata, message):
    global current_entry

    topic = message.topic
    payload = message.payload.decode("utf-8", errors="ignore")
    print(f"📥 Received from '{topic}': {payload[:80]}...")

    try:
        with entry_lock:
            # update timestamp whenever any new data arrives
            current_entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Sensor fields
            if "temp" in topic.lower():
                current_entry["temperature"] = float(payload)
            elif "hum" in topic.lower():
                current_entry["humidity"] = float(payload)
            elif "gas" in topic.lower():
                current_entry["gas"] = float(payload)

            # Full Base64 image
            elif "base64image" in topic.lower():
                img_data = base64.b64decode(payload)
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                vis, mean_rgb = detect_banana_and_avg_color(img)

                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

                filename = f"processed_img_{timestamp}.png"
                path = os.path.join(IMAGE_DIR, filename)
                with open(path, "wb") as f:
                    f.write(vis)
                print(f"📸 Saved image: {path} ({len(vis)} bytes)")
                current_entry["processed_image_path"] = filename

                current_entry["rgb"] = mean_rgb

                filename = f"img_{timestamp}.jpg"
                path = os.path.join(IMAGE_DIR, filename)
                with open(path, "wb") as f:
                    f.write(img_data)
                print(f"📸 Saved image: {path} ({len(img_data)} bytes)")
                current_entry["image_path"] = filename

            # After updating, check if entry is complete
            check_and_save_entry()

    except Exception as e:
        print("❌ Error processing message:", e)


# -------------------------------
# Replace previous save function with this: only save when all fields present
# -------------------------------
def check_and_save_entry():
    """Save current_entry only when ALL required fields are present."""
    global current_entry
    required_keys = ["timestamp", "temperature", "humidity", "gas", "image_path"]

    # Caller must hold entry_lock when invoking if calling from elsewhere;
    # here we grab it defensively if not already locked.
    lock_acquired = entry_lock.acquire(blocking=False)
    if lock_acquired:
        try:
            ready = all(current_entry.get(k) is not None for k in required_keys)
            if not ready:
                return  # not complete yet
            # Save
            try:
                df = pd.read_csv(DATA_FILE)
            except FileNotFoundError:
                df = pd.DataFrame(columns=["timestamp", "temperature", "humidity", "gas", "image_path"])

            df = pd.concat([df, pd.DataFrame([current_entry])], ignore_index=True)
            df.to_csv(DATA_FILE, index=False)
            print(f"✅ Saved COMPLETE record: {current_entry}")

            # Reset entry for next batch
            current_entry = {k: None for k in current_entry}

        finally:
            entry_lock.release()
    else:
        # If lock is already held by caller (normal path), do the check & save under that lock:
        ready = all(current_entry.get(k) is not None for k in required_keys)
        if not ready:
            return
        try:
            df = pd.read_csv(DATA_FILE)
        except FileNotFoundError:
            df = pd.DataFrame(columns=["timestamp", "temperature", "humidity", "gas", "image_path"])

        df = pd.concat([df, pd.DataFrame([current_entry])], ignore_index=True)
        df.to_csv(DATA_FILE, index=False)
        print(f"✅ Saved COMPLETE record: {current_entry}")
        current_entry = {k: None for k in current_entry}

# -------------------------------
# MQTT Background Thread
# -------------------------------
def run_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            print("⚠️ MQTT disconnected, retrying in 5s:", e)
            time.sleep(5)

# -------------------------------
# Flask Dashboard
# -------------------------------
app = Flask(__name__)

@app.route("/data")
def get_data():
    df = pd.read_csv(DATA_FILE)
    return jsonify(df.tail(10).to_dict(orient="records"))

@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/")
def index():
    df = pd.read_csv(DATA_FILE)
    rows = df.tail(10).to_dict(orient="records")
    html = """
    <html><head><title>ESP32-CAM + Sensor Dashboard</title></head>
    <body style='font-family:Arial; text-align:center; background:#f9f9f9;'>
      <h2>📊 ESP32-CAM + Sensor Dashboard</h2>
    """
    for r in reversed(rows):
        html += "<div style='margin:20px; border:1px solid #ccc; padding:10px; background:white;'>"
        html += f"<p><b>{r['timestamp']}</b><br>"
        html += f"🌡️ Temp: {r.get('temperature','')}°C | 💧 Hum: {r.get('humidity','')}% | 🧪 Gas: {r.get('gas','')}</p>"
        if r.get("image_path"):
            html += f"<img src='/images/{r['image_path']}' width='320'><br>"
        html += "</div>"
    html += "</body></html>"
    return html

# -------------------------------
# Main Entry
# -------------------------------
if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=run_mqtt, daemon=True)
    mqtt_thread.start()
    print("🚀 Combined MQTT collector + dashboard running at http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
