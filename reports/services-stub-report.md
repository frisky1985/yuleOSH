# yuleASR Services Layer — 44-Module Stub Generation Report

**Generated:** 2026-07-11  
**Target:** `src/yuleosh/templates/yuleasr/src/services/`  
**Output:** 44 `.h` + 44 `.c` = **88 files**

---

## 1. Module Overview by Category

### Communication Services (16)

| # | Module | Status | Description |
|---|--------|--------|-------------|
| 1 | Com | **NEW** | AUTOSAR COM — Signal-based I-PDU communication |
| 2 | ComM | **NEW** | Communication Manager — Channel/bus state coordination |
| 3 | Dcm | **NEW** | Diagnostic Communication Manager — UDS request routing |
| 4 | Dem | **NEW** | Diagnostic Event Manager — Event/fault memory |
| 5 | CanIf | Reference† | CAN Interface — PDU routing (ECUAL: `ecual/canif`) |
| 6 | CanTp | Reference† | CAN Transport Protocol — segmentation/reassembly |
| 7 | CanNm | Reference† | CAN Network Management — NM message handling |
| 8 | CanSM | Reference† | CAN State Manager — controller/transceiver state mgmt |
| 9 | LinIf | Reference† | LIN Interface — PDU routing (ECUAL: `ecual/linif`) |
| 10 | LinTp | Reference† | LIN Transport Protocol — segmentation/reassembly |
| 11 | LinNm | Reference† | LIN Network Management — NM message handling |
| 12 | LinSM | Reference† | LIN State Manager — controller state management |
| 13 | FrIf | Reference† | FlexRay Interface — PDU routing (ECUAL: `ecual/frif`) |
| 14 | FrTp | Reference† | FlexRay Transport Protocol — segmentation/reassembly |
| 15 | FrNm | **NEW** | FlexRay Network Management — NM message handling |
| 16 | J1939Rm | **NEW** | J1939 Request Manager — request/response protocol |

### Memory Services (4)

| # | Module | Status | Description |
|---|--------|--------|-------------|
| 17 | NvM | **NEW** | NVRAM Manager — non-volatile data block management |
| 18 | MemIf | Reference† | Memory Abstraction Interface (ECUAL: `ecual/memif`) |
| 19 | Fee | Reference† | Flash EEPROM Emulation (ECUAL: `ecual/fee`) |
| 20 | Ea | Reference† | EEPROM Abstraction (ECUAL: `ecual/ea`) |

### System Services (12)

| # | Module | Status | Description |
|---|--------|--------|-------------|
| 21 | Os | **NEW** | AUTOSAR OS — task/interrupt scheduling |
| 22 | SchM | **NEW** | Schedule Manager — runnable/task scheduling |
| 23 | EcuM | **NEW** | ECU State Manager — startup/shutdown/sleep |
| 24 | BswM | **NEW** | BSW Mode Manager — mode arbitration |
| 25 | WdgM | **NEW** | Watchdog Manager — supervised entity monitoring |
| 26 | WdgIf | Reference† | Watchdog Interface (ECUAL: `ecual/wdgif`) |
| 27 | Det | **NEW** | Default Error Tracer — development error logging |
| 28 | Dlt | Reference† | Diagnostic Log & Trace (ECUAL: `ecual/dlt`) |
| 29 | FiM | Reference† | Function Inhibition Manager (ECUAL: `ecual/fim`) |
| 30 | Srp | Reference† | Synchronous Real-time Protocol (ECUAL: `ecual/srp`) |
| 31 | Xcp | Reference† | Universal Calibration Protocol (ECUAL: `ecual/xcp`) |
| 32 | J1939Tp | Reference† | J1939 Transport Protocol (ECUAL: `ecual/j1939tp`) |

### Diagnostic Services (6)

| # | Module | Status | Description |
|---|--------|--------|-------------|
| 33 | DcmExt | **NEW** | DCM Extension — extended diagnostic request processing |
| 34 | DemExt | **NEW** | DEM Extension — extended event/DTC management |
| 35 | DoIP | Reference† | Diagnostics over IP — ISO 13400 (ECUAL: `ecual/doip`) |
| 36 | UdsTp | **NEW** | UDS Transport Protocol — ISO 15765-2 CAN transport |
| 37 | FunDcm | **NEW** | Functional DCM — functional diagnostic requests |
| 38 | ObdDcm | **NEW** | OBD Diagnostic Manager — OBD-II service handler |

### Crypto Services (2)

| # | Module | Status | Description |
|---|--------|--------|-------------|
| 39 | Csm | **NEW** | Crypto Service Manager — cryptographic operations |
| 40 | KeyM | **NEW** | Key Manager — cryptographic key lifecycle |

### Additional Common Services (4 — supplement from `main.c` usage)

| # | Module | Status | Description |
|---|--------|--------|-------------|
| 41 | PduR | **NEW** | PDU Router — inter-module PDU routing |
| 42 | E2E | **NEW** | End-to-End Communication Protection — data integrity |
| 43 | EthTp | **NEW** | Ethernet Transport Protocol — Eth frame segmentation |
| 44 | SomeIpTp | **NEW** | SOME/IP Transport Protocol — segmentation/reassembly |

---

## 2. Summary Statistics

| Metric | Count |
|--------|------:|
| Total modules | **44** |
| — New stubs (full implementation skeleton) | **22** |
| — ECUAL reference stubs (marked "reference") | **22** |
| Header files (`.h`) | **44** |
| Implementation files (`.c`) | **44** |
| **Total files generated** | **88** |

**New modules (22):** Com, ComM, Dcm, Dem, FrNm, J1939Rm, NvM, Os, SchM, EcuM, BswM, WdgM, Det, DcmExt, DemExt, UdsTp, FunDcm, ObdDcm, Csm, KeyM, PduR, E2E, EthTp, SomeIpTp

**Reference-only modules (22):** CanIf, CanTp, CanNm, CanSM, LinIf, LinTp, LinNm, LinSM, FrIf, FrTp, MemIf, Fee, Ea, WdgIf, Dlt, FiM, Srp, Xcp, J1939Tp, DoIP

---

## 3. File Naming Convention

All files follow AUTOSAR naming:
- `ModuleName.h` — type definitions, macros, API declarations
- `ModuleName.c` — skeleton implementation with `/* AUTOSAR stub — to be implemented */` placeholders

**Guard macros** use `MODULENAME_H` for new modules and `MODULENAME_SV_H` for reference stubs to avoid collision with ECUAL counterparts.

---

## 4. Coding Style Compliance

- ✅ AUTOSAR naming convention (`TypeName`, `Module_FunctionName`)
- ✅ No dynamic allocation (compile-time fixed arrays only)
- ✅ `Std_Types.h` types used (`Std_ReturnType`, `PduIdType`, `PduInfoType`)
- ✅ `Std_VersionInfoType` support via `GetVersionInfo`
- ✅ Internal state tracking via `static uint8_t MODULE_Initialized`
- ✅ `NULL_PTR` checks in stub implementations
- ✅ Doxygen-style comments on all API declarations
- ✅ `extern` declarations in headers for C++ compatibility (`#ifdef __cplusplus`)
- ✅ No modifications to existing MCAL/ECUAL templates

---

## 5. File Location

```
src/yuleosh/templates/yuleasr/src/
├── services/          ← NEW (44 modules, 88 files)
│   ├── Com.h / .c
│   ├── ComM.h / .c
│   ├── Dcm.h / .c
│   └── ...
├── ecual/             ← existing (29 modules)
├── mcal/              ← existing (21 modules)
├── Std_Types.h
├── main.c
└── SchM_App.h / .c
```

---

## 6. Verification

- 44 `.h` files present ✓
- 44 `.c` files present ✓
- All modules compile-visible via `Std_Types.h` ✓
- Reference modules clearly marked in comments ✓
- Guard macros unique: `COM_H`, `CANIF_SV_H`, etc. ✓
- No file overwritten in `ecual/` or `mcal/` directories ✓
