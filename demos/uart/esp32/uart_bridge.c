/**
 * @file    uart_bridge.c
 * @brief   ESP32 UART ↔ WiFi Bridge Implementation — yuleOSH UART Demo
 *
 * Implements the frame protocol state machine, CRC verification, and
 * bridging logic between STM32 UART and cloud/console endpoints.
 */

#include "uart_bridge.h"
#include <stdio.h>
#include <string.h>

/* ────────────────────────────────────────────────────────────────────────────
 * Default CRC-8 (Dallas 1-Wire) — polynomial 0x31, init 0x00
 * ──────────────────────────────────────────────────────────────────────────── */
static const uint8_t crc8_table[256] = {
    0x00, 0x31, 0x62, 0x53, 0xC4, 0xF5, 0xA6, 0x97,
    0xB9, 0x88, 0xDB, 0xEA, 0x7D, 0x4C, 0x1F, 0x2E,
    0x43, 0x72, 0x21, 0x10, 0x87, 0xB6, 0xE5, 0xD4,
    0xFA, 0xCB, 0x98, 0xA9, 0x3E, 0x0F, 0x5C, 0x6D,
    0x86, 0xB7, 0xE4, 0xD5, 0x42, 0x73, 0x20, 0x11,
    0x3F, 0x0E, 0x5D, 0x6C, 0xFB, 0xCA, 0x99, 0xA8,
    0xC5, 0xF4, 0xA7, 0x96, 0x01, 0x30, 0x63, 0x52,
    0x7C, 0x4D, 0x1E, 0x2F, 0xB8, 0x89, 0xDA, 0xEB,
    0x3D, 0x0C, 0x5F, 0x6E, 0xF9, 0xC8, 0x9B, 0xAA,
    0x84, 0xB5, 0xE6, 0xD7, 0x40, 0x71, 0x22, 0x13,
    0x7E, 0x4F, 0x1C, 0x2D, 0xBA, 0x8B, 0xD8, 0xE9,
    0xC7, 0xF6, 0xA5, 0x94, 0x03, 0x32, 0x61, 0x50,
    0xBB, 0x8A, 0xD9, 0xE8, 0x7F, 0x4E, 0x1D, 0x2C,
    0x02, 0x33, 0x60, 0x51, 0xC6, 0xF7, 0xA4, 0x95,
    0xF8, 0xC9, 0x9A, 0xAB, 0x3C, 0x0D, 0x5E, 0x6F,
    0x41, 0x70, 0x23, 0x12, 0x85, 0xB4, 0xE7, 0xD6,
    0x7A, 0x4B, 0x18, 0x29, 0xBE, 0x8F, 0xDC, 0xED,
    0xC3, 0xF2, 0xA1, 0x90, 0x07, 0x36, 0x65, 0x54,
    0x39, 0x08, 0x5B, 0x6A, 0xFD, 0xCC, 0x9F, 0xAE,
    0x80, 0xB1, 0xE2, 0xD3, 0x44, 0x75, 0x26, 0x17,
    0xFC, 0xCD, 0x9E, 0xAF, 0x38, 0x09, 0x5A, 0x6B,
    0x45, 0x74, 0x27, 0x16, 0x81, 0xB0, 0xE3, 0xD2,
    0xBF, 0x8E, 0xDD, 0xEC, 0x7B, 0x4A, 0x19, 0x28,
    0x06, 0x37, 0x64, 0x55, 0xC2, 0xF3, 0xA0, 0x91,
    0x47, 0x76, 0x25, 0x14, 0x83, 0xB2, 0xE1, 0xD0,
    0xFE, 0xCF, 0x9C, 0xAD, 0x3A, 0x0B, 0x58, 0x69,
    0x04, 0x35, 0x66, 0x57, 0xC0, 0xF1, 0xA2, 0x93,
    0xBD, 0x8C, 0xDF, 0xEE, 0x79, 0x48, 0x1B, 0x2A,
    0xC1, 0xF0, 0xA3, 0x92, 0x05, 0x34, 0x67, 0x56,
    0x78, 0x49, 0x1A, 0x2B, 0xBC, 0x8D, 0xDE, 0xEF,
    0x82, 0xB3, 0xE0, 0xD1, 0x46, 0x77, 0x24, 0x15,
    0x3B, 0x0A, 0x59, 0x68, 0xFF, 0xCE, 0x9D, 0xAC,
};

uint8_t platform_crc8(const uint8_t *data, size_t len) {
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; i++) {
        crc = crc8_table[crc ^ data[i]];
    }
    return crc;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Bridge implementation
 * ──────────────────────────────────────────────────────────────────────────── */

int uart_bridge_init(UARTBridge *bridge, int uart_num, uint32_t baud,
                     int tx_pin, int rx_pin) {
    if (!bridge) return -1;

    memset(bridge, 0, sizeof(UARTBridge));

    bridge->uart_num = uart_num;
    bridge->baud     = baud;
    bridge->tx_pin   = tx_pin;
    bridge->rx_pin   = rx_pin;
    bridge->rx_state = UBRIDGE_STATE_IDLE;

    /* In real ESP-IDF this would call:
     *   const uart_config_t cfg = {
     *       .baud_rate = baud,
     *       .data_bits = UART_DATA_8_BITS,
     *       .parity    = UART_PARITY_DISABLE,
     *       .stop_bits = UART_STOP_BITS_1,
     *       .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
     *   };
     *   uart_param_config(uart_num, &cfg);
     *   uart_set_pin(uart_num, tx_pin, rx_pin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
     *   uart_driver_install(uart_num, UBRIDGE_RX_BUF_SIZE, UBRIDGE_TX_BUF_SIZE, 0, NULL, 0);
     */
    char log_buf[80];
    int n = snprintf(log_buf, sizeof(log_buf),
                     "[UART Bridge] Init UART%d @ %lu baud (TX=%d, RX=%d)",
                     uart_num, (unsigned long)baud, tx_pin, rx_pin);
    if (n > 0) platform_log(log_buf);

    return 0;
}

static void reset_frame_parser(UARTBridge *bridge) {
    bridge->rx_state = UBRIDGE_STATE_IDLE;
    bridge->rx_index = 0;
    memset(bridge->rx_data, 0, sizeof(bridge->rx_data));
    bridge->rx_frame.valid = 0;
}

int uart_bridge_poll(UARTBridge *bridge) {
    if (!bridge) return 0;

    uint8_t byte;
    uint8_t raw_buffer[64];
    int n_read = platform_uart_read(bridge->uart_num, raw_buffer, sizeof(raw_buffer));
    if (n_read <= 0) return 0;

    int frames_complete = 0;

    for (int i = 0; i < n_read; i++) {
        byte = raw_buffer[i];

        switch (bridge->rx_state) {
            case UBRIDGE_STATE_IDLE:
                if (byte == UBRIDGE_STX) {
                    bridge->rx_state = UBRIDGE_STATE_LEN;
                    bridge->rx_index = 0;
                    bridge->rx_frame.valid = 0;
                }
                break;

            case UBRIDGE_STATE_LEN:
                bridge->rx_frame.length = byte;
                if (byte == 0) {
                    reset_frame_parser(bridge);  /* invalid length */
                } else {
                    bridge->rx_index = 0;
                    bridge->rx_state = UBRIDGE_STATE_PAYLOAD;
                }
                break;

            case UBRIDGE_STATE_PAYLOAD:
                bridge->rx_data[bridge->rx_index++] = byte;
                if (bridge->rx_index >= bridge->rx_frame.length) {
                    bridge->rx_state = UBRIDGE_STATE_CRC;
                }
                break;

            case UBRIDGE_STATE_CRC:
                bridge->rx_frame.crc = byte;
                /* Verify CRC */
                {
                    uint8_t calc_crc = platform_crc8(bridge->rx_data, bridge->rx_frame.length);
                    if (calc_crc == byte) {
                        bridge->rx_state = UBRIDGE_STATE_ETX;
                    } else {
                        bridge->frames_crc_errors++;
                        reset_frame_parser(bridge);
                    }
                }
                break;

            case UBRIDGE_STATE_ETX:
                if (byte == UBRIDGE_ETX) {
                    /* Valid frame received */
                    memcpy(bridge->rx_frame.payload, bridge->rx_data, bridge->rx_frame.length);
                    bridge->frames_received++;
                    frames_complete++;
                    platform_log("[UART Bridge] ✓ Frame received OK");
                    /* Set valid AFTER reset_frame_parser to avoid clobber */
                    bridge->rx_state = UBRIDGE_STATE_IDLE;
                    bridge->rx_index = 0;
                    bridge->rx_frame.valid = 1;
                } else {
                    reset_frame_parser(bridge);
                }
                break;

            default:
                reset_frame_parser(bridge);
                break;
        }
    }

    return frames_complete;
}

int uart_bridge_send(UARTBridge *bridge, const uint8_t *payload, size_t len) {
    if (!bridge || !payload) return -1;
    if (len > UBRIDGE_MAX_PAYLOAD) return -1;

    uint8_t frame[UBRIDGE_MAX_FRAME];
    size_t idx = 0;

    frame[idx++] = UBRIDGE_STX;
    frame[idx++] = (uint8_t)(len & 0xFF);
    memcpy(&frame[idx], payload, len);
    idx += len;
    frame[idx++] = platform_crc8(payload, len);
    frame[idx++] = UBRIDGE_ETX;

    int written = platform_uart_write(bridge->uart_num, frame, idx);
    if (written > 0) {
        bridge->frames_sent++;
        return 0;
    }
    return -1;
}

int uart_bridge_read_frame(UARTBridge *bridge, UBRIDGE_Frame *frame) {
    if (!bridge || !frame) return 0;

    if (bridge->rx_frame.valid) {
        memcpy(frame, &bridge->rx_frame, sizeof(UBRIDGE_Frame));
        bridge->rx_frame.valid = 0;  /* mark consumed */
        return 1;
    }
    return 0;
}

void uart_bridge_mqtt_publish(UARTBridge *bridge, const char *topic,
                              const UBRIDGE_Frame *frame) {
    (void)bridge;
    /* In real ESP-IDF this would call:
     *   esp_mqtt_client_publish(client, topic,
     *                           (const char *)frame->payload,
     *                           frame->length, 0, 0);
     */
    char log_buf[128];
    int n = snprintf(log_buf, sizeof(log_buf),
                     "[UART Bridge] MQTT publish → %s  (%u bytes)",
                     topic ? topic : "(null)", (unsigned)frame->length);
    if (n > 0) platform_log(log_buf);
}

void uart_bridge_stats(UARTBridge *bridge, uint32_t *sent,
                       uint32_t *received, uint32_t *crc_errs) {
    if (sent)     *sent     = bridge->frames_sent;
    if (received) *received = bridge->frames_received;
    if (crc_errs) *crc_errs = bridge->frames_crc_errors;
}
