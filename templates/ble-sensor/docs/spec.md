# BLE Temperature Sensor — OpenSpec Specification

> Version: 0.1.0 | Status: Draft

---

## 1. Core Functionality

### Req-001: BLE Advertising
- The system SHALL advertise Eddystone/UID and Eddystone/TLM frames at a configurable interval
- The system SHALL transmit advertising packets on BLE 5.0 channels 37, 38, and 39
- The system SHALL support advertisement intervals between 100 ms and 10000 ms
- The system SHOULD dynamically adjust advertising power based on battery level
- The system MAY support iBeacon advertising format as an alternative

#### Reason
Core BLE beacon functionality ensures device discoverability and interoperability with standard BLE scanning infrastructure.

### Req-002: Temperature Sensing
- The system SHALL read ambient temperature from an onboard digital sensor (DS18B20 or equivalent)
- The system SHALL report temperature with ±0.5°C accuracy across the range of -10°C to +85°C
- The system SHALL sample temperature at a configurable interval of 1 to 3600 seconds
- The system SHALL update the advertised TLM frame with the latest temperature reading

#### Reason
Primary sensing function — temperature measurement must be accurate and reflected in BLE advertisements for consumer applications.

### Req-003: Battery Management
- The system SHALL monitor battery voltage at least once every 60 seconds
- The system SHALL advertise battery level in the TLM frame as a percentage (0–100%)
- The system SHALL enter deep sleep mode when battery voltage drops below 2.0 V
- The system SHOULD provide a warning advertisement when battery is below 10%

#### Reason
Battery awareness is critical for long-lived BLE sensor deployments. Deep sleep at low voltage prevents battery damage.

### Req-004: Configuration and Persistence
- The system SHALL accept configuration commands over BLE GATT Write
- The system SHALL persist all configuration parameters to non-volatile flash memory within 500 ms of update
- The system SHALL restore saved configuration on power-up

#### Reason
Field configurability without physical access. Persistence ensures configuration survives power cycles.

---

## 2. Acceptance Scenarios

### Scenario: Normal Operation
- GIVEN the BLE sensor is powered with a fresh battery
- AND the sensor is configured with default parameters
- WHEN the sensor initializes
- THEN the system SHALL begin advertising on all BLE channels within 2 seconds
- AND the system SHALL report temperature in the TLM frame
- AND the system SHALL report battery level in the TLM frame

### Scenario: Low Battery Warning
- GIVEN the sensor is operating normally
- WHEN battery voltage drops below 3.0 V
- THEN the system SHALL set the battery level advertisement to the correct percentage
- AND the system SHALL continue normal temperature sensing and advertising

### Scenario: Configuration Update
- GIVEN the sensor is advertising
- WHEN a central device writes a new advertisement interval via GATT
- THEN the system SHALL save the new interval to flash
- AND the system SHALL begin advertising at the new interval within 1 second

### Scenario: Deep Sleep on Critical Battery
- GIVEN the sensor is operating
- WHEN battery voltage drops below 2.0 V
- THEN the system SHALL enter deep sleep mode within 100 ms
- AND the system SHALL stop all BLE advertising
- AND the system SHALL wake only when external power is applied
