# yuleOSH Blinky — ESP-IDF OpenSpec Specification

> Version: 0.1.0 | Status: Draft
> Target: ESP-IDF v5.x (ESP32 / ESP32-S3 / ESP32-C3)

---

## 0. Scope & Environment Note

This template is a **hardware-targeted ESP-IDF example**. It depends on the
Espressif IoT Development Framework (ESP-IDF) toolchain and real ESP32-class
silicon. It is **not host-buildable** the way the C-harness templates
(`gpio-led-chaser`, `can-bus`, `ble-sensor`, `mcu-firmware`) are:

- `CMakeLists.txt` includes `$ENV{IDF_PATH}/tools/cmake/project.cmake` and
  requires `IDF_PATH` plus the Xtensa/RISC-V cross-compiler to configure.
- `main/main.c` calls ESP-IDF / FreeRTOS / Wi-Fi / driver HAL APIs directly.

Consequence for the yuleOSH pipeline:

- **G1 (spec-check)**, **G2 (arch)**, **G3 (dev)**, **G4 (review, advisory)**,
  **G5 (test-planning)** run on the documents/code as normal.
- **G7 integration-test** cannot configure or build on a host without ESP-IDF;
  on a host it degrades to a no-op (0 tests discovered) rather than a real
  hardware/integration verification. Real verification requires
  `idf.py build flash monitor` on target hardware.
- No host C unit-test harness is vendored (would require stubbing the entire
  ESP-IDF HAL); the value of this template is the documented build/flash flow.

This is an intentional, declared limitation — not a defect to be masked.

---

## 1. Core Functionality

### Req-001: LED Blink
- The system SHALL blink an LED on `CONFIG_BLINK_GPIO` (default GPIO 2) with a
  period of `BLINK_PERIOD_MS` (default 1000 ms)
- The system SHALL hold the LED ON for half the period and OFF for half the
  period via `gpio_set_level`
- The system SHALL initialize the GPIO with `gpio_reset_pin` and
  `gpio_set_direction(..., GPIO_MODE_OUTPUT)` before the blink loop

#### Reason
The canonical "hello world" of embedded: a visible heartbeat that proves the
SoC, clock, and FreeRTOS scheduler are alive.

### Req-002: UART Diagnostic Output
- The system SHALL print a startup banner including `"Hello from yuleOSH!"`
  over the console UART at `UART_BAUD` (default 115200 baud)
- The system SHALL log each LED state transition (`LED ON` / `LED OFF`) via
  `ESP_LOGI`
- The system SHALL log Wi-Fi scan progress and per-AP results over the same
  console UART

#### Reason
UART is the standard out-of-band debug interface on ESP32; the banner and
per-state logs let a developer confirm firmware bring-up without a debugger.

### Req-003: Wi-Fi Station Scan
- The system SHALL initialize the Wi-Fi stack in `WIFI_MODE_STA` and start it
- The system SHALL perform a blocking active scan of surrounding APs
- The system SHALL print up to `max_aps` (default 20) discovered APs with
  SSID, RSSI, primary channel, and authmode
- The system SHALL re-scan every `WIFI_SCAN_INTERVAL_SEC` (default 30 s)
- The system SHALL handle scan-init and result-fetch failures gracefully and
  free the result buffer on every return path

#### Reason
Demonstrates the network stack bring-up and a realistic periodic
resource-allocating task (heap buffer + scan), exercising error handling.

### Req-004: System Initialization
- The system SHALL initialize NVS via `nvs_flash_init`, erasing and
  re-initializing when `ESP_ERR_NVS_NO_FREE_PAGES` or
  `ESP_ERR_NVS_NEW_VERSION_FOUND` is returned
- The system SHALL initialize the network interface (`esp_netif_init`),
  create the default event loop, and create the default Wi-Fi STA interface
- The system SHALL create `blink_task` and `wifi_task` FreeRTOS tasks with
  adequate stacks (2048 / 4096 words)

#### Reason
Correct bring-up order (NVS → netif → event loop → Wi-Fi → tasks) is required
before any application task can use the Wi-Fi or logging subsystems.

---

## 2. Acceptance Scenarios

### Scenario: Blink Heartbeat
- GIVEN the firmware has booted and `blink_task` is running
- WHEN `BLINK_PERIOD_MS` elapses
- THEN the LED SHALL have toggled at least once
- AND the console SHALL show a matching `LED ON` / `LED OFF` log pair

### Scenario: Startup Banner
- GIVEN the application entry `app_main` executes
- WHEN NVS and netif initialization succeed
- THEN the console SHALL print `"Hello from yuleOSH!"`

### Scenario: Wi-Fi Scan Cycle
- GIVEN Wi-Fi is started in station mode
- WHEN `wifi_task` runs its periodic loop
- THEN the system SHALL initiate a blocking scan
- AND the console SHALL print the discovered AP count and details
- AND the result buffer SHALL be freed before the next scan interval

### Scenario: NVS Version Mismatch Recovery
- GIVEN NVS partition holds data from a different firmware version
- WHEN `nvs_flash_init` returns `ESP_ERR_NVS_NEW_VERSION_FOUND`
- THEN the system SHALL erase NVS and re-initialize
- AND boot SHALL continue without a hard fault

---

## 3. Build & Flash (declared flow — requires ESP-IDF)

```
idf.py set-target esp32        # or esp32-s3 / esp32-c3
idf.py build
idf.py flash monitor
```

Integration verification (G7) is performed on real hardware via the above
commands; the host pipeline step cannot substitute for it.
