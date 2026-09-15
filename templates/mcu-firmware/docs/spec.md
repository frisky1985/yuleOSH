# MCU Firmware Core — OpenSpec Specification

> Version: 0.1.0 | Status: Draft

---

## 1. Core Functionality

### Req-001: Task Scheduling
- The system SHALL provide a cooperative round-robin task scheduler with configurable time slices
- The system SHALL support up to 16 registered tasks with individual periods
- The system SHALL track task execution statistics (cycles, min/max execution time, last run timestamp)
- The system SHOULD support task priority levels (HIGH, NORMAL, LOW) for execution ordering
- The system MAY support preemptive task scheduling via a FreeRTOS compatibility layer

#### Reason
A deterministic scheduler is the foundation of any MCU firmware. Cooperative scheduling is sufficient for most embedded control applications.

### Req-002: Watchdog Management
- The system SHALL configure the hardware watchdog timer (IWDG) with a configurable timeout between 1 and 30 seconds
- The system SHALL refresh the watchdog from the main scheduler loop after all tasks complete
- The system SHALL log a watchdog reset event with a reason code in retained RAM
- The system SHALL enter safe mode on consecutive watchdog resets (3 or more without a clean boot)

#### Reason
Watchdog coverage ensures system reliability in unattended operation. Safe mode prevents repeated crash cycling without operator intervention.

### Req-003: Diagnostic Logging
- The system SHALL provide a printf-style debug logging function with severity levels (FATAL, ERROR, WARN, INFO, DEBUG, TRACE)
- The system SHALL route log output to both a ring buffer (in-memory, 4 KB) and a UART serial port
- The system SHALL support runtime log level filtering
- The system SHALL prefix each log line with a timestamp and severity tag
- The system SHOULD support remote log output over a UDP/TCP network interface

#### Reason
Diagnostic logging is essential for development debugging and field diagnostics. The ring buffer allows post-mortem analysis after a crash.

### Req-004: Configuration Storage
- The system SHALL store persistent configuration in a dedicated flash sector with CRC-16 integrity check
- The system SHALL detect and recover from corrupted configuration by reverting to factory defaults
- The system SHALL support factory reset triggered by a GPIO pin held low for 10 seconds on boot
- The system SHOULD support multiple configuration profiles for different operating modes

#### Reason
Robust configuration storage with corruption detection is critical for field devices that may experience power loss during write operations.

---

## 1.1 Known Debt (Host-Stub Limitations)

This template is a **host-compilable simulation** of an STM32G4 firmware: `main.cpp`
calls HAL stubs (`hal_wdt_*`, `hal_flash_*`, `hal_uart_send`, `hal_gpio_*`,
`hal_get_tick_*`) that are no-ops on the host. The following spec SHALLs are
**declared debt** — they are not fully realized in the host stub and require real
silicon to verify:

- **Req-002 retained-RAM persistence**: the consecutive-watchdog-reset counter is a
  process-local `static`, not true retained RAM. It does **not** survive a real
  hardware reset in this stub; a production build would persist it in a
  battery-backed / no-init RAM region and read the RCC `RSR` reset-status register.
  The ERROR-level "Watchdog reset: reason <code>" log (added to `wdt_init`) is the
  observable record, standing in for the retained-RAM entry.
- **Req-002 / Req-004 real peripherals**: IWDG, flash sector, UART and the factory
  reset GPIO are simulated by HAL stubs. Their timing/integrity behaviour (e.g.
  a genuine 1–30 s watchdog timeout, CRC-protected flash across power loss) is not
  exercised by the host tests.

What IS realized in the host stub (honest green, not debt): Req-001 cooperative
priority scheduler; Req-002 safe-mode entry after 3 consecutive resets (counter
logic); Req-003 printf-style logger with severity levels, runtime filtering,
timestamp prefix, **and the 4 KB in-memory ring buffer** (`g_log_buffer[4096]`);
Req-004 CRC-16 config load/revert.

## 2. Acceptance Scenarios

### Scenario: Normal Boot Sequence
- GIVEN the MCU is powered on with valid configuration in flash
- WHEN the boot sequence completes
- THEN the scheduler SHALL start with all registered tasks
- AND the watchdog SHALL be refreshed within its timeout period
- AND the diagnostic log SHALL contain "System boot OK" at INFO level

### Scenario: Watchdog Reset Recovery
- GIVEN the system crashed and watchdog triggered a reset
- WHEN the system reboots
- THEN the boot loader SHALL detect the watchdog reset via the RSR register
- AND the system SHALL log "Watchdog reset: reason <code>" at ERROR level
- AND the system SHALL resume normal operation
- BUT IF the watchdog has reset 3+ times consecutively
- THEN the system SHALL enter safe mode with minimal functionality

### Scenario: Factory Reset
- GIVEN a GPIO pin (PA0) is held low
- WHEN the system has been running for 10 seconds continuously
- THEN the system SHALL erase the config flash sector
- AND the system SHALL reboot with factory default settings
- AND the diagnostic log SHALL contain "Factory reset applied" at WARN level

### Scenario: Corrupted Config Recovery
- GIVEN the configuration flash sector has an invalid CRC-16
- WHEN the system boots
- THEN the system SHALL detect the CRC mismatch
- AND the system SHALL replace corrupted config with factory defaults
- AND the system SHALL log "Config CRC mismatch — reverting to defaults" at WARN level
- AND the system SHALL continue booting normally
