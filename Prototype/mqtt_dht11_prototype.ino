/*
ESP32 Sensor Node: DHT11 + MQ2 Gas + MQTT Publisher
--------------------------------------------------------------------
Features:
 - Reads temperature and humidity from DHT11 using Adafruit Unified Sensor API
 - Reads gas concentration (ppm) using MQ-2 sensor with full calibration routine
 - Publishes sensor values to MQTT topics:
      • fruiture/temp
      • fruiture/humidity
      • fruiture/mq2gas
 - Connects to public HiveMQ MQTT broker with keep-alive and last-will support
 - Uses regression model to estimate MQ2 gas ppm
 - Includes adjustable sensor delays and customizable topic names

Author : Feng Yilong
*/

#include <Arduino.h>
#include <WiFi.h>
#include "ESP32MQTTClient.h"
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <DHT_U.h>
#include <MQUnifiedsensor.h>

/*********** WiFi & MQTT ***********/
const char *ssid = "MyWifi-ssid";
const char *password = "MyWifi-password";
const char *mqttServer = "broker.hivemq.com"; // public broker
const int mqttPort = 1883;

char *subscribeTopic = "fruiture/#";
char *publishTopicTemp = "fruiture/temp";
char *publishTopicHum = "fruiture/humidity";
char *publishTopicGas = "fruiture/mq2gas";

ESP32MQTTClient mqttClient;

/*********** DHT11 Setup ***********/
#define DHTPIN 16
#define DHTTYPE DHT11
DHT_Unified dht(DHTPIN, DHTTYPE);
uint32_t delayMS;

/*********** MQ2 Setup ***********/
#define MQ_BOARD "ESP32"
#define MQ_PIN 34 // ADC pin for ESP32
#define MQ_TYPE "MQ-2"
#define VOLT_RES 3.3 // ESP32 ADC voltage
#define ADC_BITS 12  // 12-bit ADC
#define RATIO_CLEAN_AIR 9.83

MQUnifiedsensor MQ2(MQ_BOARD, VOLT_RES, ADC_BITS, MQ_PIN, MQ_TYPE);

void setup()
{
  Serial.begin(115200);

  /***** DHT11 init *****/
  dht.begin();
  sensor_t sensor;
  dht.temperature().getSensor(&sensor);
  delayMS = sensor.min_delay / 1000;

  /***** MQ2 init *****/
  MQ2.setRegressionMethod(1); // Logarithmic
  MQ2.setA(574.25);           // From datasheet for LPG
  MQ2.setB(-2.222);           // From datasheet for LPG
  MQ2.init();
  Serial.println("Calibrating MQ2...");

  float calcR0 = 0;
  for (int i = 0; i < 10; i++)
  {
    MQ2.update();
    calcR0 += MQ2.calibrate(RATIO_CLEAN_AIR);
    Serial.print(".");
    delay(200);
  }
  MQ2.setR0(calcR0 / 10);
  Serial.println(" done!");
  MQ2.serialDebug(true);

  /***** WiFi init *****/
  WiFi.begin(ssid, pass);
  WiFi.setHostname("ESP32_FruitSensor");
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED)
  {
    Serial.print(".");
    delay(1000);
  }
  Serial.println("Connected to WiFi");

  /***** MQTT init *****/
  mqttClient.enableDebuggingMessages();
  mqttClient.setURI(mqttServer);
  mqttClient.setKeepAlive(30);
  mqttClient.enableLastWillMessage("lwt", "I am going offline");
  mqttClient.loopStart();
}

void loop()
{
  delay(delayMS);

  /***** Read DHT11 *****/
  sensors_event_t event;

  dht.temperature().getEvent(&event);
  if (!isnan(event.temperature))
  {
    Serial.print("Temperature: ");
    Serial.println(event.temperature);
    char tempMsg[50];
    snprintf(tempMsg, sizeof(tempMsg), "%.1f°C", event.temperature);
    mqttClient.publish(publishTopicTemp, tempMsg, 0, false);
  }

  dht.humidity().getEvent(&event);
  if (!isnan(event.relative_humidity))
  {
    Serial.print("Humidity: ");
    Serial.println(event.relative_humidity);
    char humMsg[50];
    snprintf(humMsg, sizeof(humMsg), "%.1f%%", event.relative_humidity);
    mqttClient.publish(publishTopicHum, humMsg, 0, false);
  }

  /***** Read MQ2 *****/
  MQ2.update();
  float gasPPM = MQ2.readSensor();
  Serial.print("MQ2 Gas Level (ppm): ");
  Serial.println(gasPPM);

  String gasLevel;
  if (gasPPM < 100)
    gasLevel = "Low";
  else if (gasPPM < 300)
    gasLevel = "Medium";
  else
    gasLevel = "High";

  char gasMsg[50];
  snprintf(gasMsg, sizeof(gasMsg), "%.1f ppm (%s)", gasPPM, gasLevel.c_str());
  mqttClient.publish(publishTopicGas, gasMsg, 0, false);

  delay(1000); // 1-second delay for loop
}

void onMqttConnect(esp_mqtt_client_handle_t client)
{
}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0)
esp_err_t handleMQTT(esp_mqtt_event_handle_t event)
{
  mqttClient.onEventCallback(event);
  return ESP_OK;
}
#else  // IDF CHECK
void handleMQTT(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
  auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
  mqttClient.onEventCallback(event);
}
#endif // // IDF CHECK