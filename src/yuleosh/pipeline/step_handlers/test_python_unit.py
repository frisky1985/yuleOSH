#!/usr/bin/env python3

# @req SWR-001.2
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step SWE.4+: 小克 — Python 单元测试 (pytest / unittest).

在 SWE.4 自测之后、接口测试之前执行。
对项目中的 Python 代码运行 pytest（首选）或 unittest discover 测试。

ASPICE 对齐: SWE.4 单元验证 — 要求在实现语言层面执行单元测试。

设计目标 (H2-3):
- pytest 首选：collect-only 探测用例数，然后 --tb=short 执行
- unittest fallback：python -m unittest discover
- JUnit XML 输出：写入 .yuleosh/reports/python-junit.xml
- 输出报告格式与 test_c_unit 一致（step/status/passed/failed/runner/output）
- 无 Python 测试文件 → 跳过（non-fatal，不阻断 pipeline）
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.test_python_unit")

__all__ = ["step_python_unit_test", "run_python_test_suite"]


def _record_step_verdict(session, verdict: str, artifact_paths: list) -> None:
    """Write step.verdict audit event non-fatally (Q1)."""
    try:
        import hashlib as _hl
        import os as _os
        from yuleosh.audit.model import AuditLog

        def _sha256(p: str) -> str:
            h = _hl.sha256()
            try:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
            except OSError:
                return ""
            return h.hexdigest()

        artifact_hashes = {
            _os.path.basename(p): _sha256(p)
            for p in artifact_paths if p
        }
        audit_root = _os.environ.get("YULEOSH_AUDIT_ROOT")
        audit_log = AuditLog(data_root=audit_root)
        session_id = getattr(session, "name", "") or getattr(session, "session_id", "")
        audit_log.record(
            actor="system",
            action="step.verdict",
            target="step:python-unit-test",
            tenant="",
            detail={
                "step": "python-unit-test",
                "session_id": session_id,
                "verdict": verdict,
                "artifact_hashes": artifact_hashes,
            },
        )
    except Exception as _e:
        log.warning("_record_step_verdict failed (non-fatal): %s", _e)

# Directories never scanned for Python tests
_EXCLUDED_DIRS = {
    ".git", ".osh", ".yuleosh", ".pytest_cache", "__pycache__",
    "artifacts", "build", "node_modules", "third_party", "vendor",
    "external", "dist", ".venv", "venv", "env",
}

# JUnit XML output path (relative to project_dir)
_JUNIT_REL = ".yuleosh/reports/python-junit.xml"


# ── Core runner (reusable, no session dependency) ─────────────────────────────

def _find_python_test_files(project_dir: Path) -> list[Path]:
    """Return all test_*.py / *_test.py files, excluding non-source dirs."""
    found = []
    for p in project_dir.rglob("*.py"):
        try:
            rel = p.relative_to(project_dir)
        except ValueError:
            continue
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        if p.stem.startswith("test_") or p.stem.endswith("_test"):
            found.append(p)
    return found


def _parse_pytest_counts(output: str) -> tuple[int, int]:
    """Extract passed/failed from pytest short summary line."""
    m = re.search(r"(\d+) passed", output)
    passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", output)
    failed = int(m.group(1)) if m else 0
    return passed, failed


def _parse_unittest_counts(output: str) -> tuple[int, int]:
    """Extract passed/failed from unittest output."""
    m = re.search(r"Ran (\d+) test", output)
    total = int(m.group(1)) if m else 0
    failed_m = re.search(r"FAILED.*?failures=(\d+)", output)
    error_m = re.search(r"FAILED.*?errors=(\d+)", output)
    failed = int(failed_m.group(1)) if failed_m else 0
    failed += int(error_m.group(1)) if error_m else 0
    passed = max(0, total - failed)
    return passed, failed


def run_python_test_suite(
    project_dir: str | Path,
    timeout: int = 300,
    python_executable: str | None = None,
) -> dict:
    """Discover and run Python unit tests. Returns a result dict.

    Runner priority:
      1. pytest (if importable in the project's Python env)
      2. unittest discover (fallback)

    Result dict keys: runner / returncode / passed / failed / output /
    status / py_test_files / junit_xml_path.
    """
    project_dir = Path(project_dir).resolve()
    python = python_executable or sys.executable

    test_files = _find_python_test_files(project_dir)
    if not test_files:
        return {
            "runner": "none",
            "returncode": None,
            "passed": 0,
            "failed": 0,
            "output": "",
            "status": "skipped",
            "reason": "No Python test files found",
            "py_test_files": 0,
            "junit_xml_path": "",
        }

    junit_path = project_dir / _JUNIT_REL
    junit_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Try pytest ────────────────────────────────────────────────────────
    try:
        probe = subprocess.run(
            [python, "-m", "pytest", "--version"],
            capture_output=True, text=True, timeout=10, cwd=str(project_dir),
        )
        has_pytest = probe.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        has_pytest = False

    if has_pytest:
        try:
            result = subprocess.run(
                [
                    python, "-m", "pytest",
                    "--tb=short", "-q",
                    f"--junitxml={junit_path}",
                ],
                capture_output=True, text=True,
                timeout=timeout,
                cwd=str(project_dir),
            )
            output = (result.stdout or "") + (result.stderr or "")
            passed, failed = _parse_pytest_counts(output)
            status = "passed" if result.returncode == 0 else "failed"
            log.info(
                "pytest: rc=%d passed=%d failed=%d",
                result.returncode, passed, failed,
            )
            return {
                "runner": "pytest",
                "returncode": result.returncode,
                "passed": passed,
                "failed": failed,
                "output": output[:8000],
                "status": status,
                "py_test_files": len(test_files),
                "junit_xml_path": str(junit_path) if junit_path.exists() else "",
            }
        except subprocess.TimeoutExpired:
            log.warning("pytest timed out after %ds", timeout)
            return {
                "runner": "pytest-timeout",
                "returncode": -1,
                "passed": 0,
                "failed": 0,
                "output": f"pytest timed out after {timeout}s",
                "status": "failed",
                "py_test_files": len(test_files),
                "junit_xml_path": "",
            }

    # ── Fallback: unittest discover ───────────────────────────────────────
    try:
        result = subprocess.run(
            [python, "-m", "unittest", "discover", "-v"],
            capture_output=True, text=True,
            timeout=timeout,
            cwd=str(project_dir),
        )
        output = (result.stdout or "") + (result.stderr or "")
        passed, failed = _parse_unittest_counts(output)
        status = "passed" if result.returncode == 0 else "failed"
        log.info(
            "unittest: rc=%d passed=%d failed=%d",
            result.returncode, passed, failed,
        )
        return {
            "runner": "unittest",
            "returncode": result.returncode,
            "passed": passed,
            "failed": failed,
            "output": output[:8000],
            "status": status,
            "py_test_files": len(test_files),
            "junit_xml_path": "",
        }
    except subprocess.TimeoutExpired:
        return {
            "runner": "unittest-timeout",
            "returncode": -1,
            "passed": 0,
            "failed": 0,
            "output": f"unittest discover timed out after {timeout}s",
            "status": "failed",
            "py_test_files": len(test_files),
            "junit_xml_path": "",
        }


# ── Pipeline step ─────────────────────────────────────────────────────────────

@timed_step
def step_python_unit_test(session: PipelineSession) -> str:
    """Step: 小克 — Python 单元测试 (pytest / unittest).

    Discovers and runs Python-level unit tests. No Python test files →
    skipped (non-fatal). Any test failure sets status=failed and raises
    PipelineStepError so the gate can triage it.
    """
    try:
        print("  🐍 [小克] Python 单元测试开始...")
        log.info("Running Python unit test step")

        project_dir = Path(
            getattr(session, "project_dir", None)
            or os.environ.get("OSH_HOME", ".")
        ).resolve()

        # ── Mock mode ─────────────────────────────────────────────────────
        if getattr(session, "mock_mode", None) is True:
            report = {
                "step": "python-unit-test",
                "agent": "小克",
                "session": session.name,
                "timestamp": datetime.now().isoformat(),
                "status": "skipped",
                "reason": "mock mode — no real code to test",
                "py_test_files": 0,
                "test_runner": "none",
            }
            out_path = Path(session.session_dir) / "python-unit-test.json"
            out_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print("  ⏭️  [小克] 跳过 Python 单元测试 — mock 模式")
            return str(out_path)

        result = run_python_test_suite(project_dir)

        runner = result["runner"]
        passed = result["passed"]
        failed = result["failed"]
        status = result["status"]
        output = result["output"]

        # Build report (same shape as test_c_unit report)
        report = {
            "step": "python-unit-test",
            "agent": "小克",
            "session": session.name,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "test_runner": runner,
            "passed": passed,
            "failed": failed,
            "py_test_files": result["py_test_files"],
            "junit_xml_path": result.get("junit_xml_path", ""),
            "output_summary": output[:2000] if output else "",
        }
        if result.get("reason"):
            report["reason"] = result["reason"]

        out_path = Path(session.session_dir) / "python-unit-test.json"
        try:
            out_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            raise PipelineStepError(f"Cannot write Python unit test report: {e}")

        session.artifacts["python-unit-test"] = str(out_path)

        if runner == "none":
            print("  ⏭️  [小克] 跳过 Python 单元测试 — 无测试文件")
            log.info("Python unit test skipped: no test files")
            return str(out_path)

        icon = "✅" if status == "passed" else "❌"
        print(
            f"  {icon} [小克] Python 单元测试完成 — "
            f"runner={runner} passed={passed} failed={failed}"
        )

        if status == "failed":
            _record_step_verdict(session, "failed", [str(out_path), result.get("junit_xml_path", "")])
            raise PipelineStepError(
                f"Python unit tests failed: {failed} failure(s) "
                f"(runner={runner}, passed={passed})"
            )

        _record_step_verdict(session, status, [str(out_path), result.get("junit_xml_path", "")])
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        raise PipelineStepError(f"python_unit_test step failed: {e}") from e
