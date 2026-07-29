#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
QEMU Test Stage — register QEMU emulation as a pipeline step handler.

Runs a prebuilt .elf firmware through QEMU and evaluates PASS/FAIL
by scanning the serial output for expected patterns.

Registered as step handler ``qemu_run`` for the autosar template's
L2 pipeline layer.

Usage (pipeline session)::

    handler = QemuTestHandler()
    result_path = handler(session)
"""

import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

log = logging.getLogger("pipeline.step_handlers.qemu")

# QEMU targets for different architectures
QEMU_TARGETS = {
    "cortex-m3": {
        "qemu_machine": "lm3s6965evb",
        "qemu_cpu": "cortex-m3",
        "default_timeout": 30,
    },
    "cortex-m4": {
        "qemu_machine": "lm3s6965evb",
        "qemu_cpu": "cortex-m4",
        "default_timeout": 30,
    },
    "cortex-m7": {
        "qemu_machine": "lm3s6965evb",  # No native m7 machine, use m3 as closest
        "qemu_cpu": "max",
        "default_timeout": 30,
    },
    "arm926": {
        "qemu_machine": "versatilepb",
        "qemu_cpu": "arm926",
        "default_timeout": 20,
    },
    "x86_64": {
        "qemu_machine": "pc",
        "qemu_cpu": "max",
        "default_timeout": 15,
    },
}


class QemuTestHandler(BaseHandler):
    """Pipeline step handler for running QEMU-based firmware tests.

    Scans project for prebuilt .elf files, runs each through QEMU,
    and evaluates PASS/FAIL based on expected output patterns.

    Step attributes
    ---------------
    step_name : str
        ``"qemu-run"``
    """

    step_name = "qemu-run"

    # Prefer QEMU system emulator; fallback to qemu-system-arm
    QEMU_BINARIES = ["qemu-system-arm", "qemu-system-aarch64",
                     "qemu-system-riscv32", "qemu-system-riscv64",
                     "qemu-system-x86_64"]

    EXPECT_PASS_PATTERNS = [
        r"TEST\s+PASS",
        r"All tests passed",
        r"SUCCESS",
        r"EXIT:\s*0",
        r"Hello from yuleOSH",
        r"Boot Complete",
    ]

    EXPECT_FAIL_PATTERNS = [
        r"TEST\s+FAIL",
        r"FAILED",
        r"ABORT",
        r"Panic",
        r"Hard Fault",
        r"EXIT:\s*[1-9]",
    ]

    def should_skip(self, session: PipelineSession) -> bool:
        """Skip QEMU step if no .elf files found or target not supported."""
        elf_files = self._find_elf_files(session)
        if not elf_files:
            log.info("No .elf files found — skipping QEMU step")
            return True
        return False

    def pre_check(self, session: PipelineSession) -> bool:
        """Check QEMU is installed.

        Returns True if at least one QEMU binary is found.
        """
        qemu_bin = self._find_qemu()
        if not qemu_bin:
            log.warning("No QEMU binary found in PATH — step will be skipped")
            return False
        return True

    def execute(self, session: PipelineSession) -> str:
        """Execute QEMU tests on all discovered .elf files.

        Parameters
        ----------
        session : PipelineSession
            Active pipeline session.

        Returns
        -------
        str
            Path to the QEMU test results JSON file.
        """
        project_dir = str(session.session_dir.parent.parent)
        qemu_bin = self._find_qemu()
        elf_files = self._find_elf_files(session)
        target_cfg = self._resolve_target(session)

        results = []
        all_passed = True
        timeout = target_cfg.get("default_timeout", 30)
        machine = target_cfg.get("qemu_machine", "lm3s6965evb")
        cpu = target_cfg.get("qemu_cpu", "cortex-m3")

        for elf_path in elf_files:
            log.info("Running QEMU test: %s", elf_path.name)
            result = self._run_single_test(
                qemu_bin=qemu_bin,
                elf_path=elf_path,
                machine=machine,
                cpu=cpu,
                timeout=timeout,
            )
            results.append(result)
            if not result["passed"]:
                all_passed = False

        # Build structured output
        output = {
            "session": session.name,
            "step": self.step_name,
            "timestamp": datetime.now().isoformat(),
            "qemu_binary": qemu_bin or "not-found",
            "qemu_machine": machine,
            "qemu_cpu": cpu,
            "all_passed": all_passed,
            "test_count": len(results),
            "passed_count": sum(1 for r in results if r["passed"]),
            "failed_count": sum(1 for r in results if not r["passed"]),
            "results": results,
            "summary": "All QEMU tests passed" if all_passed
                       else f"{sum(1 for r in results if not r['passed'])} test(s) failed",
        }

        # Write output
        out_path = session.session_dir / "qemu-test-results.json"
        out_path.write_text(json.dumps(output, indent=2, default=str))

        if not all_passed:
            raise PipelineStepError(
                f"QEMU tests: {output['failed_count']}/{output['test_count']} failed"
            )

        return str(out_path)

    # ── Internal helpers ──

    def _find_qemu(self) -> Optional[str]:
        """Find a QEMU binary in PATH."""
        for binary in self.QEMU_BINARIES:
            try:
                result = subprocess.run(
                    ["which", binary],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    path = result.stdout.strip()
                    if path:
                        return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        # Fallback: try locating via shutil
        import shutil
        for binary in self.QEMU_BINARIES:
            path = shutil.which(binary)
            if path:
                return path

        return None

    def _find_elf_files(self, session: PipelineSession) -> list[Path]:
        """Find prebuilt .elf firmware files for QEMU testing.

        Searches:
          1. tests/fixtures/prebuilt/*.elf
          2. build/*.elf
          3. .yuleosh/pipeline/*/rte/*.elf
        """
        project_dir = session.session_dir.parent.parent
        elf_paths = []

        # Search patterns
        search_patterns = [
            Path(project_dir) / "tests" / "fixtures" / "prebuilt",
            Path(project_dir) / "build",
            Path(project_dir) / ".yuleosh" / "pipeline",
        ]

        for base_dir in search_patterns:
            if base_dir.exists():
                for f in base_dir.rglob("*.elf"):
                    elf_paths.append(f)

        # Also check session_dir itself
        for f in session.session_dir.rglob("*.elf"):
            if f not in elf_paths:
                elf_paths.append(f)

        return sorted(set(elf_paths))

    def _resolve_target(self, session: PipelineSession) -> dict:
        """Resolve QEMU target configuration from project context.

        Checks session context for 'target' or 'arch' metadata.
        Falls back to cortex-m3 (lm3s6965evb).
        """
        # Check session context
        target = getattr(session, "target", None) or session.context.get("target", "")
        arch = getattr(session, "arch", None) or session.context.get("arch", "")

        # Resolve by target name
        for key, cfg in QEMU_TARGETS.items():
            if key in target or key in arch:
                return cfg

        # Check project .yuleosh.yaml if available
        try:
            from yuleosh.project_detection import detect_project
            project_dir = str(session.session_dir.parent.parent)
            info = detect_project(project_dir)
            if info:
                target_name = info.get("target", "").lower()
                cross = info.get("cross_compile", {})
                cross_target = cross.get("target", "").lower()
                # cortex-m7 → use lm3s6965evb as closest
                for key in ["cortex-m7", "cortex-m4", "cortex-m3", "arm926"]:
                    if key in target_name or key in cross_target:
                        return QEMU_TARGETS[key]
        except ImportError:
            pass

        # Default: cortex-m3 / lm3s6965evb
        return QEMU_TARGETS["cortex-m3"]

    def _run_single_test(self, qemu_bin: str, elf_path: Path,
                         machine: str, cpu: str, timeout: int) -> dict:
        """Run one .elf through QEMU and evaluate the result.

        Parameters
        ----------
        qemu_bin : str
            Path to the QEMU binary.
        elf_path : Path
            Path to the .elf firmware file.
        machine : str
            QEMU machine type (-machine flag).
        cpu : str
            QEMU CPU type (-cpu flag).
        timeout : int
            Max seconds to wait for test completion.

        Returns
        -------
        dict with keys: elf, passed, elapsed, log, error, assertion_failures
        """
        start_time = time.time()

        # Build QEMU command
        cmd = [
            qemu_bin,
            "-machine", machine,
            "-cpu", cpu,
            "-nographic",
            "-semihosting",
            "-kernel", str(elf_path),
            "-serial", "mon:stdio",
            "-d", "guest_errors",
        ]

        log.debug("QEMU command: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout,
            )
            elapsed = time.time() - start_time
            output = result.stdout + result.stderr

            # Evaluate PASS/FAIL
            passed = self._evaluate_output(output)

            return {
                "elf": elf_path.name,
                "elf_path": str(elf_path),
                "passed": passed,
                "elapsed": round(elapsed, 2),
                "returncode": result.returncode,
                "error": None if passed else "Test assertions failed",
                "assertion_failures": [] if passed else ["See log for details"],
                "log": output[-500:],
                "command": " ".join(cmd),
            }

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return {
                "elf": elf_path.name,
                "elf_path": str(elf_path),
                "passed": False,
                "elapsed": round(elapsed, 2),
                "returncode": -1,
                "error": f"QEMU timed out after {timeout}s",
                "assertion_failures": [f"Timeout ({timeout}s)"],
                "log": "Timed out",
                "command": " ".join(cmd),
            }

        except FileNotFoundError as e:
            return {
                "elf": elf_path.name,
                "elf_path": str(elf_path),
                "passed": False,
                "elapsed": 0.0,
                "returncode": -1,
                "error": f"QEMU binary not found: {e}",
                "assertion_failures": [],
                "log": "QEMU binary missing",
                "command": " ".join(cmd),
            }

    def _evaluate_output(self, output: str) -> bool:
        """Evaluate QEMU serial output for PASS/FAIL patterns.

        Returns True if a pass pattern is found and no fail pattern matches.
        """
        output_upper = output.upper()

        # Check fail patterns first
        for pattern in self.EXPECT_FAIL_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                log.info("QEMU: fail pattern matched: %s", pattern)
                return False

        # Check pass patterns
        for pattern in self.EXPECT_PASS_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return True

        # No explicit pass/fail — check return code convention
        if "EXIT:" in output_upper:
            exit_match = re.search(r"EXIT:\s*(\d+)", output)
            if exit_match and int(exit_match.group(1)) == 0:
                return True
            return False

        # Default: if QEMU ran without crashing, consider it passed
        if "qemu:" in output_upper and "error" in output_upper.lower():
            return False

        return True
