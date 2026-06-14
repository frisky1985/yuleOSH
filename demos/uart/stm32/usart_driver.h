/**
 * @file    usart_driver.h
 * @brief   STM32F4 USART Driver — yuleOSH UART Demo
 * @author  yuleOSH Demo Team
 *
 * Target:  STM32F4xx (Cortex-M4)
 * Clock:   168 MHz (SYSCLK), 84 MHz (APB1), 42 MHz (APB2 USART1)
 *
 * Pinout:
 *   USART1: TX=PA9, RX=PA10  (APB2, 42 MHz)
 *   USART2: TX=PA2, RX=PA3   (APB1, 84 MHz)
 *   USART3: TX=PB10, RX=PB11 (APB1, 84 MHz)
 *
 * Usage:
 *   #include "usart_driver.h"
 *   USART_Handle huart;
 *   usart_init(&huart, USART1, 115200);
 *   usart_send(&huart, (uint8_t*)"Hello\r\n", 7);
 */

#ifndef YULEOSH_USART_DRIVER_H
#define YULEOSH_USART_DRIVER_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------------------
 * USART peripheral base addresses (STM32F4 memory map)
 * --------------------------------------------------------------------------- */
#define USART1_BASE     0x40011000UL
#define USART2_BASE     0x40004400UL
#define USART3_BASE     0x40004800UL
#define UART4_BASE      0x40004C00UL
#define UART5_BASE      0x40005000UL
#define USART6_BASE     0x40011400UL

/* USART register map (offset from base address) */
typedef volatile struct {
    uint32_t SR;        /* 0x00: Status register */
    uint32_t DR;        /* 0x04: Data register */
    uint32_t BRR;       /* 0x08: Baud rate register */
    uint32_t CR1;       /* 0x0C: Control register 1 */
    uint32_t CR2;       /* 0x10: Control register 2 */
    uint32_t CR3;       /* 0x14: Control register 3 */
    uint32_t GTPR;      /* 0x18: Guard time and prescaler */
} USART_Regs;

/* CR1 bit definitions */
#define USART_CR1_UE    (1U << 13)  /* USART enable */
#define USART_CR1_TE    (1U << 3)   /* Transmitter enable */
#define USART_CR1_RE    (1U << 2)   /* Receiver enable */
#define USART_CR1_RXNEIE (1U << 5)  /* RX not empty interrupt enable */
#define USART_CR1_TXEIE (1U << 7)   /* TX empty interrupt enable */

/* SR bit definitions */
#define USART_SR_TXE    (1U << 7)   /* Transmit data register empty */
#define USART_SR_TC     (1U << 6)   /* Transmission complete */
#define USART_SR_RXNE   (1U << 5)   /* Read data register not empty */
#define USART_SR_ORE    (1U << 3)   /* Overrun error */
#define USART_SR_FE     (1U << 1)   /* Framing error */
#define USART_SR_PE     (1U << 0)   /* Parity error */

/* USART selection constants */
typedef enum {
    USART_ID_1 = 1,
    USART_ID_2 = 2,
    USART_ID_3 = 3,
    USART_ID_6 = 6,
} USART_Id;

/* USART handle — the user-facing object */
typedef struct {
    USART_Regs *regs;       /* Pointer to USART register block */
    USART_Id    id;         /* Peripheral identifier */
    uint32_t    baud;       /* Configured baud rate */
    uint8_t     data_bits;  /* 8 or 9 */
    uint8_t     stop_bits;  /* 1 or 2 */
    uint8_t     parity;     /* 0=none, 1=even, 2=odd */
} USART_Handle;

/* Return codes */
#define USART_OK        (0)
#define USART_ERR_BUSY  (-1)
#define USART_ERR_PARAM (-2)
#define USART_ERR_OVERFLOW (-3)
#define USART_ERR_FRAME (-4)

/* ---------------------------------------------------------------------------
 * Public API
 * --------------------------------------------------------------------------- */

/**
 * @brief  Initialize the USART peripheral.
 * @param  huart  Pointer to USART_Handle to populate
 * @param  id     USART peripheral identifier (USART_ID_1 .. USART_ID_6)
 * @param  baud   Desired baud rate (e.g. 115200, 921600)
 * @return USART_OK on success, negative error code on failure
 *
 * Configures GPIO alternate function, resets and enables USART clock,
 * sets baud rate, enables TX/RX, and enables the USART.
 */
int usart_init(USART_Handle *huart, USART_Id id, uint32_t baud);

/**
 * @brief  Send a block of data (blocking, polled mode).
 * @param  huart  Initialized USART handle
 * @param  data   Pointer to data buffer
 * @param  len    Number of bytes to send
 * @return Number of bytes sent, or negative on error
 */
int usart_send(USART_Handle *huart, const uint8_t *data, size_t len);

/**
 * @brief  Send a single byte (blocking).
 * @param  huart  Initialized USART handle
 * @param  byte   Byte to transmit
 * @return USART_OK on success, or negative on error
 */
int usart_send_byte(USART_Handle *huart, uint8_t byte);

/**
 * @brief  Receive a block of data (blocking, polled with timeout).
 * @param  huart    Initialized USART handle
 * @param  buffer   Destination buffer
 * @param  max_len  Maximum bytes to receive
 * @param  timeout_ms  Timeout in milliseconds (0 = no wait)
 * @return Number of bytes received, or negative on error
 */
int usart_receive(USART_Handle *huart, uint8_t *buffer,
                  size_t max_len, uint32_t timeout_ms);

/**
 * @brief  Check if data is available to read.
 * @param  huart  Initialized USART handle
 * @return 1 if RXNE set, 0 otherwise
 */
int usart_available(USART_Handle *huart);

/**
 * @brief  Read a single byte (non-blocking).
 * @param  huart  Initialized USART handle
 * @param  byte   Output pointer for received byte
 * @return USART_OK if byte read, USART_ERR_BUSY if no data available
 */
int usart_read_byte(USART_Handle *huart, uint8_t *byte);

/**
 * @brief  De-initialize the USART peripheral (disable, reset).
 * @param  huart  Handle to tear down
 */
void usart_deinit(USART_Handle *huart);

/**
 * @brief  Format and print a string (printf-like).
 * @param  huart  Initialized USART handle
 * @param  fmt    Format string
 * @param  ...    Format arguments
 * @return Number of characters printed
 */
int usart_printf(USART_Handle *huart, const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* YULEOSH_USART_DRIVER_H */
