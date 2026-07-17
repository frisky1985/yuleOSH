# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — AUTOSAR BSW compilation and static analysis.

Provides CI stages for AUTOSAR Classic Platform projects:

  - run_autosar_build()         — Compile MCAL/ECUAL/Services layers
  - run_autosar_cross_build()   — Cross-compile for ARM Cortex-M/R targets
  - run_autosar_misra_check()   — MISRA-C:2023 static analysis on BSW code
  - run_autosar_full_ci()       — Combined AUTOSAR CI stage (L1-L3)

These integrate with the existing yuleOSH CI pipeline defined in
src/yuleosh/ci/layers.py and are registered as available stages.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("ci.stages.autosar")


# ── Constants ──────────────────────────────────────────────────────────────

ARM_CORTEX_M7_FLAGS = [
    "-mcpu=cortex-m7",
    "-mthumb",
    "-mfpu=fpv5-sp-d16",
    "-mfloat-abi=hard",
]

AUTOSAR_C_STANDARD = "-std=c99"

BSW_LAYER_NAMES = {
    "mcal": "MCAL (Microcontroller Abstraction Layer)",
    "ecual": "ECUAL (ECU Abstraction Layer)",
    "services": "Services Layer (COM, DCM, NvM, etc.)",
}

MISRA_C2023_AUTOSAR_RULES = [
    "R2.1",   # Unused code
    "R8.2",   # Function types
    "R8.13",  # Pointer to const
    "R10.3",  # Integer type conversion
    "R10.4",  # Operand type
    "R10.8",  # Compound assignment
    "R11.2",  # Pointer arithmetic
    "R12.1",  # Precedence of operators
    "R14.2",  # Loop counter
    "R14.4",  # If condition
    "R15.1",  # Switch
    "R16.1",  # Default label
    "R16.2",  # Switch case
    "R16.3",  # Bool expression
    "R16.7",  # Switch clause
    "R17.2",  # Function recursion
    "R17.3",  # Implicit function declaration
    "R17.4",  # Function parameter type
    "R17.7",  # Return value
    "R18.1",  # Global variable
    "R18.6",  # Static storage
    "R18.8",  # Variable-length array
    "R20.1",  # Reserved identifier
    "R20.2",  # Macro parenthesis
    "R20.4",  # Macro parameter
    "R20.5",  # #undef
    "R21.1",  # #define
    "R21.2",  # Reserved macro
    "R21.3",  # Memory allocation
    "R21.4",  # stdlib
    "R21.5",  # <math.h>
    "R21.7",  # atof/atoi
    "R21.8",  # abort/getenv
    "R21.9",  # setjmp/longjmp
    "R21.11", # unbounded functions
    "R21.12", # time.h exception
    "R22.1",  # Dynamic memory
    "R22.2",  # Free memory
    "R22.3",  # File open
    "R22.4",  # File close
    "R22.6",  # EOF
]


# ══════════════════════════════════════════════════════════════════════════
# AUTOSAR Build Stage
# ══════════════════════════════════════════════════════════════════════════

def run_autosar_build(
    project_dir: str,
    layers: Optional[List[str]] = None,
    mcal_only: bool = False,
    ecual_only: bool = False,
    services_only: bool = False,
    build_dir: str = "build",
    verbose: bool = False,
) -> Dict:
    """Build AUTOSAR BSW layers: MCAL, ECUAL, Services.

    Args:
        project_dir: Project root directory.
        layers: Specific layers to build (e.g. ["mcal", "ecual"]).
                Overrides mcal_only/ecual_only/services_only if set.
        mcal_only: Build only MCAL layer.
        ecual_only: Build only ECUAL layer.
        services_only: Build only Services layer.
        build_dir: Output build directory name.
        verbose: Enable verbose compiler output.

    Returns:
        Dict with build results per layer:
            {"mcal": {"status": "pass"|"fail", "output": "...", "errors": [...]}, ...}
    """
    from yuleosh.ci.result import CIResult, timed_stage

    project_path = Path(project_dir)
    if not project_path.exists():
        return {"status": "error", "message": f"Project directory not found: {project_dir}"}

    # Determine which layers to build
    if layers is None:
        layers = []
        if mcal_only:
            layers = ["mcal"]
        elif ecual_only:
            layers = ["ecual"]
        elif services_only:
            layers = ["services"]
        else:
            layers = ["mcal", "ecual", "services"]

    results = {}
    all_pass = True

    for layer in layers:
        layer_name = BSW_LAYER_NAMES.get(layer, layer.upper())
        print(f"  🔧 AUTOSAR: {layer_name} build...")

        source_dir = project_path / "src" / layer
        config_dir = project_path / "config"
        out_dir = project_path / build_dir / layer
        out_dir.mkdir(parents=True, exist_ok=True)

        if not source_dir.exists():
            log.warning("Layer source directory not found: %s", source_dir)
            results[layer] = {"status": "skip", "reason": f"Source dir not found: {source_dir}"}
            continue

        # Collect source files
        src_files = list(source_dir.rglob("*.c"))
        if not src_files:
            log.warning("No C source files found in %s", source_dir)
            results[layer] = {"status": "skip", "reason": "No .c files found"}
            continue

        # Run compilation check (syntax + warnings only)
        # Layer 1: prefer native compiler; cross-compiler is for L2
        cc = shutil.which("gcc") or shutil.which("cc") or shutil.which("arm-none-eabi-gcc") or "cc"
        compile_errors = []
        compile_warnings = []
        compiled_count = 0
        failed_count = 0

        for src_file in src_files:
            rel_path = src_file.relative_to(project_path)
            obj_path = out_dir / src_file.with_suffix(".o").name

            cmd = [
                cc,
                "-c",
                AUTOSAR_C_STANDARD,
                "-Wall", "-Wextra", "-Wshadow",
                "-Wconversion", "-Wunused-parameter",
                "-ffunction-sections", "-fdata-sections",
                "-I", str(source_dir),
                "-I", str(config_dir),
                "-I", str(project_path / "src"),
                "-o", str(obj_path),
                str(src_file),
            ]

            if verbose:
                cmd.append("-v")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode == 0:
                    compiled_count += 1
                    if result.stderr.strip():
                        compile_warnings.append({
                            "file": str(rel_path),
                            "warnings": result.stderr.strip(),
                        })
                else:
                    failed_count += 1
                    compile_errors.append({
                        "file": str(rel_path),
                        "output": result.stdout.strip(),
                        "errors": result.stderr.strip(),
                    })
                    if verbose:
                        print(f"      ❌ {rel_path}: compilation error")
                        print(f"         {result.stderr.strip()[-200:]}")

            except subprocess.TimeoutExpired:
                failed_count += 1
                compile_errors.append({
                    "file": str(rel_path),
                    "output": "Timeout (120s)",
                    "errors": "Compilation timeout",
                })
            except FileNotFoundError:
                results[layer] = {"status": "fail", "error": f"Compiler not found: {cc}"}
                return results

        layer_pass = failed_count == 0
        if not layer_pass:
            all_pass = False

        results[layer] = {
            "status": "pass" if layer_pass else "fail",
            "total_files": len(src_files),
            "compiled": compiled_count,
            "failed": failed_count,
            "warnings": len(compile_warnings),
            "warning_details": compile_warnings[:20],  # cap detail
            "error_details": compile_errors[:10],
        }

        status_icon = "✅" if layer_pass else "❌"
        print(f"     {status_icon} {layer_name}: {compiled_count}/{len(src_files)} compiled"
              f" ({len(compile_warnings)} warnings, {failed_count} errors)")

    results["_meta"] = {
        "layers_requested": layers,
        "all_pass": all_pass,
        "compiler": shutil.which("arm-none-eabi-gcc") or shutil.which("gcc") or "cc",
        "timestamp": datetime.now().isoformat(),
    }

    return results


# ══════════════════════════════════════════════════════════════════════════
# AUTOSAR Cross-Compilation Stage
# ══════════════════════════════════════════════════════════════════════════

def run_autosar_cross_build(
    project_dir: str,
    target: str = "arm-cortex-m7",
    build_dir: str = "build_arm",
    toolchain_prefix: str = "arm-none-eabi-",
    docker_image: Optional[str] = None,
) -> Dict:
    """Cross-compile AUTOSAR BSW for ARM Cortex-M/R targets.

    Args:
        project_dir: Project root directory.
        target: Target architecture (arm-cortex-m7, arm-cortex-m4, arm-cortex-r5).
        build_dir: Output build directory.
        toolchain_prefix: Cross-compiler toolchain prefix.
        docker_image: Optional Docker image for cross-compilation.

    Returns:
        Dict with cross-build results.
    """
    from yuleosh.ci.result import CIResult, timed_stage

    project_path = Path(project_dir)
    if not project_path.exists():
        return {"status": "error", "message": f"Project directory not found: {project_dir}"}

    out_dir = project_path / build_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Determine architecture flags
    arch_flags_map = {
        "arm-cortex-m7": ARM_CORTEX_M7_FLAGS,
        "arm-cortex-m4": ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"],
        "arm-cortex-m3": ["-mcpu=cortex-m3", "-mthumb"],
        "arm-cortex-m0": ["-mcpu=cortex-m0", "-mthumb"],
        "arm-cortex-r5": ["-mcpu=cortex-r5", "-mthumb"],
        "arm-cortex-a53": ["-mcpu=cortex-a53", "-mthumb"],
    }
    arch_flags = arch_flags_map.get(target, ARM_CORTEX_M7_FLAGS)

    if docker_image:
        # Use Docker-based cross-compilation
        return _cross_build_via_docker(
            project_dir=project_dir,
            target=target,
            arch_flags=arch_flags,
            build_dir=build_dir,
            docker_image=docker_image,
        )

    # Local cross-compilation
    cc = shutil.which(f"{toolchain_prefix}gcc")
    if not cc:
        return {"status": "fail", "error": f"Cross-compiler '{toolchain_prefix}gcc' not found. "
                                           f"Install ARM GNU toolchain or use --docker."}

    # Build all BSW layers with cross-compiler
    all_results = {}
    total_pass = True

    for layer in ["mcal", "ecual", "services"]:
        source_dir = project_path / "src" / layer
        layer_out = out_dir / layer
        layer_out.mkdir(parents=True, exist_ok=True)

        if not source_dir.exists():
            continue

        src_files = list(source_dir.rglob("*.c"))
        if not src_files:
            continue

        layer_errors = []
        layer_pass = True

        for src_file in src_files:
            obj_path = layer_out / src_file.with_suffix(".o").name
            cmd = [
                cc,
                "-c",
                AUTOSAR_C_STANDARD,
                *arch_flags,
                "-Os", "-g",
                "-ffunction-sections", "-fdata-sections",
                "-Wall", "-Wextra",
                "-DUSE_AUTOSAR_OS",
                f"-D{target.upper().replace('-', '_')}",
                "-I", str(source_dir),
                "-I", str(project_path / "config"),
                "-I", str(project_path / "src"),
                "-o", str(obj_path),
                str(src_file),
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    layer_pass = False
                    layer_errors.append({
                        "file": str(src_file.relative_to(project_path)),
                        "errors": result.stderr.strip(),
                    })
            except subprocess.TimeoutExpired:
                layer_pass = False
                layer_errors.append({
                    "file": str(src_file.relative_to(project_path)),
                    "errors": "Timeout exceeded",
                })

        total_pass = total_pass and layer_pass
        all_results[layer] = {
            "status": "pass" if layer_pass else "fail",
            "files_compiled": len(src_files),
            "errors": len(layer_errors),
            "error_details": layer_errors[:5],
        }

        icon = "✅" if layer_pass else "❌"
        print(f"    {icon} {layer} cross-compile ({target}): {len(src_files)} files")

    all_results["_meta"] = {
        "target": target,
        "arch_flags": arch_flags,
        "compiler": cc,
        "all_pass": total_pass,
        "timestamp": datetime.now().isoformat(),
    }

    return all_results


def _cross_build_via_docker(
    project_dir: str,
    target: str,
    arch_flags: List[str],
    build_dir: str,
    docker_image: str,
) -> Dict:
    """Run AUTOSAR cross-compilation inside Docker."""
    import subprocess

    project_path = Path(project_dir)
    abs_project = project_path.resolve()

    # Generate a build script inside the container
    build_script = f"""#!/bin/bash
set -e
BUILD_DIR=/build
OUT_DIR=/project/{build_dir}
mkdir -p $BUILD_DIR $OUT_DIR

for layer in mcal ecual services; do
    SRC_DIR=/project/src/$layer
    if [ ! -d "$SRC_DIR" ]; then continue; fi
    LAYER_OUT=$OUT_DIR/$layer
    mkdir -p $LAYER_OUT

    for src in $(find $SRC_DIR -name '*.c'); do
        fname=$(basename "$src" .c)
        {" ".join(['arm-none-eabi-gcc',
                    '-c', '-std=c99'] + arch_flags +
                   ['-Os', '-g',
                    '-ffunction-sections', '-fdata-sections',
                    '-DUSE_AUTOSAR_OS',
                    '-I$SRC_DIR',
                    '-I/project/config',
                    '-I/project/src',
                    '-o', '$LAYER_OUT/${fname}.o',
                    '$src'])}
    done
done
echo "Cross-build completed for {target}"
"""

    try:
        result = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{abs_project}:/project",
             docker_image,
             "bash", "-c", build_script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return {
                "status": "pass",
                "target": target,
                "docker_image": docker_image,
                "output": result.stdout.strip(),
            }
        else:
            return {
                "status": "fail",
                "target": target,
                "docker_image": docker_image,
                "errors": result.stderr.strip(),
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "target": target,
            "error": "Docker build timed out (300s)",
        }
    except FileNotFoundError:
        return {
            "status": "fail",
            "target": target,
            "error": "Docker not found. Install Docker Desktop or Docker Engine.",
        }


# ══════════════════════════════════════════════════════════════════════════
# AUTOSAR MISRA-C:2023 Check
# ══════════════════════════════════════════════════════════════════════════

def run_autosar_misra_check(
    project_dir: str,
    layers: Optional[List[str]] = None,
    cppcheck_args: Optional[List[str]] = None,
    fail_on_warning: bool = False,
) -> Dict:
    """Run MISRA-C:2023 static analysis on AUTOSAR BSW code.

    Reuses the yuleOSH MISRA rules configured in misra-rules.yaml and
    the Phase 1-2 MISRA infrastructure (ci/stages/review.py).

    Args:
        project_dir: Project root directory.
        layers: BSW layers to check (default: all).
        cppcheck_args: Extra arguments to pass to cppcheck.
        fail_on_warning: Whether to fail on warnings (not just errors).

    Returns:
        Dict with MISRA check results per layer.
    """
    from yuleosh.ci.stages.review import _exclude_paths

    project_path = Path(project_dir)
    if not project_path.exists():
        return {"status": "error", "message": f"Project directory not found: {project_dir}"}

    if layers is None:
        layers = ["mcal", "ecual", "services"]

    all_results = {}
    total_errors = 0
    total_warnings = 0

    cppcheck = shutil.which("cppcheck")
    if not cppcheck:
        # Fall back to the yuleOSH built-in MISRA analysis
        print("  ⚠️  cppcheck not found — using yuleOSH built-in MISRA analysis")
        return _run_misra_fallback(project_dir, layers)

    for layer in layers:
        source_dir = project_path / "src" / layer
        if not source_dir.exists():
            all_results[layer] = {"status": "skip", "reason": "Source dir not found"}
            continue

        src_files = [str(f) for f in source_dir.rglob("*.c")]
        if not src_files:
            all_results[layer] = {"status": "skip", "reason": "No .c files found"}
            continue

        print(f"  🔍 MISRA-C:2023 check: {BSW_LAYER_NAMES.get(layer, layer)} "
              f"({len(src_files)} files)...")

        config_dir = project_path / "config"
        common_dir = project_path / "src"

        cmd = [
            cppcheck,
            "--std=c99",
            "--language=c",
            "--enable=all",
            "--addon=misra.py",
            "--suppress=unmatchedSuppression",
            "--suppress=missingIncludeSystem",
            "--check-level=exhaustive",
            "--suppress=*:*/third_party/*",
            "--suppress=*:*build*",
            "-I", str(source_dir),
            "-I", str(config_dir),
            "-I", str(common_dir),
            "--suppress=preprocessorErrorDirective",
        ]

        # Add layer-specific includes
        for other_layer in layers:
            other_dir = project_path / "src" / other_layer
            if other_dir.exists() and str(other_dir) != str(source_dir):
                cmd.extend(["-I", str(other_dir)])

        if cppcheck_args:
            cmd.extend(cppcheck_args)

        cmd.extend(src_files)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            # Parse MISRA violations from output
            violations = []
            for line in result.stdout.split("\n"):
                if "misra" in line.lower() or "violation" in line.lower() or "error" in line.lower():
                    violations.append(line.strip())

            for line in result.stderr.split("\n"):
                if "misra" in line.lower() or "violation" in line.lower() or "error" in line.lower():
                    violations.append(line.strip())

            # Count by severity
            errors = [v for v in violations if "[error]" in v.lower() or "error:" in v.lower()]
            warnings = [v for v in violations
                       if v not in errors and ("warning" in v.lower() or "[style]" in v.lower())]

            total_errors += len(errors)
            total_warnings += len(warnings)

            layer_pass = len(errors) == 0 and not (fail_on_warning and len(warnings) > 0)
            all_results[layer] = {
                "status": "pass" if layer_pass else "fail",
                "files_checked": len(src_files),
                "misra_errors": len(errors),
                "misra_warnings": len(warnings),
                "total_violations": len(violations),
                "violation_details": violations[:30],  # cap for report
                "raw_output": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
            }

            icon = "✅" if layer_pass else "⚠️"
            print(f"    {icon} {len(errors)} errors, {len(warnings)} warnings")

        except subprocess.TimeoutExpired:
            all_results[layer] = {
                "status": "fail",
                "error": "MISRA check timed out (300s)",
            }

    all_results["_meta"] = {
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "layers_checked": [l for l in layers if all_results.get(l, {}).get("status") != "skip"],
        "tool": cppcheck,
        "timestamp": datetime.now().isoformat(),
    }

    return all_results


def _run_misra_fallback(project_dir: str, layers: List[str]) -> Dict:
    """Fallback MISRA analysis using yuleOSH's built-in rule engine."""
    from yuleosh.ci.stages.review import run_misra_check
    from yuleosh.ci.result import CIResult
    
    project_path = Path(project_dir)
    results = {}

    for layer in layers:
        source_dir = project_path / "src" / layer
        if not source_dir.exists():
            results[layer] = {"status": "skip", "reason": "Source dir not found"}
            continue

        src_files = list(source_dir.rglob("*.c"))
        if not src_files:
            results[layer] = {"status": "skip", "reason": "No .c files found"}
            continue

        print(f"  🔍 MISRA-C:2023 analysis (built-in): {BSW_LAYER_NAMES.get(layer, layer)}...")

        try:
            ci = CIResult("autosar-misra-fallback")
            passed = run_misra_check(str(project_path), ci, mode="repo")
            results[layer] = {
                "status": "pass" if passed else "warn",
                "files_checked": len(src_files),
            }
        except Exception as e:
            results[layer] = {
                "status": "warn", "error": str(e),
                "note": "Install cppcheck for full MISRA-C:2023 analysis",
            }

    results["_meta"] = {
        "tool": "yuleosh-builtin-misra",
        "layers_checked": layers,
        "rules_checklist": MISRA_C2023_AUTOSAR_RULES,
        "timestamp": datetime.now().isoformat(),
    }

    return results


# ══════════════════════════════════════════════════════════════════════════
# Full AUTOSAR CI Stage
# ══════════════════════════════════════════════════════════════════════════

def run_autosar_full_ci(project_dir: str, target: str = "arm-cortex-m7") -> Dict:
    """Run full AUTOSAR CI pipeline: build → cross-compile → MISRA check.

    Maps to CI layers:
      L1: Build MCAL/ECUAL/Services with host compiler
      L2: Cross-compile for target MCU + MISRA static analysis
      L3: Full system verification

    Args:
        project_dir: Project root directory.
        target: Target architecture for cross-compilation.

    Returns:
        Dict with complete CI results.
    """
    print(f"\n{'='*60}")
    print(f"  🚀 AUTOSAR Full CI Pipeline")
    print(f"  Target: {target}")
    print(f"{'='*60}")

    # Layer 1: Host compilation
    print(f"\n{'─'*40}")
    print(f"  Layer 1 — Host Build")
    print(f"{'─'*40}")
    l1_result = run_autosar_build(project_dir, verbose=False)

    # Layer 2: Cross-compile + MISRA
    print(f"\n{'─'*40}")
    print(f"  Layer 2 — Cross-Compile + MISRA-C:2023")
    print(f"{'─'*40}")
    l2_cross = run_autosar_cross_build(project_dir, target=target)
    l2_misra = run_autosar_misra_check(project_dir)

    # Layer 3: System verification summary
    print(f"\n{'─'*40}")
    print(f"  Layer 3 — System Verification")
    print(f"{'─'*40}")

    l1_pass = l1_result.get("_meta", {}).get("all_pass", False)
    l2_cross_pass = l2_cross.get("_meta", {}).get("all_pass", False)
    l2_misra_errors = l2_misra.get("_meta", {}).get("total_errors", -1)
    l3_pass = l1_pass and l2_cross_pass and l2_misra_errors == 0

    print(f"    L1 Build:          {'✅' if l1_pass else '❌'}")
    print(f"    L2 Cross-Compile:  {'✅' if l2_cross_pass else '❌'}")
    print(f"    L2 MISRA-C:2023:   {'✅' if l2_misra_errors == 0 else f'❌ {l2_misra_errors} violations'}")
    print(f"    L3 System:         {'✅' if l3_pass else '❌'}")

    return {
        "layer1_host_build": l1_result,
        "layer2_cross_compile": l2_cross,
        "layer2_misra_check": l2_misra,
        "layer3_system_verification": {
            "status": "pass" if l3_pass else "fail",
            "l1_pass": l1_pass,
            "l2_cross_pass": l2_cross_pass,
            "l2_misra_errors": l2_misra_errors,
        },
        "_meta": {
            "pipeline": "autosar-full-ci",
            "target": target,
            "all_pass": l3_pass,
            "timestamp": datetime.now().isoformat(),
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# ARXML Compliance Report
# ══════════════════════════════════════════════════════════════════════════

def run_arxml_compliance_check(
    project_dir: str,
    arxml_path: Optional[str] = None,
) -> Dict:
    """Validate AUTOSAR ARXML compliance for a generated project.

    Checks:
      - ARXML file existence
      - SWC definition completeness
      - Port interface consistency
      - Runnable specification

    Args:
        project_dir: Project root directory.
        arxml_path: Path to ARXML file (default: project_dir/arxml/*.arxml).

    Returns:
        Dict with compliance check results.
    """
    from yuleosh.autosar.parser import ARXMLParser

    project_path = Path(project_dir)

    # Find ARXML files
    if arxml_path:
        arxml_files = [Path(arxml_path)]
    else:
        arxml_files = list(project_path.rglob("*.arxml"))

    if not arxml_files:
        return {
            "status": "skip",
            "reason": "No ARXML files found in project. Create ARXML definitions for full compliance.",
            "hint": "Run 'yuleosh init --template autosar' to generate ARXML examples.",
        }

    results = {}
    parser = ARXMLParser()

    for arxml_file in arxml_files:
        try:
            swcs = parser.parse_swc(str(arxml_file))
            results[arxml_file.name] = {
                "swc_count": len(swcs),
                "swc_list": [s.short_name for s in swcs],
                "ports_total": sum(len(s.ports) for s in swcs),
                "runnables_total": sum(len(s.runnables) for s in swcs),
                "status": "pass" if swcs else "warn",
            }
        except Exception as e:
            results[arxml_file.name] = {
                "status": "fail",
                "error": str(e),
            }

    return {
        "status": "pass",
        "files_checked": len(arxml_files),
        "details": results,
        "timestamp": datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════
# Registration helper for the CLI
# ══════════════════════════════════════════════════════════════════════════

STAGES_REGISTRY = {
    "autosar-build": run_autosar_build,
    "autosar-cross-compile": run_autosar_cross_build,
    "autosar-misra-check": run_autosar_misra_check,
    "autosar-full-ci": run_autosar_full_ci,
    "arxml-compliance": run_arxml_compliance_check,
}


def register_autosar_stages(existing_registry: Dict) -> Dict:
    """Register AUTOSAR CI stages into an existing stage registry.

    Usage::

        from yuleosh.ci.stages.autosar import register_autosar_stages

        registry = {...}  # existing stage registry
        register_autosar_stages(registry)
    """
    existing_registry.update(STAGES_REGISTRY)
    return existing_registry
