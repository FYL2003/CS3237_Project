# -*- coding: utf-8 -*-
from flask import Flask, jsonify
import threading
import paho.mqtt.client as mqtt
import pandas as pd
import base64
import os
import time
import json

# -------------------------------
# Global data storage
# -------------------------------
DATA_FILE = "esp32_data.csv"
IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# Temporary in-memory record
current_entry = {
    "timestamp": None,
    "temperature": None,
    "humidity": None,
    "gas": None,
    "image_path": None
}

# Create or load the data file
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=["timestamp", "temperature", "humidity", "gas", "image_path"])
    df.to_csv(DATA_FILE, index=False)

# -------------------------------
# MQTT setup
# -------------------------------
def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)
    client.subscribe("esp32/AY2526CS3237Project/#")  # Expecting esp32/temp, esp32/hum, esp32/gas, esp32/image

def on_message(client, userdata, message):
    global current_entry
    topic = message.topic
    payload = message.payload.decode("utf-8", errors="ignore")
    print(f"Received from '{topic}': {payload[:50]}...")

    try:
        # always update timestamp to the current time for this entry
        current_entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Update entry based on topic
        if "temp" in topic:
            current_entry["temperature"] = float(payload)
        elif "hum" in topic:
            current_entry["humidity"] = float(payload)
        elif "gas" in topic:
            current_entry["gas"] = float(payload)
        elif "image" in topic:
            # Save Base64 image to file
            image_data = base64.b64decode(payload)
            timestamp_unix = int(time.time())
            image_path = os.path.join(IMAGE_DIR, f"img_{timestamp_unix}.jpg")
            with open(image_path, "wb") as f:
                f.write(image_data)
            current_entry["image_path"] = image_path

        print(current_entry)

        # Check if we have all required fields (timestamp is always set now)
        required_keys = ["timestamp", "temperature", "humidity", "gas", "image_path"]
        if all(current_entry.get(k) is not None for k in required_keys):
            # Append to CSV
            df = pd.read_csv(DATA_FILE)
            df = pd.concat([df, pd.DataFrame([current_entry])], ignore_index=True)
            df.to_csv(DATA_FILE, index=False)

            print("✅ Saved record:", current_entry)

            # Reset for next record
            current_entry = {
                "timestamp": None,
                "temperature": None,
                "humidity": None,
                "gas": None,
                "image_path": None
            }

    except Exception as e:
        print("Error processing message:", e)


def run_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("broker.hivemq.com", 1883, 60)
    client.loop_forever()

# -------------------------------
# Flask dashboard (optional)
# -------------------------------
app = Flask(__name__)

@app.route("/data")
def get_data():
    df = pd.read_csv(DATA_FILE)
    return jsonify(df.tail(10).to_dict(orient="records"))  # Last 10 records

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=run_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    app.run(host="0.0.0.0", port=5001, debug=False)
