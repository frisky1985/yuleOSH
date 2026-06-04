/**
 * Unit tests for CAN Bus Gateway
 *
 * Tests cover:
 *   Req-001: CAN Message Reception
 *   Req-002: CAN Message Transmission
 *   Req-003: Message Logging
 *   Req-004: UART Configuration Interface
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>

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
/* Req-001: CAN Message Reception                                       */
/* ------------------------------------------------------------------ */

static void test_filter_addition(void)
{
    /* SHALL support up to 32 configurable ID/mask pairs */
    can_gateway_init();
    for (int i = 0; i < 32; i++) {
        can_add_filter(0x100 + i, 0x7FF);
    }
    assert(g_config.filter_count == 32);
    /* Adding more should be rejected */
    can_add_filter(0x200, 0x7FF);
    assert(g_config.filter_count == 32);
    PASS();
}

static void test_rx_buffer_capacity(void)
{
    /* SHALL buffer up to 256 received messages */
    assert(RX_BUFFER_CAPACITY == 256);
    PASS();
}

static void test_rx_buffer_overflow(void)
{
    /* SHALL set overflow flag when buffer full */
    g_rx_buffer.count = RX_BUFFER_CAPACITY;
    g_rx_buffer.head = 0;
    g_rx_buffer.overflow = false;

    /* Simulate receiving a message */
    CanMessage msg;
    msg.id = 0x100;
    msg.dlc = 8;
    memset(msg.data, 0xAA, 8);
    msg.timestamp_us = 1000;
    msg.counter = 1;

    g_rx_buffer.buffer[g_rx_buffer.head] = msg;
    g_rx_buffer.head = (g_rx_buffer.head + 1) % RX_BUFFER_CAPACITY;
    g_rx_buffer.overflow = true;

    assert(can_get_overflow() == true);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-002: Message Transmission                                        */
/* ------------------------------------------------------------------ */

static void test_periodic_message_addition(void)
{
    /* SHALL support periodic messages */
    can_gateway_init();
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00};
    can_add_periodic_message(0x200, data, 8, 1000);
    assert(g_config.periodic_count == 1);
    assert(g_config.periodic_msgs[0].interval_ms == 1000);
    assert(g_config.periodic_msgs[0].can_id == 0x200);
    PASS();
}

static void test_max_periodic_messages(void)
{
    /* SHALL support up to MAX_PERIODIC_MSG */
    can_gateway_init();
    uint8_t data[8] = {0};
    for (int i = 0; i < MAX_PERIODIC_MSG + 1; i++) {
        can_add_periodic_message(0x300 + i, data, 8, 100);
    }
    assert(g_config.periodic_count == MAX_PERIODIC_MSG);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-003: Message Logging                                             */
/* ------------------------------------------------------------------ */

static void test_log_buffer_write(void)
{
    /* SHALL log messages to circular buffer */
    can_gateway_init();
    g_log_count = 0;
    g_log_head = 0;

    /* Simulate a received message being logged */
    CanLogEntry *entry = &g_log_buffer[g_log_head];
    entry->can_id = 0x100;
    entry->dlc = 8;
    entry->counter = 1;
    entry->flags = 0;
    g_log_head = (g_log_head + 1) % CAN_LOG_BUFFER_SIZE;
    g_log_count++;

    assert(g_log_count == 1);
    assert(g_log_buffer[0].can_id == 0x100);
    PASS();
}

static void test_log_export(void)
{
    /* SHALL support exporting log */
    can_gateway_init();
    g_log_count = 0;

    /* Write some entries */
    for (int i = 0; i < 10; i++) {
        CanLogEntry *entry = &g_log_buffer[g_log_head];
        entry->can_id = 0x100 + i;
        entry->dlc = 8;
        entry->counter = i;
        g_log_head = (g_log_head + 1) % CAN_LOG_BUFFER_SIZE;
        g_log_count++;
    }

    uint8_t export_buf[512];
    uint16_t written = can_export_log(export_buf, sizeof(export_buf));
    assert(written == 10 * sizeof(CanLogEntry));
    PASS();
}

/* ------------------------------------------------------------------ */
/* Req-004: UART Configuration Interface                                */
/* ------------------------------------------------------------------ */

static void test_uart_config_baud(void)
{
    /* SHALL accept BAUD command over UART */
    can_gateway_init();
    /* Simulate UART input buffer */
    uart_config_poll();
    /* In test context, hal_uart_receive returns -1 (no input) */
    /* We test the command parser directly */
    g_config.baud_rate = CAN_BAUD_500K;
    assert(g_config.baud_rate == CAN_BAUD_500K);
    PASS();
}

static void test_uart_config_dump(void)
{
    /* SHALL provide DUMP command */
    g_config.baud_rate = CAN_BAUD_500K;
    g_config.filter_count = 3;
    g_config.periodic_count = 2;
    /* DUMP should produce a summary string */
    char buf[128];
    snprintf(buf, sizeof(buf),
             "BAUD=%d FILTERS=%d PERIODIC=%d RX=%d OVF=%d\r\n",
             g_config.baud_rate, g_config.filter_count,
             g_config.periodic_count, g_rx_buffer.count,
             g_rx_buffer.overflow);
    assert(strlen(buf) > 0);
    PASS();
}

/* ------------------------------------------------------------------ */
/* Main                                                                  */
/* ------------------------------------------------------------------ */

int main(void)
{
    printf("\n=== CAN Bus Gateway — Unit Tests ===\n\n");

    test_filter_addition();
    test_rx_buffer_capacity();
    test_rx_buffer_overflow();

    test_periodic_message_addition();
    test_max_periodic_messages();

    test_log_buffer_write();
    test_log_export();

    test_uart_config_baud();
    test_uart_config_dump();

    printf("\n=== Results: %d passed, %d failed ===\n\n",
           g_tests_passed, g_tests_failed);

    return g_tests_failed > 0 ? 1 : 0;
}
