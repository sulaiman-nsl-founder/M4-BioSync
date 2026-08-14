#include <WiFi.h>
#include <WebServer.h>
#include <Adafruit_Fingerprint.h>
#include <Adafruit_NeoPixel.h>
#include <WiFiUdp.h>
#include <mbedtls/aes.h>
#include <mbedtls/base64.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>

// --- HARDWARE PINS ---
#define R307_RX_PIN  16
#define R307_TX_PIN  17
#define LED_PIN      18
#define BUZZER_PIN   19
#define NUM_LEDS     8

// --- WI-FI CREDENTIALS ---
const char* ssid = "Nsl";          // REPLACE with your exact Wi-Fi name
const char* password = "12345678"; // REPLACE with your Wi-Fi password

// --- INSTANCES ---
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);
Adafruit_NeoPixel pixels(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);
WebServer server(80);
WiFiUDP udp;
const int UDP_PORT = 8888;
const char* AES_KEY = "AttendanceKey16!";

// --- GLOBAL VARIABLES ---
String currentStatus = "Idle. Ready to scan.";
int lastScannedID = -1;
bool isEnrolling = false;
int enrollStep = 0;
int targetID = 0;

String encryptPayload(String jsonStr) {
  mbedtls_aes_context aes;
  mbedtls_aes_init(&aes);
  mbedtls_aes_setkey_enc(&aes, (const unsigned char*)AES_KEY, 128);

  int len = jsonStr.length();
  int padLen = 16 - (len % 16);
  int paddedLen = len + padLen;
  unsigned char* paddedData = (unsigned char*)malloc(paddedLen);
  memcpy(paddedData, jsonStr.c_str(), len);
  for (int i = len; i < paddedLen; i++) {
    paddedData[i] = padLen;
  }

  unsigned char* encryptedData = (unsigned char*)malloc(paddedLen);
  for (int i = 0; i < paddedLen; i += 16) {
    mbedtls_aes_crypt_ecb(&aes, MBEDTLS_AES_ENCRYPT, paddedData + i, encryptedData + i);
  }

  size_t olen = 0;
  mbedtls_base64_encode(NULL, 0, &olen, encryptedData, paddedLen);
  unsigned char* base64Data = (unsigned char*)malloc(olen + 1);
  mbedtls_base64_encode(base64Data, olen + 1, &olen, encryptedData, paddedLen);
  
  String result = String((char*)base64Data);

  free(paddedData);
  free(encryptedData);
  free(base64Data);
  mbedtls_aes_free(&aes);

  return result;
}

void setLED(uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < NUM_LEDS; i++) {
    pixels.setPixelColor(i, pixels.Color(r, g, b));
  }
  pixels.show();
}

void playBeep(int durationMs, int freq = 2000) {
  tone(BUZZER_PIN, freq, durationMs);
  delay(durationMs);
  noTone(BUZZER_PIN);
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  pixels.begin();
  setLED(255, 165, 0); // Orange = Booting

  // 1. GENTLE WI-FI STARTUP TO PREVENT BROWNOUT
  WiFi.mode(WIFI_STA);
  WiFi.setTxPower(WIFI_POWER_8_5dBm); // Lowers power spike
  WiFi.begin(ssid, password);
  
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected! ESP32 IP Address: " + WiFi.localIP().toString());
  
  // 1.5 OTA ENDPOINT (Server Pull)
  server.on("/update_firmware", HTTP_GET, []() {
    if (server.hasArg("url")) {
      String fw_url = server.arg("url");
      server.send(200, "text/plain", "Starting OTA from: " + fw_url);
      
      // Turn LED orange to indicate update in progress
      setLED(255, 165, 0);
      delay(1000); // Give time for response to send
      
      WiFiClient client;
      t_httpUpdate_return ret = httpUpdate.update(client, fw_url);
      
      switch (ret) {
        case HTTP_UPDATE_FAILED:
          Serial.printf("HTTP_UPDATE_FAILED Error (%d): %s\n", httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
          setLED(255, 0, 0); // Red on error
          break;
        case HTTP_UPDATE_NO_UPDATES:
          Serial.println("HTTP_UPDATE_NO_UPDATES");
          break;
        case HTTP_UPDATE_OK:
          Serial.println("HTTP_UPDATE_OK");
          setLED(0, 255, 0); // Green on success (device will reboot)
          break;
      }
    } else {
      server.send(400, "text/plain", "Missing URL parameter");
    }
  });

  // 2. INITIALIZE SENSOR
  mySerial.begin(57600, SERIAL_8N1, R307_RX_PIN, R307_TX_PIN);
  finger.begin(57600);
  if (finger.verifyPassword()) {
    setLED(0, 255, 0); // Green = Ready
    playBeep(200);
    delay(1000);
    setLED(0, 0, 0);
  } else {
    setLED(255, 0, 0); // Red = Sensor Error
  }

  // 3. UDP DISCOVERY SERVER
  udp.begin(UDP_PORT);

  // 4. API ENDPOINTS FOR PYTHON APP
  server.on("/status", HTTP_GET, []() {
    // Python asks for the current state
    String json = "{\"status\":\"" + currentStatus + "\", \"last_id\":" + String(lastScannedID) + "}";
    server.send(200, "application/json", json);
    // Note: Do not reset lastScannedID here; /poll will handle it.
  });

  server.on("/poll", HTTP_GET, []() {
    String json;
    if (lastScannedID != -1) {
      json = "{\"id\":" + String(lastScannedID) + ",\"confidence\":98,\"timestamp\":\"" + String(millis()) + "\"}";
      lastScannedID = -1; // Reset after reading
    } else {
      json = "{\"id\":-1}";
    }
    String encrypted = encryptPayload(json);
    server.send(200, "text/plain", encrypted);
  });

  server.on("/start_enroll", HTTP_GET, []() {
    if (server.hasArg("id")) {
      targetID = server.arg("id").toInt();
      isEnrolling = true;
      enrollStep = 1;
      currentStatus = "Place finger to enroll ID " + String(targetID);
      setLED(0, 0, 255); // Blue for enroll mode
      server.send(200, "text/plain", "Enrollment started");
    } else {
      server.send(400, "text/plain", "Missing ID");
    }
  });

  server.begin();
}

void loop() {
  server.handleClient(); // Listen for Python requests

  // Handle UDP Discovery
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char incomingPacket[255];
    int len = udp.read(incomingPacket, 255);
    if (len > 0) {
      incomingPacket[len] = 0;
    }
    if (strcmp(incomingPacket, "FIND_ATTENDANCE_DEVICE") == 0) {
      udp.beginPacket(udp.remoteIP(), udp.remotePort());
      String reply = "ATTENDANCE_DEVICE:" + WiFi.localIP().toString() + ":UNIT_01";
      udp.print(reply);
      udp.endPacket();
    }
  }

  // Handle Enrollment State Machine
  if (isEnrolling) {
    if (enrollStep == 1) {
      if (finger.getImage() == FINGERPRINT_OK) {
        finger.image2Tz(1);
        currentStatus = "Remove finger";
        playBeep(100);
        enrollStep = 2;
        delay(1000); // Wait for user to remove finger
      }
    } 
    else if (enrollStep == 2) {
      if (finger.getImage() == FINGERPRINT_NOFINGER) {
        currentStatus = "Place same finger again";
        enrollStep = 3;
      }
    } 
    else if (enrollStep == 3) {
      if (finger.getImage() == FINGERPRINT_OK) {
        finger.image2Tz(2);
        if (finger.createModel() == FINGERPRINT_OK) {
          if (finger.storeModel(targetID) == FINGERPRINT_OK) {
            currentStatus = "Success! ID " + String(targetID) + " enrolled.";
            playBeep(200);
            setLED(0, 255, 0);
          } else {
            currentStatus = "Error: Failed to save.";
            setLED(255, 0, 0);
          }
        } else {
          currentStatus = "Error: Prints did not match.";
          setLED(255, 0, 0);
        }
        delay(1500);
        setLED(0, 0, 0);
        isEnrolling = false; // Exit enroll mode
        currentStatus = "Idle. Ready to scan.";
      }
    }
  } 
  // Handle Normal Scanning
  else {
    if (finger.getImage() == FINGERPRINT_OK) {
      if (finger.image2Tz() == FINGERPRINT_OK) {
        if (finger.fingerSearch() == FINGERPRINT_OK) {
          lastScannedID = finger.fingerID;
          currentStatus = "Scanned ID: " + String(lastScannedID);
          setLED(0, 255, 0);
          playBeep(100, 2500); delay(50); playBeep(100, 2500);
          delay(1000);
          setLED(0, 0, 0);
        } else {
          currentStatus = "Unknown Finger";
          setLED(255, 0, 0);
          playBeep(500, 1000);
          delay(1000);
          setLED(0, 0, 0);
        }
      }
    }
  }
}