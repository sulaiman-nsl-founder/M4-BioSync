# Functional Specification Document (FSD)
## Smart Biometric Attendance System — ESP32 + R307S

**Document Version:** 1.0  
**Date:** August 2026  
**Status:** Draft

---

## 1. Document Overview

This FSD defines the complete functional requirements, system behavior, data flows, error handling, and test cases for the Smart Biometric Attendance System. It serves as the binding specification between hardware firmware and the companion desktop application.

---

## 2. System Overview

The system consists of two primary subsystems:

| Subsystem | Platform | Role |
|-----------|----------|------|
| **Attendance Terminal** | ESP32-WROOM-32 + R307S | Captures fingerprints, encrypts data, serves HTTP API |
| **Companion Application** | Windows PC (Python) | Discovers device, decrypts data, manages users, syncs to cloud |

Communication occurs over **Wi-Fi LAN** using HTTP (REST) and UDP protocols with AES-128 encrypted payloads.

---

## 3. Functional Requirements

### 3.1 FR-01: Fingerprint Enrollment

| Field | Detail |
|-------|--------|
| **ID** | FR-01 |
| **Priority** | High |
| **Description** | The system shall allow enrolling new fingerprints with a unique ID (1–127) |
| **Trigger** | Companion app sends `POST /enroll?id=<N>` |
| **Process** | 1. ESP32 receives enrollment request<br>2. LED turns BLUE, buzzer plays enrollment tone<br>3. User places finger twice for template capture<br>4. R307S stores template in flash memory<br>5. LED turns GREEN on success, RED on failure |
| **Success Criteria** | Fingerprint template stored, HTTP 200 returned with `{"status":"enrolled","id":N}` |
| **Error Cases** | Invalid ID → HTTP 400; Sensor timeout → HTTP 408; Duplicate template → HTTP 409 |

### 3.2 FR-02: Fingerprint Identification (Attendance Marking)

| Field | Detail |
|-------|--------|
| **ID** | FR-02 |
| **Priority** | High |
| **Description** | The system shall identify a placed finger and record attendance |
| **Trigger** | User places finger on R307S sensor |
| **Process** | 1. R307S detects finger presence<br>2. Captures image, generates template, searches library<br>3. If match found: LED GREEN + success beep + store event<br>4. If no match: LED RED + error beep |
| **Output** | Attendance event stored in ESP32 buffer with ID, confidence score, and timestamp |
| **Performance** | Identification shall complete within 1 second |

### 3.3 FR-03: UDP Device Discovery

| Field | Detail |
|-------|--------|
| **ID** | FR-03 |
| **Priority** | High |
| **Description** | The companion app shall auto-discover the ESP32 on the local network |
| **Protocol** | UDP Broadcast on port 8888 |
| **Process** | 1. App broadcasts `FIND_ATTENDANCE_DEVICE` to `255.255.255.255:8888`<br>2. ESP32 UDP listener receives packet<br>3. ESP32 replies with `ATTENDANCE_DEVICE:<IP_ADDRESS>:<DEVICE_NAME>` |
| **Timeout** | 5 seconds; retry up to 3 times before showing "Device Not Found" |

### 3.4 FR-04: Attendance Data Polling

| Field | Detail |
|-------|--------|
| **ID** | FR-04 |
| **Priority** | High |
| **Description** | Companion app shall continuously poll ESP32 for new attendance events |
| **Endpoint** | `GET /poll` |
| **Response** | AES-128 encrypted JSON: `{"id": N, "confidence": C, "timestamp": T}` |
| **Polling Interval** | 1 second (configurable) |
| **Threading** | Background thread to prevent UI freeze |

### 3.5 FR-05: AES-128 Payload Encryption

| Field | Detail |
|-------|--------|
| **ID** | FR-05 |
| **Priority** | High |
| **Description** | All data payloads between ESP32 and companion app shall be AES-128 encrypted |
| **Algorithm** | AES-128-ECB (upgradeable to CBC) |
| **Key Management** | Pre-shared 16-byte symmetric key hardcoded on both endpoints |
| **ESP32 Library** | mbedTLS (built into ESP-IDF) |
| **Python Library** | PyCryptodome (`Crypto.Cipher.AES`) |
| **Payload Flow** | ESP32: JSON → Pad → AES Encrypt → Base64 Encode → HTTP Body |
| **Decryption Flow** | App: HTTP Body → Base64 Decode → AES Decrypt → Unpad → JSON Parse |

### 3.6 FR-06: User Management (Local Database)

| Field | Detail |
|-------|--------|
| **ID** | FR-06 |
| **Priority** | Medium |
| **Description** | Companion app shall maintain a local mapping of fingerprint IDs to user names/roles |
| **Storage** | CSV file managed via Pandas DataFrame |
| **Fields** | `id, name, role, department, enrolled_date` |
| **Operations** | Add, edit, delete, search user records |

### 3.7 FR-07: Google Sheets Cloud Synchronization

| Field | Detail |
|-------|--------|
| **ID** | FR-07 |
| **Priority** | Medium |
| **Description** | Attendance records shall be automatically synced to a Google Sheet |
| **Library** | `gspread` with Service Account JSON key authentication |
| **Sheet Columns** | `Date, Time, User ID, User Name, Department, Confidence Score` |
| **Sync Trigger** | Each successful attendance event triggers an append operation |
| **Offline Handling** | Queue events locally; batch sync when connection resumes |

### 3.8 FR-08: Visual Feedback (WS2812B LED)

| State | LED Color | Pattern |
|-------|-----------|---------|
| System Ready / Idle | CYAN | Slow breathing (fade in/out) |
| Finger Detected | WHITE | Solid |
| Identification Success | GREEN | 3 flashes then return to idle |
| Identification Failure | RED | 3 flashes then return to idle |
| Enrollment Mode | BLUE | Pulsing |
| Enrollment Success | GREEN | Solid 2 seconds |
| Enrollment Failure | RED | Solid 2 seconds |
| Wi-Fi Connecting | YELLOW | Fast blink |
| Error / Fault | RED | Rapid strobe |

### 3.9 FR-09: Auditory Feedback (Buzzer)

| Event | Tone Pattern |
|-------|-------------|
| Attendance Success | Two short ascending beeps (1000Hz → 1500Hz, 100ms each) |
| Attendance Failure | One long low beep (400Hz, 500ms) |
| Enrollment Step | Single medium beep (800Hz, 200ms) |
| Enrollment Complete | Three ascending beeps |
| System Boot | Rising sweep (500Hz → 2000Hz, 300ms) |
| Error | Three rapid low beeps (300Hz, 100ms each) |

### 3.10 FR-10: Power Management

| Field | Detail |
|-------|--------|
| **ID** | FR-10 |
| **Priority** | High |
| **Description** | Firmware shall reduce Wi-Fi TX power to prevent USB brownouts |
| **Implementation** | `WiFi.setTxPower(WIFI_POWER_8_5dBm)` as first line in `setup()` |
| **Rationale** | Combined R307S + Wi-Fi + LED current draw can exceed USB 500mA limit |

---

## 4. Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-01 | **Performance** | Fingerprint identification ≤ 1 second |
| NFR-02 | **Reliability** | System shall operate continuously for 8+ hours without restart |
| NFR-03 | **Security** | All wireless payloads encrypted with AES-128 |
| NFR-04 | **Usability** | Companion app usable without technical training |
| NFR-05 | **Scalability** | Architecture supports future multi-device management |
| NFR-06 | **Portability** | Companion app runs on Windows 10/11 without Python installation |
| NFR-07 | **Accuracy** | FAR < 0.001%, FRR < 1% (per R307S sensor specification) |
| NFR-08 | **Availability** | Offline operation: local attendance logging when cloud unavailable |

---

## 5. Data Flow Diagram

### 5.1 Level 0 — Context Diagram
```
                    Fingerprint
  [User] ─────────────────────► [Attendance Terminal]
                                       │
                              AES Encrypted Data
                              (Wi-Fi HTTP/UDP)
                                       │
                                       ▼
                              [Companion App (PC)]
                                       │
                              Google Sheets API
                                       │
                                       ▼
                              [Google Cloud Sheets]
                                       │
                                       ▼
                              [Admin / Manager]
```

### 5.2 Level 1 — Process Decomposition
```
  P1: Fingerprint Capture ──► P2: Template Matching ──► P3: Event Encryption
         │                                                       │
         ▼                                                       ▼
  P4: LED/Buzzer Feedback                              P5: HTTP API Response
                                                                 │
                                                                 ▼
                                                      P6: AES Decryption
                                                                 │
                                                                 ▼
                                                      P7: Local DB Update
                                                                 │
                                                                 ▼
                                                      P8: Cloud Sync
```

---

## 6. API Specification

### 6.1 `GET /poll`
```json
// Response (after AES decryption + Base64 decode):
{
  "status": "match_found",
  "last_id": 5,
  "confidence": 98,
  "timestamp": "2026-08-14T14:30:00"
}
```

### 6.2 `POST /enroll?id=<N>`
```json
// Response:
{
  "status": "enrolled",
  "id": 5,
  "message": "Fingerprint enrolled successfully"
}
```

### 6.3 `GET /status`
```json
{
  "status": "Ready",
  "enrolled_count": 12,
  "last_id": -1,
  "uptime_seconds": 3600,
  "wifi_rssi": -45
}
```

### 6.4 UDP Discovery
```
// Client → Broadcast:
FIND_ATTENDANCE_DEVICE

// ESP32 → Reply:
ATTENDANCE_DEVICE:192.168.1.100:UNIT_01
```

---

## 7. Error Handling Matrix

| Error Code | Condition | Firmware Response | App Response |
|------------|-----------|-------------------|--------------|
| E-01 | R307S sensor not detected at boot | RED LED strobe, error beep, halt | Show "Sensor Error" |
| E-02 | Wi-Fi connection failed | YELLOW blink, retry every 10s | Show "Connecting..." |
| E-03 | Fingerprint capture timeout (5s) | Return to idle, single error beep | Log timeout event |
| E-04 | Enrollment duplicate ID | HTTP 409, RED LED | Show "ID already exists" |
| E-05 | AES decryption failure | — | Log error, request re-poll |
| E-06 | Google Sheets API unreachable | — | Queue locally, retry in 60s |
| E-07 | UDP discovery timeout | — | Show "Device not found", manual IP entry option |
| E-08 | Sensor library full (127 templates) | HTTP 507, error beep | Show "Storage full" |
| E-09 | Power brownout detected | ESP32 auto-restart, log event | Show "Device restarted" |
| E-10 | Invalid enrollment ID (not 1-127) | HTTP 400 | Show validation error |

---

## 8. Test Cases

### 8.1 Hardware Tests

| TC-ID | Test Case | Steps | Expected Result |
|-------|-----------|-------|-----------------|
| TC-H01 | R307S UART Communication | Power on, check Serial2 init | Sensor responds with ACK |
| TC-H02 | WS2812B LED Color Cycle | Boot sequence | LED cycles R→G→B→CYAN |
| TC-H03 | Buzzer Tone Test | Boot sequence | Rising sweep tone plays |
| TC-H04 | Power Stability Test | Run all peripherals for 30 min | No brownout resets |
| TC-H05 | Sensor False Acceptance | Test 50 unenrolled fingers | 0 false accepts (FAR<0.001%) |

### 8.2 Firmware Tests

| TC-ID | Test Case | Steps | Expected Result |
|-------|-----------|-------|-----------------|
| TC-F01 | Wi-Fi Connection | Boot with valid credentials | Connected, IP assigned |
| TC-F02 | UDP Discovery Response | Send discovery broadcast | ESP32 replies with IP |
| TC-F03 | HTTP /poll Endpoint | GET /poll via browser | Returns AES encrypted JSON |
| TC-F04 | Enrollment Flow | POST /enroll?id=1 + 2x finger | Template stored, HTTP 200 |
| TC-F05 | AES Encryption Validity | Decrypt response with known key | Valid JSON recovered |
| TC-F06 | Concurrent Requests | 5 simultaneous /poll requests | All return valid responses |

### 8.3 Application Tests

| TC-ID | Test Case | Steps | Expected Result |
|-------|-----------|-------|-----------------|
| TC-A01 | Auto-Discovery | Launch app on same subnet | ESP32 found within 5 seconds |
| TC-A02 | Live Attendance Feed | Scan enrolled finger | Event appears in dashboard |
| TC-A03 | AES Decryption | Receive encrypted payload | Decrypted JSON displayed |
| TC-A04 | User Management CRUD | Add/edit/delete user | CSV updated correctly |
| TC-A05 | Google Sheets Sync | Mark attendance | Row appended to Google Sheet |
| TC-A06 | Offline Resilience | Disconnect internet, scan | Event queued, syncs on reconnect |
| TC-A07 | .exe Deployment | Run on clean Windows PC | App launches without Python |
| TC-A08 | UI Responsiveness | Scan during poll | UI does not freeze |

---

## 9. Security Considerations

1. **Encryption:** AES-128 symmetric encryption prevents packet sniffing on shared Wi-Fi.
2. **Key Storage:** Pre-shared key stored in firmware flash; companion app config file.
3. **Network Isolation:** System operates on LAN only; no internet-facing endpoints.
4. **Anti-Replay:** Timestamp validation prevents replayed attendance events.
5. **Sensor Tamper:** R307S has built-in anti-spoofing for basic fake-finger detection.

---

## 10. Future Enhancements

1. Upgrade to AES-256-CBC with IV for stronger encryption
2. Add MQTT protocol support for IoT platform integration
3. Implement OTA firmware updates via companion app
4. Add face recognition as secondary biometric factor
5. Mobile app (Flutter) for remote monitoring
6. Custom PCB design to replace breadboard prototype
7. RFID fallback for users with unreadable fingerprints
8. Attendance analytics dashboard with charts and export

---

**Document End**
