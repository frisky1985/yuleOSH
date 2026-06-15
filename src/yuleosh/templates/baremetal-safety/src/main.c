/*
 * Safety-Critical Bare Metal Application (ASIL-B)
 */

#include <stdint.h>

static uint32_t cpu_register_test(void)
{
    uint32_t test = 0xA5A5A5A5;
    uint32_t read;
    __asm__ volatile ("mov %0, %2\n\tmov %1, %0" : "=r" (read), "=r" (read) : "r" (test));
    return (read == test) ? 0U : 1U;
}

int main(void)
{
    if (cpu_register_test() != 0U) {
        while (1) {} /* Enter safe state */
    }
    while (1) {
        /* Main safety loop */
    }
    return 0;
}
