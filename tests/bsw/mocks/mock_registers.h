/**
 * @file mock_registers.h
 * @brief Mock register access for BSW module host-side testing.
 *
 * Provides MockRegisters_Read32/Write32 to intercept REG_READ32/REG_WRITE32
 * macro calls, enabling verification of register-level operations without
 * real hardware.
 *
 * License: Elastic License 2.0
 */

#ifndef MOCK_REGISTERS_H
#define MOCK_REGISTERS_H

#include <stdint.h>
#include <stdbool.h>

#define MOCK_REG_MAX 64

typedef struct {
    uint32_t address;
    uint32_t value;
    bool     written;
} MockRegEntry;

typedef struct {
    MockRegEntry entries[MOCK_REG_MAX];
    uint32_t     read_count;
    uint32_t     write_count;
    uint32_t     last_read_addr;
    uint32_t     last_write_addr;
    uint32_t     last_write_value;
} MockRegistersState;

extern MockRegistersState g_mock_regs;

void MockRegisters_Init(void);
void MockRegisters_Reset(void);
void MockRegisters_SetReadValue(uint32_t address, uint32_t value);
uint32_t MockRegisters_Read32(uint32_t address);
void MockRegisters_Write32(uint32_t address, uint32_t value);
uint32_t MockRegisters_GetWriteCount(void);
uint32_t MockRegisters_GetReadCount(void);
uint32_t MockRegisters_GetLastWriteValue(void);
bool MockRegisters_WasWritten(uint32_t address);
uint32_t MockRegisters_GetWrittenValue(uint32_t address);

#define REG_READ32(addr)  MockRegisters_Read32(addr)
#define REG_WRITE32(addr, val) MockRegisters_Write32((addr), (val))

#endif /* MOCK_REGISTERS_H */
