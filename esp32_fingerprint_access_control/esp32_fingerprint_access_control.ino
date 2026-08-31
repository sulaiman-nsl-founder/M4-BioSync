#include <WiFi.h>
#include <WebServer.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include <Adafruit_Fingerprint.h>
#include <Adafruit_NeoPixel.h>
#include <WiFiUdp.h>
#include <mbedtls/aes.h>
#include <mbedtls/base64.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <SPI.h>
#include <SD.h>
#include <Wire.h>
#include <RTClib.h>

// --- HARDWARE PINS ---
#define R307_RX_PIN  16
#define R307_TX_PIN  17
#define LED_PIN      18
#define BUZZER_PIN   19
#define NUM_LEDS     8

// --- SD & RTC PINS ---
#define SD_MOSI 13
#define SD_MISO 12
#define SD_SCK  14
#define SD_CS   15

#include <Preferences.h>

Preferences preferences;
String ssid = "Nsl";
String password = "12345678";
bool isAPMode = false;

// --- INSTANCES ---
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);
Adafruit_NeoPixel pixels(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);
WebServer server(80);
WiFiUDP udp;
const int UDP_PORT = 8888;
const char* AES_KEY = "AttendanceKey16!";

RTC_DS1307 rtc;
SPIClass spiHSPI(HSPI);
bool sdReady = false;
bool rtcReady = false;

// --- GLOBAL VARIABLES ---
String currentStatus = "Idle. Ready to scan.";
int lastScannedID = -1;
String lastScannedTimestamp = "";
bool isEnrolling = false;
int enrollStep = 0;
int targetID = 0;
unsigned long lastPollTime = 0;

// Cooldown tracking (assumes max 255 IDs)
unsigned long lastPunchMillis[256] = {0};
bool isCheckedIn[256] = {false}; // Track check-in vs check-out state for LEDs
const unsigned long COOLDOWN_MS = 5000; // 5 seconds (Reduced for testing)

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

void logOfflineScan(int id) {
  if (!sdReady) {
    Serial.println("Cannot log offline: SD not ready");
    return;
  }
  
  String timestamp;
  if (rtcReady) {
    DateTime now = rtc.now();
    timestamp = String(now.year()) + "-" + String(now.month()) + "-" + String(now.day()) + "T" + 
                String(now.hour()) + ":" + String(now.minute()) + ":" + String(now.second());
  } else {
    // Fallback: use uptime in seconds if RTC not available
    unsigned long uptime = millis() / 1000;
    timestamp = "uptime_" + String(uptime) + "s";
    Serial.println("WARNING: RTC not ready, using uptime timestamp.");
  }
  
  String json = "{\"id\":" + String(id) + ",\"confidence\":98,\"timestamp\":\"" + timestamp + "\"}";
  String encrypted = encryptPayload(json);
  
  File file = SD.open("/queue.csv", FILE_APPEND);
  if (!file) {
    Serial.println("SD write failed! Attempting hardware auto-recovery...");
    // Auto-recover the SD Card SPI bus in case Wi-Fi corrupted it
    SD.end();
    spiHSPI.end();
    digitalWrite(SD_CS, HIGH);
    delay(500); // 500ms allows the SD card internal controller to fully power-cycle
    
    spiHSPI.begin(SD_SCK, SD_MISO, SD_MOSI, SD_CS);
    if (SD.begin(SD_CS, spiHSPI)) {
      file = SD.open("/queue.csv", FILE_APPEND);
      if (!file) {
        file = SD.open("/queue.csv", FILE_WRITE); // Fallback to write if append unsupported
      }
    }
  }
  
  if (file) {
    file.println(encrypted);
    file.close();
    Serial.println("Saved punch to SD card offline queue.");
  } else {
    Serial.println("CRITICAL: Failed to open SD file even after auto-recovery");
  }
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
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Disable brownout detector
  Serial.begin(115200);
  delay(2000); // Wait for serial monitor to connect
  
  pinMode(BUZZER_PIN, OUTPUT);
  pixels.begin();
  setLED(255, 165, 0); // Orange = Booting
  
  Serial.println("\n--- BioSync ESP32 Booting ---");

  // 0. INITIALIZE RTC & SD CARD
  Wire.begin(21, 22);
  if (!rtc.begin()) {
    Serial.println("Couldn't find RTC");
  } else {
    rtcReady = true;
    if (!rtc.isrunning()) {
      Serial.println("RTC is NOT running, setting to compile time!");
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
  }

  // SD Card Init with retry loop (handles warm boot SPI bus issues)
  pinMode(SD_CS, OUTPUT);
  digitalWrite(SD_CS, HIGH);
  delay(100);
  
  for (int sdAttempt = 1; sdAttempt <= 5; sdAttempt++) {
    spiHSPI.begin(SD_SCK, SD_MISO, SD_MOSI, SD_CS);
    if (SD.begin(SD_CS, spiHSPI)) {
      sdReady = true;
      Serial.println("SD Card mounted successfully (attempt " + String(sdAttempt) + ")");
      
      // Perform a quick write test to guarantee file system is writable
      File testWrite = SD.open("/testlog.txt", FILE_WRITE);
      if (testWrite) {
        testWrite.println("SD Write Test OK");
        testWrite.close();
        Serial.println("SD Write Test: SUCCESS");
      } else {
        Serial.println("SD Write Test: FAILED TO OPEN FILE");
      }
      break;
    } else {
      Serial.println("SD Card mount failed, attempt " + String(sdAttempt) + "/5...");
      SD.end();
      spiHSPI.end(); // CRITICAL: Tear down the SPI bus before calling begin() on the next loop
      digitalWrite(SD_CS, HIGH);
      delay(500); 
    }
  }
  
  if (!sdReady) {
    Serial.println("CRITICAL ERROR: SD Card unavailable! Halting system to prevent data loss.");
    // Blink LED red forever and halt execution
    while (true) {
      setLED(255, 0, 0);
      delay(500);
      setLED(0, 0, 0);
      delay(500);
    }
  }
  
  // 1. WI-FI PROVISIONING & STARTUP
  preferences.begin("wifi", false);
  // Use the global variables as default fallbacks
  ssid = preferences.getString("ssid", ssid);
  password = preferences.getString("password", password);

  if (ssid == "") { // Force AP mode if it's empty
    Serial.println("No valid Wi-Fi credentials found! Starting AP mode...");
    isAPMode = true;
  } else {
    WiFi.mode(WIFI_STA);
    WiFi.setTxPower(WIFI_POWER_8_5dBm); // CRITICAL: Prevents 500mA spike that browns out SD card
    WiFi.setAutoReconnect(true);
    WiFi.begin(ssid.c_str(), password.c_str());
    
    Serial.print("Connecting to Wi-Fi");
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 20) {
      delay(500);
      Serial.print(".");
      retries++;
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nConnected! ESP32 IP Address: " + WiFi.localIP().toString());
    } else {
      Serial.println("\nConnection failed! Starting AP fallback while continuing to search...");
      // Use AP_STA so it hosts the setup portal BUT the watchdog keeps scanning!
      WiFi.mode(WIFI_AP_STA); 
      WiFi.softAP("BioSync_Setup", "12345678");
      Serial.println("AP Mode Started: Connect to 'BioSync_Setup' (Password: 12345678)");
      Serial.println("ESP32 IP Address: " + WiFi.softAPIP().toString());
      isAPMode = true;
    }
  }

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
  Serial.println("Initializing R307S Fingerprint Sensor...");
  mySerial.begin(57600, SERIAL_8N1, R307_RX_PIN, R307_TX_PIN);
  finger.begin(57600);
  if (finger.verifyPassword()) {
    Serial.println("Fingerprint sensor found!");
    
    // CRITICAL CLONE FIX: Some generic R307S sensors report a broken "capacity" of 0 or 1.
    // This physically prevents the fingerSearch() function from looking past ID 1!
    // We force the capacity to 1000 to guarantee it searches the entire flash database.
    finger.capacity = 1000; 
    
    setLED(0, 255, 0); // Green = Ready
    playBeep(200);
    delay(1000);
    setLED(0, 0, 0);
  } else {
    Serial.println("ERROR: Did not find fingerprint sensor!");
    setLED(255, 0, 0); // Red = Sensor Error
  }

  // 3. UDP DISCOVERY SERVER
  Serial.println("Starting UDP Server on port 8888...");
  udp.begin(UDP_PORT);
  
  Serial.println("Starting HTTP Server on port 80...");

  // 4. API ENDPOINTS FOR PYTHON APP
  server.on("/status", HTTP_GET, []() {
    String json = "{\"status\":\"" + currentStatus + "\",";
    json += "\"last_id\":" + String(lastScannedID) + ",";
    json += "\"enrolled\":" + String(finger.templateCount) + ",";
    json += "\"uptime\":" + String(millis() / 1000) + ",";
    json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
    
    if (rtcReady) {
      DateTime now = rtc.now();
      json += "\"time\":\"" + now.timestamp(DateTime::TIMESTAMP_FULL) + "\"}";
    } else {
      json += "\"time\":\"unavailable\"}";
    }
    server.send(200, "application/json", json);
  });

  server.on("/poll", HTTP_GET, []() {
    lastPollTime = millis();
    String json;
    if (lastScannedID != -1) {
      json = "{\"id\":" + String(lastScannedID) + ",\"confidence\":98,\"timestamp\":\"" + lastScannedTimestamp + "\"}";
      lastScannedID = -1; // Reset after reading
    } else {
      json = "{\"id\":-1}";
    }
    String encrypted = encryptPayload(json);
    server.send(200, "text/plain", encrypted);
  });

  server.on("/sync_offline", HTTP_GET, []() {
    if (!sdReady) {
      server.send(500, "text/plain", "SD Card not initialized");
      return;
    }
    File file = SD.open("/queue.csv");
    if (!file) {
      server.send(200, "text/plain", ""); // No offline data
      return;
    }
    String data = "";
    while (file.available()) {
      data += (char)file.read();
    }
    file.close();
    if (data.length() > 0) {
      server.send(200, "text/plain", data);
      SD.remove("/queue.csv");
    } else {
      server.send(200, "text/plain", ""); // No offline data
    }
  });

  server.on("/start_enroll", HTTP_GET, []() {
    Serial.println("[API] Received /start_enroll request");
    if (server.hasArg("id")) {
      targetID = server.arg("id").toInt();
      isEnrolling = true;
      enrollStep = 1;
      currentStatus = "Place finger to enroll ID " + String(targetID);
      setLED(0, 0, 255); // Blue for enroll mode
      Serial.println("[API] Enrollment started for ID: " + String(targetID));
      server.send(200, "text/plain", "Enrollment started");
    } else {
      Serial.println("[API] /start_enroll missing ID!");
      server.send(400, "text/plain", "Missing ID");
    }
  });

  server.on("/clear_sensor", HTTP_GET, []() {
    finger.emptyDatabase();
    server.send(200, "text/plain", "Sensor memory completely wiped.");
    Serial.println("[API] Sensor database wiped by user!");
  });

  server.on("/sync_time", HTTP_GET, []() {
    if (server.hasArg("y") && server.hasArg("m") && server.hasArg("d") && server.hasArg("h") && server.hasArg("min") && server.hasArg("s")) {
      if (rtcReady) {
        rtc.adjust(DateTime(
          server.arg("y").toInt(),
          server.arg("m").toInt(),
          server.arg("d").toInt(),
          server.arg("h").toInt(),
          server.arg("min").toInt(),
          server.arg("s").toInt()
        ));
        server.send(200, "text/plain", "RTC time synchronized with PC!");
        Serial.println("[API] RTC time synchronized!");
      } else {
        server.send(500, "text/plain", "RTC not ready");
      }
    } else {
      server.send(400, "text/plain", "Missing time arguments");
    }
  });

  server.on("/set_wifi", HTTP_GET, []() {
    if (server.hasArg("ssid") && server.hasArg("pass")) {
      preferences.putString("ssid", server.arg("ssid"));
      preferences.putString("password", server.arg("pass"));
      server.send(200, "text/plain", "Credentials saved! Rebooting...");
      delay(1000);
      ESP.restart();
    } else {
      server.send(400, "text/plain", "Missing ssid or pass parameters");
    }
  });

  server.on("/delete_finger", HTTP_GET, []() {
    if (server.hasArg("id")) {
      int id = server.arg("id").toInt();
      if (finger.deleteModel(id) == FINGERPRINT_OK) {
        server.send(200, "text/plain", "Finger deleted successfully.");
        Serial.println("[API] Deleted finger ID: " + String(id));
      } else {
        server.send(500, "text/plain", "Failed to delete finger from sensor memory.");
        Serial.println("[API] Failed to delete finger ID: " + String(id));
      }
    } else {
      server.send(400, "text/plain", "Missing ID parameter");
    }
  });

  server.begin();
}

void loop() {
  server.handleClient(); // Listen for Python requests

  // Wi-Fi Auto-Reconnect Watchdog (Non-Blocking)
  static unsigned long lastWifiCheck = millis();
  if (ssid != "") { // Always try to reconnect if we have credentials, regardless of AP mode
    if (WiFi.status() != WL_CONNECTED) {
      if (millis() - lastWifiCheck > 15000) { // Try reconnecting every 15 seconds
        Serial.println("Wi-Fi connection lost! Performing hardware-level Wi-Fi reset...");
        WiFi.disconnect();
        WiFi.mode(WIFI_OFF);
        delay(50);
        // If we were hosting the AP portal, keep hosting it while resetting STA
        WiFi.mode(isAPMode ? WIFI_AP_STA : WIFI_STA);
        WiFi.setTxPower(WIFI_POWER_8_5dBm);
        WiFi.begin(ssid.c_str(), password.c_str());
        lastWifiCheck = millis();
      }
    } else {
      lastWifiCheck = millis(); // Keep timer reset while connected
    }
  }

  // If in AP Mode, the device acts as a standalone offline logger.
  // The user can connect to the BioSync_Setup AP to configure Wi-Fi,
  // but it will continue scanning fingers and logging to SD!

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
        Serial.println("[ENROLL] Step 1: Image taken");
        if (finger.image2Tz(1) == FINGERPRINT_OK) {
          Serial.println("[ENROLL] Step 1: Converted to Tz1");
          currentStatus = "Remove finger";
          playBeep(100);
          enrollStep = 2;
          delay(1000); // Wait for user to remove finger
        } else {
          Serial.println("[ENROLL] Step 1: image2Tz(1) failed (messy print)");
        }
      }
    } 
    else if (enrollStep == 2) {
      if (finger.getImage() == FINGERPRINT_NOFINGER) {
        Serial.println("[ENROLL] Step 2: Finger removed");
        currentStatus = "Place same finger again";
        enrollStep = 3;
      }
    } 
    else if (enrollStep == 3) {
      if (finger.getImage() == FINGERPRINT_OK) {
        Serial.println("[ENROLL] Step 3: Second image taken");
        if (finger.image2Tz(2) == FINGERPRINT_OK) {
          Serial.println("[ENROLL] Step 3: Converted to Tz2");
          if (finger.createModel() == FINGERPRINT_OK) {
            Serial.println("[ENROLL] Step 3: Model created successfully!");
            if (finger.storeModel(targetID) == FINGERPRINT_OK) {
              Serial.println("[ENROLL] Step 3: Stored model in flash at ID " + String(targetID));
              currentStatus = "Success! ID " + String(targetID) + " enrolled.";
              playBeep(200);
              setLED(0, 255, 0);
            } else {
              Serial.println("[ENROLL] Error: storeModel failed!");
              currentStatus = "Error: Failed to save.";
              setLED(255, 0, 0);
            }
          } else {
            Serial.println("[ENROLL] Error: createModel failed (Prints did not match)");
            currentStatus = "Error: Prints did not match.";
            setLED(255, 0, 0);
          }
          
          // Non-blocking delay to allow Python app to fetch the status
          unsigned long startWait = millis();
          while (millis() - startWait < 2000) {
            server.handleClient();
            delay(10);
          }
          
          setLED(0, 0, 0);
          isEnrolling = false; // Exit enroll mode
          currentStatus = "Idle. Ready to scan.";
          Serial.println("[ENROLL] Exited enrollment mode.");
        } else {
          Serial.println("[ENROLL] Step 3: image2Tz(2) failed (messy print)");
        }
      }
    }
  } 
  // Handle Normal Scanning
  else {
    uint8_t p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      Serial.println("[SCAN] Image taken");
      p = finger.image2Tz();
      if (p == FINGERPRINT_OK) {
        Serial.println("[SCAN] Image converted");
        p = finger.fingerSearch();
        if (p == FINGERPRINT_OK) {
          int scannedID = finger.fingerID;
          Serial.println("[SCAN] Match found! ID: " + String(scannedID) + " Confidence: " + String(finger.confidence));
          
          // Duplicate Punch Cooldown Check
          if (scannedID < 256 && (millis() - lastPunchMillis[scannedID] < COOLDOWN_MS)) {
            currentStatus = "Cooldown active for ID " + String(scannedID);
            setLED(255, 255, 0); // Yellow flash for cooldown
            playBeep(300, 1000);
            delay(1000);
            setLED(0, 0, 0);
            return;
          }
          
          if (scannedID < 256) {
            lastPunchMillis[scannedID] = millis();
          }
          
          lastScannedID = scannedID;
          currentStatus = "Scanned ID: " + String(lastScannedID);
          
          if (rtcReady) {
            DateTime now = rtc.now();
            lastScannedTimestamp = String(now.year()) + "-" + String(now.month()) + "-" + String(now.day()) + "T" + String(now.hour()) + ":" + String(now.minute()) + ":" + String(now.second());
          } else {
            lastScannedTimestamp = String(millis());
          }
          
          // Toggle hardware state for LED colors
          isCheckedIn[scannedID] = !isCheckedIn[scannedID];
          if (isCheckedIn[scannedID]) {
            setLED(0, 255, 0); // Green for Check-In
          } else {
            setLED(0, 0, 255); // Blue for Check-Out
          }
          
          playBeep(100, 2500); delay(50); playBeep(100, 2500);
          
          unsigned long timeSinceLastPoll = millis() - lastPollTime;
          Serial.println("Watchdog: Time since last Python poll = " + String(timeSinceLastPoll) + "ms");
          
          // 30s threshold: Python app worst-case cycle = 5s + 5s + 1s + overhead
          if (timeSinceLastPoll > 30000) {
            logOfflineScan(lastScannedID);
            lastScannedID = -1; // Clear it so it isn't polled later
            currentStatus = "Offline: Saved to SD";
          }
          
          delay(1000);
          setLED(0, 0, 0);
        } else {
          Serial.println("[SCAN] fingerSearch failed with code: 0x" + String(p, HEX));
          if (p == FINGERPRINT_NOTFOUND) {
            Serial.println(" -> NOT FOUND (Fingerprint does not match any enrolled IDs)");
          }
          currentStatus = "Unknown Finger";
          setLED(255, 0, 0);
          playBeep(500, 1000);
          delay(1000);
          setLED(0, 0, 0);
        }
      } else {
        Serial.println("[SCAN] image2Tz failed with code: 0x" + String(p, HEX));
        if (p == FINGERPRINT_IMAGEMESS) {
          Serial.println(" -> IMAGE MESS (Image too blurry or messy)");
        } else if (p == FINGERPRINT_FEATUREFAIL) {
          Serial.println(" -> FEATURE FAIL (Could not find fingerprint features)");
        }
      }
    } else if (p != FINGERPRINT_NOFINGER) {
      // Ignore NOFINGER because that just means no one is touching it
      Serial.println("[SCAN] getImage failed with code: 0x" + String(p, HEX));
    }
  }
}