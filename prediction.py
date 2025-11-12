# -*- coding: utf-8 -*-
"""
🍌 Fruiture Banana Age Prediction & Telegram Alert (Descriptive Message)
---------------------------------------------------------------
Uses trained RandomForest regression model to:
 - Load ml_input.json (latest average sensor data)
 - Predict banana ripeness (Day 1–5)
 - Send Telegram notification with natural description
"""

import os
import json
import pandas as pd
import joblib
import paho.mqtt.client as mqtt
import requests

# ---------------------------------------------------
# Configuration
# ---------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(BASE_DIR, "ml_input.json")
MODEL_FILE = os.path.join(BASE_DIR, "banana_regression_model.pkl")
SCALER_FILE = os.path.join(BASE_DIR, "banana_scaler.pkl")
BOT_FILE = os.path.join(BASE_DIR, "BotAPI.txt")

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "fruiture/servo_angle"

# ---------------------------------------------------
# Load model and scaler
# ---------------------------------------------------
print("🧠 Loading trained model and scaler...")
model = joblib.load(MODEL_FILE)
scaler = joblib.load(SCALER_FILE)
print("✅ Model and scaler loaded successfully.")

# ---------------------------------------------------
# Read input JSON
# ---------------------------------------------------
if not os.path.exists(JSON_FILE):
    raise FileNotFoundError(f"❌ {JSON_FILE} not found. Run your data collector first!")

with open(JSON_FILE, "r") as f:
    data = json.load(f)
print(f"📄 Loaded ml_input.json → {data}")

# ---------------------------------------------------
# Prepare data for prediction
# ---------------------------------------------------
data_fixed = {
    "Max_gas": data["max_gas"],
    "Average_Gas": data["average_gas"],
    "temperature": data["average_temperature"],
    "humidity": data["average_humidity"],
    "R": data["average_R"],
    "G": data["average_G"],
    "B": data["average_B"]
}

features = ["Max_gas", "Average_Gas", "temperature", "humidity", "R", "G", "B"]
X_input = pd.DataFrame([[data_fixed[f] for f in features]], columns=features)

# ---------------------------------------------------
# Predict banana ripeness (regression)
# ---------------------------------------------------
X_scaled = scaler.transform(X_input)
predicted_day = float(model.predict(X_scaled)[0])
predicted_day_rounded = int(round(predicted_day))
predicted_day_clamped = min(max(predicted_day_rounded, 1), 5)

servo_angle = int((predicted_day_clamped - 1) * 45)

# 🧾 Generate a natural-language description
if predicted_day_clamped == 1:
    status_msg = "🍃 Very fresh — around 4 days until it spoils."
elif predicted_day_clamped == 2:
    status_msg = "🌿 Still fresh — about 3 days remaining."
elif predicted_day_clamped == 3:
    status_msg = "🍌 Nicely ripe — good for eating now."
elif predicted_day_clamped == 4:
    status_msg = "🍯 Getting soft — best to eat today or tomorrow."
else:  # Day 5
    status_msg = "⚠️ Overripe — eat soon or it will spoil!"

print("\n🍌 === Banana Prediction Result ===")
print(f"Predicted Day : {predicted_day_clamped}")
print(f"Status        : {status_msg}")
print(f"Servo Angle (0–180°) : {servo_angle}°")


# ---------------------------------------------------
# Publish result to ESP32 via MQTT (no servo angle printed)
# ---------------------------------------------------
payload = json.dumps({
    "predicted_day": predicted_day_clamped,
    "servo_angle": servo_angle,
    "timestamp": data.get("timestamp", "N/A")
})

try:
    print(f"\n📡 Connecting to MQTT broker {MQTT_BROKER}...")
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    client.publish(MQTT_TOPIC, payload)
    print(f"✅ Published to {MQTT_TOPIC}: {payload}")
    client.loop_stop()
    client.disconnect()
except Exception as e:
    print(f"⚠️ MQTT publish failed: {e}")


# ---------------------------------------------------
# Send Telegram notifications (multi-user)
# ---------------------------------------------------
if os.path.exists(BOT_FILE):
    with open(BOT_FILE, "r") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        TOKEN = lines[0]
        CHAT_IDS = lines[1:]  # all remaining lines

    TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    message = (
        f"🍌 *Fruiture Banana Update!*\n"
        f"Predicted ripeness: *Day {predicted_day_clamped}*\n"
        f"{status_msg}\n"
        f"Timestamp: {data.get('timestamp', 'N/A')}"
    )

    for chat_id in CHAT_IDS:
        try:
            r = requests.post(TELEGRAM_URL, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            })
            if r.status_code == 200:
                print(f"✅ Telegram alert sent to {chat_id}")
            else:
                print(f"⚠️ Telegram failed for {chat_id}: {r.status_code} {r.text}")
        except Exception as e:
            print(f"⚠️ Telegram send error for {chat_id}: {e}")
else:
    print("⚠️ No BotAPI.txt found, skipping Telegram alert.")

print("\n🎯 Done! Prediction completed and Telegram alerts sent.")
