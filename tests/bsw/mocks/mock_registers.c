/**
 * @file mock_registers.c
 * @brief Mock register access implementation.
 *
 * License: Elastic License 2.0
 */

#include "mock_registers.h"
#include <string.h>

MockRegistersState g_mock_regs;

void MockRegisters_Init(void) {
    MockRegisters_Reset();
}

void MockRegisters_Reset(void) {
    memset(&g_mock_regs, 0, sizeof(g_mock_regs));
}

void MockRegisters_SetReadValue(uint32_t address, uint32_t value) {
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (g_mock_regs.entries[i].address == address && g_mock_regs.entries[i].written) {
            g_mock_regs.entries[i].value = value;
            return;
        }
    }
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (!g_mock_regs.entries[i].written) {
            g_mock_regs.entries[i].address = address;
            g_mock_regs.entries[i].value = value;
            g_mock_regs.entries[i].written = false;
            return;
        }
    }
}

uint32_t MockRegisters_Read32(uint32_t address) {
    g_mock_regs.read_count++;
    g_mock_regs.last_read_addr = address;
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (g_mock_regs.entries[i].address == address && g_mock_regs.entries[i].written) {
            return g_mock_regs.entries[i].value;
        }
    }
    return 0xFFFFFFFFU;
}

void MockRegisters_Write32(uint32_t address, uint32_t value) {
    g_mock_regs.write_count++;
    g_mock_regs.last_write_addr = address;
    g_mock_regs.last_write_value = value;
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (g_mock_regs.entries[i].address == address) {
            g_mock_regs.entries[i].value = value;
            g_mock_regs.entries[i].written = true;
            return;
        }
    }
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (!g_mock_regs.entries[i].written) {
            g_mock_regs.entries[i].address = address;
            g_mock_regs.entries[i].value = value;
            g_mock_regs.entries[i].written = true;
            return;
        }
    }
}

uint32_t MockRegisters_GetWriteCount(void) {
    return g_mock_regs.write_count;
}

uint32_t MockRegisters_GetReadCount(void) {
    return g_mock_regs.read_count;
}

uint32_t MockRegisters_GetLastWriteValue(void) {
    return g_mock_regs.last_write_value;
}

bool MockRegisters_WasWritten(uint32_t address) {
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (g_mock_regs.entries[i].address == address && g_mock_regs.entries[i].written) {
            return true;
        }
    }
    return false;
}

uint32_t MockRegisters_GetWrittenValue(uint32_t address) {
    for (uint32_t i = 0; i < MOCK_REG_MAX; i++) {
        if (g_mock_regs.entries[i].address == address && g_mock_regs.entries[i].written) {
            return g_mock_regs.entries[i].value;
        }
    }
    return 0xFFFFFFFFU;
}
