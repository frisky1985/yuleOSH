/**
 * hello.c — Minimal ARM bare-metal firmware for yuleOSH SIL testing.
 *
 * Outputs status messages over the QEMU emulated UART at 0x40001000
 * (matching the lm3s6965evb / stm32vldiscovery UART peripheral),
 * then enters an infinite loop.
 *
 * Expected serial output:
 *   Hello from yuleOSH cross-compilation test!
 *   Architecture: ARM
 *   Test Complete
 */

/* UART data register for lm3s6965evb / stm32vldiscovery */
#define UART_DR  ((volatile unsigned int *)0x40001000)

/**
 * Send a null-terminated string over the emulated UART.
 */
void uart_send(const char *s) {
    while (*s) {
        *UART_DR = (unsigned int)(*s);
        ++s;
    }
}

/**
 * Entry point (called from startup.c Reset_Handler).
 *
 * Initialises the UART and prints diagnostic messages, then halts.
 * _start MUST NOT return — the startup code spins if it does.
 */
void _start(void) {
    /* UART initialisation — on lm3s6965evb the UART is pre-configured
     * by QEMU's -semihosting and -serial setup.  No explicit init needed. */

    uart_send("Hello from yuleOSH cross-compilation test!\n");
    uart_send("Architecture: ARM\n");
    uart_send("Test Complete\n");

    /* Halt — QEMU will either exit via semihosting or be terminated */
    while (1) {
        __asm__ volatile("wfi");  /* Wait For Interrupt — reduces power */
    }
}
