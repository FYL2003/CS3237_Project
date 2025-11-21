/*
ESP32-CAM Full Image Capture + Base64 MQTT Uploader
--------------------------------------------------------------------
Features:
 - Initializes AI Thinker ESP32-CAM with configurable resolution and JPEG quality
 - Sends Base64-encoded images at adjustable time intervals
 - Connects to Wi-Fi and public HiveMQ MQTT broker
 - Captures full JPEG images and converts them into Base64
 - Publishes the Base64 image string to MQTT topic: fruiture/Base64image
 - Includes automatic MQTT reconnection handling and status reporting

Credits:
 - ESP32 camera base code adapted from Du Yanzhang

Author : Feng Yilong
*/

#include "esp_camera.h"
#include "Arduino.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "driver/rtc_io.h"
#include "Base64.h"
#include <WiFi.h>
#include "ESP32MQTTClient.h"

// ---------- Wi-Fi and MQTT ----------
const char *ssid = "MyWifi-ssid";
const char *password = "MyWifi-password";
const char *mqttURI = "mqtt://broker.hivemq.com:1883";
const char *publishTopic = "fruiture/Base64image";

ESP32MQTTClient mqttClient;

// ---------- Camera Pins (AI Thinker ESP32-CAM) ----------
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

#define PHOTO_INTERVAL 10000 // 10 seconds
unsigned long lastPhotoTime = 0;

void setup()
{
  Serial.begin(115200);
  Serial.println("ESP32-CAM Base64 MQTT Sender (Full Image)");

  // Disable brownout detector
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  // --- Camera Configuration ---
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK)
  {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    while (true)
      ;
  }
  Serial.println("Camera initialized.");

  // --- Wi-Fi Connection ---
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED)
  {
    Serial.print(".");
    delay(500);
  }
  Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());

  // --- MQTT Setup ---
  mqttClient.enableDebuggingMessages();
  mqttClient.setKeepAlive(30);
  mqttClient.setURI(mqttURI);
  mqttClient.enableLastWillMessage("fruiture/status", "ESP32-CAM offline");
  mqttClient.loopStart();

  Serial.print("Connecting to MQTT broker");
  while (!mqttClient.isConnected())
  {
    Serial.print(".");
    delay(500);
  }
  Serial.println("\nMQTT connected!");
}

void loop()
{
  if (millis() - lastPhotoTime >= PHOTO_INTERVAL)
  {
    takePhotoAndSend();
    lastPhotoTime = millis();
  }
}

void takePhotoAndSend()
{
  Serial.println("Capturing photo...");
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb)
  {
    Serial.println("Camera capture failed!");
    return;
  }

  String encoded = base64::encode(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  Serial.printf("Photo size: %d bytes, Base64 length: %d\n", fb->len, encoded.length());

  if (!mqttClient.isConnected())
  {
    Serial.println("MQTT not connected! Trying to reconnect...");
    mqttClient.loopStart();
    if (!mqttClient.isConnected())
    {
      Serial.println("Failed to reconnect. Skipping send.");
      return;
    }
  }

  if (mqttClient.publish(publishTopic, encoded.c_str(), 0, false))
  {
    Serial.println("✅ Full Base64 image sent successfully!");
  }
  else
  {
    Serial.println("❌ Failed to send full Base64 image!");
  }
}

void onMqttConnect(esp_mqtt_client_handle_t client)
{
  // Optional: subscribe if needed
}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0)
esp_err_t handleMQTT(esp_mqtt_event_handle_t event)
{
  mqttClient.onEventCallback(event);
  return ESP_OK;
}
#else
void handleMQTT(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
  auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
  mqttClient.onEventCallback(event);
}
#endif
