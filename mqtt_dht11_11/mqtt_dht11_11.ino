#include <Arduino.h>
#include <WiFi.h>
#include "ESP32MQTTClient.h"
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <DHT_U.h>
#include <MQUnifiedsensor.h>

/*********** WiFi & MQTT ***********/
const char* ssid = "ftc"; 
const char* pass = "ftc1312666";
const char* mqttURI = "mqtt://test.mosquitto.org:1883";

char* publishTopicTemp  = "fruiture/temp";
char* publishTopicHum   = "fruiture/humidity";
char* publishTopicGas   = "fruiture/mq2gas";
char* publishTopicTrend = "fruiture/trend";

ESP32MQTTClient mqttClient;

/*********** DHT11 Setup ***********/
#define DHTPIN 16
#define DHTTYPE DHT11
DHT_Unified dht(DHTPIN, DHTTYPE);
uint32_t delayMS;

/*********** MQ2 Setup ***********/
#define MQ_BOARD "ESP32"
#define MQ_PIN 34
#define MQ_TYPE "MQ-2"
#define VOLT_RES 3.3
#define ADC_BITS 12
#define RATIO_CLEAN_AIR 9.83

MQUnifiedsensor MQ2(MQ_BOARD, VOLT_RES, ADC_BITS, MQ_PIN, MQ_TYPE);

/*********** Variables ***********/
float BASELINE_AIR = 0.0;
float filteredGasPPM = 0.0;
const float SMOOTH_ALPHA = 0.5; // smoothing factor

/*********** Stable Calibration ***********/
float calibrateBaselineDynamic(float tolerance = 0.05, int stableCount = 10, int maxIterations = 300) {
  Serial.println("🌬️ Starting clean-air baseline calibration...");
  float lastPPM = 0;
  int stable = 0;
  int total = 0;

  while (stable < stableCount && total < maxIterations) {
    MQ2.update();
    float ppm = MQ2.readSensor();
    if (isnan(ppm) || ppm <= 0) continue;

    if (fabs(ppm - lastPPM) <= tolerance && lastPPM != 0) {
      stable++;
      Serial.printf("Stable %d/%d | %.3f ppm\n", stable, stableCount, ppm);
    } else {
      stable = 0;
      Serial.printf("Drifting... %.3f ppm\n", ppm);
    }

    lastPPM = ppm;
    total++;
    delay(300);
  }

  // Average 10 final stable samples
  float sum = 0;
  int samples = 10;
  Serial.println("✅ Stability reached! Averaging last 10 samples...");
  for (int i = 0; i < samples; i++) {
    MQ2.update();
    float ppm = MQ2.readSensor();
    sum += ppm;
    Serial.printf("  Sample %d: %.3f ppm\n", i + 1, ppm);
    delay(300);
  }

  float baseline = sum / samples;
  Serial.printf("📏 Final clean-air baseline: %.3f ppm\n", baseline);
  return baseline;
}

/*********** Setup ***********/
void setup() {
  Serial.begin(115200);
  Serial.println("🍌 ESP32 Fruiture Banana Sensor Initializing...");

  /***** DHT11 init *****/
  dht.begin();
  sensor_t sensor;
  dht.temperature().getSensor(&sensor);
  delayMS = sensor.min_delay / 1000;

  /***** MQ2 init *****/
  MQ2.setRegressionMethod(1); // Logarithmic
  MQ2.setA(574.25);
  MQ2.setB(-2.222);
  MQ2.init();

  Serial.println("🔥 Warming up MQ2 sensor (30s)...");
  delay(30000);

  // --- Calibrate R0 ---
  float calcR0 = 0;
  for (int i = 0; i < 10; i++) {
    MQ2.update();
    calcR0 += MQ2.calibrate(RATIO_CLEAN_AIR);
    Serial.print(".");
    delay(200);
  }
  MQ2.setR0(calcR0 / 10);
  Serial.printf("\n✅ MQ2 Calibrated R0 = %.2f\n", calcR0 / 10);

  // --- Stable clean-air baseline ---
  BASELINE_AIR = calibrateBaselineDynamic();          // ✅ move baseline here before publish
  MQ2.serialDebug(false);

  // ✅ Publish baseline AFTER calibration
  char baseMsg[50];
  snprintf(baseMsg, sizeof(baseMsg), "%.3f ppm", BASELINE_AIR);
  mqttClient.publish("fruiture/baseline", baseMsg, 0, true);
  Serial.printf("📡 Published baseline: %.3f ppm\n", BASELINE_AIR);

  /***** WiFi init *****/
  WiFi.begin(ssid, pass);
  WiFi.setHostname("ESP32_FruitSensor");
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(1000);
  }
  Serial.println("\n✅ Connected to WiFi!");

  /***** MQTT init *****/
  mqttClient.enableDebuggingMessages();
  mqttClient.setURI(mqttURI);
  mqttClient.setKeepAlive(30);
  mqttClient.enableLastWillMessage("fruiture/status", "Sensor offline");
  mqttClient.loopStart();
  Serial.println("✅ MQTT Client Ready!");
}

/*********** Loop ***********/
void loop() {
  delay(delayMS);

  /***** Read DHT11 *****/
  sensors_event_t event;
  float temperature = NAN, humidity = NAN;

  dht.temperature().getEvent(&event);
  if (!isnan(event.temperature)) {
    temperature = event.temperature;
    char tempMsg[50];
    snprintf(tempMsg, sizeof(tempMsg), "%.1f°C", temperature);
    mqttClient.publish(publishTopicTemp, tempMsg, 0, false);
  }

  dht.humidity().getEvent(&event);
  if (!isnan(event.relative_humidity)) {
    humidity = event.relative_humidity;
    char humMsg[50];
    snprintf(humMsg, sizeof(humMsg), "%.1f%%", humidity);
    mqttClient.publish(publishTopicHum, humMsg, 0, false);
  }

  /***** Read MQ2 Gas *****/
  MQ2.update();
  float gasPPM = MQ2.readSensor();
  if (isnan(gasPPM) || gasPPM <= 0) gasPPM = 0.01;

  // Smooth reading
  filteredGasPPM = SMOOTH_ALPHA * gasPPM + (1 - SMOOTH_ALPHA) * filteredGasPPM;

  // ✅ Subtract baseline directly
  float gasPPM_corrected = filteredGasPPM - BASELINE_AIR;
  if (gasPPM_corrected < 0) gasPPM_corrected = 0;

  // Compute ratio relative to baseline
  float ratio = gasPPM_corrected / BASELINE_AIR;

  // Interpret freshness
  String gasLevel;
  if (ratio < 0.2) gasLevel = "Fresh";
  else if (ratio < 0.8) gasLevel = "Ripening";
  else if (ratio < 1.5) gasLevel = "Ripe";
  else gasLevel = "Overripe";

  Serial.printf("🔥 MQ2 Gas: %.2f ppm (after baseline) | MQ2 Gas: %.2f ppm (before baseline) Ratio: %.2f | %s\n",
                gasPPM_corrected, filteredGasPPM, ratio, gasLevel.c_str());

  // ✅ Publish corrected gas value
  char gasMsg[64];
  snprintf(gasMsg, sizeof(gasMsg), "%.2f ppm (%s)", gasPPM_corrected, gasLevel.c_str());
  mqttClient.publish(publishTopicGas, gasMsg, 0, false);

  char rawGasMsg[64];
  snprintf(rawGasMsg, sizeof(rawGasMsg), "%.2f ppm (filtered)", filteredGasPPM);
  mqttClient.publish("fruiture/rawgas", rawGasMsg, 0, false);

  char trendMsg[128];
  snprintf(trendMsg, sizeof(trendMsg), 
           "%.1f,%.1f,%.2f,%.2f,%s",
           temperature, humidity, gasPPM_corrected, ratio, gasLevel.c_str());
  mqttClient.publish(publishTopicTrend, trendMsg, 0, false);

  delay(2000);
}

/*********** MQTT Handling ***********/
void onMqttConnect(esp_mqtt_client_handle_t client) {}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0)
esp_err_t handleMQTT(esp_mqtt_event_handle_t event) {
  mqttClient.onEventCallback(event);
  return ESP_OK;
}
#else
void handleMQTT(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data) {
  auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
  mqttClient.onEventCallback(event);
}
#endif
