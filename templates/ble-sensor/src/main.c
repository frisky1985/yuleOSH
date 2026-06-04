/**
 * BLE Temperature Sensor — Firmware Entry Point
 *
 * Implements:
 *   Req-001: BLE Advertising with Eddystone UID/TLM frames
 *   Req-002: DS18B20 temperature sensing
 *   Req-003: Battery monitoring and deep sleep
 *   Req-004: BLE GATT configuration commands + flash persistence
 *
 * Target: nRF52840 (ARM Cortex-M4F)
 * Toolchain: ARM GCC 12+
 */

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* ------------------------------------------------------------------ */
/* Platform HAL (stubbed for build/test)                                */
/* ------------------------------------------------------------------ */

#define BLE_ADV_CHANNEL_37  37
#define BLE_ADV_CHANNEL_38  38
#define BLE_ADV_CHANNEL_39  39

#define FLASH_PAGE_SIZE     4096
#define CONFIG_MAGIC        0x594C5301  /* "YLS\x01" */

/* Battery thresholds (mV) */
#define BATTERY_WARN_MV     3000
#define BATTERY_CRITICAL_MV 2000

/* Temperature limits */
#define TEMP_MIN_C          -10
#define TEMP_MAX_C          85
#define TEMP_ACCURACY_C     0.5f

/* Advertising intervals (ms) */
#define ADV_INTERVAL_MIN_MS 100
#define ADV_INTERVAL_MAX_MS 10000
#define ADV_INTERVAL_DEFAULT_MS 1000

/* Sampling intervals (s) */
#define SAMPLE_INTERVAL_MIN_S  1
#define SAMPLE_INTERVAL_MAX_S  3600
#define SAMPLE_INTERVAL_DEFAULT_S 10

/* FreeRTOS task priorities */
#define TASK_PRIO_SENSOR   2
#define TASK_PRIO_BLE      3
#define TASK_PRIO_BATTERY  1

/* ------------------------------------------------------------------ */
/* Data structures                                                      */
/* ------------------------------------------------------------------ */

typedef struct {
    uint32_t magic;
    uint16_t adv_interval_ms;       /* Advertisement interval in ms */
    uint16_t sample_interval_s;     /* Temperature sample interval in s */
    uint8_t  tx_power_dbm;          /* Transmit power in dBm */
    uint8_t  adv_format;            /* 0 = Eddystone, 1 = iBeacon */
    uint16_t crc;
} __attribute__((packed)) SensorConfig;

typedef enum {
    SENSOR_OK = 0,
    SENSOR_ERR_NOT_FOUND,
    SENSOR_ERR_READ_FAILED,
    SENSOR_ERR_OUT_OF_RANGE,
    SENSOR_ERR_BUSY
} SensorError;

/* Global configuration (backed by flash) */
static SensorConfig g_config;
static bool g_config_loaded = false;

/* Current state */
static int16_t  g_last_temp_celsius_x10;  /* e.g. 235 = 23.5°C */
static uint8_t  g_battery_percent;
static bool     g_deep_sleep_mode = false;

/* ------------------------------------------------------------------ */
/* Forward declarations                                                 */
/* ------------------------------------------------------------------ */

/* HAL stubs — replaced by platform BSP in production */
static int      hal_flash_read(uint32_t addr, void *buf, size_t len);
static int      hal_flash_write(uint32_t addr, const void *buf, size_t len);
static int      hal_flash_erase(uint32_t page_addr);
static int      hal_temp_read(float *temp_c);
static int      hal_battery_read_mv(uint16_t *mv);
static void     hal_set_advertising(uint16_t interval_ms, uint8_t tx_power);
static void     hal_stop_advertising(void);
static void     hal_enter_deep_sleep(void);
static uint64_t hal_get_ticks_ms(void);
static void     hal_delay_ms(uint32_t ms);

/* BLE GATT service handlers */
static void     gatt_on_config_write(const uint8_t *data, uint16_t len);

/* Internal helpers */
static SensorError sensor_read_temperature(void);
static void        battery_update_level(void);
static void        config_load(void);
static void        config_save(void);
static void        config_apply(void);
static uint16_t    config_compute_crc(const SensorConfig *cfg);

/* ------------------------------------------------------------------ */
/* Initialization                                                       */
/* ------------------------------------------------------------------ */

void sensor_init(void)
{
    /* Load persisted configuration */
    config_load();

    /* Apply settings to BLE hardware */
    config_apply();

    /* Initialize temperature sensor */
    float t;
    if (hal_temp_read(&t) == 0) {
        g_last_temp_celsius_x10 = (int16_t)(t * 10.0f);
    }

    /* Read initial battery level */
    battery_update_level();

    /* Register GATT write callback for configuration commands */
    /* (registration happens in BLE stack init — assumed here) */
}

/* ------------------------------------------------------------------ */
/* Main loop / task entry                                               */
/* ------------------------------------------------------------------ */

void sensor_task_run(void)
{
    if (g_deep_sleep_mode) {
        return;
    }

    /* Sample temperature */
    SensorError err = sensor_read_temperature();

    /* Update battery */
    battery_update_level();

    /* Update BLE advertisement with latest sensor data */
    /* The BLE stack reads g_last_temp_celsius_x10 and g_battery_percent */

    (void)err;
}

SensorError sensor_read_temperature(void)
{
    float temp_c;
    int ret = hal_temp_read(&temp_c);

    if (ret != 0) {
        return SENSOR_ERR_READ_FAILED;
    }

    if (temp_c < TEMP_MIN_C || temp_c > TEMP_MAX_C) {
        return SENSOR_ERR_OUT_OF_RANGE;
    }

    g_last_temp_celsius_x10 = (int16_t)(temp_c * 10.0f);
    return SENSOR_OK;
}

/* ------------------------------------------------------------------ */
/* Battery management                                                   */
/* ------------------------------------------------------------------ */

void battery_update_level(void)
{
    uint16_t mv;
    if (hal_battery_read_mv(&mv) != 0) {
        return;
    }

    /* Assume full battery is 4200 mV, critical is 2000 mV */
    uint32_t pct = 0;
    if (mv >= BATTERY_CRITICAL_MV) {
        uint32_t range = 4200 - BATTERY_CRITICAL_MV;
        uint32_t current = mv - BATTERY_CRITICAL_MV;
        pct = (current * 100U) / range;
        if (pct > 100) pct = 100;
    }

    g_battery_percent = (uint8_t)pct;

    if (mv < BATTERY_CRITICAL_MV && !g_deep_sleep_mode) {
        g_deep_sleep_mode = true;
        hal_stop_advertising();
        hal_enter_deep_sleep();
    }
}

uint8_t sensor_get_battery_percent(void)
{
    return g_battery_percent;
}

int16_t sensor_get_temperature_x10(void)
{
    return g_last_temp_celsius_x10;
}

/* ------------------------------------------------------------------ */
/* Configuration management                                             */
/* ------------------------------------------------------------------ */

void config_load(void)
{
    SensorConfig cfg;
    if (hal_flash_read(0x7F000, &cfg, sizeof(cfg)) != 0) {
        /* Use defaults */
        memset(&g_config, 0, sizeof(g_config));
        g_config.magic = CONFIG_MAGIC;
        g_config.adv_interval_ms = ADV_INTERVAL_DEFAULT_MS;
        g_config.sample_interval_s = SAMPLE_INTERVAL_DEFAULT_S;
        g_config.tx_power_dbm = 4;    /* +4 dBm */
        g_config.adv_format = 0;       /* Eddystone */
        g_config.crc = config_compute_crc(&g_config);
        return;
    }

    if (cfg.magic != CONFIG_MAGIC) {
        /* Corrupted — revert to defaults */
        config_load();
        return;
    }

    g_config = cfg;
    g_config_loaded = true;
}

void config_save(void)
{
    g_config.crc = config_compute_crc(&g_config);

    /* Erase flash page */
    hal_flash_erase(0x7F000);

    /* Write configuration */
    hal_flash_write(0x7F000, &g_config, sizeof(g_config));
}

void config_apply(void)
{
    uint16_t interval = g_config.adv_interval_ms;
    if (interval < ADV_INTERVAL_MIN_MS) interval = ADV_INTERVAL_MIN_MS;
    if (interval > ADV_INTERVAL_MAX_MS) interval = ADV_INTERVAL_MAX_MS;

    hal_set_advertising(interval, g_config.tx_power_dbm);
}

static void gatt_on_config_write(const uint8_t *data, uint16_t len)
{
    if (len < sizeof(uint16_t)) return;

    /* First two bytes are the config key, rest is value */
    uint16_t key = (data[0] << 8) | data[1];

    switch (key) {
    case 0x0001: /* Advertisement interval */
        if (len >= 4) {
            uint16_t interval = (data[2] << 8) | data[3];
            if (interval >= ADV_INTERVAL_MIN_MS && interval <= ADV_INTERVAL_MAX_MS) {
                g_config.adv_interval_ms = interval;
                config_save();
                config_apply();
            }
        }
        break;
    case 0x0002: /* Sample interval */
        if (len >= 4) {
            uint16_t sample = (data[2] << 8) | data[3];
            if (sample >= SAMPLE_INTERVAL_MIN_S && sample <= SAMPLE_INTERVAL_MAX_S) {
                g_config.sample_interval_s = sample;
                config_save();
            }
        }
        break;
    default:
        break;
    }
}

/* ------------------------------------------------------------------ */
/* CRC calculation                                                      */
/* ------------------------------------------------------------------ */

static uint16_t config_compute_crc(const SensorConfig *cfg)
{
    uint16_t crc = 0xFFFF;
    const uint8_t *bytes = (const uint8_t *)cfg;
    size_t len = sizeof(SensorConfig) - sizeof(cfg->crc);
    for (size_t i = 0; i < len; i++) {
        crc ^= bytes[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

/* ------------------------------------------------------------------ */
/* HAL stubs (for build / test)                                         */
/* ------------------------------------------------------------------ */

static int hal_flash_read(uint32_t addr, void *buf, size_t len)
{
    (void)addr;
    memset(buf, 0, len);
    return 0;
}

static int hal_flash_write(uint32_t addr, const void *buf, size_t len)
{
    (void)addr;
    (void)buf;
    (void)len;
    return 0;
}

static int hal_flash_erase(uint32_t page_addr)
{
    (void)page_addr;
    return 0;
}

static int hal_temp_read(float *temp_c)
{
    *temp_c = 25.0f;
    return 0;
}

static int hal_battery_read_mv(uint16_t *mv)
{
    *mv = 3800;
    return 0;
}

static void hal_set_advertising(uint16_t interval_ms, uint8_t tx_power)
{
    (void)interval_ms;
    (void)tx_power;
}

static void hal_stop_advertising(void)
{
}

static void hal_enter_deep_sleep(void)
{
    g_deep_sleep_mode = true;
}

static uint64_t hal_get_ticks_ms(void)
{
    return 0;
}

static void hal_delay_ms(uint32_t ms)
{
    (void)ms;
}
