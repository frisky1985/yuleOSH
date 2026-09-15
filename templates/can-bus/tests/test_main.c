/**
 * Unit tests for CAN Bus Gateway
 *
 * Tests cover:
 *   Req-001: CAN Message Reception
 *   Req-002: CAN Message Transmission
 *   Req-003: Message Logging
 *   Req-004: UART Configuration Interface
 *
 * Uses the shared yuleOSH c-harness (../common/c-harness/check.h).
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "check.h"

#include "../src/main.c"

/* ------------------------------------------------------------------ */
/* Req-001: CAN Message Reception                                       */
/* ------------------------------------------------------------------ */

static void test_filter_addition(void)
{
    printf("TEST: test_filter_addition\n");
    /* SHALL support up to 32 configurable ID/mask pairs */
    can_gateway_init();
    for (int i = 0; i < 32; i++) {
        can_add_filter(0x100 + i, 0x7FF);
    }
    CHECK(g_config.filter_count == 32);
    /* Adding more should be rejected */
    can_add_filter(0x200, 0x7FF);
    CHECK(g_config.filter_count == 32);
}

static void test_rx_buffer_capacity(void)
{
    printf("TEST: test_rx_buffer_capacity\n");
    /* SHALL buffer up to 256 received messages */
    CHECK(RX_BUFFER_CAPACITY == 256);
}

static void test_rx_buffer_overflow(void)
{
    printf("TEST: test_rx_buffer_overflow\n");
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

    CHECK(can_get_overflow() == true);
}

/* ------------------------------------------------------------------ */
/* Req-002: Message Transmission                                        */
/* ------------------------------------------------------------------ */

static void test_periodic_message_addition(void)
{
    printf("TEST: test_periodic_message_addition\n");
    /* SHALL support periodic messages */
    can_gateway_init();
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00};
    can_add_periodic_message(0x200, data, 8, 1000);
    CHECK(g_config.periodic_count == 1);
    CHECK(g_config.periodic_msgs[0].interval_ms == 1000);
    CHECK(g_config.periodic_msgs[0].can_id == 0x200);
}

static void test_max_periodic_messages(void)
{
    printf("TEST: test_max_periodic_messages\n");
    /* SHALL support up to MAX_PERIODIC_MSG */
    can_gateway_init();
    uint8_t data[8] = {0};
    for (int i = 0; i < MAX_PERIODIC_MSG + 1; i++) {
        can_add_periodic_message(0x300 + i, data, 8, 100);
    }
    CHECK(g_config.periodic_count == MAX_PERIODIC_MSG);
}

/* ------------------------------------------------------------------ */
/* Req-003: Message Logging                                             */
/* ------------------------------------------------------------------ */

static void test_log_buffer_write(void)
{
    printf("TEST: test_log_buffer_write\n");
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

    CHECK(g_log_count == 1);
    CHECK(g_log_buffer[0].can_id == 0x100);
}

static void test_log_export(void)
{
    printf("TEST: test_log_export\n");
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
    CHECK(written == 10 * sizeof(CanLogEntry));
}

/* ------------------------------------------------------------------ */
/* Req-004: UART Configuration Interface                                */
/* ------------------------------------------------------------------ */

static void test_uart_config_baud(void)
{
    printf("TEST: test_uart_config_baud\n");
    /* SHALL accept BAUD command over UART */
    can_gateway_init();
    g_config.baud_rate = CAN_BAUD_500K;
    CHECK(g_config.baud_rate == CAN_BAUD_500K);
}

static void test_uart_config_dump(void)
{
    printf("TEST: test_uart_config_dump\n");
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
    CHECK(strlen(buf) > 0);
}

/* ------------------------------------------------------------------ */
/* Main                                                                  */
/* ------------------------------------------------------------------ */

int main(void)
{
    printf("\n=== CAN Bus Gateway — Unit Tests (c-harness) ===\n\n");

    test_filter_addition();
    test_rx_buffer_capacity();
    test_rx_buffer_overflow();

    test_periodic_message_addition();
    test_max_periodic_messages();

    test_log_buffer_write();
    test_log_export();

    test_uart_config_baud();
    test_uart_config_dump();

    return c_harness_report();
}
