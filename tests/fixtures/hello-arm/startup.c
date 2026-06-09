/**
 * startup.c — Minimal ARM vector table and reset handler.
 *
 * Provides the vector table for Cortex-M3 QEMU targets (lm3s6965evb)
 * and a Reset_Handler that delegates to _start() in hello.c.
 */

extern void _start(void);

/* ------------------------------------------------------------------ */
/*  Default weak exception handlers                                    */
/* ------------------------------------------------------------------ */

__attribute__((interrupt)) void Default_Handler(void) {
    while (1) {}
}

void NMI_Handler(void)          __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)          __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)      __attribute__((weak, alias("Default_Handler")));

/* ------------------------------------------------------------------ */
/*  Vector table                                                       */
/* ------------------------------------------------------------------ */

__attribute__((section(".vectors")))
void (* const vector_table[16])(void) = {
    (void (*)(void))0x20001000,  /* Stack pointer */
    _start,                      /* Reset handler — delegates to hello.c */
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,                 /* Reserved */
    SVC_Handler,
    DebugMon_Handler,
    0,
    PendSV_Handler,
    SysTick_Handler,
};
