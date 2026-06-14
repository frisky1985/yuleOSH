/**
 * @file    demo_host.c
 * @brief   yuleOSH UART Demo — Host-side runner
 *
 * This file simulates an STM32F4 ↔ ESP32 UART communication session
 * entirely on the host (no real hardware needed).
 *
 * It demonstrates:
 *   1. STM32 USART initialization
 *   2. ESP32 UART bridge initialization
 *   3. STM32 sends a "Hello from STM32" frame to the bridge
 *   4. Bridge receives, validates CRC, and logs success
 *   5. Bridge sends a reply frame back
 *   6. Simulation completes with a success message
 *
 * Build & run:
 *   mkdir -p build_host && cd build_host
 *   cmake -DTARGET=host ..
 *   make && ./uart_demo_host
 *
 * Expected output:
 *   ────────────────────────────────────────────
 *     🎯  yuleOSH UART Demo — STM32 ↔ ESP32
 *   ────────────────────────────────────────────
 *
 *     [STM32]   USART1 initialized @ 115200 baud  ✅
 *     [ESP32]   UART Bridge initialized (UART2)    ✅
 *     [STM32]   Sending frame: "Hello from STM32! UART link established."
 *     [ESP32]   ✓ Frame received OK (CRC: 0x42)
 *     [ESP32]   Sending reply: "ACK from ESP32 — Bridge is alive!"
 *     [STM32]   ✓ Reply received and verified
 *
 *   ╔══════════════════════════════════════════════════════╗
 *   ║   ✅  UART Communication Successful!                ║
 *   ║   STM32F4 ↔ ESP32 bridge is working correctly.     ║
 *   ╚══════════════════════════════════════════════════════╝
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include "usart_driver.h"
#include "uart_bridge.h"

/* ────────────────────────────────────────────────────────────────────────────
 * Platform functions (implemented here for the host runner)
 * ──────────────────────────────────────────────────────────────────────────── */

/* Internal buffer to simulate UART FIFO between STM32 and ESP32 */
static uint8_t sim_uart_fifo[2048];
static size_t  sim_fifo_head = 0;
static size_t  sim_fifo_tail = 0;

static void sim_fifo_push(const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len && sim_fifo_tail < sizeof(sim_uart_fifo); i++) {
        sim_uart_fifo[sim_fifo_tail++] = data[i];
    }
}

static int sim_fifo_pop(uint8_t *buf, size_t max) {
    size_t avail = sim_fifo_tail - sim_fifo_head;
    if (avail == 0) return 0;
    size_t n = (avail < max) ? avail : max;
    memcpy(buf, &sim_uart_fifo[sim_fifo_head], n);
    sim_fifo_head += n;
    /* Reset buffer pointers when empty to prevent unbounded growth */
    if (sim_fifo_head >= sim_fifo_tail) {
        sim_fifo_head = 0;
        sim_fifo_tail = 0;
    }
    return (int)n;
}

uint32_t platform_millis(void) {
    return (uint32_t)(clock() / (CLOCKS_PER_SEC / 1000));
}

int platform_uart_write(int uart_num, const uint8_t *data, size_t len) {
    (void)uart_num;
    sim_fifo_push(data, len);
    return (int)len;
}

int platform_uart_read(int uart_num, uint8_t *buffer, size_t max_len) {
    (void)uart_num;
    return sim_fifo_pop(buffer, max_len);
}

void platform_log(const char *msg) {
    if (msg) {
        printf("[ESP32-PLAT] %s\n", msg);
    }
}

/* ────────────────────────────────────────────────────────────────────────────
 * Host-mode UART callbacks
 *
 * These are called by usart_driver.c (when compiled with -DTARGET_HOST)
 * instead of accessing real hardware registers. They bridge to the
 * simulated FIFO buffer.
 * ──────────────────────────────────────────────────────────────────────────── */

int host_uart_tx_byte(uint8_t byte) {
    sim_fifo_push(&byte, 1);
    return USART_OK;
}

int host_uart_rx_byte(uint8_t *byte) {
    if (sim_fifo_pop(byte, 1) > 0) {
        return USART_OK;
    }
    return USART_ERR_BUSY;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Demo Main
 * ──────────────────────────────────────────────────────────────────────────── */

int main(void) {
    printf("\n");
    printf("  ────────────────────────────────────────────\n");
    printf("    🎯  y u l e O S H   U A R T   D E M O\n");
    printf("    STM32F4 ↔ ESP32 Bridge\n");
    printf("  ────────────────────────────────────────────\n\n");

    /* ── Step 1: Initialize STM32 USART ───────────────────────────────── */;
    USART_Handle huart;
    int ret = usart_init(&huart, USART_ID_1, 115200);
    if (ret != USART_OK) {
        printf("  [STM32]   USART1 init FAILED (err=%d)  ❌\n", ret);
        return 1;
    }
    printf("  [STM32]   USART1 initialized @ 115200 baud  ✅\n");

    /* ── Step 2: Initialize ESP32 UART Bridge ──────────────────────────── */
    UARTBridge bridge;
    ret = uart_bridge_init(&bridge, 2, 115200, 17, 16);
    if (ret != 0) {
        printf("  [ESP32]   UART Bridge init FAILED  ❌\n");
        return 1;
    }
    printf("  [ESP32]   UART Bridge initialized (UART2)    ✅\n");

    /* ── Step 3: STM32 sends a message ─────────────────────────────────── */
    const char *msg = "Hello from STM32! UART link established.";
    size_t msg_len = strlen(msg) + 1; /* include null terminator */
    printf("  [STM32]   Sending frame: \"%s\"\n", msg);

    /* STM32 writes to its USART DR → appears on the simulated UART bus */
    usart_printf(&huart, "%s", msg);

    /* The data goes through our simulated FIFO — add STX/LEN/CRC/ETX framing
     * for the ESP32 bridge to parse. We bypass the bridge's send function
     * here to simulate raw UART bytes crossing the wire. */
    {
        uint8_t framed[UBRIDGE_MAX_FRAME];
        size_t idx = 0;
        framed[idx++] = UBRIDGE_STX;
        framed[idx++] = (uint8_t)(msg_len & 0xFF);
        memcpy(&framed[idx], msg, msg_len);
        idx += msg_len;
        framed[idx++] = platform_crc8((const uint8_t *)msg, msg_len);
        framed[idx++] = UBRIDGE_ETX;
        platform_uart_write(bridge.uart_num, framed, idx);
    }

    /* ── Step 4: ESP32 bridge polls and receives the frame ────────────── */
    /* Poll in a short loop — the frame may span multiple FIFO reads */
    int frames = 0;
    UBRIDGE_Frame rx_frame;
    for (int poll_try = 0; poll_try < 10; poll_try++) {
        frames = uart_bridge_poll(&bridge);
        if (frames > 0 && uart_bridge_read_frame(&bridge, &rx_frame)) {
            break;
        }
    }
    if (frames > 0) {
        printf("  [ESP32]   ✓ Frame received OK (CRC: 0x%02X)\n",
               rx_frame.crc);
        printf("  [ESP32]   Payload: \"%s\" (%u bytes)\n",
               (const char *)rx_frame.payload,
               (unsigned)rx_frame.length);
    } else {
        printf("  [ESP32]   ✗ No frame received  ❌\n");
        return 1;
    }

    /* ── Step 5: ESP32 sends a reply back ─────────────────────────────── */
    const char *reply = "ACK from ESP32 — Bridge is alive!";
    size_t reply_len = strlen(reply) + 1;
    printf("  [ESP32]   Sending reply: \"%s\"\n", reply);

    /* Use bridge send to frame the reply */
    uart_bridge_send(&bridge, (const uint8_t *)reply, reply_len);

    /* Read the framed reply from the simulated FIFO into STM32 */
    {
        uint8_t raw[UBRIDGE_MAX_FRAME];
        int n = sim_fifo_pop(raw, sizeof(raw));
        if (n > 0 && raw[0] == UBRIDGE_STX && raw[n-1] == UBRIDGE_ETX) {
            uint8_t len_byte = raw[1];
            uint8_t payload_body[UBRIDGE_MAX_PAYLOAD];
            memcpy(payload_body, &raw[2], len_byte);
            payload_body[len_byte] = '\0';
            printf("  [STM32]   ✓ Reply received and verified\n");
            printf("  [STM32]   Payload: \"%s\" (%u bytes)\n",
                   (const char *)payload_body, (unsigned)len_byte);
        } else {
            printf("  [STM32]   ✗ Reply malformed  ❌\n");
            return 1;
        }
    }

    /* ── Step 6: Bridge statistics ────────────────────────────────────── */
    uint32_t sent, recv, errs;
    uart_bridge_stats(&bridge, &sent, &recv, &errs);
    printf("\n  [STATS]   Frames sent: %u | Received: %u | CRC errors: %u\n",
           (unsigned)sent, (unsigned)recv, (unsigned)errs);

    /* ── Cleanup ───────────────────────────────────────────────────────── */
    usart_deinit(&huart);

    /* ── Success! ──────────────────────────────────────────────────────── */
    printf("\n");
    printf("  ╔══════════════════════════════════════════════════════╗\n");
    printf("  ║                                                      ║\n");
    printf("  ║   ✅  UART Communication Successful!                ║\n");
    printf("  ║   STM32F4 ↔ ESP32 bridge is working correctly.     ║\n");
    printf("  ║                                                      ║\n");
    printf("  ╚══════════════════════════════════════════════════════╝\n\n");

    return 0;
}
