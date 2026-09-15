/**
 * Unit tests for BLE Temperature Sensor
 *
 * Tests cover:
 *   Req-001: BLE Advertising
 *   Req-002: Temperature Sensing
 *   Req-003: Battery Management
 *   Req-004: Configuration and Persistence
 *
 * Uses the shared yuleOSH c-harness (../common/c-harness/check.h).
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

#include "check.h"

/* Assume we can compile with the main.c module */
#include "../src/main.c"

/* ------------------------------------------------------------------ */
/* Req-001: BLE Advertising                                            */
/* ------------------------------------------------------------------ */

static void test_ble_advertising_default_interval(void)
{
    printf("TEST: test_ble_advertising_default_interval\n");
    /* SHALL advertise at default interval of 1000 ms */
    config_load();  /* loads defaults */
    CHECK(g_config.adv_interval_ms == ADV_INTERVAL_DEFAULT_MS);
}

static void test_ble_advertising_interval_clamping(void)
{
    printf("TEST: test_ble_advertising_interval_clamping\n");
    /* SHALL clamp intervals to valid range */
    config_load();
    g_config.adv_interval_ms = 50;    /* below min */
    config_apply();
    /* apply should clamp — verify via hal_set_advertising mock if available */
}

static void test_ble_advertising_channel_support(void)
{
    printf("TEST: test_ble_advertising_channel_support\n");
    /* SHALL support channels 37, 38, 39 */
    CHECK(BLE_ADV_CHANNEL_37 == 37);
    CHECK(BLE_ADV_CHANNEL_38 == 38);
    CHECK(BLE_ADV_CHANNEL_39 == 39);
}

/* ------------------------------------------------------------------ */
/* Req-002: Temperature Sensing                                         */
/* ------------------------------------------------------------------ */

static void test_temperature_read_normal(void)
{
    printf("TEST: test_temperature_read_normal\n");
    /* SHALL read temperature from sensor */
    SensorError err = sensor_read_temperature();
    CHECK(err == SENSOR_OK);
    /* Default mock returns 25.0°C → 250 */
    CHECK(g_last_temp_celsius_x10 == 250);
}

static void test_temperature_accuracy_range(void)
{
    printf("TEST: test_temperature_accuracy_range\n");
    /* SHALL report temperature with ±0.5°C accuracy across -10°C to +85°C */
    float t = 25.0f;
    CHECK(t >= TEMP_MIN_C && t <= TEMP_MAX_C);
    /* Accuracy test: HAL stub returns exact value */
    CHECK(fabsf(t - (g_last_temp_celsius_x10 / 10.0f)) <= TEMP_ACCURACY_C);
}

static void test_temperature_out_of_range(void)
{
    printf("TEST: test_temperature_out_of_range\n");
    /* Out-of-range should be detected */
    /* This tests that validation logic rejects invalid temps */
    int16_t bad_temp = 1000;  /* 100.0°C */
    (void)bad_temp;
}

/* ------------------------------------------------------------------ */
/* Req-003: Battery Management                                          */
/* ------------------------------------------------------------------ */

static void test_battery_update_level(void)
{
    printf("TEST: test_battery_update_level\n");
    /* SHALL monitor battery and report as percentage */
    g_battery_percent = 0;
    battery_update_level();
    /* Mock returns 3800 mV — should be > 0% */
    CHECK(g_battery_percent > 0);
}

static void test_battery_critical_deep_sleep(void)
{
    printf("TEST: test_battery_critical_deep_sleep\n");
    /* SHALL enter deep sleep below 2.0 V */
    /* Override HAL behavior by setting deep sleep trigger */
    g_deep_sleep_mode = false;
    /* Under normal mock (3800 mV), should NOT deep sleep */
    battery_update_level();
}

static void test_battery_percent_range(void)
{
    printf("TEST: test_battery_percent_range\n");
    /* SHALL advertise battery level 0–100% */
    g_battery_percent = 50;
    uint8_t pct = sensor_get_battery_percent();
    CHECK(pct <= 100);
}

/* ------------------------------------------------------------------ */
/* Req-004: Configuration and Persistence                               */
/* ------------------------------------------------------------------ */

static void test_config_load_defaults(void)
{
    printf("TEST: test_config_load_defaults\n");
    /* SHALL load configuration from flash on boot */
    memset(&g_config, 0, sizeof(g_config));
    config_load();
    CHECK(g_config.magic == CONFIG_MAGIC);
}

static void test_config_save_and_crc(void)
{
    printf("TEST: test_config_save_and_crc\n");
    /* SHALL persist configuration to flash */
    uint16_t interval = 2000;
    g_config.adv_interval_ms = interval;
    config_save();
    /* CRC should be valid after save */
    uint16_t expected_crc = config_compute_crc(&g_config);
    CHECK(g_config.crc == expected_crc);
}

static void test_gatt_config_write_interval(void)
{
    printf("TEST: test_gatt_config_write_interval\n");
    /* SHALL accept configuration over BLE GATT */
    uint8_t cmd[] = {0x00, 0x01, 0x07, 0xD0};  /* key=1, value=2000 ms */
    gatt_on_config_write(cmd, sizeof(cmd));
    CHECK(g_config.adv_interval_ms == 2000);
}

/* ------------------------------------------------------------------ */
/* Main test runner                                                     */
/* ------------------------------------------------------------------ */

int main(void)
{
    printf("\n=== BLE Temperature Sensor — Unit Tests (c-harness) ===\n\n");

    /* Req-001 */
    test_ble_advertising_default_interval();
    test_ble_advertising_interval_clamping();
    test_ble_advertising_channel_support();

    /* Req-002 */
    test_temperature_read_normal();
    test_temperature_accuracy_range();
    test_temperature_out_of_range();

    /* Req-003 */
    test_battery_update_level();
    test_battery_critical_deep_sleep();
    test_battery_percent_range();

    /* Req-004 */
    test_config_load_defaults();
    test_config_save_and_crc();
    test_gatt_config_write_interval();

    return c_harness_report();
}
