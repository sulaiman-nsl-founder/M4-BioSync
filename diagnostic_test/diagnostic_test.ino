#include <Adafruit_Fingerprint.h>
#include <Adafruit_NeoPixel.h>
#include <RTClib.h>
#include <SPI.h>
#include <SD.h>

// --- Pin Definitions ---
// R307S Fingerprint Sensor (Serial2)
#define FINGER_RX 16
#define FINGER_TX 17

// WS2812B LED Ring
#define LED_PIN 18
#define NUM_LEDS 8

// Buzzer
#define BUZZER_PIN 19

// SD Card (HSPI)
#define SD_CS 15
#define SPI_SCK 14
#define SPI_MISO 12
#define SPI_MOSI 13

// DS1307 RTC (I2C default: SDA=21, SCL=22)

// --- Object Instantiations ---
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);
Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);
RTC_DS1307 rtc;
SPIClass spiHSPI(HSPI);

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  
  Serial.println("\n--- BioSync Phase 1: Diagnostic Test ---");

  // 1. Buzzer Validation
  Serial.println("\n[1] Testing Buzzer...");
  pinMode(BUZZER_PIN, OUTPUT);
  // Play rising sweep tone (500Hz -> 2000Hz) on boot
  for (int freq = 500; freq <= 2000; freq += 100) {
    tone(BUZZER_PIN, freq, 50);
    delay(50);
  }
  noTone(BUZZER_PIN);
  
  // 2. LED Validation
  Serial.println("\n[2] Testing WS2812B LEDs...");
  strip.begin();
  strip.setBrightness(50);
  strip.show(); // Initialize all pixels to 'off'
  
  uint32_t colors[] = {
    strip.Color(255, 0, 0),    // RED
    strip.Color(0, 255, 0),    // GREEN
    strip.Color(0, 0, 255),    // BLUE
    strip.Color(0, 255, 255),  // CYAN
    strip.Color(0, 0, 0)       // OFF
  };
  
  for(int c=0; c<5; c++) {
    for(int i=0; i<NUM_LEDS; i++) {
      strip.setPixelColor(i, colors[c]);
    }
    strip.show();
    delay(500);
  }
  
  // 3. Sensor Communication Test
  Serial.println("\n[3] Testing R307S Fingerprint Sensor...");
  mySerial.begin(57600, SERIAL_8N1, FINGER_RX, FINGER_TX);
  finger.begin(57600);
  if (finger.verifyPassword()) {
    Serial.println("  -> Found fingerprint sensor!");
  } else {
    Serial.println("  -> ERROR: Did not find fingerprint sensor :(");
  }

  // 4. RTC Validation
  Serial.println("\n[4] Testing DS1307 RTC...");
  if (!rtc.begin()) {
    Serial.println("  -> ERROR: Couldn't find RTC");
  } else {
    if (!rtc.isrunning()) {
      Serial.println("  -> RTC is NOT running, setting the time to compile time!");
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
    DateTime now = rtc.now();
    Serial.print("  -> Current time: ");
    Serial.print(now.year(), DEC);
    Serial.print('/');
    Serial.print(now.month(), DEC);
    Serial.print('/');
    Serial.print(now.day(), DEC);
    Serial.print(" ");
    Serial.print(now.hour(), DEC);
    Serial.print(':');
    Serial.print(now.minute(), DEC);
    Serial.print(':');
    Serial.print(now.second(), DEC);
    Serial.println();
  }

  // 5. SD Card Validation
  Serial.println("\n[5] Testing SD Card...");
  spiHSPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI, SD_CS);
  if (!SD.begin(SD_CS, spiHSPI)) {
    Serial.println("  -> ERROR: SD Card initialization failed!");
  } else {
    Serial.println("  -> SD Card initialized.");
    File testFile = SD.open("/test.txt", FILE_WRITE);
    if (testFile) {
      testFile.println("BioSync Phase 1 SD Test");
      testFile.close();
      Serial.println("  -> Successfully wrote to /test.txt");
    } else {
      Serial.println("  -> ERROR: opening /test.txt for writing");
    }
    
    testFile = SD.open("/test.txt");
    if (testFile) {
      Serial.print("  -> Read from /test.txt: ");
      while (testFile.available()) {
        Serial.write(testFile.read());
      }
      testFile.close();
    } else {
      Serial.println("  -> ERROR: opening /test.txt for reading");
    }
  }
  
  Serial.println("\n--- Setup Complete. Testing Integrated Feedback ---");
  Serial.println("Waiting for finger touch... (Runs indefinitely to test power stability)");
}

void loop() {
  // 6. Integrated Feedback Test
  if (finger.getImage() == FINGERPRINT_OK) {
    Serial.println("Finger detected!");
    
    // All 8 LEDs turn GREEN
    for(int i=0; i<NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(0, 255, 0));
    }
    strip.show();
    
    // Two ascending beeps
    tone(BUZZER_PIN, 1000, 100);
    delay(150);
    tone(BUZZER_PIN, 1500, 100);
    delay(150);
    noTone(BUZZER_PIN);
    
    // Wait until finger is removed
    while (finger.getImage() == FINGERPRINT_OK) {
      delay(10);
    }
    
    // Turn off LEDs
    for(int i=0; i<NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(0, 0, 0));
    }
    strip.show();
  }
  
  delay(50);
}
