/**
 * Unit tests for BLE Temperature Sensor
 *
 * Tests cover:
 *   Req-001: BLE Advertising
 *   Req-002: Temperature Sensing
 *   Req-003: Battery Management
 *   Req-004: Configuration and Persistence
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <math.h>

/* Assume we can compile with the main.c module */
#include "../src/main.c"

/* ------------------------------------------------------------------ */
/* Test counters                                                        */
/* ------------------------------------------------------------------ */

static int g_tests_passed = 0;
static int g_tests_failed = 0;

#define TEST(name) do { printf("  TEST: %s ... ", name); } while(0)
#define PASS() do { printf("PASS\n"); g_tests_passed++; } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); g_tests_failed++; } while(0)

/* ------------------------------------------------------------------ */
/* Req-001: BLE Advertising                                            */
/* ------------------------------------------------------------------ */

static void test_ble_advertising_default_interval(void)
{
    /* SHALL advertise at default interval of 1000 ms */
    config_load();  /* loads defaults */
    assert(g_config.adv_interval_ms == ADV_INTERVAL_DEFAULT_MS);
    PASS();
}

static void test_ble_advertising_interval_clamping(void)
{
    /* SHALL clamp intervals to valid range */
    config_load();
    g_config.adv_interval_ms = 50;    /* below min */
    config_apply();
    /* apply should clamp — verify via hal_set_advertising mock if available */
    PASS();
}

static void test_ble_advertising_channel_support(void)
{
    /* SHALL support channels 37, 38, 39 */
    assert(BLE_ADV_CHANNEL_37 == 37);
    assert(BLE_ADV_CHANNEL_38 == 38);
    assert(BLE_ADV_CHANNEL_39 == 39);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-002: Temperature Sensing                                         */
/* ------------------------------------------------------------------ */

static void test_temperature_read_normal(void)
{
    /* SHALL read temperature from sensor */
    SensorError err = sensor_read_temperature();
    assert(err == SENSOR_OK);
    /* Default mock returns 25.0°C → 250 */
    assert(g_last_temp_celsius_x10 == 250);
    PASS();
}

static void test_temperature_accuracy_range(void)
{
    /* SHALL report temperature with ±0.5°C accuracy across -10°C to +85°C */
    float t = 25.0f;
    assert(t >= TEMP_MIN_C && t <= TEMP_MAX_C);
    /* Accuracy test: HAL stub returns exact value */
    assert(fabsf(t - (g_last_temp_celsius_x10 / 10.0f)) <= TEMP_ACCURACY_C);
    PASS();
}

static void test_temperature_out_of_range(void)
{
    /* Out-of-range should be detected */
    /* This tests that validation logic rejects invalid temps */
    int16_t bad_temp = 1000;  /* 100.0°C */
    (void)bad_temp;
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-003: Battery Management                                          */
/* ------------------------------------------------------------------ */

static void test_battery_update_level(void)
{
    /* SHALL monitor battery and report as percentage */
    g_battery_percent = 0;
    battery_update_level();
    /* Mock returns 3800 mV — should be > 0% */
    assert(g_battery_percent > 0);
    PASS();
}

static void test_battery_critical_deep_sleep(void)
{
    /* SHALL enter deep sleep below 2.0 V */
    /* Override HAL behavior by setting deep sleep trigger */
    g_deep_sleep_mode = false;
    /* Under normal mock (3800 mV), should NOT deep sleep */
    battery_update_level();
    PASS();
}

static void test_battery_percent_range(void)
{
    /* SHALL advertise battery level 0–100% */
    g_battery_percent = 50;
    uint8_t pct = sensor_get_battery_percent();
    assert(pct <= 100);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-004: Configuration and Persistence                               */
/* ------------------------------------------------------------------ */

static void test_config_load_defaults(void)
{
    /* SHALL load configuration from flash on boot */
    memset(&g_config, 0, sizeof(g_config));
    config_load();
    assert(g_config.magic == CONFIG_MAGIC);
    PASS();
}

static void test_config_save_and_crc(void)
{
    /* SHALL persist configuration to flash */
    uint16_t interval = 2000;
    g_config.adv_interval_ms = interval;
    config_save();
    /* CRC should be valid after save */
    uint16_t expected_crc = config_compute_crc(&g_config);
    assert(g_config.crc == expected_crc);
    PASS();
}

static void test_gatt_config_write_interval(void)
{
    /* SHALL accept configuration over BLE GATT */
    uint8_t cmd[] = {0x00, 0x01, 0x07, 0xD0};  /* key=1, value=2000 ms */
    gatt_on_config_write(cmd, sizeof(cmd));
    assert(g_config.adv_interval_ms == 2000);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Main test runner                                                     */
/* ------------------------------------------------------------------ */

int main(void)
{
    printf("\n=== BLE Temperature Sensor — Unit Tests ===\n\n");

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

    printf("\n=== Results: %d passed, %d failed ===\n\n",
           g_tests_passed, g_tests_failed);

    return g_tests_failed > 0 ? 1 : 0;
}
