# -*- coding: utf-8 -*-
"""
ESP32-CAM Sensor Fusion + Banana Ripeness Prediction + Telegram Alerts
-----------------------------------------------------------------------
Features:
 - Subscribes to ESP32 temperature, humidity, gas, and Base64 camera feeds via MQTT
 - Uses improved banana detection (no-grey version) for accurate RGB extraction
 - Converts extracted RGB → ripeness score (0 = green, 1 = overripe)
 - Feeds (temperature, humidity, ripeness) into a trained spoilage prediction model
 - Prints remaining days before spoilage and sends Telegram alerts when threshold is met
 - Runs MQTT listener continuously in a background processing thread

Credits:
 - Banana detection module (banana_detector_no_grey) by Du Yanzhang
 - Spoilage prediction ML model by Liu HengYi

Author : Feng Yilong
"""

import requests
import cv2
import numpy as np
import base64
import time
import threading
import colorsys
import joblib
import paho.mqtt.client as mqtt
from banana_detector_no_grey import detect_banana_ultimate  # same as before

# Read token and chat ID from BoxAPI.txt
with open("BotAPI.txt", "r") as f:
    lines = f.read().splitlines()
    TOKEN = lines[0].strip()      # first line = bot token
    CHAT_ID = lines[1].strip()    # second line = chat ID

instruction = "Please eat banana! It only have less than n days to rot!"

# Telegram API endpoint
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": instruction
}

# -------------------------------
# Configuration
# -------------------------------
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "fruiture/#"

# Load your trained model once
loaded_model = joblib.load("banana_spoilage_model.pkl")

# -------------------------------
# Temporary storage for one batch of readings
# -------------------------------
current_entry = {
    "timestamp": None,
    "temperature": None,
    "humidity": None,
    "gas": None,
    "rgb": None
}
entry_lock = threading.Lock()

# -------------------------------
# Convert RGB → ripeness (0 to 1)
# -------------------------------
def rgb_to_ripeness(r, g, b):
    # normalize RGB to [0,1]
    r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0
    h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)
    h_deg = h * 360
    # green ~120°, yellow ~60°, brown ~30°, black ~0°
    ripeness = (120 - h_deg) / 120  # 0 = green, 1 = brown/black
    ripeness = np.clip(ripeness, 0, 1)
    return ripeness

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

            # Update numeric sensor values
            if "temp" in topic.lower():
                current_entry["temperature"] = float(payload)
            elif "hum" in topic.lower():
                current_entry["humidity"] = float(payload)
            elif "gas" in topic.lower():
                current_entry["gas"] = float(payload)

            # Handle Base64 image input
            elif "base64image" in topic.lower():
                img_data = base64.b64decode(payload)
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                # detect_banana_and_avg_color returns (visualized_image, mean_rgb)
                vis, mean_rgb, ripeness, proportions = detect_banana_ultimate(img)
                current_entry["rgb"] = mean_rgb
                print(f"🎨 Mean RGB: {mean_rgb}")

            # After any update, check if all fields ready
            check_and_predict()

    except Exception as e:
        print("❌ Error processing message:", e)

# -------------------------------
# When all fields are received → predict using model
# -------------------------------
def check_and_predict():
    """Run model prediction once all values are ready."""
    global current_entry
    required = ["temperature", "humidity", "rgb"]

    # If all fields are present, run prediction
    if all(current_entry.get(k) is not None for k in required):
        temp = current_entry["temperature"]
        hum = current_entry["humidity"]
        r, g, b = current_entry["rgb"]

        # Convert RGB to ripeness
        ripeness = rgb_to_ripeness(r, g, b)

        # Prepare model input
        new_sample = np.array([[temp, hum, ripeness]])

        # Predict
        predicted_days = loaded_model.predict(new_sample)[0]
        print(f"🍌 Predicted days until banana goes bad: {predicted_days:.2f}")

        # Reset for next cycle
        current_entry = {k: None for k in current_entry}

        if predicted_days < 4:
            # Send the message
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                print("Message sent successfully!")
            else:
                print("Failed to send message:", response.status_code, response.text)


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
# Main Entry
# -------------------------------
if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=run_mqtt, daemon=True)
    mqtt_thread.start()
    print("🚀 Prediction system ready and waiting for MQTT data...")
    while True:
        time.sleep(1)
