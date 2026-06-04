/**
 * MCU Firmware Core — Application Entry Point
 *
 * Implements:
 *   Req-001: Cooperative round-robin task scheduler
 *   Req-002: Hardware watchdog management with safe mode
 *   Req-003: Diagnostic logging with ring buffer + UART
 *   Req-004: Flash configuration storage with CRC-16
 *
 * Target: STM32G474RE (ARM Cortex-M4F)
 * Toolchain: ARM GCC 12+
 */

#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdarg>

/* ------------------------------------------------------------------ */
/* Configuration limits                                                 */
/* ------------------------------------------------------------------ */

constexpr uint16_t MAX_TASKS             = 16;
constexpr uint16_t LOG_RING_BUFFER_SIZE  = 4096;
constexpr uint32_t CONFIG_FLASH_SECTOR   = 0x08060000;
constexpr uint32_t CONFIG_FLASH_SIZE     = 16384;
constexpr uint16_t CONFIG_MAGIC          = 0x594C;  /* "YL" */
constexpr uint8_t  MAX_CONSECUTIVE_WDT   = 3;
constexpr uint32_t FACTORY_RESET_HOLD_MS = 10000;
constexpr uint32_t WDT_TIMEOUT_MIN_S     = 1;
constexpr uint32_t WDT_TIMEOUT_MAX_S     = 30;

/* ------------------------------------------------------------------ */
/* Enums and types                                                      */
/* ------------------------------------------------------------------ */

enum class LogLevel : uint8_t {
    FATAL = 0,
    ERROR = 1,
    WARN  = 2,
    INFO  = 3,
    DEBUG = 4,
    TRACE = 5
};

enum class TaskPriority : uint8_t {
    HIGH   = 0,
    NORMAL = 1,
    LOW    = 2
};

struct TaskControlBlock {
    void (*handler)(void);
    uint32_t period_ms;
    uint64_t last_run_ms;
    uint32_t exec_count;
    uint32_t max_exec_us;
    uint32_t min_exec_us;
    TaskPriority priority;
    bool enabled;
    const char *name;
};

struct LogEntry {
    uint32_t timestamp_ms;
    LogLevel level;
    char message[64];
};

struct McuConfig {
    uint16_t magic;
    uint16_t crc16;
    uint32_t watchdog_timeout_s;
    LogLevel  log_level;
    uint8_t  reserved[4072];  /* Pad to sector size */
} __attribute__((packed));

/* ------------------------------------------------------------------ */
/* Global state                                                         */
/* ------------------------------------------------------------------ */

static TaskControlBlock g_tasks[MAX_TASKS];
static uint8_t          g_task_count = 0;
static uint64_t         g_system_ticks_ms = 0;

/* Log ring buffer */
static LogEntry         g_log_buffer[LOG_RING_BUFFER_SIZE];
static uint16_t         g_log_head = 0;
static uint16_t         g_log_count = 0;
static LogLevel         g_log_level = LogLevel::INFO;

/* Watchdog state */
static uint8_t          g_consecutive_wdt_resets = 0;
static bool             g_safe_mode = false;
static bool             g_wdt_reset_detected = false;
static uint32_t         g_wdt_timeout_s = 10;

/* Configuration */
static McuConfig        g_config;
static bool             g_config_valid = false;
static bool             g_factory_reset_requested = false;

/* HAL stubs */
static void     hal_wdt_init(uint32_t timeout_s);
static void     hal_wdt_refresh(void);
static uint32_t hal_wdt_get_reset_reason(void);
static void     hal_flash_read(uint32_t addr, void *buf, size_t len);
static int      hal_flash_write(uint32_t addr, const void *buf, size_t len);
static int      hal_flash_erase(uint32_t sector_addr);
static void     hal_uart_send(const char *str, uint16_t len);
static void     hal_gpio_init(void);
static bool     hal_gpio_read_factory_pin(void);
static uint64_t hal_get_tick_ms(void);
static uint32_t hal_get_tick_us(void);
static void     hal_delay_ms(uint32_t ms);
static void     hal_system_reset(void);

/* ------------------------------------------------------------------ */
/* Req-003: Diagnostic Logging                                          */
/* ------------------------------------------------------------------ */

static const char* log_level_to_string(LogLevel level)
{
    switch (level) {
        case LogLevel::FATAL: return "FATAL";
        case LogLevel::ERROR: return "ERROR";
        case LogLevel::WARN:  return "WARN";
        case LogLevel::INFO:  return "INFO";
        case LogLevel::DEBUG: return "DEBUG";
        case LogLevel::TRACE: return "TRACE";
        default:              return "?????";
    }
}

void log_write(LogLevel level, const char *fmt, ...)
{
    if (level > g_log_level) return;

    char buf[128];
    uint32_t now = (uint32_t)hal_get_tick_ms();

    /* Format: [TIMESTAMP] [LEVEL] message */
    int prefix_len = snprintf(buf, sizeof(buf), "[%06u] [%s] ",
                              now, log_level_to_string(level));

    va_list args;
    va_start(args, fmt);
    int msg_len = vsnprintf(buf + prefix_len, sizeof(buf) - prefix_len, fmt, args);
    va_end(args);

    if (msg_len < 0) return;

    uint16_t total_len = (uint16_t)(prefix_len + msg_len);
    if (total_len > sizeof(buf) - 1) total_len = sizeof(buf) - 1;
    buf[total_len] = '\n';

    /* Write to ring buffer */
    LogEntry *entry = &g_log_buffer[g_log_head];
    entry->timestamp_ms = now;
    entry->level = level;
    strncpy(entry->message, buf, sizeof(entry->message) - 1);
    entry->message[sizeof(entry->message) - 1] = '\0';

    g_log_head = (g_log_head + 1) % LOG_RING_BUFFER_SIZE;
    if (g_log_count < LOG_RING_BUFFER_SIZE) g_log_count++;

    /* Write to UART */
    hal_uart_send(buf, total_len + 1);
}

void log_set_level(LogLevel level)
{
    g_log_level = level;
    log_write(LogLevel::INFO, "Log level set to %s", log_level_to_string(level));
}

/* ------------------------------------------------------------------ */
/* Req-001: Task Scheduler                                              */
/* ------------------------------------------------------------------ */

bool scheduler_add_task(const char *name, void (*handler)(void),
                         uint32_t period_ms, TaskPriority priority)
{
    if (g_task_count >= MAX_TASKS) return false;
    if (handler == nullptr) return false;

    auto *tcb = &g_tasks[g_task_count];
    tcb->name = name;
    tcb->handler = handler;
    tcb->period_ms = period_ms;
    tcb->last_run_ms = 0;
    tcb->exec_count = 0;
    tcb->max_exec_us = 0;
    tcb->min_exec_us = UINT32_MAX;
    tcb->priority = priority;
    tcb->enabled = true;

    g_task_count++;
    log_write(LogLevel::DEBUG, "Task '%s' registered (period=%u ms, prio=%d)",
              name, period_ms, static_cast<int>(priority));
    return true;
}

void scheduler_run(void)
{
    uint64_t now_ms = hal_get_tick_ms();

    for (uint8_t i = 0; i < g_task_count; i++) {
        auto *tcb = &g_tasks[i];
        if (!tcb->enabled) continue;

        if ((now_ms - tcb->last_run_ms) >= tcb->period_ms) {
            uint32_t start_us = hal_get_tick_us();

            tcb->handler();

            uint32_t elapsed_us = hal_get_tick_us() - start_us;
            tcb->exec_count++;
            if (elapsed_us > tcb->max_exec_us) tcb->max_exec_us = elapsed_us;
            if (elapsed_us < tcb->min_exec_us) tcb->min_exec_us = elapsed_us;
            tcb->last_run_ms = now_ms;
        }
    }

    /* Update system tick (10 ms tick assumed) */
    g_system_ticks_ms += 10;
}

/* ------------------------------------------------------------------ */
/* Req-002: Watchdog Management                                         */
/* ------------------------------------------------------------------ */

void wdt_init(void)
{
    /* Check reset reason */
    uint32_t rsr = hal_wdt_get_reset_reason();
    if (rsr & (1 << 2)) {  /* IWDG reset flag */
        g_wdt_reset_detected = true;
        g_consecutive_wdt_resets++;
    } else {
        /* Clean boot — reset counter */
        g_consecutive_wdt_resets = 0;
    }

    /* Check for safe mode threshold */
    if (g_consecutive_wdt_resets >= MAX_CONSECUTIVE_WDT) {
        g_safe_mode = true;
        log_write(LogLevel::FATAL,
                  "Entering SAFE MODE: %d consecutive watchdog resets",
                  g_consecutive_wdt_resets);
    }

    /* Initialize hardware WDT */
    uint32_t timeout = g_config_valid ? g_config.watchdog_timeout_s : g_wdt_timeout_s;
    if (timeout < WDT_TIMEOUT_MIN_S) timeout = WDT_TIMEOUT_MIN_S;
    if (timeout > WDT_TIMEOUT_MAX_S) timeout = WDT_TIMEOUT_MAX_S;

    hal_wdt_init(timeout);
    log_write(LogLevel::INFO, "Watchdog initialized: timeout=%u s", timeout);
}

void wdt_refresh(void)
{
    hal_wdt_refresh();
}

bool wdt_is_safe_mode(void)
{
    return g_safe_mode;
}

uint8_t wdt_get_consecutive_resets(void)
{
    return g_consecutive_wdt_resets;
}

/* ------------------------------------------------------------------ */
/* Req-004: Configuration Storage                                       */
/* ------------------------------------------------------------------ */

static uint16_t crc16_compute(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
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

void config_load(void)
{
    McuConfig cfg;
    hal_flash_read(CONFIG_FLASH_SECTOR, &cfg, sizeof(cfg));

    if (cfg.magic != CONFIG_MAGIC) {
        log_write(LogLevel::WARN, "Config CRC mismatch — reverting to defaults");
        config_defaults();
        return;
    }

    /* Verify CRC */
    uint16_t stored_crc = cfg.crc16;
    cfg.crc16 = 0;
    uint16_t computed_crc = crc16_compute((const uint8_t *)&cfg, sizeof(cfg) - sizeof(cfg.crc16));

    if (computed_crc != stored_crc) {
        log_write(LogLevel::WARN, "Config CRC mismatch — reverting to defaults");
        config_defaults();
        return;
    }

    g_config = cfg;
    g_config_valid = true;
    g_wdt_timeout_s = cfg.watchdog_timeout_s;
    g_log_level = static_cast<LogLevel>(cfg.log_level);

    log_write(LogLevel::INFO, "Configuration loaded (WDT=%us, log=%s)",
              g_wdt_timeout_s, log_level_to_string(g_log_level));
}

void config_defaults(void)
{
    memset(&g_config, 0, sizeof(g_config));
    g_config.magic = CONFIG_MAGIC;
    g_config.watchdog_timeout_s = 10;
    g_config.log_level = static_cast<uint8_t>(LogLevel::INFO);
    g_config.crc16 = crc16_compute((const uint8_t *)&g_config, sizeof(g_config) - sizeof(g_config.crc16));
    g_config_valid = true;
}

void config_save(void)
{
    /* Update CRC */
    g_config.crc16 = crc16_compute((const uint8_t *)&g_config, sizeof(g_config) - sizeof(g_config.crc16));

    hal_flash_erase(CONFIG_FLASH_SECTOR);
    int ret = hal_flash_write(CONFIG_FLASH_SECTOR, &g_config, sizeof(g_config));
    if (ret == 0) {
        log_write(LogLevel::INFO, "Configuration saved to flash");
    } else {
        log_write(LogLevel::ERROR, "Failed to save configuration");
    }
}

void config_check_factory_reset(void)
{
    if (!hal_gpio_read_factory_pin()) {
        /* Pin held low — start counting */
        uint32_t start = hal_get_tick_ms();
        while (!hal_gpio_read_factory_pin() &&
               (hal_get_tick_ms() - start) < FACTORY_RESET_HOLD_MS) {
            /* Wait — realistically use a timer ISR */
            hal_delay_ms(100);
        }

        if (!hal_gpio_read_factory_pin()) {
            hal_flash_erase(CONFIG_FLASH_SECTOR);
            log_write(LogLevel::WARN, "Factory reset applied");
            hal_system_reset();
        }
    }
}

/* ------------------------------------------------------------------ */
/* Application tasks (example)                                          */
/* ------------------------------------------------------------------ */

static void task_heartbeat(void)
{
    /* Toggle an LED — implemented in platform BSP */
    static bool toggle = false;
    toggle = !toggle;
}

static void task_sensor_read(void)
{
    /* Read sensor — implemented in platform BSP */
    static uint32_t count = 0;
    count++;
    log_write(LogLevel::TRACE, "Sensor read cycle %u", count);
}

static void task_comms(void)
{
    /* Poll communication interfaces */
}

/* ------------------------------------------------------------------ */
/* Application entry point                                              */
/* ------------------------------------------------------------------ */

int main(void)
{
    /* Platform initialization */
    hal_gpio_init();

    /* Load configuration (may trigger factory reset) */
    config_load();

    /* Check factory reset pin (Req-004) */
    config_check_factory_reset();

    /* Initialize watchdog (Req-002) */
    wdt_init();

    /* Register application tasks (Req-001) */
    scheduler_add_task("heartbeat", task_heartbeat, 500, TaskPriority::LOW);
    scheduler_add_task("sensor",   task_sensor_read, 100, TaskPriority::HIGH);
    scheduler_add_task("comms",    task_comms, 50, TaskPriority::NORMAL);

    /* Boot complete */
    log_write(LogLevel::INFO, "System boot OK — %d tasks registered, safe_mode=%d",
              g_task_count, g_safe_mode);

    /* Main loop */
    while (true) {
        if (!g_safe_mode) {
            scheduler_run();
        } else {
            /* Safe mode: minimal heartbeat only */
            task_heartbeat();
        }

        wdt_refresh();
    }

    return 0;
}

/* ------------------------------------------------------------------ */
/* HAL stubs (for host build / test)                                    */
/* ------------------------------------------------------------------ */

void     hal_wdt_init(uint32_t timeout_s) { (void)timeout_s; }
void     hal_wdt_refresh(void) {}
uint32_t hal_wdt_get_reset_reason(void) { return 0; }
void     hal_flash_read(uint32_t addr, void *buf, size_t len) { memset(buf, 0, len); (void)addr; }
int      hal_flash_write(uint32_t addr, const void *buf, size_t len) { (void)addr; (void)buf; (void)len; return 0; }
int      hal_flash_erase(uint32_t sector_addr) { (void)sector_addr; return 0; }
void     hal_uart_send(const char *str, uint16_t len) { (void)str; (void)len; }
void     hal_gpio_init(void) {}
bool     hal_gpio_read_factory_pin(void) { return true; }  /* Pulled high (inactive) */
uint64_t hal_get_tick_ms(void) { static uint64_t t = 0; return t += 10; }
uint32_t hal_get_tick_us(void) { static uint32_t t = 0; return t += 1000; }
void     hal_delay_ms(uint32_t ms) { (void)ms; }
void     hal_system_reset(void) {}
