# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
AUTOSAR Pipeline Compliance Tests — GIVEN/WHEN/THEN framework.

Tests the yuleOSH AUTOSAR CI pipeline stages:
  - build: Compile MCAL/ECUAL/Services layers
  - cross-compile: ARM Cortex-M cross-compilation
  - MISRA: C:2023 static analysis
  - ARXML: Compliance validation

Run with:
  python3 -m pytest tests/test_autosar_pipeline.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.ci.stages.autosar import (
    run_autosar_build,
    run_autosar_cross_build,
    run_autosar_misra_check,
    run_arxml_compliance_check,
    STAGES_REGISTRY,
)


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_autosar_project(tmp_path):
    """Create a minimal AUTOSAR project structure for testing."""
    src_dirs = [
        tmp_path / "src" / "mcal" / "mcu",
        tmp_path / "src" / "mcal" / "dio",
        tmp_path / "src" / "mcal" / "port",
        tmp_path / "src" / "ecual" / "canif",
        tmp_path / "src" / "ecual" / "memif",
        tmp_path / "src" / "services" / "com",
        tmp_path / "src" / "services" / "dcm",
        tmp_path / "src" / "services" / "ecum",
        tmp_path / "config",
    ]
    for d in src_dirs:
        d.mkdir(parents=True, exist_ok=True)

    # MCAL stub: Mcu.c
    (tmp_path / "src" / "mcal" / "mcu" / "Mcu.c").write_text("""
#include "Mcu.h"
#include "Std_Types.h"
void Mcu_Init(const Mcu_ConfigType* ConfigPtr) { (void)ConfigPtr; }
void Mcu_SetMode(Mcu_ModeType Mode) { (void)Mode; }
""")
    (tmp_path / "src" / "mcal" / "mcu" / "Mcu.h").write_text("""
#ifndef MCU_H
#define MCU_H
#include "Std_Types.h"
typedef uint32_t Mcu_ModeType;
#define MCU_MODE_NORMAL 0U
typedef struct {} Mcu_ConfigType;
void Mcu_Init(const Mcu_ConfigType* ConfigPtr);
void Mcu_SetMode(Mcu_ModeType Mode);
#endif
""")

    # MCAL stub: Dio.c
    (tmp_path / "src" / "mcal" / "dio" / "Dio.c").write_text("""
#include "Dio.h"
void Dio_Init(const Dio_ConfigType* ConfigPtr) { (void)ConfigPtr; }
Dio_LevelType Dio_ReadChannel(Dio_ChannelType ChannelId) { (void)ChannelId; return STD_LOW; }
""")
    (tmp_path / "src" / "mcal" / "dio" / "Dio.h").write_text("""
#ifndef DIO_H
#define DIO_H
#include "Std_Types.h"
typedef uint8_t Dio_LevelType;
typedef uint8_t Dio_ChannelType;
#define STD_LOW  0U
#define STD_HIGH 1U
typedef struct {} Dio_ConfigType;
void Dio_Init(const Dio_ConfigType* ConfigPtr);
Dio_LevelType Dio_ReadChannel(Dio_ChannelType ChannelId);
#endif
""")

    # MCAL stub: Port.c
    (tmp_path / "src" / "mcal" / "port" / "Port.c").write_text("""
#include "Port.h"
void Port_Init(const Port_ConfigType* ConfigPtr) { (void)ConfigPtr; }
""")
    (tmp_path / "src" / "mcal" / "port" / "Port.h").write_text("""
#ifndef PORT_H
#define PORT_H
typedef struct {} Port_ConfigType;
void Port_Init(const Port_ConfigType* ConfigPtr);
#endif
""")

    # ECUAL stub: CanIf.c
    (tmp_path / "src" / "ecual" / "canif" / "CanIf.c").write_text("""
#include "CanIf.h"
void CanIf_Init(void) {}
void CanIf_MainFunction(void) {}
""")
    (tmp_path / "src" / "ecual" / "canif" / "CanIf.h").write_text("""
#ifndef CANIF_H
#define CANIF_H
void CanIf_Init(void);
void CanIf_MainFunction(void);
#endif
""")

    # ECUAL stub: MemIf.c
    (tmp_path / "src" / "ecual" / "memif" / "MemIf.c").write_text("""
#include "MemIf.h"
void MemIf_Init(void) {}
""")
    (tmp_path / "src" / "ecual" / "memif" / "MemIf.h").write_text("""
#ifndef MEMIF_H
#define MEMIF_H
void MemIf_Init(void);
#endif
""")

    # Services stub: Com.c
    (tmp_path / "src" / "services" / "com" / "Com.c").write_text("""
#include "Com.h"
void Com_Init(void) {}
void Com_MainFunction(void) {}
""")
    (tmp_path / "src" / "services" / "com" / "Com.h").write_text("""
#ifndef COM_H
#define COM_H
void Com_Init(void);
void Com_MainFunction(void);
#endif
""")

    # Services stub: Dcm.c
    (tmp_path / "src" / "services" / "dcm" / "Dcm.c").write_text("""
#include "Dcm.h"
void Dcm_Init(void) {}
void Dcm_MainFunction(void) {}
""")
    (tmp_path / "src" / "services" / "dcm" / "Dcm.h").write_text("""
#ifndef DCM_H
#define DCM_H
void Dcm_Init(void);
void Dcm_MainFunction(void);
#endif
""")

    # Services stub: EcuM.c
    (tmp_path / "src" / "services" / "ecum" / "EcuM.c").write_text("""
#include "EcuM.h"
void EcuM_Init(void) {}
void EcuM_MainFunction(void) {}
""")
    (tmp_path / "src" / "services" / "ecum" / "EcuM.h").write_text("""
#ifndef ECUM_H
#define ECUM_H
void EcuM_Init(void);
void EcuM_MainFunction(void);
#endif
""")

    # Common Std_Types.h
    (tmp_path / "src" / "Std_Types.h").write_text("""
#ifndef STD_TYPES_H
#define STD_TYPES_H
#include <stdint.h>
typedef uint8_t Std_ReturnType;
#define E_OK    0U
#define E_NOT_OK 1U
#endif
""")

    # Config stubs
    (tmp_path / "config" / "Mcu_Cfg.h").write_text("""
#ifndef MCU_CFG_H
#define MCU_CFG_H
#define MCU_CORE_CLOCK_HZ 120000000UL
#define MCU_BUS_CLOCK_HZ  60000000UL
#endif
""")
    (tmp_path / "config" / "Dio_Cfg.h").write_text("""
#ifndef DIO_CFG_H
#define DIO_CFG_H
#define DIO_NUM_CHANNELS 4U
#endif
""")

    # ARXML example
    arxml_dir = tmp_path / "arxml"
    arxml_dir.mkdir(exist_ok=True)
    (arxml_dir / "example.arxml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGE>
    <SHORT-NAME>Test</SHORT-NAME>
    <ELEMENTS>
      <APPLICATION-SW-COMPONENT-TYPE UUID="00000000-0000-0000-0000-000000000001">
        <SHORT-NAME>TestComponent</SHORT-NAME>
        <PORTS>
          <P-PORT-PROTOTYPE>
            <SHORT-NAME>TestOutput</SHORT-NAME>
            <PROVIDED-INTERFACE-TREF DEST="SENDER-RECEIVER-INTERFACE">/Test/If/TestIf</PROVIDED-INTERFACE-TREF>
          </P-PORT-PROTOTYPE>
        </PORTS>
        <INTERNAL-BEHAVIORS>
          <SWC-INTERNAL-BEHAVIOR>
            <SHORT-NAME>Behavior</SHORT-NAME>
            <RUNNABLE-ENTITY>
              <SHORT-NAME>MainRunnable</SHORT-NAME>
              <SYMBOL>Test_MainRunnable</SYMBOL>
              <MINIMUM-START-INTERVAL>0.01</MINIMUM-START-INTERVAL>
              <EVENT-TIMING-EVENT>
                <SHORT-NAME>TimingEvent</SHORT-NAME>
                <TIMING-PERIOD>0.01</TIMING-PERIOD>
              </EVENT-TIMING-EVENT>
            </RUNNABLE-ENTITY>
          </SWC-INTERNAL-BEHAVIOR>
        </INTERNAL-BEHAVIORS>
      </APPLICATION-SW-COMPONENT-TYPE>
    </ELEMENTS>
  </AR-PACKAGE>
</AUTOSAR>""")

    return tmp_path


# ══════════════════════════════════════════════════════════════════
# GIVEN/WHEN/THEN Compliance Tests
# ══════════════════════════════════════════════════════════════════


class TestAutosarBuild:
    """GIVEN an AUTOSAR project with MCAL/ECUAL/Services source files"""

    def test_build_mcal_layer(self, sample_autosar_project):
        """
        GIVEN a project with MCAL source files (Mcu.c, Dio.c, Port.c)
        WHEN run_autosar_build is called with mcal_only=True
        THEN all MCAL files compile without errors
        """
        result = run_autosar_build(
            str(sample_autosar_project),
            mcal_only=True,
            verbose=False,
        )

        assert "mcal" in result
        assert result["mcal"]["status"] == "pass", \
            f"MCAL build failed: {result['mcal'].get('error_details', [])}"
        assert result["mcal"]["compiled"] >= 3, \
            f"Expected ≥3 MCAL files compiled, got {result['mcal']['compiled']}"

    def test_build_ecual_layer(self, sample_autosar_project):
        """
        GIVEN a project with ECUAL source files (CanIf.c, MemIf.c)
        WHEN run_autosar_build is called with ecual_only=True
        THEN all ECUAL files compile without errors
        """
        result = run_autosar_build(
            str(sample_autosar_project),
            ecual_only=True,
            verbose=False,
        )

        assert "ecual" in result
        assert result["ecual"]["status"] == "pass", \
            f"ECUAL build failed: {result['ecual'].get('error_details', [])}"

    def test_build_services_layer(self, sample_autosar_project):
        """
        GIVEN a project with Services source files (Com.c, Dcm.c, EcuM.c)
        WHEN run_autosar_build is called with services_only=True
        THEN all Services files compile without errors
        """
        result = run_autosar_build(
            str(sample_autosar_project),
            services_only=True,
            verbose=False,
        )

        assert "services" in result
        assert result["services"]["status"] == "pass", \
            f"Services build failed: {result['services'].get('error_details', [])}"

    def test_build_all_layers(self, sample_autosar_project):
        """
        GIVEN a project with all three BSW layers
        WHEN run_autosar_build is called with no filters
        THEN all layers compile and _meta.all_pass is True
        """
        result = run_autosar_build(str(sample_autosar_project))

        assert "_meta" in result
        assert result["_meta"]["all_pass"] is True
        assert result["mcal"]["status"] == "pass"
        assert result["ecual"]["status"] == "pass"
        assert result["services"]["status"] == "pass"

    def test_build_nonexistent_project(self):
        """
        GIVEN a non-existent project directory
        WHEN run_autosar_build is called
        THEN it returns an error status
        """
        result = run_autosar_build("/nonexistent/path")
        assert "error" in result.get("message", "") or result.get("status") == "error"


class TestAutosarMisraCheck:
    """GIVEN AUTOSAR BSW source files with known MISRA patterns"""

    def test_misra_check_skip_missing_layer(self, sample_autosar_project):
        """
        GIVEN a project with missing ECUAL layer directory
        WHEN run_autosar_misra_check is called
        THEN it skips the missing layer gracefully
        """
        # Remove ecual to test graceful skip
        ecual_dir = sample_autosar_project / "src" / "ecual"
        if ecual_dir.exists():
            shutil.rmtree(str(ecual_dir))

        result = run_autosar_misra_check(str(sample_autosar_project), layers=["ecual"])

        assert "ecual" in result
        assert result["ecual"]["status"] == "skip"


class TestArxmlCompliance:
    """GIVEN an AUTOSAR project with ARXML descriptor files"""

    def test_arxml_compliance_pass(self, sample_autosar_project):
        """
        GIVEN a project with a valid ARXML file
        WHEN run_arxml_compliance_check is called
        THEN it reports compliance status
        """
        result = run_arxml_compliance_check(str(sample_autosar_project))

        assert result["status"] in ("pass", "skip")
        assert result["files_checked"] >= 1

    def test_arxml_compliance_no_files(self, tmp_path):
        """
        GIVEN a project with no ARXML files
        WHEN run_arxml_compliance_check is called
        THEN it returns skip status with a hint
        """
        tmp_path.mkdir(exist_ok=True)
        result = run_arxml_compliance_check(str(tmp_path))

        assert result["status"] == "skip"
        assert "hint" in result


class TestStageRegistry:
    """GIVEN the AUTOSAR stage registry"""

    def test_registry_has_all_stages(self):
        """
        GIVEN the STAGES_REGISTRY dict
        WHEN checked for expected keys
        THEN all AUTOSAR CI stages are registered
        """
        expected = [
            "autosar-build",
            "autosar-cross-compile",
            "autosar-misra-check",
            "autosar-full-ci",
            "arxml-compliance",
        ]
        for stage in expected:
            assert stage in STAGES_REGISTRY, f"Missing stage: {stage}"

    def test_registry_functions_are_callable(self):
        """
        GIVEN the STAGES_REGISTRY dict
        WHEN each entry is checked
        THEN each entry is a callable function
        """
        for name, func in STAGES_REGISTRY.items():
            assert callable(func), f"Stage '{name}' is not callable"
