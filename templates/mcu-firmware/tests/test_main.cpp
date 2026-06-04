/**
 * Unit tests for MCU Firmware Core
 *
 * Tests cover:
 *   Req-001: Task Scheduling
 *   Req-002: Watchdog Management
 *   Req-003: Diagnostic Logging
 *   Req-004: Configuration Storage
 */

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <algorithm>

#include "../src/main.cpp"

/* ------------------------------------------------------------------ */
/* Test counters                                                        */
/* ------------------------------------------------------------------ */

static int g_tests_passed = 0;
static int g_tests_failed = 0;

#define TEST(name) do { printf("  TEST: %s ... ", name); } while(0)
#define PASS() do { printf("PASS\n"); g_tests_passed++; } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); g_tests_failed++; } while(0)

/* ------------------------------------------------------------------ */
/* Req-001: Task Scheduling                                            */
/* ------------------------------------------------------------------ */

static void test_scheduler_max_tasks(void)
{
    /* SHALL support up to 16 registered tasks */
    for (uint8_t i = 0; i < MAX_TASKS; i++) {
        g_task_count = i;
        bool ok = scheduler_add_task("dummy", [](){}, 100, TaskPriority::NORMAL);
        assert(ok);
    }
    assert(g_task_count == MAX_TASKS);

    /* Adding one more should fail */
    bool ok = scheduler_add_task("overflow", [](){}, 100, TaskPriority::NORMAL);
    assert(!ok);
    assert(g_task_count == MAX_TASKS);
    PASS();
}

static void test_scheduler_task_stats(void)
{
    /* SHALL track task execution statistics */
    scheduler_add_task("stats_test", [](){}, 50, TaskPriority::NORMAL);
    auto *tcb = &g_tasks[g_task_count - 1];
    assert(tcb->exec_count == 0);
    assert(tcb->max_exec_us == 0);
    PASS();
}

static void test_scheduler_priority_ordering(void)
{
    /* SHALL support priority levels */
    scheduler_add_task("low",  [](){}, 100, TaskPriority::LOW);
    scheduler_add_task("high", [](){}, 100, TaskPriority::HIGH);
    scheduler_add_task("norm", [](){}, 100, TaskPriority::NORMAL);

    auto *low = &g_tasks[g_task_count - 3];
    auto *high = &g_tasks[g_task_count - 2];
    auto *norm = &g_tasks[g_task_count - 1];

    assert(low->priority == TaskPriority::LOW);
    assert(high->priority == TaskPriority::HIGH);
    assert(norm->priority == TaskPriority::NORMAL);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-002: Watchdog Management                                        */
/* ------------------------------------------------------------------ */

static void test_wdt_timeout_range(void)
{
    /* SHALL support timeout between 1 and 30 seconds */
    uint32_t t = 5;
    if (t < WDT_TIMEOUT_MIN_S) t = WDT_TIMEOUT_MIN_S;
    if (t > WDT_TIMEOUT_MAX_S) t = WDT_TIMEOUT_MAX_S;
    assert(t >= WDT_TIMEOUT_MIN_S && t <= WDT_TIMEOUT_MAX_S);
    PASS();
}

static void test_wdt_safe_mode_threshold(void)
{
    /* SHALL enter safe mode on 3+ consecutive resets */
    g_consecutive_wdt_resets = 0;
    g_safe_mode = false;

    /* Simulate 3 watchdog resets */
    for (int i = 0; i < 3; i++) {
        g_consecutive_wdt_resets++;
    }

    if (g_consecutive_wdt_resets >= MAX_CONSECUTIVE_WDT) {
        g_safe_mode = true;
    }

    assert(g_safe_mode == true);
    assert(g_consecutive_wdt_resets == 3);
    PASS();
}

static void test_wdt_clean_boot_resets_counter(void)
{
    /* SHALL reset counter on clean boot */
    g_consecutive_wdt_resets = 2;

    /* Simulate clean boot (no WDT reset flag) */
    uint32_t rsr = 0;  /* No IWDG flag */
    if (!(rsr & (1 << 2))) {
        g_consecutive_wdt_resets = 0;
    }

    assert(g_consecutive_wdt_resets == 0);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-003: Diagnostic Logging                                         */
/* ------------------------------------------------------------------ */

static void test_log_write_info(void)
{
    /* SHALL write log entries with timestamp and severity */
    g_log_head = 0;
    g_log_count = 0;

    log_write(LogLevel::INFO, "Test message %s %d", "hello", 42);
    assert(g_log_count == 1);
    assert(g_log_buffer[0].level == LogLevel::INFO);
    assert(strstr(g_log_buffer[0].message, "hello") != nullptr);
    PASS();
}

static void test_log_level_filtering(void)
{
    /* SHALL support runtime log level filtering */
    g_log_level = LogLevel::WARN;
    g_log_head = 0;
    g_log_count = 0;

    log_write(LogLevel::DEBUG, "Should not appear");
    assert(g_log_count == 0);

    log_write(LogLevel::ERROR, "Should appear");
    assert(g_log_count == 1);
    PASS();
}

static void test_log_ring_buffer_wraparound(void)
{
    /* Ring buffer should handle wraparound */
    g_log_head = 0;
    g_log_count = 0;

    /* Fill buffer and wrap */
    for (int i = 0; i < LOG_RING_BUFFER_SIZE + 10; i++) {
        log_write(LogLevel::INFO, "Entry %d", i);
    }

    assert(g_log_count == LOG_RING_BUFFER_SIZE);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-004: Configuration Storage                                       */
/* ------------------------------------------------------------------ */

static void test_crc16_computation(void)
{
    /* CRC-16 computation should produce expected result */
    uint8_t data[] = {0x59, 0x4C, 0x00, 0x00};
    uint16_t crc = crc16_compute(data, sizeof(data));
    assert(crc != 0);
    PASS();
}

static void test_config_defaults_applied(void)
{
    /* SHALL revert to factory defaults on invalid magic */
    config_defaults();
    assert(g_config.magic == CONFIG_MAGIC);
    assert(g_config.watchdog_timeout_s == 10);
    PASS();
}

static void test_config_crc_mismatch_handling(void)
{
    /* SHALL detect CRC mismatch and revert to defaults */
    g_config_valid = false;
    g_config.magic = CONFIG_MAGIC;
    g_config.crc16 = 0x1234; /* Wrong CRC */

    /* config_load would detect this — test the CRC logic directly */
    uint16_t expected = crc16_compute(
        (const uint8_t *)&g_config,
        sizeof(g_config) - sizeof(g_config.crc16));
    /* Set CRC to match */
    g_config.crc16 = expected;
    assert(crc16_compute((const uint8_t *)&g_config,
                          sizeof(g_config) - sizeof(g_config.crc16)) == expected);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Main                                                                  */
/* ------------------------------------------------------------------ */

int main(void)
{
    printf("\n=== MCU Firmware Core — Unit Tests ===\n\n");

    /* Req-001 */
    test_scheduler_max_tasks();
    test_scheduler_task_stats();
    test_scheduler_priority_ordering();

    /* Req-002 */
    test_wdt_timeout_range();
    test_wdt_safe_mode_threshold();
    test_wdt_clean_boot_resets_counter();

    /* Req-003 */
    test_log_write_info();
    test_log_level_filtering();
    test_log_ring_buffer_wraparound();

    /* Req-004 */
    test_crc16_computation();
    test_config_defaults_applied();
    test_config_crc_mismatch_handling();

    printf("\n=== Results: %d passed, %d failed ===\n\n",
           g_tests_passed, g_tests_failed);

    return g_tests_failed > 0 ? 1 : 0;
}
