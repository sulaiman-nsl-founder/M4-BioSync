#include <WiFi.h>
#include <WebServer.h>
#include <Adafruit_Fingerprint.h>
#include <Adafruit_NeoPixel.h>

// --- HARDWARE PINS ---
#define R307_RX_PIN  16
#define R307_TX_PIN  17
#define LED_PIN      18
#define BUZZER_PIN   19
#define NUM_LEDS     1

// --- WI-FI CREDENTIALS ---
const char* ssid = "Nsl";          // REPLACE with your exact Wi-Fi name
const char* password = "12345678"; // REPLACE with your Wi-Fi password

// --- INSTANCES ---
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);
Adafruit_NeoPixel pixels(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);
WebServer server(80);

// --- GLOBAL VARIABLES ---
String currentStatus = "Idle. Ready to scan.";
int lastScannedID = -1;
bool isEnrolling = false;
int enrollStep = 0;
int targetID = 0;

void setLED(uint8_t r, uint8_t g, uint8_t b) {
  pixels.setPixelColor(0, pixels.Color(r, g, b));
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

  // 3. API ENDPOINTS FOR PYTHON APP
  server.on("/status", HTTP_GET, []() {
    // Python asks for the current state
    String json = "{\"status\":\"" + currentStatus + "\", \"last_id\":" + String(lastScannedID) + "}";
    server.send(200, "application/json", json);
    lastScannedID = -1; // Reset after reading
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