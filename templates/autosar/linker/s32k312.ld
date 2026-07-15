/*
 * Linker script for NXP S32K312 (Arm Cortex-M7)
 *
 * Memory map:
 *   Flash:  0x00400000 - 0x007FFFFF  (512 KB)  Program Flash
 *           0x10000000 - 0x1003FFFF  (256 KB)  Data Flash
 *   SRAM:   0x1FFF8000 - 0x20007FFF  (64 KB)   SRAM_L
 *           0x20008000 - 0x20017FFF  (64 KB)   SRAM_U
 */

MEMORY
{
    PFLASH (rx)  : ORIGIN = 0x00400000, LENGTH = 512K
    DFLASH (rw)  : ORIGIN = 0x10000000, LENGTH = 256K
    SRAM_L (rwx) : ORIGIN = 0x1FFF8000, LENGTH = 64K
    SRAM_U (rwx) : ORIGIN = 0x20008000, LENGTH = 64K
}

SECTIONS
{
    /* Program code in program flash */
    .text :
    {
        . = ALIGN(4);
        KEEP(*(.isr_vector))
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
        _etext = .;
    } > PFLASH

    /* Initialized data — copy from flash to SRAM_U at startup */
    .data : AT (ADDR(.text) + SIZEOF(.text))
    {
        . = ALIGN(4);
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > SRAM_U

    /* BSS — zero-initialized */
    .bss :
    {
        . = ALIGN(4);
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > SRAM_U

    /* Stack and heap */
    .heap (NOLOAD) :
    {
        . = ALIGN(8);
        _heap_start = .;
        . += 0x1000;
        _heap_end = .;
    } > SRAM_L

    .stack (NOLOAD) :
    {
        . = ALIGN(8);
        _stack_end = .;
        . += 0x2000;
        . = ALIGN(8);
        _stack_start = .;
    } > SRAM_L

    /* Data flash for EEPROM emulation (Fee) */
    .dflash (NOLOAD) :
    {
        *(.dflash*)
    } > DFLASH

    /* Discard unwind tables (not needed in embedded) */
    /DISCARD/ :
    {
        *(.ARM.exidx*)
        *(.ARM.attributes*)
        *(.comment*)
    }
}
