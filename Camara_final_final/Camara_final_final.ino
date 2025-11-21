#include "esp_camera.h"
#include "Arduino.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "driver/rtc_io.h"
#include "Base64.h"
#include <WiFi.h>
#include "ESP32MQTTClient.h"

// ---------- Wi-Fi & MQTT ----------
const char* ssid = "ftc";
const char* password = "ftc1312666";
const char* mqttURI = "mqtt://test.mosquitto.org:1883";
const char* publishTopic = "fruiture/Base64image";

ESP32MQTTClient mqttClient;

// ---------- Camera Pins (AI Thinker ESP32-CAM) ----------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define PHOTO_INTERVAL 20000UL  // 20s for bigger frames
unsigned long lastPhotoTime = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("🚀 ESP32-CAM Banana Vision (High-Res SXGA Edition)");

  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);  // Disable brownout

  // --- Camera Configuration ---
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM; config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format  = PIXFORMAT_JPEG;

  // --- Resolution and quality ---
  config.frame_size   = FRAMESIZE_SXGA;  // 1280x1024
  config.jpeg_quality = 8;               // lower = higher quality
  config.fb_count     = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    while (true);
  }
  Serial.println("Camera initialized.");

  sensor_t * s = esp_camera_sensor_get();
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
  s->set_exposure_ctrl(s, true);
  s->set_gain_ctrl(s, true);
  s->set_whitebal(s, true);
  s->set_awb_gain(s, true);
  s->set_brightness(s, 1);
  s->set_contrast(s, 2);
  s->set_saturation(s, 1);
  s->set_ae_level(s, 1);
  s->set_wb_mode(s, 0);
  s->set_lenc(s, 1);
  s->set_raw_gma(s, 1);
  s->set_special_effect(s, 0);
  Serial.println("🎨 Auto WB + exposure active. Sharp high-res tuning complete.");

  // --- Wi-Fi ---
  WiFi.begin(ssid, password);
  Serial.print("Connecting Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(500);
  }
  Serial.println("\nWi-Fi connected! IP: " + WiFi.localIP().toString());

  // --- MQTT Setup ---
  mqttClient.enableDebuggingMessages();
  mqttClient.setKeepAlive(120);  // increased for large payloads
  mqttClient.setURI(mqttURI);
  mqttClient.enableLastWillMessage("fruiture/status", "ESP32-CAM offline");
  mqttClient.loopStart();

  Serial.print("Connecting MQTT");
  unsigned long start = millis();
  while (!mqttClient.isConnected() && millis() - start < 10000) {
    Serial.print(".");
    delay(500);
  }
  if (mqttClient.isConnected())
    Serial.println("\nMQTT connected!");
  else
    Serial.println("\n⚠️ MQTT connection timeout, continuing...");
}

void loop() {
  if (millis() - lastPhotoTime >= PHOTO_INTERVAL) {
    takePhotoAndSend();
    lastPhotoTime = millis();
  }
}

void takePhotoAndSend() {
  Serial.println("📸 Capturing photo...");
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Capture failed!");
    return;
  }

  // --- Encode and release buffer early ---
  String encoded = base64::encode(fb->buf, fb->len);
  size_t base64Len = encoded.length();
  esp_camera_fb_return(fb);

  Serial.printf("Photo size: %d bytes, Base64 length: %d\n", fb->len, base64Len);

  // --- Ensure MQTT connection ---
  if (!mqttClient.isConnected()) {
    Serial.println("⚠️ MQTT not connected! Attempting reconnect...");
    mqttClient.loopStart();
    unsigned long start = millis();
    while (!mqttClient.isConnected() && millis() - start < 5000) {
      delay(200);
    }
    if (!mqttClient.isConnected()) {
      Serial.println("❌ MQTT reconnect failed, skipping send.");
      return;
    }
  }

  delay(300); // ensure socket buffer clear before heavy send
  mqttClient.setKeepAlive(120); // refresh keep-alive to avoid timeout

  // --- Safe publish with retry ---
  bool sent = false;
  for (int i = 1; i <= 3 && !sent; i++) {
    Serial.printf("🚀 Sending image attempt %d...\n", i);
    sent = mqttClient.publish(publishTopic, encoded.c_str(), 0, false);
    if (!sent) {
      Serial.println("⚠️ Publish failed, retrying in 1s...");
      delay(1000);
    }
  }

  if (sent)
    Serial.printf("✅ Image sent successfully! (%d bytes)\n", base64Len);
  else
    Serial.println("❌ MQTT publish failed after 3 attempts!");
}

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
