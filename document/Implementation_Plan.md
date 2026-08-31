# 🚀 Detailed Implementation Plan
## M4 BioSync — Smart Biometric Attendance System
### ESP32 + R307S + DS1307 RTC + SD Card

**Document Version:** 3.0  
**Organization:** BioSync Startup  
**Methodology:** Modular Incremental Development (6 Phases)  
**Estimated Duration:** 14–16 Weeks

---

## Feature Set Overview

### 🔵 Essential Features (Foundation)

| Category | Feature |
|----------|---------|
| **User & Enrollment Management** | Admin PIN authentication, Biometric enrollment wizard (2-step), Employee profile CRUD (Name, ID, Dept, Designation) |
| **Attendance & Timing Engine** | Real-time punch logging (YYYY-MM-DD HH:MM:SS), NTP + RTC sync, duplicate punch cooldown, punch type detection |
| **Data Management** | CSV/Excel export, SD Card offline backup, daily attendance summaries |
| **Hardware Feedback** | LED states for all scan outcomes, device connectivity indicators via companion app |

### 🟣 Advanced Features (Enterprise)

| Category | Feature |
|----------|---------|
| **Shift & Policy** | Shift management, grace periods, OT calculation, half-day rules |
| **Cloud & Multi-Device** | Google Sheets cloud backup, remote admin access |
| **Security** | RBAC (Super Admin / HR Manager / Viewer), AES-128 encryption, audit trail |
| **Leave Management** | Holiday calendars, leave marking, manual punch correction with reason tags |

### 🎨 UI Design Principles

- **Single-Click Actions** — Primary buttons (+ Add Employee, Export, Filter) always visible in top-right
- **Visual Hierarchy** — Color-coded status tags: 🟢 On-Time, 🟡 Late, 🔴 Absent — no cluttered tables
- **Modal Wizards** — Enrollment and profile editing inside step-by-step modals to keep main screen clean

---

## Phase 1: Hardware Diagnostics & Component Validation
**Duration:** Week 1–2 | **Priority:** Critical | **Dependencies:** None

### 1.1 Objective
Verify all hardware components are functional and the circuit is electrically stable before introducing any networking or software complexity.

### 1.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 1.1 | Circuit Assembly | Wire ESP32 → R307S (GPIO16/17), WS2812B 8-LED (GPIO18), Buzzer (GPIO19), DS1307 RTC (GPIO21/22 I2C), SD Card (GPIO13/12/14/15 HSPI) |
| 1.2 | Diagnostic Firmware | Write `diagnostic_test.ino` — NO Wi-Fi or networking code |
| 1.3 | Sensor Communication Test | Initialize R307S on Serial2 (57600 baud), verify ACK packet received |
| 1.4 | LED Validation | Cycle all 8 WS2812B LEDs through RED → GREEN → BLUE → CYAN → OFF |
| 1.5 | Buzzer Validation | Play rising sweep tone (500Hz → 2000Hz) on boot |
| 1.6 | RTC Validation | Initialize DS1307 via I2C (GPIO21/22), set time, read back to Serial Monitor |
| 1.7 | SD Card Validation | Initialize SD via HSPI, write `test.txt`, read it back, verify data integrity |
| 1.8 | Integrated Feedback Test | On successful finger touch: all 8 LEDs turn GREEN + two ascending beeps |
| 1.9 | Power Stability Test | Run ALL peripherals simultaneously for 30 min, monitor for brownout resets |

### 1.3 Acceptance Criteria
- [ ] R307S responds to serial commands (visible in Serial Monitor)
- [ ] All 8 WS2812B LEDs display all colors correctly
- [ ] Buzzer produces audible tones at correct frequencies
- [ ] DS1307 holds correct time after power cycle (with CR2032 battery backup)
- [ ] SD Card writes and reads `test.txt` successfully
- [ ] Finger touch triggers visual + auditory feedback
- [ ] No brownout resets after 30-minute continuous operation

### 1.4 Deliverables
- `diagnostic_test.ino` — Validated diagnostic firmware
- Hardware verification report (pass/fail for each component)
- Circuit photograph with labeled connections

---

## Phase 2: Firmware — Network, API Core & Offline Engine
**Duration:** Week 3–5 | **Priority:** Critical | **Dependencies:** Phase 1 passed

### 2.1 Objective
Develop production firmware with Wi-Fi connectivity, HTTP REST API, UDP device discovery, AES-128 encryption, DS1307 timestamping, duplicate punch cooldown, and SD Card offline queuing.

### 2.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 2.1 | Power Management | `WiFi.setTxPower(WIFI_POWER_8_5dBm)` to prevent brownout on USB power |
| 2.2 | Wi-Fi Auto-Reconnect | `WiFi.onEvent()` listener — reconnects automatically, no restart needed |
| 2.3 | UDP Discovery Server | Listener on port 8888, reply `ATTENDANCE_DEVICE:<IP>:UNIT_01` |
| 2.4 | HTTP Web Server | `WebServer` on port 80 |
| 2.5 | `/poll` Endpoint | Return latest scan event as AES-encrypted Base64 JSON |
| 2.6 | `/sync_offline` Endpoint | Stream entire SD queue file to caller, then delete the file |
| 2.7 | `/start_enroll` Endpoint | Accept `id` param, initiate 2-step R307S fingerprint enrollment |
| 2.8 | `/status` Endpoint | Return JSON: enrolled count, uptime, Wi-Fi RSSI, RTC time |
| 2.9 | `/update_firmware` Endpoint | Server-pull OTA from URL via `HTTPUpdate.update()` |
| 2.10 | AES-128 Encryption | mbedTLS: JSON → PKCS7 pad → AES-128-ECB → Base64 |
| 2.11 | DS1307 Timestamping | On every valid scan, read RTC time → format `YYYY-MM-DDTHH:MM:SS` |
| 2.12 | Duplicate Punch Cooldown | Reject same ID within configurable timeout (default: 2 min); flash YELLOW LED |
| 2.13 | Offline Queue Logic | If Wi-Fi down: encrypt scan + RTC timestamp → append to `/offline_queue.txt` on SD |
| 2.14 | LED State Machine | ORANGE=booting, CYAN=idle, GREEN=success, RED=error, BLUE=enrolling, YELLOW=cooldown, PURPLE=OTA |
| 2.15 | Buzzer Patterns | Success: 2× ascending beeps; Error: 1× long low beep; Enroll OK: 3× rising beeps |

### 2.3 Firmware Architecture
```
esp32_fingerprint_access_control.ino
├── setup()
│   ├── Wire.begin(21, 22)           // DS1307 I2C
│   ├── spiHSPI.begin(14,12,13,15)   // SD Card HSPI
│   ├── SD.begin(SD_CS, spiHSPI)
│   ├── rtc.begin()
│   ├── WiFi.setTxPower(8.5dBm)
│   ├── WiFi.onEvent(auto_reconnect)
│   ├── WiFi.begin(SSID, PASS)
│   ├── udp.begin(8888)
│   ├── server.on("/poll")
│   ├── server.on("/sync_offline")
│   ├── server.on("/start_enroll")
│   ├── server.on("/status")
│   ├── server.on("/update_firmware")
│   └── server.begin()
│
└── loop()
    ├── server.handleClient()
    ├── handleUDPDiscovery()
    ├── checkFingerprint()          // Non-blocking scan + cooldown check
    ├── updateLEDState()            // State machine tick
    └── handleBuzzerQueue()         // Non-blocking tone queue
```

### 2.4 Acceptance Criteria
- [ ] ESP32 connects to Wi-Fi and prints IP to Serial Monitor
- [ ] ESP32 auto-reconnects without restart when router drops
- [ ] `/poll` returns valid AES-encrypted Base64 with correct RTC timestamp
- [ ] Duplicate scan within 2 min is rejected (YELLOW LED flash)
- [ ] Offline scan is stored to SD with correct RTC timestamp
- [ ] `/sync_offline` delivers all queued data and clears the file
- [ ] OTA update via `/update_firmware?url=...` succeeds with LED feedback

### 2.5 Deliverables
- `esp32_fingerprint_access_control.ino` — Production firmware
- API endpoint reference (curl test results)

---

## Phase 3: Companion App — Core UI, Auth & Polling Engine
**Duration:** Week 6–7 | **Priority:** Critical | **Dependencies:** Phase 2 API functional

### 3.1 Objective
Build the Windows companion application with admin PIN authentication, a professional sidebar-navigation UI, automated UDP device discovery, background HTTP polling, and automatic offline sync trigger.

### 3.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 3.1 | Admin PIN Login Screen | Startup PIN screen — blocks all features until authenticated |
| 3.2 | App Shell & Sidebar Nav | Left sidebar: Dashboard, Attendance, Employees, Reports, Settings |
| 3.3 | Dashboard View | Today's stats card: Total Present, Absent, Late + recent scan feed |
| 3.4 | Device Status Bar | Top bar: ESP32 IP, 🟢/🔴 connection dot, Wi-Fi RSSI, RTC clock |
| 3.5 | UDP Discovery on Launch | Broadcast → auto-fill IP → fallback to manual IP entry dialog |
| 3.6 | Background Polling Engine | `threading.Thread(daemon=True)` polling `/poll` every 1 second |
| 3.7 | Offline Sync Trigger | On reconnect: call `/sync_offline` → decrypt and populate live feed |
| 3.8 | Thread-Safe UI Updates | All widget updates via `self.after(0, callback)` — no UI freezes |
| 3.9 | Live Attendance Feed | Real-time scrollable list with tags: 🟢 On-Time, 🟡 Late, 🔴 Unknown |
| 3.10 | OTA Update Panel | Settings view: file picker → host `.bin` → call `/update_firmware` |
| 3.11 | Local OTA HTTP Server | Background `socketserver.TCPServer` on port 8080 to serve firmware file |

### 3.3 Application UI Layout
```
┌──────────────────────────────────────────────────────────────────┐
│  🔷 M4 BioSync  │  🟢 ESP32 @ 192.168.1.100  │ RSSI:-42 │ 14:30 │
├──────────────┬───────────────────────────────────────────────────┤
│              │                                                    │
│ 📊 Dashboard │   TODAY'S SUMMARY                                 │
│ 🕐 Attendance│   ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│ 👥 Employees │   │Present 24│ │ Absent 3 │ │  Late  2 │         │
│ 📄 Reports   │   └──────────┘ └──────────┘ └──────────┘         │
│ ⚙️ Settings  │                                                    │
│              │   RECENT SCANS                                     │
│              │   14:30:05  Ahmed Ali    IT       ✅ On-Time      │
│              │   14:29:58  Sara Khan    HR       🟡 Late         │
│              │   14:29:45  Ali Hassan   Finance  ✅ On-Time      │
└──────────────┴───────────────────────────────────────────────────┘
```

### 3.4 Acceptance Criteria
- [ ] Admin PIN blocks all screens until the correct code is entered
- [ ] Sidebar navigation switches views smoothly without lag
- [ ] UDP discovery finds ESP32 within 5 seconds on the same subnet
- [ ] UI does NOT freeze during background polling or offline sync
- [ ] Offline queue is auto-fetched and displayed in live feed on reconnect
- [ ] Color-coded status tags (🟢/🟡/🔴) display correctly

### 3.5 Deliverables
- `attendance_app.py` — Updated main app with sidebar shell
- `discovery.py` — UDP discovery module
- `auth.py` — PIN authentication module
- UI screenshots

---

## Phase 4: Employee Management & Enrollment Wizard
**Duration:** Week 7–8 | **Priority:** Critical | **Dependencies:** Phase 3 UI functional

### 4.1 Objective
Build the complete employee profile database and a multi-step modal enrollment wizard with full CRUD operations, search, and deactivation support.

### 4.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 4.1 | Employee Data Schema | `employees.csv`: `emp_id`, `full_name`, `department`, `designation`, `finger_id`, `enrolled_date`, `status` |
| 4.2 | Employee List View | Table: ID, Name, Department, Designation, Status with row actions |
| 4.3 | Search & Filter Bar | Live search by name or dept; filter dropdown (Active/Inactive/All) |
| 4.4 | Enrollment Wizard (Modal) | **Step 1:** Fill profile form → **Step 2:** Place finger → **Step 3:** Place again to confirm → **Step 4:** Success |
| 4.5 | Re-enrollment Flow | For damaged fingers: void old template, restart enrollment for same `emp_id` |
| 4.6 | Edit Profile Modal | Update name, department, designation without re-enrolling fingerprint |
| 4.7 | Deactivate / Delete | Soft-delete preserves history; Hard-delete wipes record permanently |
| 4.8 | Pandas Data Manager | All CRUD operations backed by `employees.csv` via `data_manager.py` |

### 4.3 Enrollment Wizard Modal
```
┌─── Enroll Employee — Step 1 of 3 ────────────────┐
│  Full Name:      [ Ahmed Ali                    ] │
│  Employee ID:    [ EMP-004                      ] │
│  Department:     [ Engineering              ▼  ] │
│  Designation:    [ Senior Engineer              ] │
│                                                   │
│                          [Cancel]  [Next Step →] │
└───────────────────────────────────────────────────┘

┌─── Enroll Employee — Step 2 of 3 ────────────────┐
│                                                   │
│          🔵  Place finger on sensor now...        │
│                                                   │
│  Status: Waiting...                               │
│  [████████████████░░░░] Scan 1 of 2              │
└───────────────────────────────────────────────────┘
```

### 4.4 Acceptance Criteria
- [x] Enrollment wizard guides through all steps with live status updates
- [x] Employee record is created in `employees.csv` after successful enrollment
- [x] Edit and delete operations persist correctly across app restarts
- [x] Re-enrollment successfully replaces the old fingerprint template on R307S
- [x] Inactive employees do not receive attendance entries

### 4.5 Developer Notes & Critical Bug Fixes (Phase 4)
* **Windows Hotspot UDP Routing Bug:** Windows often fails to route `255.255.255.255` UDP broadcast packets to Mobile Hotspot adapters. **Fix:** `discovery.py` was rewritten to dynamically calculate and explicitly broadcast to all local subnets (e.g., `192.168.137.255`), guaranteeing auto-discovery on any network.
* **ESP32 WebServer Blocking:** Using `delay()` on the ESP32 freezes the HTTP server, causing the Python app to miss critical status updates (like `"Success!"`). **Fix:** All blocking delays in the ESP32 firmware were replaced with non-blocking `millis()` loops that continuously call `server.handleClient()`.
* **Pandas Type Coercion:** Pandas automatically inferred numeric `emp_id`s (like `1234`) as `int64`, which broke Python string comparisons during deletion and lookup. **Fix:** Forced `dtype={"emp_id": str}` in `load_employees()`.

---

## Phase 5: Attendance Engine, Reporting & Cloud Sync
**Duration:** Week 9–11 | **Priority:** High | **Dependencies:** Phase 4 complete

### 5.1 Objective
Build the full attendance timing engine covering punch type detection, grace periods, OT calculation, half-day rules, shift configuration, leave management, CSV/Excel export, and Google Sheets cloud sync.

### 5.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 5.1 | Punch Type Engine | Auto-classify each scan: `Check-In`, `Check-Out`, `Break-Out`, `Break-In` |
| 5.2 | Grace Period Rules | Configurable window (default: 15 min). Scans after grace period → `Late In` |
| 5.3 | OT Calculation | Calculate hours worked beyond shift end time → tag as `Overtime` |
| 5.4 | Half-Day Rule | If daily hours < 50% of shift duration → mark `Half-Day` |
| 5.5 | Shift Configuration | Admin UI: create/edit shifts with Name, Start Time, End Time, Active Days |
| 5.6 | Holiday Calendar | Admin marks public + custom holidays. Absent tag suppressed on those days |
| 5.7 | Leave Marking | Admin records approved leave: Sick, Casual, Annual with reason field |
| 5.8 | Manual Punch Correction | Admin adds/edits missed punch with reason tag and manual timestamp |
| 5.9 | AES Decryption | `crypto_utils.py`: Base64 → AES-128-ECB decrypt → PKCS7 unpad → JSON |
| 5.10 | Attendance Log CSV | Each event: `Date, Time, Emp_ID, Name, Dept, Punch_Type, Status, Confidence` |
| 5.11 | CSV / Excel Export | Filter by date range, employee, or department → `.csv` or `.xlsx` |
| 5.12 | Daily Summary Report | Per-employee status: Present/Absent/Late/Half-Day with total hours |
| 5.13 | Google Sheets Sync | `sheets_sync.py` with gspread service-account: real-time row append on each event |
| 5.14 | Offline Cloud Queue | If Sheets API unreachable: queue events in RAM, batch-sync on reconnect |
| 5.15 | Audit Trail Logger | `audit_log.py`: log every admin action (add user, manual punch, leave entry) with timestamp + admin ID |

### 5.3 Acceptance Criteria
- [ ] Check-In / Check-Out correctly auto-classified from scan sequence
- [ ] Late In tag applied when scan occurs after grace period
- [ ] OT hours correctly calculated per employee per day
- [ ] Exported `.csv` / `.xlsx` opens correctly with all expected columns
- [ ] Google Sheet receives new row within 3 seconds of a valid scan
- [ ] Holiday days are not marked as absent
- [ ] Audit trail records every admin modification with timestamp

### 5.4 Deliverables
- `data_manager.py` — Pandas attendance CRUD engine
- `shift_engine.py` — Punch type, OT, grace period logic
- `sheets_sync.py` — Google Sheets integration
- `audit_log.py` — Admin audit trail
- `shift_config.json` — Shift and policy configuration
- `holidays.json` — Holiday calendar

---

## Phase 6: RBAC Security, Testing & Deployment Packaging
**Duration:** Week 12–14 | **Priority:** High | **Dependencies:** All previous phases

### 6.1 Objective
Implement Role-Based Access Control, finalize all security hardening, run comprehensive integration and stress tests, and package the application as a standalone `.exe`.

### 6.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 6.1 | RBAC Engine | Role tiers: `Super Admin` (full), `HR Manager` (reports + leave), `Viewer` (read-only) |
| 6.2 | Secure PIN Storage | Admin PIN stored as bcrypt hash in `config.ini` — never plaintext |
| 6.3 | Session Timeout | Auto-lock after configurable idle period (default: 5 min) |
| 6.4 | Wireshark Validation | Capture HTTP traffic — verify all payloads are ciphertext, no plaintext visible |
| 6.5 | End-to-End Integration Test | Finger scan → RTC timestamp → AES encrypt → HTTP → decrypt → UI → cloud |
| 6.6 | Stress Test | 100 consecutive scans — verify no data loss, no duplicate entries |
| 6.7 | Offline Resilience Test | Simulate Wi-Fi drops → verify SD save → verify auto-sync on reconnect |
| 6.8 | OTA Update Test | Flash new firmware via OTA button in app → verify ESP32 reboots correctly |
| 6.9 | Duplicate Cooldown Test | Scan same finger within 1 min → verify rejection; after timeout → verify acceptance |
| 6.10 | Multi-User Enrollment | Enroll 15+ users, verify >90% identification accuracy |
| 6.11 | UI/UX Polish | Finalize colors, fonts, micro-animations, tooltips, loading states, error messages |
| 6.12 | PyInstaller Packaging | `pyinstaller --noconsole --onefile --icon=icon.ico app.py` |
| 6.13 | .exe Deployment Test | Run on a clean Windows 10/11 PC without Python — verify full functionality |
| 6.14 | Quick-Start Documentation | Setup guide with screenshots for hardware wiring, app install, first enrollment |

### 6.3 RBAC Permission Matrix

| Permission | Super Admin | HR Manager | Viewer |
|------------|:-----------:|:----------:|:------:|
| View Live Attendance | ✅ | ✅ | ✅ |
| Export Reports (CSV/Excel) | ✅ | ✅ | ❌ |
| Enroll / Edit Employees | ✅ | ✅ | ❌ |
| Mark Leave / Manual Punch | ✅ | ✅ | ❌ |
| Shift & Policy Configuration | ✅ | ❌ | ❌ |
| Holiday Calendar Management | ✅ | ❌ | ❌ |
| Device Settings & OTA Update | ✅ | ❌ | ❌ |
| Change Admin PIN | ✅ | ❌ | ❌ |
| View Audit Trail | ✅ | ✅ | ❌ |

### 6.4 Test Results

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-INT-01 | Full scan-to-cloud pipeline | ☐ Pass / ☐ Fail | |
| TC-INT-02 | 100 rapid consecutive scans | ☐ Pass / ☐ Fail | |
| TC-INT-03 | 8-hour continuous operation | ☐ Pass / ☐ Fail | |
| TC-INT-04 | Wi-Fi drop → SD save → auto-sync on reconnect | ☐ Pass / ☐ Fail | |
| TC-INT-05 | Wireshark payload encryption check | ☐ Pass / ☐ Fail | |
| TC-INT-06 | Duplicate punch cooldown rejection | ☐ Pass / ☐ Fail | |
| TC-INT-07 | OTA firmware update via app button | ☐ Pass / ☐ Fail | |
| TC-INT-08 | 15-user enrollment + identification | ☐ Pass / ☐ Fail | |
| TC-INT-09 | RBAC: Viewer blocked from admin actions | ☐ Pass / ☐ Fail | |
| TC-INT-10 | .exe launch on clean Windows 10/11 PC | ☐ Pass / ☐ Fail | |

### 6.5 Acceptance Criteria
- [ ] All 10 integration tests pass
- [ ] Zero data loss in 100-scan stress test
- [ ] Offline scans stored to SD and correctly synced on reconnect
- [ ] Wireshark shows no plaintext attendance data in any HTTP packet
- [ ] .exe runs on clean Windows 10/11 without any Python installation
- [ ] RBAC blocks all unauthorized actions for Viewer and HR Manager roles
- [ ] All 15 enrolled users identified with >90% confidence

### 6.6 Final Deliverables
- `BioSyncAttendance.exe` — Standalone Windows application
- `esp32_fingerprint_access_control.ino` — Production ESP32 firmware
- `service_account.json` — Google Sheets credentials template
- `employees.csv` — Employee database template
- `config.ini` — Application configuration
- `shift_config.json` — Shift and policy definitions
- `holidays.json` — Holiday calendar
- Quick-Start Guide (PDF)
- Test Results Report
- Complete Project Documentation (FSD, Implementation Plan, Project Description)

---

## Appendix A: Complete File Structure

```
M4_BioSync/
├── esp32_fingerprint_access_control/
│   ├── esp32_fingerprint_access_control.ino   # Production ESP32 firmware
│   └── build/                                  # Compiled .bin files (gitignored)
│
├── attendance_app.py       # Main Python app (sidebar navigation shell)
├── auth.py                 # Admin PIN login & RBAC module
├── crypto_utils.py         # AES-128 decryption module
├── discovery.py            # UDP device discovery module
├── data_manager.py         # Pandas/CSV CRUD engine (employees + attendance)
├── shift_engine.py         # Punch type, OT, grace period, half-day logic
├── sheets_sync.py          # Google Sheets sync module
├── audit_log.py            # Admin action audit trail logger
├── config.ini              # Config: AES key, OTA port, cooldown timeout, PIN hash
├── shift_config.json       # Shift definitions (name, start, end, days)
├── holidays.json           # Public and custom holiday calendar
├── service_account.json    # Google Sheets service account (gitignored)
├── requirements.txt        # Python dependencies
│
├── data/
│   ├── employees.csv       # Employee database
│   ├── attendance_log.csv  # Full attendance event log
│   └── audit_trail.csv     # Admin action log
│
├── document/
│   ├── Project Description        # Project overview & BOM
│   ├── FSD.md                     # Functional Specification Document
│   ├── Implementation_Plan.md     # This document
│   └── Quick_Start_Guide.pdf      # Deployment guide
│
└── dist/
    └── BioSyncAttendance.exe      # Packaged standalone executable
```

---

## Appendix B: Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| USB power brownout under full load | High | Critical | Use `WiFi.setTxPower(8.5dBm)`; use powered USB hub |
| R307S false rejection of valid fingers | Medium | High | Clean sensor surface; re-enroll with dry fingers |
| DS1307 clock drift without coin cell battery | Medium | Medium | Install CR2032; verify RTC time on every boot |
| SD Card data corruption on sudden power loss | Low | High | Flush file after every write; use `file.close()` immediately |
| Wi-Fi interference in dense RF environments | Medium | Medium | Use 2.4GHz channel 1, 6, or 11 |
| Google Sheets API rate limiting (60 req/min) | Low | Medium | Batch sync; implement exponential backoff |
| AES pre-shared key compromise | Low | High | Store in `config.ini` (not source code); rotate periodically |
| PyInstaller packaging issues on Windows | Medium | Medium | Test on Windows 10 and 11; include all DLL dependencies |

---

**Document Version:** 3.0  
**Organization:** BioSync Startup  
**Last Updated:** August 2026


---

## Phase 1: Hardware Diagnostics & Component Validation
**Duration:** Week 1–2 | **Priority:** Critical | **Dependencies:** None

### 1.1 Objective
Verify all hardware components are functional and the circuit is electrically stable before introducing networking complexity. This isolates hardware faults from software faults.

### 1.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 1.1 | Circuit Assembly | Wire ESP32 → R307S (GPIO16/17), WS2812B (GPIO18), Buzzer (GPIO19), DS3231 RTC (GPIO21/22 I2C), SD Card (GPIO13/12/14/15 HSPI) |
| 1.2 | Diagnostic Firmware | Write `diagnostic_test.cpp` — NO Wi-Fi logic in this phase |
| 1.3 | Sensor Communication Test | Initialize R307S on Serial2 (57600 baud), verify ACK packet received |
| 1.4 | LED Validation | Cycle WS2812B through RED → GREEN → BLUE → CYAN → OFF |
| 1.5 | Buzzer Validation | Play rising sweep tone (500Hz → 2000Hz) on boot |
| 1.6 | Integrated Feedback Test | On successful finger touch: LED turns GREEN + two ascending beeps |
| 1.7 | RTC Validation | Initialize DS3231 via I2C, set default time, read time successfully |
| 1.8 | SD Card Validation | Initialize SD Card via HSPI, write test file, read test file |
| 1.9 | Power Stability Test | Run all peripherals simultaneously for 30 minutes, monitor Serial for brownout resets |

### 1.3 Firmware Requirements (diagnostic_test.cpp)
```
- Include: Adafruit_Fingerprint.h, Adafruit_NeoPixel.h
- Serial2 initialization: HardwareSerial(2) at 57600 baud, RX=16, TX=17
- NeoPixel initialization: Pin 18, 1 LED, NEO_GRB + NEO_KHZ800
- Buzzer: Pin 19, use tone() function
- Main loop:
  1. Check finger.getImage() for finger presence
  2. On finger detected → LED GREEN + beep
  3. On no finger → LED CYAN (idle breathing)
  4. Print sensor status to Serial Monitor at 115200 baud
- DO NOT include: WiFi.h, WebServer.h, or any networking code
```

### 1.4 Acceptance Criteria
- [ ] R307S responds to serial commands (visible in Serial Monitor)
- [ ] LED displays all colors correctly
- [ ] Buzzer produces audible tones at correct frequencies
- [ ] Finger touch triggers visual + auditory feedback
- [ ] No brownout resets after 30-minute continuous operation
- [ ] Serial Monitor shows no error messages

### 1.5 Deliverables
- `diagnostic_test.cpp` — Validated diagnostic firmware
- Hardware verification report (pass/fail for each component)
- Circuit photograph with labeled connections

---

## Phase 2: Firmware — Network & API Core
**Duration:** Week 3–4 | **Priority:** Critical | **Dependencies:** Phase 1 passed

### 2.1 Objective
Develop the production firmware with Wi-Fi connectivity, HTTP REST API server, UDP device discovery listener, and AES-128 encryption — transforming the ESP32 into a network-accessible attendance terminal.

### 2.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 2.1 | Power Management | Implement `WiFi.setTxPower(WIFI_POWER_8_5dBm)` as FIRST line in `setup()` |
| 2.2 | Wi-Fi Connection | Hardcode SSID/password, connect with retry logic (max 20 attempts, 500ms interval) |
| 2.3 | UDP Discovery Server | Create UDP listener on port 8888, reply to `FIND_ATTENDANCE_DEVICE` with device IP |
| 2.4 | HTTP Web Server | Initialize `WebServer` on port 80 with CORS headers |
| 2.5 | `/poll` Endpoint | Return latest attendance event as AES-encrypted Base64 JSON |
| 2.6 | `/enroll` Endpoint | Accept ID parameter, initiate R307S enrollment sequence (2x finger capture) |
| 2.7 | `/status` Endpoint | Return device health: enrolled count, uptime, Wi-Fi RSSI, last event |
| 2.8 | AES-128 Encryption | Implement using mbedTLS: JSON → PKCS7 pad → AES-128-ECB encrypt → Base64 encode |
| 2.9 | Fingerprint Integration | Merge Phase 1 sensor code with network code; background finger scanning in `loop()` |
| 2.10 | Offline Data Queue | If Wi-Fi disconnected: read DS3231 timestamp, append encrypted scan to SD Card |
| 2.11 | Data Sync Logic | Upon Wi-Fi reconnect: transmit queued SD Card payloads to companion app |
| 2.12 | LED State Machine | Implement all LED states (idle breathing, success flash, error, OTA update) |
| 2.13 | Buzzer Patterns | Implement all buzzer tones from FSD FR-09 |

### 2.3 Firmware Architecture
```
main.cpp
├── setup()
│   ├── WiFi.setTxPower(WIFI_POWER_8_5dBm)  // FIRST LINE
│   ├── Serial.begin(115200)
│   ├── Serial2.begin(57600, SERIAL_8N1, 16, 17)
│   ├── finger.begin(57600)
│   ├── neopixel.begin()
│   ├── WiFi.begin(SSID, PASS)
│   ├── udp.begin(8888)
│   ├── server.on("/poll", handlePoll)
│   ├── server.on("/enroll", handleEnroll)
│   ├── server.on("/status", handleStatus)
│   └── server.begin()
│
└── loop()
    ├── server.handleClient()
    ├── handleUDPDiscovery()
    ├── checkFingerprint()      // Non-blocking scan
    ├── updateLEDState()        // State machine tick
    └── handleBuzzerQueue()     // Non-blocking tone queue
```

### 2.4 AES Encryption Implementation Detail
```
Pre-shared Key: 16-byte key (e.g., "AttendanceKey16!")
Padding: PKCS7 (pad to 16-byte blocks)
Mode: AES-128-ECB (Phase 1) → Upgrade to CBC in future
Library: mbedtls/aes.h (built into ESP-IDF, no external dependency)

Encryption Flow:
  1. Construct JSON string: {"id":5,"confidence":98,"timestamp":"..."}
  2. Apply PKCS7 padding to make length multiple of 16
  3. Encrypt each 16-byte block with mbedtls_aes_crypt_ecb()
  4. Base64 encode the encrypted bytes
  5. Return Base64 string as HTTP response body
```

### 2.5 Acceptance Criteria
- [ ] ESP32 connects to Wi-Fi and prints IP to Serial Monitor
- [ ] UDP broadcast discovery works from Python test script
- [ ] `/poll` returns valid AES-encrypted Base64 response
- [ ] `/enroll?id=1` initiates enrollment (LED turns BLUE)
- [ ] `/status` returns valid JSON with device health
- [ ] Fingerprint scan triggers attendance event stored in buffer
- [ ] LED state machine operates correctly for all states
- [ ] No brownout resets under Wi-Fi + sensor + LED load

### 2.6 Deliverables
- `main.cpp` — Production firmware
- `platformio.ini` — PlatformIO configuration with all dependencies
- API test results (curl/Postman screenshots)

---

## Phase 3: Python Companion App — UI & Device Discovery
**Duration:** Week 5–6 | **Priority:** Critical | **Dependencies:** Phase 2 API functional

### 3.1 Objective
Build the Windows companion application with a professional two-panel GUI, automated UDP device discovery, and background HTTP polling — all without blocking the UI thread.

### 3.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 3.1 | Project Setup | Create virtual environment, install `customtkinter`, `requests` |
| 3.2 | Application Window | 900×600 window, dark theme, "Smart Attendance System" title |
| 3.3 | Left Panel — Live Feed | Scrollable frame showing real-time attendance events with timestamp |
| 3.4 | Right Panel — User Management | Table view of enrolled users (ID, Name, Department, Role) with CRUD buttons |
| 3.5 | Connection Status Bar | Top bar showing device IP, connection status (colored indicator), Wi-Fi RSSI |
| 3.6 | UDP Discovery Module | `socket.AF_INET, SOCK_DGRAM` broadcast to `255.255.255.255:8888` |
| 3.7 | Auto-Discovery on Launch | On app start: attempt discovery → if found, show IP → if not, show manual entry |
| 3.8 | Background Polling Thread | `threading.Thread(daemon=True)` polling `/poll` every 1 second |
| 3.9 | Thread-Safe UI Updates | Use `self.after(0, callback)` to update CustomTkinter widgets from background thread |
| 3.10 | Enrollment Dialog | Modal dialog: enter ID + name + department → send to `/enroll?id=N` |
| 3.11 | Event Logging Panel | Bottom panel with timestamped log messages (scrollable textbox) |

### 3.3 Application Layout
```
┌──────────────────────────────────────────────────────────┐
│  ● Connected to 192.168.1.100 (UNIT_01)  │ RSSI: -42dBm │
├────────────────────────┬─────────────────────────────────┤
│   📋 LIVE FEED         │   👥 USER MANAGEMENT            │
│                        │                                 │
│  14:30:05 - Ahmed (3)  │  ID │ Name    │ Dept    │ Role │
│  14:29:58 - Sara (7)   │  1  │ Admin   │ IT      │ Admin│
│  14:29:45 - Ali (2)    │  2  │ Ali     │ HR      │ Staff│
│  14:28:30 - Fatima (5) │  3  │ Ahmed   │ Finance │ Staff│
│                        │  7  │ Sara    │ IT      │ Staff│
│                        │                                 │
│                        │  [+ Enroll] [✏ Edit] [🗑 Delete]│
├────────────────────────┴─────────────────────────────────┤
│  📝 LOG: System connected to ESP32 at 192.168.1.100     │
│  📝 LOG: User ID 3 scanned successfully (conf: 98%)     │
└──────────────────────────────────────────────────────────┘
```

### 3.4 UDP Discovery Implementation
```python
# Discovery function (runs in thread)
def discover_device(timeout=5, retries=3):
    for attempt in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.sendto(b"FIND_ATTENDANCE_DEVICE", ("255.255.255.255", 8888))
        try:
            data, addr = sock.recvfrom(1024)
            # Parse: "ATTENDANCE_DEVICE:192.168.1.100:UNIT_01"
            return parse_response(data.decode())
        except socket.timeout:
            continue
        finally:
            sock.close()
    return None  # Device not found
```

### 3.5 Acceptance Criteria
- [ ] App launches with CustomTkinter dark theme, 900×600 window
- [ ] UDP discovery finds ESP32 within 5 seconds on same subnet
- [ ] Live feed panel updates in real-time when fingers are scanned
- [ ] UI does NOT freeze during background polling
- [ ] Enrollment dialog sends request and shows success/failure
- [ ] User management table displays and allows CRUD operations
- [ ] Connection status bar shows accurate device info and RSSI

### 3.6 Deliverables
- `app.py` — Main application file
- `requirements.txt` — Python dependencies
- UI screenshots demonstrating all panels

---

## Phase 4: Security Integration & Cloud Synchronization
**Duration:** Week 7–8 | **Priority:** High | **Dependencies:** Phase 3 polling functional

### 4.1 Objective
Integrate AES-128 decryption into the companion app, implement local data management with Pandas, and add Google Sheets cloud synchronization for remote access to attendance records.

### 4.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 4.1 | AES Decryption Module | Implement PyCryptodome AES-128-ECB decryption matching ESP32 encryption |
| 4.2 | Decryption Pipeline | HTTP response → Base64 decode → AES decrypt → PKCS7 unpad → JSON parse |
| 4.3 | Key Configuration | Store pre-shared AES key in config file (not hardcoded in app) |
| 4.4 | Pandas Local Database | CSV-backed DataFrame: `users.csv` with ID, Name, Role, Department, Enrolled Date |
| 4.5 | Attendance Log CSV | Append each event to `attendance_log.csv`: Date, Time, ID, Name, Confidence |
| 4.6 | Google Sheets Setup | Create Service Account in Google Cloud Console, download JSON key file |
| 4.7 | gspread Integration | Authenticate with Service Account, open spreadsheet by name/key |
| 4.8 | Cloud Sync Logic | On each attendance event: append row to Google Sheet with all fields |
| 4.9 | Offline Queue | If Sheets API unreachable: queue events in local list, batch sync on reconnect |
| 4.10 | Data Validation | Validate decrypted data integrity: check ID range, timestamp format, confidence bounds |

### 4.3 AES Decryption Implementation
```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64, json

AES_KEY = b"AttendanceKey16!"  # Must match ESP32 key exactly

def decrypt_payload(encrypted_b64: str) -> dict:
    encrypted_bytes = base64.b64decode(encrypted_b64)
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    decrypted_padded = cipher.decrypt(encrypted_bytes)
    decrypted = unpad(decrypted_padded, AES.block_size)
    return json.loads(decrypted.decode('utf-8'))
```

### 4.4 Google Sheets Integration
```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPES = ['https://spreadsheets.google.com/feeds',
           'https://www.googleapis.com/auth/drive']

def init_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        'service_account.json', SCOPES)
    client = gspread.authorize(creds)
    return client.open("Attendance Records").sheet1

def log_attendance(sheet, event: dict, user_name: str):
    sheet.append_row([
        event['timestamp'].split('T')[0],  # Date
        event['timestamp'].split('T')[1],  # Time
        event['id'],
        user_name,
        event.get('department', 'N/A'),
        event['confidence']
    ])
```

### 4.5 Acceptance Criteria
- [ ] Encrypted `/poll` response is correctly decrypted to valid JSON
- [ ] Decrypted data matches original data on ESP32 (verified via Serial Monitor)
- [ ] Local `users.csv` persists across app restarts
- [ ] Local `attendance_log.csv` records all events with correct timestamps
- [ ] Google Sheet receives new row within 3 seconds of finger scan
- [ ] Offline queue stores events and batch-syncs when Sheets becomes reachable
- [ ] Invalid/corrupted encrypted payloads are handled gracefully (logged, not crashed)

### 4.6 Deliverables
- Updated `app.py` with decryption + cloud sync modules
- `service_account.json` setup guide
- `users.csv` template
- Google Sheet template with column headers

---

## Phase 5: Testing, Optimization & Deployment Packaging
**Duration:** Week 9–10 | **Priority:** High | **Dependencies:** All previous phases

### 5.1 Objective
Perform comprehensive integration testing, optimize performance and power stability, and package the companion application as a standalone Windows executable.

### 5.2 Tasks

| Task # | Task | Description |
|--------|------|-------------|
| 5.1 | Integration Testing | End-to-end test: finger scan → encryption → HTTP → decryption → UI display → cloud sync |
| 5.2 | Stress Testing | 50 consecutive scans in rapid succession — verify no data loss |
| 5.3 | Power Longevity Test | Run system for 8 continuous hours, monitor for brownouts/crashes |
| 5.4 | Network Resilience Test | Simulate Wi-Fi drops during operation — verify auto-reconnect |
| 5.5 | Security Validation | Capture HTTP traffic with Wireshark — verify payloads are encrypted |
| 5.6 | Multi-User Enrollment Test | Enroll 10+ users, verify all correctly identified with >90% confidence |
| 5.7 | False Acceptance Test | Test 50 unenrolled fingers — verify 0 false accepts |
| 5.8 | UI/UX Polish | Refine colors, fonts, spacing, animations, error messages |
| 5.9 | PyInstaller Packaging | `pyinstaller --noconsole --onefile --icon=icon.ico app.py` |
| 5.10 | .exe Deployment Test | Run generated .exe on clean Windows 10/11 PC without Python |
| 5.11 | User Documentation | Create quick-start guide with setup screenshots |

### 5.3 PyInstaller Configuration
```bash
# Install PyInstaller
pip install pyinstaller

# Build standalone executable
pyinstaller --noconsole --onefile --icon=icon.ico --name="AttendanceSystem" app.py

# Output: dist/AttendanceSystem.exe
# Include with deployment:
#   - AttendanceSystem.exe
#   - service_account.json (for Google Sheets)
#   - users.csv (pre-populated or empty template)
#   - config.ini (AES key, default settings)
```

### 5.4 Test Results Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-INT-01 | Full scan-to-cloud pipeline | ☐ Pass / ☐ Fail | |
| TC-INT-02 | 50 rapid consecutive scans | ☐ Pass / ☐ Fail | |
| TC-INT-03 | 8-hour continuous operation | ☐ Pass / ☐ Fail | |
| TC-INT-04 | Wi-Fi reconnection after drop | ☐ Pass / ☐ Fail | |
| TC-INT-05 | Wireshark encrypted payload verification | ☐ Pass / ☐ Fail | |
| TC-INT-06 | 10-user enrollment + identification | ☐ Pass / ☐ Fail | |
| TC-INT-07 | 50-finger false acceptance test | ☐ Pass / ☐ Fail | |
| TC-INT-08 | .exe launch on clean Windows PC | ☐ Pass / ☐ Fail | |
| TC-INT-09 | Offline queue + batch sync | ☐ Pass / ☐ Fail | |
| TC-INT-10 | UDP discovery on different subnets | ☐ Pass / ☐ Fail | |

### 5.5 Acceptance Criteria
- [ ] All integration tests pass
- [ ] Zero data loss in stress test (50 scans)
- [ ] No brownout resets in 8-hour longevity test
- [ ] Wireshark capture shows no plaintext attendance data
- [ ] .exe runs on clean Windows 10/11 without any dependencies
- [ ] All 10 enrolled users identified correctly (>90% confidence)
- [ ] Zero false acceptances from unenrolled fingers

### 5.6 Final Deliverables
- `AttendanceSystem.exe` — Standalone Windows application
- `main.cpp` — Production ESP32 firmware (PlatformIO project)
- `service_account.json` — Google Sheets credentials (template)
- `users.csv` — User database template
- `config.ini` — Application configuration
- User Quick-Start Guide (PDF)
- Test results report
- Project documentation (FSD, Implementation Plan, Project Description)

---

## Appendix A: File Structure

```
app_finger/
├── firmware/
│   ├── src/
│   │   └── main.cpp              # ESP32 production firmware
│   ├── include/
│   │   └── config.h              # Wi-Fi credentials, AES key, pin definitions
│   ├── test/
│   │   └── diagnostic_test.cpp   # Phase 1 hardware test firmware
│   └── platformio.ini            # PlatformIO configuration
│
├── companion_app/
│   ├── app.py                    # Main Python application
│   ├── crypto_utils.py           # AES decryption module
│   ├── discovery.py              # UDP device discovery module
│   ├── sheets_sync.py            # Google Sheets integration
│   ├── data_manager.py           # Pandas CSV data management
│   ├── config.ini                # App configuration (AES key, settings)
│   ├── requirements.txt          # Python dependencies
│   └── icon.ico                  # Application icon
│
├── data/
│   ├── users.csv                 # User database
│   └── attendance_log.csv        # Local attendance log
│
├── docs/
│   ├── Project Description       # Project overview document
│   ├── FSD.md                    # Functional Specification Document
│   ├── Implementation_Plan.md    # This document
│   └── quick_start_guide.pdf     # User deployment guide
│
└── dist/
    └── AttendanceSystem.exe      # Packaged standalone executable
```

---

## Appendix B: Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| USB power brownout under full load | High | Critical | Reduce Wi-Fi TX power; use powered USB hub |
| R307S false rejection of valid fingers | Medium | High | Clean sensor surface; re-enroll with dry fingers |
| Wi-Fi interference in dense environments | Medium | Medium | Use 2.4GHz channel selection; reduce TX range |
| Google Sheets API rate limiting | Low | Medium | Batch sync; implement exponential backoff |
| AES key compromise | Low | High | Rotate keys periodically; store key in config file (not source code) |
| PyInstaller compatibility issues | Medium | Medium | Test on multiple Windows versions; include all DLLs |

---

**Document End**