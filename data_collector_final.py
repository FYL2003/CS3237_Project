# -*- coding: utf-8 -*-
import cv2
import numpy as np
from flask import Flask, jsonify, send_from_directory
import threading
import paho.mqtt.client as mqtt
import pandas as pd
import base64
import os
import time
import re
import json
from datetime import datetime
import joblib

from banana_detector_no_grey import detect_banana_ultimate  # <-- your existing detector

# -------------------------------
# Configuration
# -------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "esp32_data.csv")
SENSOR_LOG = os.path.join(BASE_DIR, "sensor_log.csv")
IMAGE_DIR = os.path.join(BASE_DIR, "images")
ML_JSON = os.path.join(BASE_DIR, "ml_input.json")
ML_HISTORY = os.path.join(BASE_DIR, "ml_input_history.csv")
os.makedirs(IMAGE_DIR, exist_ok=True)

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "fruiture/#"

print("📁 Image folder:", IMAGE_DIR)
print("📄 Main CSV file:", DATA_FILE)
print("📄 Continuous log file:", SENSOR_LOG)
print("📄 ML summary history:", ML_HISTORY)

# -------------------------------
# Prepare CSV files
# -------------------------------
if not os.path.exists(DATA_FILE):
    pd.DataFrame(columns=[
        "timestamp", "temperature", "humidity", "gas",
        "ripeness", "avg_R", "avg_G", "avg_B",
        "green_%", "yellow_%", "brown_%", "black_%",
        "image_path", "processed_image_path"
    ]).to_csv(DATA_FILE, index=False)

if not os.path.exists(SENSOR_LOG):
    pd.DataFrame(columns=["timestamp", "temperature", "humidity", "gas"]).to_csv(SENSOR_LOG, index=False)

if not os.path.exists(ML_HISTORY):
    pd.DataFrame(columns=[
        "timestamp", "record_count",
        "average_temperature", "average_humidity",
        "average_gas", "max_gas",
        "average_R", "average_G", "average_B",
        "predicted_day", "confidence", "servo_angle"
    ]).to_csv(ML_HISTORY, index=False)

# -------------------------------
# Global shared entry
# -------------------------------
current_entry = {
    "timestamp": None,
    "temperature": None,
    "humidity": None,
    "gas": None,
    "ripeness": None,
    "avg_R": None,
    "avg_G": None,
    "avg_B": None,
    "green_%": None,
    "yellow_%": None,
    "brown_%": None,
    "black_%": None,
    "image_path": None,
    "processed_image_path": None,
}
entry_lock = threading.Lock()

# -------------------------------
# MQTT Callbacks
# -------------------------------
def on_connect(client, userdata, flags, rc):
    print("✅ Connected to MQTT broker with result code:", rc)
    client.subscribe(MQTT_TOPIC)
    print(f"📡 Subscribed to topic: {MQTT_TOPIC}")

def on_message(client, userdata, message):
    global current_entry
    topic = message.topic
    payload = message.payload.decode("utf-8", errors="ignore")
    print(f"📥 Received from '{topic}': {payload[:80]}...")

    try:
        with entry_lock:
            current_entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

            sensor_updated = False
            if "temp" in topic.lower():
                match = re.search(r"[-+]?\d*\.?\d+", payload)
                if match:
                    current_entry["temperature"] = float(match.group())
                    sensor_updated = True

            elif "hum" in topic.lower():
                match = re.search(r"[-+]?\d*\.?\d+", payload)
                if match:
                    current_entry["humidity"] = float(match.group())
                    sensor_updated = True

            elif "rawgas" in topic.lower():
                match = re.search(r"[-+]?\d*\.?\d+", payload)
                if match:
                    current_entry["raw_gas"] = float(match.group())
                    print(f"🧪 Raw Gas (filtered): {current_entry['raw_gas']} ppm")
                    # You can choose to NOT mark this as sensor_updated, since you only want to view it
                    # sensor_updated = True  # uncomment if you want to log it to CSV
                    # (otherwise it just prints, not saved)

            elif "gas" in topic.lower() and "rawgas" not in topic.lower():
                match = re.search(r"[-+]?\d*\.?\d+", payload)
                if match:
                    current_entry["gas"] = float(match.group())
                    print(f"⚗️ Corrected Gas (after baseline): {current_entry['gas']} ppm")
                    sensor_updated = True



            if sensor_updated:
                log_sensor_data(current_entry)

            elif "base64image" in topic.lower():
                img_data = base64.b64decode(payload)
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    print("⚠️ Image decode failed.")
                    return

                vis, mean_rgb, ripeness, proportions = detect_banana_ultimate(img)
                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

                processed_filename = f"processed_{timestamp}.png"
                processed_path = os.path.join(IMAGE_DIR, processed_filename)
                cv2.imwrite(processed_path, vis)
                current_entry["processed_image_path"] = processed_filename

                raw_filename = f"raw_{timestamp}.jpg"
                raw_path = os.path.join(IMAGE_DIR, raw_filename)
                with open(raw_path, "wb") as f:
                    f.write(img_data)
                current_entry["image_path"] = raw_filename

                if mean_rgb:
                    current_entry["avg_R"] = mean_rgb[0]
                    current_entry["avg_G"] = mean_rgb[1]
                    current_entry["avg_B"] = mean_rgb[2]
                if ripeness is not None:
                    current_entry["ripeness"] = ripeness
                if proportions:
                    for color, value in proportions.items():
                        current_entry[f"{color}_%"] = value

            check_and_save_entry()

    except Exception as e:
        print("❌ Error processing message:", e)

# -------------------------------
# Continuous Sensor Logging
# -------------------------------
def log_sensor_data(entry):
    try:
        df = pd.DataFrame([{
            "timestamp": entry["timestamp"],
            "temperature": entry.get("temperature"),
            "humidity": entry.get("humidity"),
            "gas": entry.get("gas")
        }])
        df.to_csv(SENSOR_LOG, mode="a", header=False, index=False)
        print(f"📝 Logged continuous data at {entry['timestamp']}")
    except Exception as e:
        print("⚠️ Failed to log sensor data:", e)

# -------------------------------
# Save Complete Record
# -------------------------------
def check_and_save_entry():
    global current_entry
    required = ["timestamp", "temperature", "humidity", "gas", "image_path"]
    if not all(current_entry.get(k) is not None for k in required):
        return
    try:
        df = pd.read_csv(DATA_FILE)
    except FileNotFoundError:
        df = pd.DataFrame(columns=[
            "timestamp", "temperature", "humidity", "gas",
            "ripeness", "avg_R", "avg_G", "avg_B",
            "green_%", "yellow_%", "brown_%", "black_%",
            "image_path", "processed_image_path"
        ])
    df = pd.concat([df, pd.DataFrame([current_entry])], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)
    print(f"✅ Saved record: {current_entry['timestamp']} | Ripeness {current_entry.get('ripeness','?')}")
    current_entry = {k: None for k in current_entry}

# -------------------------------
# 10-Minute Summary Thread (with ML)
# -------------------------------
def periodic_summary_task():
    PUBLISH_INTERVAL = 600
    MQTT_TOPIC_SUMMARY = "fruiture/ml_input"
    MQTT_TOPIC_PREDICT = "fruiture/servo_angle"

    # Try to load model & scaler, but don't abort if missing
    model, scaler = None, None
    try:
        model = joblib.load(os.path.join(BASE_DIR, "banana_model.pkl"))
        scaler = joblib.load(os.path.join(BASE_DIR, "banana_scaler.pkl"))
        print("✅ ML model and scaler loaded.")
    except Exception as e:
        print("⚠️ ML model/scaler not loaded (will still publish summaries):", e)

    def safe_mean(df, col):
        if col in df.columns:
            try:
                return round(df[col].astype(float).mean(skipna=True), 3)
            except Exception:
                return None
        return None

    def safe_max(df, col):
        if col in df.columns:
            try:
                return round(df[col].astype(float).max(skipna=True), 3)
            except Exception:
                return None
        return None

    client = mqtt.Client()
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        print("❌ MQTT summary thread connection failed:", e)
        # Even if MQTT connect fails, we still compute JSON locally and retry next loop

    while True:
        try:
            if not os.path.exists(DATA_FILE):
                print("ℹ️ Waiting for esp32_data.csv to be created...")
                time.sleep(PUBLISH_INTERVAL)
                continue

            df = pd.read_csv(DATA_FILE)
            if df.empty:
                print("⚠️ esp32_data.csv is empty; no summary yet.")
                time.sleep(PUBLISH_INTERVAL)
                continue

            summary = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "record_count": int(len(df)),
                "average_temperature": safe_mean(df, "temperature"),
                "average_humidity": safe_mean(df, "humidity"),
                "average_gas": safe_mean(df, "gas"),
                "max_gas": safe_max(df, "gas"),
                "average_R": safe_mean(df, "avg_R"),
                "average_G": safe_mean(df, "avg_G"),
                "average_B": safe_mean(df, "avg_B"),
            }

            # Always save JSON + append history
            try:
                with open(ML_JSON, "w") as f:
                    json.dump(summary, f, indent=4)
                print(f"💾 Wrote {ML_JSON}")
            except Exception as e:
                print("❌ Failed to write ml_input.json:", e)

            try:
                pd.DataFrame([summary]).to_csv(ML_HISTORY, mode="a", header=not os.path.exists(ML_HISTORY) or os.path.getsize(ML_HISTORY) == 0, index=False)
                print(f"📝 Appended summary to {ML_HISTORY}")
            except Exception as e:
                print("❌ Failed to append to ml_input_history.csv:", e)

            # Publish summary (if MQTT is connected)
            try:
                client.publish(MQTT_TOPIC_SUMMARY, json.dumps(summary))
                print(f"📡 Published 10-min summary → {MQTT_TOPIC_SUMMARY}")
            except Exception as e:
                print("❌ Failed to publish summary MQTT:", e)

            # ---- Optional ML → Servo (only if model loaded) ----
            if (model is not None) and (scaler is not None):
                try:
                    X_input = pd.DataFrame([[
                        summary["max_gas"],
                        summary["average_gas"],
                        summary["average_temperature"],
                        summary["average_humidity"],
                        summary["average_R"],
                        summary["average_G"],
                        summary["average_B"]
                    ]], columns=[
                        "Max_gas_diff", "Average_gas_diff", "temperature",
                        "Humidity", "R", "G", "B"
                    ])

                    # If any are None, skip ML step this cycle
                    if X_input.isnull().any().any():
                        print("ℹ️ Missing summary fields for ML this cycle; skipping prediction.")
                    else:
                        X_scaled = scaler.transform(X_input)
                        prediction = int(model.predict(X_scaled)[0])
                        confidence = float(max(model.predict_proba(X_scaled)[0]))
                        servo_angle = int((prediction - 1) * 45)  # 1–5 → 0–180

                        payload = json.dumps({
                            "predicted_day": prediction,
                            "confidence": round(confidence, 3),
                            "servo_angle": servo_angle,
                            "timestamp": summary["timestamp"]
                        })

                        if confidence >= 0.7:
                            client.publish(MQTT_TOPIC_PREDICT, payload)
                            print(f"🤖 Predicted day {prediction} ({confidence*100:.1f}%) → Servo {servo_angle}°")
                        else:
                            print(f"⚠️ Low confidence ({confidence*100:.1f}%), skipping servo command.")
                except Exception as e:
                    print("⚠️ ML prediction failed:", e)

        except Exception as e:
            print("⚠️ Summary thread error:", e)

        print("⏳ Sleeping 10 minutes before next summary...\n")
        time.sleep(PUBLISH_INTERVAL)


# -------------------------------
# MQTT Thread
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
    <html><head><title>🍌 Fruiture Dashboard</title></head>
    <body style='font-family:Arial; text-align:center; background:#f9f9f9;'>
      <h2>📊 ESP32-CAM + Sensor + Banana Detector</h2>
    """
    for r in reversed(rows):
        html += "<div style='margin:20px; border:1px solid #ccc; padding:10px; background:white;'>"
        html += f"<p><b>{r['timestamp']}</b><br>"
        html += f"🌡️ Temp: {r.get('temperature','')}°C | 💧 Hum: {r.get('humidity','')}% | 🧪 Gas: {r.get('gas','')} ppm<br>"
        if r.get("ripeness") is not None:
            html += f"🍌 Ripeness: {r['ripeness']}/100<br>"
        if r.get("avg_R") is not None:
            html += f"🎨 RGB: ({r['avg_R']}, {r['avg_G']}, {r['avg_B']})<br>"
        html += f"🟩 {r.get('green_%','')}% 🟨 {r.get('yellow_%','')}% 🟫 {r.get('brown_%','')}% ⬛ {r.get('black_%','')}%<br>"
        if r.get("processed_image_path"):
            html += f"<img src='/images/{r['processed_image_path']}' width='320'><br>"
        html += "</div>"
    html += "</body></html>"
    return html

# -------------------------------
# Main Entry
# -------------------------------
if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=run_mqtt, daemon=True)
    mqtt_thread.start()

    summary_thread = threading.Thread(target=periodic_summary_task, daemon=True)
    summary_thread.start()

    print("🚀 Dashboard running: http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
