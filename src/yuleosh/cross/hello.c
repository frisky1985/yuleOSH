/**
 * yuleOSH — Cross-compilation test program
 *
 * A minimal C program used to verify cross-compilation toolchains
 * (ARM, RISC-V) in CI.  Prints a greeting and returns 0 on success.
 */

#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    printf("Hello from yuleOSH cross-compilation test!\n");
    printf("Architecture: ");
#ifdef __arm__
    printf("ARM\n");
#elif defined(__riscv)
    printf("RISC-V\n");
#elif defined(__x86_64__) || defined(__i386__)
    printf("x86\n");
#else
    printf("unknown\n");
#endif
    return EXIT_SUCCESS;
}
