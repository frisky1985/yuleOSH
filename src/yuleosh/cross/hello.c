/**
 * yuleOSH — Cross-compilation test program
 *
 * A minimal C program used to verify cross-compilation toolchains
 * (ARM, RISC-V) in CI.  Prints a greeting and returns 0 on success.
 *
 * Note:
 * - stdio.h and stdlib.h are used intentionally for CI diagnostics.
 * - In production code, use MISRA-compliant alternatives.
 */

#include <stdio.h>   /* MISRA 21.6: stdio.h used for CI test output only */
#include <stdlib.h>  /* MISRA 21.6: EXIT_SUCCESS used for CI exit code */

int main(void)
{
    (void)printf("Hello from yuleOSH cross-compilation test!\n");
    (void)printf("Architecture: ");
#ifdef __arm__
    (void)printf("ARM\n");
#elif defined(__riscv)
    (void)printf("RISC-V\n");
#elif defined(__x86_64__) || defined(__i386__)
    (void)printf("x86\n");
#else
    (void)printf("unknown\n");
#endif
    return EXIT_SUCCESS;
}
