/**
 * @file    usart_driver.c
 * @brief   STM32F4 USART Driver Implementation — yuleOSH UART Demo
 *
 * Implements register-level USART communication for STM32F4.
 * No HAL, no CubeMX — pure CMSIS-style register access.
 *
 * On host builds (TARGET_HOST defined), hardware register access is simulated
 * so the demo can run on any machine with a C compiler.
 */

#include "usart_driver.h"
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#if defined(TARGET_HOST)
/* ── Host simulation: static buffers instead of real HW registers ── */
static USART_Regs host_regs_storage;
static int         host_initialized = 0;

static void host_regs_init(USART_Regs *r) {
    r->SR  = USART_SR_TXE | USART_SR_TC;  /* TX ready, TX complete */
    r->DR  = 0;
    r->BRR = 0;
    r->CR1 = 0;
    r->CR2 = 0;
    r->CR3 = 0;
}
#endif

/* ---------------------------------------------------------------------------
 * Internal helpers
 * --------------------------------------------------------------------------- */

/* Very crude busy-wait µs delay (168 MHz ≈ 168 cycles/µs) */
static void delay_us(uint32_t us) {
    for (uint32_t i = 0; i < us * 168; i++) {
        __asm__ volatile("nop");
    }
}

/* Map USART_Id to register block pointer
 * On real STM32: returns the actual peripheral base address
 * On host:      returns a static simulated register block
 */
static USART_Regs *usart_regs(USART_Id id) {
#if defined(TARGET_HOST)
    (void)id;
    if (!host_initialized) {
        host_regs_init(&host_regs_storage);
        host_initialized = 1;
    }
    return &host_regs_storage;
#else
    switch (id) {
        case USART_ID_1: return (USART_Regs *)USART1_BASE;
        case USART_ID_2: return (USART_Regs *)USART2_BASE;
        case USART_ID_3: return (USART_Regs *)USART3_BASE;
        case USART_ID_6: return (USART_Regs *)USART6_BASE;
        default:         return NULL;
    }
#endif
}

/* Dummy clock/RCC setup */
static void rcc_enable_usart_clock(USART_Id id) {
    (void)id;
}

static void rcc_disable_usart_clock(USART_Id id) {
    (void)id;
}

/* Dummy GPIO config */
static void gpio_config_usart(USART_Id id) {
    (void)id;
}

/* Compute BRR value for given baud rate */
static uint16_t compute_brr(USART_Id id, uint32_t baud) {
    uint32_t fck;
    switch (id) {
        case USART_ID_1:
        case USART_ID_6:
            fck = 42000000U;
            break;
        default:
            fck = 84000000U;
            break;
    }
    uint32_t brr = (fck + (baud / 2)) / baud;
    return (uint16_t)(brr & 0xFFFFU);
}

/* ── Host-mode TX/RX callbacks (defined in demo_host.c) ── */
#if defined(TARGET_HOST)
extern int host_uart_tx_byte(uint8_t byte);
extern int host_uart_rx_byte(uint8_t *byte);
#endif

/* ---------------------------------------------------------------------------
 * Public API implementation
 * --------------------------------------------------------------------------- */

int usart_init(USART_Handle *huart, USART_Id id, uint32_t baud) {
    if (!huart) return USART_ERR_PARAM;

    huart->regs      = usart_regs(id);
    if (!huart->regs) return USART_ERR_PARAM;

    huart->id        = id;
    huart->baud      = baud;
    huart->data_bits = 8;
    huart->stop_bits = 1;
    huart->parity    = 0;

    rcc_enable_usart_clock(id);
    gpio_config_usart(id);

    /* Reset USART registers */
    huart->regs->CR1 = 0;
    huart->regs->CR2 = 0;
    huart->regs->CR3 = 0;

    huart->regs->BRR = compute_brr(id, baud);

    /* Enable TX, RX */
    huart->regs->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
#if defined(TARGET_HOST)
    huart->regs->SR  = USART_SR_TXE | USART_SR_TC;
#endif

    delay_us(10);

    return USART_OK;
}

int usart_send(USART_Handle *huart, const uint8_t *data, size_t len) {
    if (!huart || !data) return USART_ERR_PARAM;

    for (size_t i = 0; i < len; i++) {
        int ret = usart_send_byte(huart, data[i]);
        if (ret < 0) return (int)i;
    }
    return (int)len;
}

int usart_send_byte(USART_Handle *huart, uint8_t byte) {
    if (!huart || !huart->regs) return USART_ERR_PARAM;

#if defined(TARGET_HOST)
    /* Host mode: redirect to host callback */
    return host_uart_tx_byte(byte);
#else
    /* Wait until TX data register is empty */
    while (!(huart->regs->SR & USART_SR_TXE)) {
        /* spin */
    }
    huart->regs->DR = byte;
    return USART_OK;
#endif
}

int usart_receive(USART_Handle *huart, uint8_t *buffer,
                  size_t max_len, uint32_t timeout_ms) {
    if (!huart || !buffer) return USART_ERR_PARAM;

#if defined(TARGET_HOST)
    (void)timeout_ms;
    size_t count = 0;
    while (count < max_len) {
        uint8_t byte;
        if (host_uart_rx_byte(&byte) != USART_OK) break;
        buffer[count++] = byte;
    }
    return (int)count;
#else
    size_t count = 0;
    uint32_t timeout_loops = timeout_ms * 1000 * 168;

    while (count < max_len) {
        uint32_t waited = 0;
        while (!(huart->regs->SR & USART_SR_RXNE)) {
            if (timeout_ms > 0 && waited++ > timeout_loops)
                return (int)count;
        }
        uint32_t sr = huart->regs->SR;
        if (sr & USART_SR_ORE) {
            (void)huart->regs->DR;
            return USART_ERR_OVERFLOW;
        }
        if (sr & USART_SR_FE) {
            (void)huart->regs->DR;
            return USART_ERR_FRAME;
        }
        buffer[count++] = (uint8_t)(huart->regs->DR & 0xFFU);
    }
    return (int)count;
#endif
}

int usart_available(USART_Handle *huart) {
    if (!huart || !huart->regs) return 0;

#if defined(TARGET_HOST)
    uint8_t dummy;
    return (host_uart_rx_byte(&dummy) == USART_OK) ? 1 : 0;
#else
    return (huart->regs->SR & USART_SR_RXNE) ? 1 : 0;
#endif
}

int usart_read_byte(USART_Handle *huart, uint8_t *byte) {
    if (!huart || !byte || !huart->regs) return USART_ERR_PARAM;

#if defined(TARGET_HOST)
    return host_uart_rx_byte(byte);
#else
    if (!(huart->regs->SR & USART_SR_RXNE)) return USART_ERR_BUSY;
    *byte = (uint8_t)(huart->regs->DR & 0xFFU);
    return USART_OK;
#endif
}

void usart_deinit(USART_Handle *huart) {
    if (!huart || !huart->regs) return;
    huart->regs->CR1 = 0;
    rcc_disable_usart_clock(huart->id);
    huart->regs = NULL;
}

int usart_printf(USART_Handle *huart, const char *fmt, ...) {
    if (!huart || !fmt) return 0;

    char buf[256];
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    if (n > 0) {
        size_t len = (size_t)(n < (int)sizeof(buf) ? n : sizeof(buf) - 1);
        usart_send(huart, (const uint8_t *)buf, len);
    }
    return n;
}
