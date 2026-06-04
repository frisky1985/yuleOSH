# CAN Bus Gateway — OpenSpec Specification

> Version: 0.1.0 | Status: Draft

---

## 1. Core Functionality

### Req-001: CAN Message Reception
- The system SHALL receive CAN 2.0B extended frames (29-bit identifier) on a configurable set of CAN IDs
- The system SHALL support a receive filter with up to 32 configurable ID/mask pairs
- The system SHALL timestamp each received message with microsecond resolution
- The system SHALL buffer up to 256 received messages before overflow
- The system SHOULD support CAN FD frames at up to 8 Mbps data phase

#### Reason
Core CAN bus monitoring requires robust message reception with filtering and timestamping for diagnostics and logging applications.

### Req-002: CAN Message Transmission
- The system SHALL transmit CAN 2.0B frames with selectable data length (0–8 bytes)
- The system SHALL support periodic transmission of configurable messages at intervals from 10 ms to 60000 ms
- The system SHALL respect error passive state and bus-off recovery per ISO 11898-1
- The system MAY support CAN FD with up to 64 bytes payload

#### Reason
Transmission capability is needed for gateway and actuator applications. Periodic messages enable sensor emulation and heartbeat patterns.

### Req-003: Message Logging
- The system SHALL log all received CAN messages to a circular buffer in RAM
- The system SHALL support exporting the log buffer as a structured binary blob
- The system SHALL include a 32-bit rolling counter with each log entry
- The system SHALL log error frames with an error flag bit set

#### Reason
Logging is essential for diagnostics and protocol analysis. The circular buffer design ensures continuous recording without allocation overhead.

### Req-004: Configuration Interface
- The system SHALL accept configuration commands over UART at 115200 baud
- The system SHALL support configuration of CAN bit rate (125 kbps, 250 kbps, 500 kbps, 1 Mbps)
- The system SHALL persist configuration to flash and restore on power-up
- The system SHALL provide a read-only command to dump current configuration

#### Reason
Field reconfiguration without physical access to the CAN bus pins. UART is a standard debug/provisioning interface.

---

## 2. Acceptance Scenarios

### Scenario: Message Reception
- GIVEN the CAN bus gateway is initialized with filters set to IDs 0x100–0x1FF
- WHEN a CAN frame with ID 0x150 and data length 8 bytes appears on the bus
- THEN the system SHALL accept the frame through the filter
- AND the system SHALL timestamp the message
- AND the system SHALL store it in the receive buffer

### Scenario: Periodic Transmission
- GIVEN the system is configured with a periodic message (ID 0x200, interval 1000 ms)
- WHEN the system has been running for 5 seconds
- THEN the system SHALL have transmitted the periodic message at least 4 times
- AND each transmission SHALL respect the CAN bus arbitration rules

### Scenario: Buffer Overflow
- GIVEN the receive buffer is full (256 messages)
- WHEN a new message arrives
- THEN the system SHALL discard the oldest message
- AND the system SHALL set the overflow flag

### Scenario: Bit Rate Configuration
- GIVEN the system is idle
- WHEN the user sends "BAUD 500000\r\n" over UART
- THEN the system SHALL reconfigure the CAN controller for 500 kbps
- AND the system SHALL save the new baud rate to flash
- AND the system SHALL respond with "OK\r\n"
