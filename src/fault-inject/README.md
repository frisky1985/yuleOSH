# A66-T Fault Injection Framework

**yuleOSH formal module — ASPICE SWE.5 / ASIL-B (supporting)**

## Overview

The fault-inject module provides two complementary fault injection layers for
the A66-T SBM MCU (Z20K148M, ARM Cortex-M4F):

| Layer | Name | Mechanism | Effect | Reset Required |
|-------|------|-----------|--------|:--------------:|
| **Layer 1** | System-Level CPU Exception Injection | Real null-pointer deref, division by zero, undefined instruction, etc. | Triggers HardFault / BusFault / UsageFault / MemManage | **Yes** |
| **Layer 2** | Per-Task Simulated Fault Injection | FreeRTOS Task Notifications | Simulates error conditions (NULL handle, timeout, queue full) | **No** |

## Directory Structure

```
src/fault-inject/
├── CMakeLists.txt               # Build integration
├── README.md                    # This file
├── doc.go                       # Go-style module documentation (ASPICE annotations)
├── inc/
│   ├── FaultInject.h            # Layer 1 public API
│   ├── FaultInject_Cfg.h        # Layer 1 compile-time configuration
│   ├── TaskFaultInject.h        # Layer 2 public API
│   └── TaskFaultInject_Cfg.h    # Layer 2 compile-time configuration
├── src/
│   ├── FaultInject.c            # Layer 1 implementation
│   └── TaskFaultInject.c        # Layer 2 implementation
└── test/
    └── FaultInject_Test.c       # Self-test suite
```

## Build Integration

### As a CMake subdirectory

```cmake
add_subdirectory(path/to/fault-inject)
target_link_libraries(your_target PRIVATE fault-inject)
```

### For test/debug builds (with injection enabled)

```cmake
set(FAULT_INJECT_TESTS ON CACHE BOOL "Enable fault injection")
add_subdirectory(path/to/fault-inject)
target_link_libraries(your_test_target PRIVATE fault-inject-test)
```

### Standalone test build

```bash
mkdir build && cd build
cmake .. -DFAULT_INJECT_TESTS=ON -DFAULT_INJECT_BUILD_TEST=ON
cmake --build .
ctest  # runs self-test
```

## Configuration

### Layer 1: `FaultInject_Cfg.h`

| Macro | STD_ON | Description |
|-------|--------|-------------|
| `A66T_FAULT_INJECTION_TEST_ENABLE` | OFF (default) | Master switch — **must be OFF in production** |
| `A66T_FAULT_INJECT_NULL_POINTER` | ON | TC-01: Null pointer deref |
| `A66T_FAULT_INJECT_INVALID_FUNC` | ON | TC-02: Invalid function call |
| `A66T_FAULT_INJECT_DIV_BY_ZERO` | ON | TC-03: Division by zero |
| `A66T_FAULT_INJECT_UNALIGNED` | ON | TC-04: Unaligned access |
| `A66T_FAULT_INJECT_STACK_OVERFLOW` | ON | TC-05: Stack overflow |
| `A66T_FAULT_INJECT_MPU_VIOLATION` | OFF | TC-06: MPU violation |
| `A66T_FAULT_INJECT_UNDEF_INSTR` | ON | TC-07: Undefined instruction |
| `A66T_FAULT_INJECT_DIRECT_SCB` | ON | TC-08: Direct SCB injection |
| `A66T_FAULT_INJECT_BUS_ACCESS` | ON | TC-09: Bus fault access |

### Layer 2: `TaskFaultInject_Cfg.h`

| Macro | STD_ON | Description |
|-------|--------|-------------|
| `A66T_TASK_FAULT_INJECT_ENABLE` | OFF (default) | Master switch — **must be OFF in production** |
| `A66T_TASK_FAULT_SIM_NULL_HANDLE` | ON | Simulate critical handle NULL |
| `A66T_TASK_FAULT_SIM_INVALID_PARAM` | ON | Simulate invalid parameter |
| `A66T_TASK_FAULT_SIM_TIMEOUT` | ON | Simulate timeout / deadline miss |
| `A66T_TASK_FAULT_SIM_QUEUE_FULL` | ON | Simulate message queue full |
| `A66T_TASK_FAULT_SIM_BUFFER_OVF` | ON | Simulate buffer overrun condition |
| `A66T_TASK_FAULT_SIM_RESOURCE_LOST` | ON | Simulate peripheral resource lost |
| `A66T_TASK_FAULT_SIM_STATE_CORRUPT` | ON | Simulate state machine corruption |
| `A66T_TASK_FAULT_REAL_STACK_DEPLETE` | OFF | Real stack consumption (risky) |

## API Quick Reference

### Layer 1 (System-Level)

```c
// Initialization — call once after NoInit_Init()
FaultInject_Init();

// Inject a specific fault (triggers CPU exception + system reset)
FaultInject_Run(FAULT_INJECT_NULL_POINTER);

// After reset: check if a test result is available
if (FaultInject_CheckResult()) {
    const A66T_FaultInject_TestResult_St *r = FaultInject_GetResult();
    // r->status == FAULT_INJECT_STATUS_PASSED or FAILED or ERROR
}
```

### Layer 2 (Per-Task)

```c
// System init (after scheduler starts)
TaskFault_Init();

// Each task registers itself
TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "MyTask");

// At top of each task loop iteration
TASK_FAULT_CHECK();

// Inside error paths, check for injected fault
if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE)) {
    handle = NULL;  // Force fault condition
}
if (handle == NULL) {
    TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
    return;
}

// At end of each task loop iteration
TASK_FAULT_END_CHECK();

// From injector task or UDS handler
TaskFault_Inject(targetTask, TASK_FAULT_SIM_TIMEOUT);
```

## UDS Integration

| DID | Function | Security Level |
|:---:|----------|:--------------:|
| 0xF190 | System-level fault injection trigger | 0x01 |
| 0xF193 | Per-task fault injection trigger | 0x01 |

## Safety Notes

- **NEVER** compile `fault-inject` into production firmware.
- Both modules use dual compile-time guards: a master switch + individual
  method enables. All default to `STD_OFF` in shipped headers.
- When `STD_OFF`, all API calls compile to static inline no-ops or empty
  macros, ensuring zero code size impact.
- Safety builds should explicitly `#undef` or override at the build system
  level to prevent accidental enablement.

## Migration from ref/

This module is the formal yuleOSH replacement for the reference implementations:

- `ref/fault-inject/FaultInject/` → **`src/fault-inject/`** (Layer 1)
- `ref/fault-inject/v2/` → **`src/fault-inject/`** (Layers 1 + 2)

The reference implementations are retained for traceability but should not be
used for new development. All new integration should use `src/fault-inject/`.

## See Also

- `INTEGRATION_GUIDE.md` — Full integration walkthrough
- `doc.go` — Module documentation with ASPICE annotations
- `test/FaultInject_Test.c` — Self-test suite
- `../yuleosh/pipeline/step_handlers/fault_inject.py` — yuleOSH pipeline integration
