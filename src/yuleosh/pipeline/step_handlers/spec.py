#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Spec/validation step handler.

Exports:
  step_spec_check — OpenSpec compliance check via CLI validator
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import yuleosh

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.spec_contracts import contracts_check

log = logging.getLogger("pipeline.step_handlers.spec")

__all__ = ["step_spec_check"]


def _spec_validator_env() -> dict:
    """Build env so the spec-validator subprocess can import yuleosh.

    yuleosh_cli.py may be invoked by absolute path from an arbitrary cwd;
    the child process inherits PYTHONPATH and would fail with
    ``No module named 'yuleosh'`` unless the package src dir is injected.
    """
    env = os.environ.copy()
    pkg_root = str(Path(yuleosh.__file__).resolve().parent.parent)
    current = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = os.pathsep.join(
        [pkg_root] + ([current] if current else [])
    )
    return env


def step_spec_check(session: PipelineSession) -> str:
    """Step 0: 小明 — OpenSpec 合规检查"""
    try:
        print("  🔍 [小明] Validating OpenSpec...")
        log.info(f"Validating spec: {session.spec_path}")
        result = subprocess.run(
            [sys.executable, "-m", "yuleosh.spec.validate", session.spec_path, "--json"],
            capture_output=True, text=True, timeout=60,
            env=_spec_validator_env(),
        )
        out_path = session.session_dir / "spec-check.json"
        with open(out_path, "w") as f:
            f.write(result.stdout if result.stdout else result.stderr)

        if result.returncode != 0:
            err_msg = result.stderr or result.stdout or "Unknown error"
            log.error(f"Spec validation failed (exit {result.returncode}): {err_msg[:200]}")
            raise PipelineStepError(f"Spec validation failed:\n{err_msg}")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            log.error(f"Spec check output is not valid JSON: {e}")
            raw_preview = result.stdout[:500] if result.stdout else "(empty output)"
            raise PipelineStepError(
                f"Spec check output is not valid JSON: {e}\n"
                f"Raw output (first 500 chars):\n{raw_preview}"
            )

        if data.get("error_count", 0) > 0:
            issues = [i["message"] for i in data.get("issues", []) if i["severity"] == "ERROR"]
            for iss in issues:
                log.error(f"Spec error: {iss}")
            raise PipelineStepError(f"Spec has {data['error_count']} error(s): {'; '.join(issues)}")

        print(f"  ✅ [小明] Spec validated: {data['coverage']['score']}% coverage")
        log.info(f"Spec validated: {data['coverage']['score']}% coverage")

        # ── 契约完整性机器校验 (方案 A, 2026-08-16) ──────────────────
        # 长 spec 固定截断会让下游 LLM 看不到尾部契约 (codegen/claude-review
        # 连续 3 轮 RED 根因)。这里是确定性检查: 抽取 spec 中的接口契约/
        # 行为护栏/参数边界/NVM 布局为 contracts.json, 完整性不满足直接 RED,
        # 防回归从 LLM 人审迁移到机器检查。
        try:
            check = contracts_check(session.spec_path)
        except Exception as e:  # pragma: no cover - defensive
            log.error(f"Contract extraction failed: {e}")
            check = {"validation": {"passed": False, "missing": [f"contract extraction error: {e}"], "details": {}}}

        contracts_path = session.session_dir / "contracts.json"
        try:
            contracts_path.write_text(
                json.dumps(check, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:  # pragma: no cover - defensive
            log.warning(f"contracts.json write failed (non-fatal): {e}")

        v = check["validation"]
        if not v["passed"]:
            missing = "; ".join(v["missing"])
            log.error(f"Contract integrity check FAILED: {missing}")
            raise PipelineStepError(
                f"Contract integrity check FAILED — spec 契约抽取不完整, "
                f"下游 LLM (codegen/评审) 将看不到关键契约: {missing}"
            )
        iface = v["details"].get("interfaces", {})
        gr = v["details"].get("guardrails", {})
        pm = v["details"].get("params", {})
        print(
            f"  🛡️ [小明] Contract integrity: {len(iface.get('headers', []))} headers / "
            f"{len(gr.get('ids', []))} guardrails / {len(pm.get('names', []))} params PASS"
        )

        return str(out_path)
    except subprocess.TimeoutExpired:
        log.error("Spec validation timed out")
        raise PipelineStepError("Spec validation timed out")
    except subprocess.CalledProcessError as e:
        log.error(f"Spec validation subprocess failed: {e}")
        raise PipelineStepError(f"Spec validation subprocess failed: {e}")
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Spec validation unexpected error: {e}")
        raise PipelineStepError(f"Spec validation unexpected error: {e}")
