# -*- coding: utf-8 -*-
from flask import Flask, jsonify, render_template_string
import threading
import paho.mqtt.client as mqtt
import joblib
import pandas as pd

# -------------------------------
# Load ML model and scaler
# -------------------------------
model = joblib.load("window_gnb_model.pkl")
scaler = joblib.load("window_scaler.pkl")

# -------------------------------
# Shared State
# -------------------------------
latest_data = {
    "temperature": None,
    "humidity": None,
    "prediction": None,
}

# -------------------------------
# Flask Web Server
# -------------------------------
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Window Status Dashboard</title>
    <style>
        body { font-family: Arial; text-align: center; margin-top: 50px; }
        .card { border: 1px solid #ccc; border-radius: 10px; padding: 20px; width: 300px; margin: auto; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1 { color: #444; }
        .status { font-size: 24px; margin-top: 20px; color: #2b6; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Window Prediction</h1>
        <p>Temperature: <span id="temp">N/A</span> °C</p>
        <p>Humidity: <span id="hum">N/A</span> %</p>
        <p class="status">Predicted Status: <b><span id="pred">N/A</span></b></p>
    </div>

    <script>
        async function fetchData() {
            const response = await fetch("/data");
            const data = await response.json();

            document.getElementById("temp").innerText = data.temperature !== null ? data.temperature : "N/A";
            document.getElementById("hum").innerText = data.humidity !== null ? data.humidity : "N/A";
            document.getElementById("pred").innerText = data.prediction !== null ? data.prediction : "N/A";
        }

        setInterval(fetchData, 1000); // Refresh every second
        fetchData(); // Initial load
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/data")
def data():
    return jsonify(latest_data)

# -------------------------------
# MQTT setup
# -------------------------------
def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)
    client.subscribe("weather/#")

def on_message(client, userdata, message):
    try:
        topic = message.topic
        payload = message.payload.decode("utf-8")
        print("Received from '{}': {}".format(topic, payload))

        if "temp" in topic.lower():
            latest_data["temperature"] = float(payload)
        elif "hum" in topic.lower():
            latest_data["humidity"] = float(payload)

        if latest_data["temperature"] is not None and latest_data["humidity"] is not None:
            temp = latest_data["temperature"]
            hum = latest_data["humidity"]

            features = pd.DataFrame([[temp, hum]], columns=["temperature", "humidity"])
            scaled_features = scaler.transform(features)

            prediction = model.predict(scaled_features)[0]
            print("Predicted window status: {}".format(prediction))

            latest_data["prediction"] = str(prediction)

            # Publish prediction back via MQTT
            client.publish("window/status", str(prediction))

    except Exception as e:
        print("Error processing message: {}".format(e))

def run_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("127.0.0.1", 1883, 60)  # Replace with your broker IP
    client.loop_forever()

# -------------------------------
# Run both MQTT and Flask
# -------------------------------
if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=run_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    app.run(host="0.0.0.0", port=5001, debug=False)
