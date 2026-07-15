// Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
// SPDX-License-Identifier: LicenseRef-Ingeek-Proprietary
//
// Package fault-inject — A66-T HardFault & Per-Task Fault Injection Framework
//
// ASPICE Classification: SWE.5 (Integration Test)
// Safety Integrity: ASIL-B (supporting verification)
//
//
// ==== Module Architecture ====
//
// ┌─────────────────────────────────────────────────────────────────────┐
// │                    fault-inject                                     │
// │  Formal yuleOSH C module for software-implemented fault injection   │
// ├─────────────────────────────────────────────────────────────────────┤
// │  Layer 1: System-Level CPU Exception Injection                     │
// │    API: FaultInject.h / FaultInject.c                              │
// │    Desc: Injects real ARM Cortex-M4F exceptions (HardFault,        │
// │          BusFault, UsageFault, MemManage) via null-pointer deref,  │
// │          undefined instructions, stack overflow, etc.              │
// │    Target: A66-T SBM (Z20K148M, ARM Cortex-M4F)                   │
// │    Safety: NEVER enable in production builds                       │
// │    Config: FaultInject_Cfg.h                                       │
// │                                                                     │
// │  Layer 2: Per-Task Simulated Fault Injection                       │
// │    API: TaskFaultInject.h / TaskFaultInject.c                      │
// │    Desc: Injects simulated fault conditions into FreeRTOS tasks    │
// │          via Task Notifications. Does NOT trigger CPU exceptions.  │
// │    Target: A66-T SBM + FreeRTOS                                    │
// │    Safety: Safe for debug/test builds, compiled out in production  │
// │    Config: TaskFaultInject_Cfg.h                                   │
// │                                                                     │
// │  Layer 3: UDS Remote Trigger                                       │
// │    DID 0xF190 — System-level fault injection via UDS $2E           │
// │    DID 0xF193 — Per-task fault injection via UDS $2E               │
// └─────────────────────────────────────────────────────────────────────┘
//
//
// ==== ASPICE Traceability ====
//
// SWE.5 (Integration Testing):
//   - Fault injection verifies that exception handlers (Exception.c) save
//     context correctly to NoInit RAM across all 9 CPU fault types
//   - Per-task injection verifies each RTOS task's error-handling paths
//     (null handles, timeouts, queue-full, buffer-overflow, etc.)
//
// SWE.6 (Qualification Testing):
//   - Post-reset result verification proves the fault-handling chain
//     (handler → save → reset → report) is functionally complete
//
// ASIL-B Safety Requirements:
//   - A66T_FAULT_INJECTION_TEST_ENABLE=STD_OFF: all injection code is
//     compiled out (static inline stubs)
//   - Dual compile-time guards (master + individual) prevent accidental
//     enablement in safety builds
//   - Build system integration (CMake) enforces separate test/lib targets
//     so production never links injection code
//
//
// ==== File Inventory ====
//
//  inc/FaultInject.h             — Public API (Layer 1)
//  inc/FaultInject_Cfg.h         — Compile-time configuration
//  inc/TaskFaultInject.h         — Public API (Layer 2)
//  inc/TaskFaultInject_Cfg.h     — Compile-time configuration
//  src/FaultInject.c             — Implementation (Layer 1)
//  src/TaskFaultInject.c         — Implementation (Layer 2)
//  test/FaultInject_Test.c       — Self-test suite
//  CMakeLists.txt                — Build integration
//  README.md                     — Module documentation
//  doc.go                        — This file (Go-style module doc)
//  ../../ref/fault-inject/       — Original reference implementations
//  INTEGRATION_GUIDE.md          — Integration guide (module-level)
package faultinject
