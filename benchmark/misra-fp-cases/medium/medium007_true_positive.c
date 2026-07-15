/*
 * MISRA Benchmark — Medium 007: True Positive
 * Rule: MISRA C:2023 Rule 21.5 — The standard header file <signal.h> shall not be used
 * Rules: 21.5, 21.6
 *
 * Signal handler registration in embedded systems is dangerous and MISRA-prohibited.
 *
 * Expected: Two violations (signal() and raise() usage)
 */
#include <signal.h>
#include <stdint.h>

static volatile uint32_t flag = 0;

static void handler(int sig) {
    (void)sig;
    flag = 1;
}

void configure_signal(void) {
    signal(SIGINT, handler);  /* MISRA 21.5: signal.h shall not be used */
    raise(SIGUSR1);           /* MISRA 21.6: raise() prohibited */
}
