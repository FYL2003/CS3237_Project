#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

/************ WiFi & MQTT ************/
const char* ssid = "ftc";
const char* password = "ftc1312666";
const char* mqtt_server = "test.mosquitto.org";

WiFiClient espClient;
PubSubClient client(espClient);
Servo myServo;

/************ MQTT Topics ************/
const char* subscribeTopic = "fruiture/servo_angle";     // incoming command
const char* feedbackTopic  = "fruiture/servo_feedback";  // outgoing feedback

/************ Servo Setup ************/
#define SERVO_PIN 14     // your signal pin
int currentAngle = 0;

/************ Function Prototypes ************/
void setup_wifi();
void callback(char* topic, byte* payload, unsigned int length);
void reconnect();

/************ Setup ************/
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n🍌 ESP32 Servo Controller Initializing...");

  setup_wifi();

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);

  // Explicitly configure pulse width range for ESP32 PWM driver
  myServo.attach(SERVO_PIN, 550, 2500);  // safe 0–180° range

  // --- Startup movement test ---
  Serial.println("🌀 Performing servo self-test sweep...");
  myServo.write(0);
  delay(500);
  myServo.write(90);
  delay(500);
  myServo.write(0);
  delay(500);

  currentAngle = 0;
  Serial.println("✅ Servo attached and initialized at 0°");
}

/************ Main Loop ************/
void loop() {
  if (!client.connected()) reconnect();
  client.loop();
}

/************ WiFi Connection ************/
void setup_wifi() {
  delay(10);
  Serial.printf("📶 Connecting to %s", ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi connected!");
  Serial.print("🧭 IP: ");
  Serial.println(WiFi.localIP());
}

/************ MQTT Callback ************/
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.printf("\n📩 Message arrived [%s]: ", topic);

  // Copy payload into buffer
  char msg[length + 1];
  memcpy(msg, payload, length);
  msg[length] = '\0';
  Serial.println(msg);

  // Parse JSON
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, msg);
  if (error) {
    Serial.print("⚠️ JSON parse error: ");
    Serial.println(error.c_str());
    return;
  }

  int predicted_day = doc["predicted_day"] | -1;
  float confidence  = doc["confidence"]     | 0.0;
  int target_angle  = doc["servo_angle"]    | 0;
  const char* timestamp = doc["timestamp"]  | "unknown";

  Serial.printf("🤖 Predicted day: %d | Confidence: %.2f | Target: %d° | Time: %s\n",
                predicted_day, confidence, target_angle, timestamp);

  // Ensure valid range
  int target_angle_cali = constrain((int)(target_angle * 1.10), 0, 180);

  // Smoothly move servo
  int step = (target_angle_cali > currentAngle) ? 1 : -1;
  for (int pos = currentAngle; pos != target_angle_cali; pos += step) {
    myServo.write(pos);
    delay(15);  // adjust speed
  }
  myServo.write(target_angle_cali);
  currentAngle = target_angle_cali;

  Serial.printf("🎯 Servo positioned at %d°\n", currentAngle);

  // Send confirmation feedback
  StaticJsonDocument<256> feedback;
  feedback["servo_angle"]    = currentAngle;
  feedback["predicted_day"]  = predicted_day;
  feedback["confidence"]     = confidence;
  feedback["timestamp"]      = timestamp;
  feedback["status"]         = "completed";

  char feedbackMsg[256];
  serializeJson(feedback, feedbackMsg);
  client.publish(feedbackTopic, feedbackMsg);

  Serial.printf("📡 Feedback published to %s → %s\n", feedbackTopic, feedbackMsg);
}

/************ MQTT Reconnection ************/
void reconnect() {
  while (!client.connected()) {
    Serial.print("🔄 Attempting MQTT connection...");
    String clientId = "ESP32Servo-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("✅ connected");
      client.subscribe(subscribeTopic);
      Serial.printf("📡 Subscribed to %s\n", subscribeTopic);
    } else {
      Serial.printf("❌ failed, rc=%d → retrying in 5s\n", client.state());
      delay(5000);
    }
  }
}
