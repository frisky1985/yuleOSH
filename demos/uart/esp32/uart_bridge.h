/**
 * @file    uart_bridge.h
 * @brief   ESP32 UART ↔ WiFi Bridge — yuleOSH UART Demo
 * @author  yuleOSH Demo Team
 *
 * Target:  ESP32 (Xtensa LX6) / ESP-IDF v5.x
 *
 * The ESP32 sits between the STM32F4 (sensor/motor controller) and the cloud.
 * It bridges UART frames from the STM32 to:
 *   a) MQTT (AWS IoT / Mosquitto)
 *   b) Serial console (USB-CDC for debug)
 *   c) Log buffer (local file system / SPIFFS)
 *
 * Protocol:
 *   STM32 → ESP32:  <STX><LEN><PAYLOAD><CRC><ETX>
 *   ESP32 → STM32:  <STX><CMD_ID><PAYLOAD><CRC><ETX>
 *
 * STX = 0x02, ETX = 0x03
 *
 * Example frame:
 *   02 0A 48 65 6C 6C 6F 0A 00  D7  03
 *   STX LEN H  e  l  l  o  \n \0 CRC ETX
 *
 * Usage:
 *   UARTBridge bridge;
 *   uart_bridge_init(&bridge, UART_NUM_2, 115200, GPIO_NUM_17, GPIO_NUM_16);
 *   uart_bridge_poll(&bridge);
 */

#ifndef YULEOSH_UART_BRIDGE_H
#define YULEOSH_UART_BRIDGE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ────────────────────────────────────────────────────────────────────────────
 * Protocol constants
 * ──────────────────────────────────────────────────────────────────────────── */

#define UBRIDGE_STX             0x02
#define UBRIDGE_ETX             0x03
#define UBRIDGE_ESC             0x1B

#define UBRIDGE_MAX_PAYLOAD     256
#define UBRIDGE_FRAME_OVERHEAD  4   /* STX + LEN + CRC + ETX */
#define UBRIDGE_MAX_FRAME       (UBRIDGE_MAX_PAYLOAD + UBRIDGE_FRAME_OVERHEAD)

#define UBRIDGE_RX_BUF_SIZE     1024
#define UBRIDGE_TX_BUF_SIZE     512

/* ────────────────────────────────────────────────────────────────────────────
 * Command IDs (ESP32 → STM32)
 * ──────────────────────────────────────────────────────────────────────────── */

#define UBRIDGE_CMD_PING        0x01
#define UBRIDGE_CMD_LED_ON      0x10
#define UBRIDGE_CMD_LED_OFF     0x11
#define UBRIDGE_CMD_SAMPLE_RATE 0x20
#define UBRIDGE_CMD_REBOOT      0xFF

/* ────────────────────────────────────────────────────────────────────────────
 * Frame state machine
 * ──────────────────────────────────────────────────────────────────────────── */

typedef enum {
    UBRIDGE_STATE_IDLE,     /* Waiting for STX */
    UBRIDGE_STATE_LEN,      /* Received STX, reading length byte */
    UBRIDGE_STATE_PAYLOAD,  /* Reading payload bytes */
    UBRIDGE_STATE_CRC,      /* Reading CRC */
    UBRIDGE_STATE_ETX,      /* Checking ETX */
} UBRIDGE_State;

/* ────────────────────────────────────────────────────────────────────────────
 * Received frame (parsed)
 * ──────────────────────────────────────────────────────────────────────────── */

typedef struct {
    uint8_t  length;
    uint8_t  payload[UBRIDGE_MAX_PAYLOAD];
    uint8_t  crc;
    uint8_t  valid;   /* 1 if CRC and ETX check passed */
} UBRIDGE_Frame;

/* ────────────────────────────────────────────────────────────────────────────
 * UART Bridge handle
 * ──────────────────────────────────────────────────────────────────────────── */

typedef struct {
    int         uart_num;        /* ESP-IDF UART port number */
    uint32_t    baud;            /* Baud rate */
    int         tx_pin;          /* TX GPIO */
    int         rx_pin;          /* RX GPIO */

    /* Internal state */
    UBRIDGE_State  rx_state;
    UBRIDGE_Frame  rx_frame;
    uint8_t        rx_data[UBRIDGE_MAX_PAYLOAD];
    uint16_t       rx_index;

    /* Counters */
    uint32_t       frames_sent;
    uint32_t       frames_received;
    uint32_t       frames_crc_errors;
} UARTBridge;

/* ────────────────────────────────────────────────────────────────────────────
 * Public API
 * ──────────────────────────────────────────────────────────────────────────── */

/**
 * @brief  Initialize the UART bridge.
 * @param  bridge   Pointer to UARTBridge handle
 * @param  uart_num ESP-IDF UART port (UART_NUM_1, UART_NUM_2)
 * @param  baud     Baud rate (must match STM32)
 * @param  tx_pin   TX GPIO number
 * @param  rx_pin   RX GPIO number
 * @return 0 on success, -1 on error
 */
int uart_bridge_init(UARTBridge *bridge, int uart_num, uint32_t baud,
                     int tx_pin, int rx_pin);

/**
 * @brief  Poll the bridge — read and parse incoming frames.
 *         Call in the main loop (non-blocking).
 * @param  bridge  Initialized handle
 * @return Number of complete frames received, 0 if none
 */
int uart_bridge_poll(UARTBridge *bridge);

/**
 * @brief  Send a frame to the STM32.
 * @param  bridge  Initialized handle
 * @param  payload Data to send
 * @param  len     Payload length (≤ UBRIDGE_MAX_PAYLOAD)
 * @return 0 on success, -1 on error
 */
int uart_bridge_send(UARTBridge *bridge, const uint8_t *payload, size_t len);

/**
 * @brief  Get the last parsed frame (valid=1) and mark it consumed.
 * @param  bridge  Initialized handle
 * @param  frame   Output pointer for the frame
 * @return 1 if a new frame was available, 0 otherwise
 */
int uart_bridge_read_frame(UARTBridge *bridge, UBRIDGE_Frame *frame);

/**
 * @brief  Publish a frame payload to MQTT (requires MQTT client).
 * @param  bridge  Initialized handle
 * @param  topic   MQTT topic string
 * @param  frame   Frame to publish
 */
void uart_bridge_mqtt_publish(UARTBridge *bridge, const char *topic,
                              const UBRIDGE_Frame *frame);

/**
 * @brief  Get bridge statistics.
 */
void uart_bridge_stats(UARTBridge *bridge, uint32_t *sent,
                       uint32_t *received, uint32_t *crc_errs);

/* ────────────────────────────────────────────────────────────────────────────
 * Platform Abstractions (must be provided by the demo platform layer)
 *
 * These are called by the bridge but implemented in platform.c
 * ──────────────────────────────────────────────────────────────────────────── */

/**
 * @brief  Write bytes to the UART (blocking).
 */
int platform_uart_write(int uart_num, const uint8_t *data, size_t len);

/**
 * @brief  Read bytes from the UART (non-blocking).
 * @return Number of bytes read
 */
int platform_uart_read(int uart_num, uint8_t *buffer, size_t max_len);

/**
 * @brief  Compute CRC-8 (Dallas/Maxim 1-Wire) over buffer.
 */
uint8_t platform_crc8(const uint8_t *data, size_t len);

/**
 * @brief  Log a message (USB-CDC or RTT).
 */
void platform_log(const char *msg);

/**
 * @brief  Millisecond tick for timeouts.
 */
uint32_t platform_millis(void);

#ifdef __cplusplus
}
#endif

#endif /* YULEOSH_UART_BRIDGE_H */
