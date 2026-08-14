# yuleOSH ISO 26262 Safety Concept — v2.4.0

> Status: Skeleton / Phase 1 | ASIL: QM–D | Reference: ISO 26262:2018
> Format: Requirements follow RS-XXX / SWR-XXX numbering convention

---

## 1. Safety Goals (SG)

### SG-001: Pipeline Execution Integrity

| Attribute | Value |
|:----------|:------|
| **ID** | SG-001 |
| **Title** | Pipeline execution SHALL NOT produce corrupted artifacts |
| **ASIL** | **B** |
| **Status** | Draft |
| **Ref** | RS-001 |

#### Safe State
- Pipeline SHALL abort on any artifact integrity check failure
- Pipeline SHALL NOT propagate corrupted artifacts to downstream stages

#### FTTI (Fault Tolerant Time Interval)
- < 500 ms from fault detection to safe state entry

#### SG-001.1 — Artifact Integrity Verification
- The system SHALL verify artifact checksum (SHA-256) after each pipeline stage
- The system SHALL abort the pipeline if any artifact integrity check fails
- The system SHALL log the integrity failure with stage ID and artifact path for audit

#### SG-001.2 — Pipeline Stage Isolation
- The system SHALL execute each pipeline stage in an isolated workspace
- The system SHALL clean the workspace between pipeline runs to prevent artifact contamination
- The system SHALL reject cross-stage file references that violate stage boundaries

---

### SG-002: Spec Parsing Integrity

| Attribute | Value |
|:----------|:------|
| **ID** | SG-002 |
| **Title** | Spec parsing SHALL NOT accept malformed input that could cause undefined behavior |
| **ASIL** | **C** |
| **Status** | Draft |
| **Ref** | RS-002 |

#### Safe State
- Return parse error with diagnostic message; do not proceed with undefined spec state

#### SG-002.1 — Input Validation
- The system SHALL reject spec files containing unrecognized syntax constructs
- The system SHALL validate all SHALL/SHOULD/MAY statements against RFC 2119 grammar
- The system SHALL reject spec files exceeding a configurable maximum size (default 10 MB)

#### SG-002.2 — Parse Error Handling
- The system SHALL report the exact line and column of any parse error
- The system SHALL NOT proceed to pipeline execution if spec parsing fails
- The system SHALL record parse errors in the audit log with timestamp

---

### SG-003: CI/CD Gate Integrity

| Attribute | Value |
|:----------|:------|
| **ID** | SG-003 |
| **Title** | CI/CD gates SHALL NOT be bypassed or report incorrect results |
| **ASIL** | **B** |
| **Status** | Draft |
| **Ref** | RS-004 |

#### Safe State
- Pipeline SHALL remain blocked if any CI gate returns FAIL
- Gate results SHALL be archived tamper-evident

#### SG-003.1 — Gate Non-Bypassability
- The system SHALL enforce that all configured CI gates execute before any build promotion
- The system SHALL NOT allow manual override of CI gate results without audit trail
- The system SHALL record every gate override with user ID, reason, and timestamp

#### SG-003.2 — Coverage Gate Accuracy
- The system SHALL compare line/branch coverage against the configured threshold (default > 98%)
- The system SHALL reject coverage data that is incomplete or corrupted
- The system SHALL NOT cache coverage results across different builds

---

### SG-004: Authentication & Access Control

| Attribute | Value |
|:----------|:------|
| **ID** | SG-004 |
| **Title** | Unauthorized access to system resources SHALL be prevented |
| **ASIL** | **C** |
| **Status** | Draft |
| **Ref** | RS-007 |

#### Safe State
- Return 401/403 for unauthorized requests; log the attempt

#### SG-004.1 — API Authentication
- The system SHALL require valid JWT bearer tokens for all sensitive API endpoints
- The system SHALL reject requests with expired, revoked, or malformed tokens
- The system SHALL log all authentication failures with IP address and timestamp

#### SG-004.2 — Role-Based Access Control
- The system SHALL enforce role-based access (admin/member/viewer) for all operations
- The system SHALL deny write operations for read-only roles
- The system SHALL deny admin operations for non-admin roles

---

### SG-005: Audit Trail Integrity

| Attribute | Value |
|:----------|:------|
| **ID** | SG-005 |
| **Title** | Audit records SHALL be complete, accurate, and tamper-evident |
| **ASIL** | **A** |
| **Status** | Draft |
| **Ref** | RS-005 |

#### Safe State
- Audit logging failure SHALL NOT block pipeline execution
- Audit data loss SHALL be detected and reported as a warning

#### SG-005.1 — Audit Logging Completeness
- The system SHALL record every API request (method, path, status, IP, duration)
- The system SHALL record every pipeline execution with stage-level granularity
- The system SHALL record every CI gate result with pass/fail/error distinction

#### SG-005.2 — Audit Log Protection
- The system SHALL NOT allow deletion of audit log entries
- The system SHALL support audit log export in a tamper-evident format
- The system SHALL retain audit logs for a minimum of 12 months

---

### SG-006: Evidence Pack Integrity

| Attribute | Value |
|:----------|:------|
| **ID** | SG-006 |
| **Title** | Generated compliance evidence SHALL be correct and verifiable |
| **ASIL** | **A** |
| **Status** | Draft |
| **Ref** | RS-005 |

#### Safe State
- Evidence generation failure SHALL result in an empty or error manifest
- Corrupted evidence packs SHALL be rejected on download

#### SG-006.1 — Evidence Generation Consistency
- The system SHALL generate evidence only from completed, verified pipeline runs
- The system SHALL include a manifest with SHA-256 checksums for every artifact in the pack
- The system SHALL timestamp every evidence generation event

#### SG-006.2 — Evidence Verification
- The system SHALL verify evidence pack integrity on download (manifest checksums)
- The system SHALL reject evidence packs with mismatched checksums
- The system SHALL log evidence pack verification results

---

### SG-007: SIL/HIL Test Safety

| Attribute | Value |
|:----------|:------|
| **ID** | SG-007 |
| **Title** | SIL/HIL test execution SHALL NOT damage hardware or produce unsafe firmware |
| **ASIL** | **D** |
| **Status** | Draft |
| **Ref** | RS-008, RS-009 |

#### Safe State
- Abort test execution on any hardware communication failure
- Do not flash firmware with failed verification

#### SG-007.1 — SIL Execution Safety
- The system SHALL enforce timeout-based termination (default 30s) for all SIL tests
- The system SHALL isolate each SIL test in its own QEMU process
- The system SHALL clean up QEMU processes after test completion or timeout

#### SG-007.2 — HIL Execution Safety
- The system SHALL verify target connectivity before attempting to flash
- The system SHALL verify flash integrity (checksum comparison) after programming
- The system SHALL NOT execute HIL tests without a verified serial connection
- The system SHALL implement a watchdog timer for HIL test execution

#### SG-007.3 — Firmware Integrity
- The system SHALL verify firmware binary checksum before flashing
- The system SHALL NOT flash firmware with unresolved safety violations
- The system SHALL record firmware version and hash in the test report

---

## 2. Functional Safety Requirements (FSR)

### FSR-001: Error Detection

| ID | SHALL | ASIL | Ref SG | Status |
|:---|:------|:----:|:------:|:------:|
| FSR-001-01 | The system SHALL detect pipeline stage execution failures within 500 ms | B | SG-001 | Draft |
| FSR-001-02 | The system SHALL detect spec parsing errors with line/column precision | C | SG-002 | Draft |
| FSR-001-03 | The system SHALL detect CI gate bypass attempts at runtime | B | SG-003 | Draft |
| FSR-001-04 | The system SHALL detect invalid/expired JWT tokens on each request | C | SG-004 | Draft |
| FSR-001-05 | The system SHALL detect evidence pack integrity violations on generation | A | SG-006 | Draft |
| FSR-001-06 | The system SHALL detect SIL test timeout and terminate the QEMU process | D | SG-007 | Draft |

### FSR-002: Error Response

| ID | SHALL | ASIL | Ref SG | Status |
|:---|:------|:----:|:------:|:------:|
| FSR-002-01 | On stage failure, the system SHALL abort the pipeline and mark all downstream stages as blocked | B | SG-001 | Draft |
| FSR-002-02 | On spec parse error, the system SHALL return a 400-level error with diagnostic details | C | SG-002 | Draft |
| FSR-002-03 | On CI gate failure, the system SHALL block build promotion until the gate passes | B | SG-003 | Draft |
| FSR-002-04 | On auth failure, the system SHALL return 401 and log the attempt | C | SG-004 | Draft |
| FSR-002-05 | On evidence integrity failure, the system SHALL reject the evidence pack and report | A | SG-006 | Draft |
| FSR-002-06 | On HIL communication failure, the system SHALL abort the test and not attempt flash | D | SG-007 | Draft |

### FSR-003: Fault Tolerance

| ID | SHALL | ASIL | Ref SG | Status |
|:---|:------|:----:|:------:|:------:|
| FSR-003-01 | The system SHALL use isolated workspaces per pipeline run | B | SG-001 | Draft |
| FSR-003-02 | The system SHALL use parameterized queries for all database operations | C | SG-004 | Draft |
| FSR-003-03 | The system SHALL apply path normalization to prevent traversal attacks | C | SG-004 | Draft |
| FSR-003-04 | The system SHALL clean up all QEMU processes on test timeout or abort | D | SG-007 | Draft |
| FSR-003-05 | The audit logging system SHALL operate independently of the main request handling | A | SG-005 | Draft |

### FSR-004: Verification & Validation

| ID | SHALL | ASIL | Ref SG | Status |
|:---|:------|:----:|:------:|:------:|
| FSR-004-01 | The system SHALL verify artifact SHA-256 checksums after each pipeline stage | B | SG-001 | Draft |
| FSR-004-02 | The system SHALL verify all spec inputs against RFC 2119 grammar | C | SG-002 | Draft |
| FSR-004-03 | The system SHALL verify coverage thresholds are met before build promotion | B | SG-003 | Draft |
| FSR-004-04 | The system SHALL verify JWT signature and expiration on every authenticated request | C | SG-004 | Draft |
| FSR-004-05 | The system SHALL verify evidence pack manifest checksums on generation and download | A | SG-006 | Draft |
| FSR-004-06 | The system SHALL verify firmware binary checksum before flashing to hardware | D | SG-007 | Draft |

---

## 3. ASIL Decomposition & Freedom from Interference (FFI)

### 3.1 ASIL Tree

```
System Level
├── SG-001 (ASIL B) — Pipeline Execution Integrity
├── SG-002 (ASIL C) — Spec Parsing Integrity
├── SG-003 (ASIL B) — CI/CD Gate Integrity
├── SG-004 (ASIL C) — Authentication & Access Control
├── SG-005 (ASIL A) — Audit Trail Integrity
├── SG-006 (ASIL A) — Evidence Pack Integrity
└── SG-007 (ASIL D) — SIL/HIL Test Safety
         ↑
    Highest ASIL determines overall system ASIL
```

### 3.2 ASIL Decomposition Strategy

For mixed-ASIL components:

| Component | SG(s) | Native ASIL | Decomposed To | Method |
|:----------|:------|:-----------:|:-------------:|:-------|
| Pipeline Runner | SG-001, SG-003 | B | QM(A) + B(B) | Sufficiently independent execution stages |
| API Gateway | SG-004 | C | QM(A) + C(B) | Auth middleware isolated from business logic |
| HIL Runner | SG-007 | D | B(C) + B(D) | Independent watchdog and test scheduler |

### 3.3 Freedom from Interference (FFI)

| Domain | Higher ASIL | Lower ASIL | Interference | FFI Measure |
|:-------|:-----------:|:----------:|:------------|:------------|
| Pipeline Steps | B | QM | Corruption of high-ASIL artifacts by QM steps | SHA-256 verification after each step |
| API Routes | C | A | Auth bypass by lower-ASIL routes | Centralized middleware with no bypass |
| Test Execution | D | B | QEMU failure affecting HIL | Separate processes, watchdog timer |

---

## 4. Safety Lifecycle Mapping

| ISO 26262 Part | yuleOSH Mapping | Status |
|:---------------|:----------------|:------:|
| Part 3: Concept Phase | SG-001–SG-007 defined above | Draft |
| Part 4: System-Level | Pipeline orchestration, CI/CD gates | Draft |
| Part 5: Hardware-Level | HIL adapters, flash abstractions | Draft |
| Part 6: Software-Level | SIL runner, code review, static analysis | Draft |
| Part 8: Supporting Processes | Evidence pack, audit trail, traceability | Draft |
| Part 9: ASIL & Safety Analysis | Decomposition table above | Draft |
| Part 10: Guideline on ISO 26262 | This document follows ISO 26262:2018 structure | Draft |

---

## 5. Confirmatory Measures

| Safety Goal | Confirmation Measure | Responsible | ASIL |
|:------------|:---------------------|:------------|:----:|
| SG-001 | Independent review of pipeline stage isolation | Safety Manager | B |
| SG-002 | Input fuzzing of spec parser | Test Engineer | C |
| SG-003 | Audit of gate override records | Quality Manager | B |
| SG-004 | Penetration testing of API auth | Security Engineer | C |
| SG-005 | Audit log review for completeness | Quality Manager | A |
| SG-006 | Evidence pack spot-check against source | Assessor | A |
| SG-007 | HIL safety review and watchdog validation | Safety Engineer | D |

---

## 6. Dependencies & Assumptions

### Dependencies
- D-001: QEMU version ≥ 7.2 (for ARM Cortex-M3/M4 emulation)
- D-002: OpenOCD ≥ 0.12 or JLink ≥ V7.94 (for HIL flashing)
- D-003: Python ≥ 3.11 (for JWT, bcrypt, subprocess isolation)
- D-004: Operating system with process isolation support (Linux/macOS)

### Assumptions
- A-001: The user is responsible for configuring appropriate ASIL targets per project
- A-002: SIL tests represent the target execution environment within QEMU capability limits
- A-003: HIL connectivity failures are detected by the flash abstraction layer before test execution
- A-004: Static analysis results (MISRA) are reviewed by domain experts before safety sign-off

---

*This document is a Phase 1 safety concept skeleton. Each Safety Goal and FSR requires refinement through hazard analysis and risk assessment (HARA) in subsequent phases.*
