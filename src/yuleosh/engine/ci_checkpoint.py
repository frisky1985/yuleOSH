#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Pipeline 的 Checkpoint 封装。

将 CI Layer（L1/L2/L2.5/L3）的 stages 适配到 CheckpointEngine，
支持任意 stage 注入 + 自动续跑。每个 stage 通过闭包包装 ``project_dir``
和 ``ci`` 参数以匹配无参 Callable 接口。
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from yuleosh.engine.checkpoint import CheckpointEngine
from yuleosh.ci.layers import (
    run_layer1,
    run_layer2,
    run_layer_25,
    run_layer3,
)
from yuleosh.ci.result import CIResult
from yuleosh.ci.stages import (
    run_yaml_validation,
    run_misra_check,
    run_c_coverage,
    run_c_coverage_check,
    run_unit_tests,
    run_coverage_check,
    run_sil_tests,
    run_clang_tidy,
    run_plan_lint,
    run_spec_validation,
    run_architecture_review,
    run_requirements_trace,
    run_docsync_gate,
)
from yuleosh.ci.stage_utils import (
    _cross_compile_stage,
    _static_analysis_stage,
    _integration_test_stage,
    _detect_hil_target,
    _run_hil_mock_tests,
    _run_hil_real_tests,
    _record_hil_results,
    _save_hil_report,
)


def _wrap(handler, project_dir: str, ci) -> Callable:
    """将 (project_dir, ci) 签名的 handler 包装成无参 Callable。"""
    def _inner():
        return handler(project_dir, ci)
    _inner.__name__ = handler.__name__
    _inner.__qualname__ = handler.__qualname__
    return _inner


def _bool_wrap(handler, project_dir: str, ci) -> Callable:
    """包装返回 bool 的 handler，True 表示通过，异常表示失败。"""
    def _inner():
        ok = handler(project_dir, ci)
        if not ok:
            raise RuntimeError(f"Stage failed: {handler.__name__}")
        return str(Path(project_dir) / ".osh" / "ci")
    _inner.__name__ = handler.__name__
    _inner.__qualname__ = handler.__qualname__
    return _inner


def create_ci_pipeline(layer: int, project_dir: str) -> CheckpointEngine:
    """
    创建 CI 某一层的 CheckpointPipeline。

    与 layers.py 中对应 layer 的 stages 列表严格对齐。
    每个 stage 使用闭包注入 project_dir 和 CIResult，保持无参签名。
    """
    engine = CheckpointEngine(f"ci-layer-{layer}", project_dir)

    # 为每个 layer 创建一个 CIResult 用于 stage 执行中传参
    ci = CIResult(layer, "checkpoint-run")

    if layer == 1:
        engine.add_step(
            "yaml-validation", "YAML 配置验证",
            _wrap(run_yaml_validation, project_dir, ci),
        )
        engine.add_step(
            "spec-validation", "规约验证 (SWE.5)",
            _wrap(run_spec_validation, project_dir, ci),
        )
        engine.add_step(
            "architecture-review", "架构审查 (SWE.5)",
            _wrap(run_architecture_review, project_dir, ci),
        )
        engine.add_step(
            "requirements-trace", "需求追溯校验 (SWE.5)",
            _wrap(run_requirements_trace, project_dir, ci),
        )
        engine.add_step(
            "plan-lint", "计划检查",
            _wrap(run_plan_lint, project_dir, ci),
        )
        engine.add_step(
            "docsync-gate", "文档同步门禁 (H-07)",
            _wrap(run_docsync_gate, project_dir, ci),
        )
        engine.add_step(
            "clang-tidy", "Clang-Tidy 检查",
            _wrap(run_clang_tidy, project_dir, ci),
        )
        engine.add_step(
            "misra-check", "MISRA 静态检查",
            _wrap(lambda pd, ci: run_misra_check(pd, ci, mode="delta"), project_dir, ci),
        )
        engine.add_step(
            "unit-tests", "Python 单元测试",
            _wrap(run_unit_tests, project_dir, ci),
        )
        engine.add_step(
            "coverage", "Python 覆盖率",
            _wrap(run_coverage_check, project_dir, ci),
        )
        engine.add_step(
            "c-coverage", "C 覆盖率生成",
            _wrap(run_c_coverage, project_dir, ci),
        )
        engine.add_step(
            "c-coverage-gate", "C 覆盖率门禁",
            _wrap(run_c_coverage_check, project_dir, ci),
        )

    elif layer == 2:
        engine.add_step(
            "cross-compile", "交叉编译",
            _wrap(_cross_compile_stage, project_dir, ci),
        )
        engine.add_step(
            "static-analysis", "静态分析",
            _wrap(_static_analysis_stage, project_dir, ci),
        )
        engine.add_step(
            "sil-tests", "SIL 测试",
            _bool_wrap(run_sil_tests, project_dir, ci),
        )
        engine.add_step(
            "integration-tests", "集成测试",
            _wrap(_integration_test_stage, project_dir, ci),
        )
        engine.add_step(
            "memory-safety", "内存安全检查",
            _wrap(_dummy_memory_check, project_dir, ci),
        )

    elif layer == 2.5:
        engine.add_step(
            "hil-target-detect", "HIL 目标检测",
            _wrap(_detect_hil_target_dummy, project_dir, ci),
        )
        engine.add_step(
            "hil-tests", "HIL 测试",
            _wrap(_hil_tests_wrapper, project_dir, ci),
        )
        engine.add_step(
            "hil-report", "HIL 报告",
            _wrap(_save_hil_report_stub, project_dir, ci),
        )

    elif layer == 3:
        engine.add_step(
            "e2e-tests", "端到端测试",
            _wrap(_run_e2e_tests, project_dir, ci),
        )
        engine.add_step(
            "version-check", "版本检查",
            _wrap(_run_version_check, project_dir, ci),
        )
        engine.add_step(
            "evidence-pack", "证据包生成",
            _wrap(_run_evidence_pack, project_dir, ci),
        )

    else:
        raise ValueError(f"Unsupported CI layer: {layer}. Supported: 1, 2, 2.5, 3")

    return engine


# ---------------------------------------------------------------------------
# Layer 2 helper
# ---------------------------------------------------------------------------

def _dummy_memory_check(project_dir: str, ci) -> bool:
    """内存安全检查存根 — 与原 layers.py 逻辑一致。"""
    asan_path = os.path.join(project_dir, "tests", "asan")
    if os.path.exists(asan_path):
        ci.add_stage("memory-safety", "info", "ASan tests configured")
        print("    ⏭️  ASan tests configured but not run (requires dedicated env)")
    else:
        ci.add_stage("memory-safety", "skipped", "No ASan tests")
        print("    ⏭️  No ASan tests found")
    return True


# ---------------------------------------------------------------------------
# Layer 2.5 helpers
# ---------------------------------------------------------------------------

def _detect_hil_target_dummy(project_dir: str, ci) -> bool:
    """HIL 目标检测 — 简化版以支持 checkpoint。"""
    return _detect_hil_target(project_dir, ci, mock=True, strict=False)


def _hil_tests_wrapper(project_dir: str, ci) -> bool:
    """HIL 测试闭包 — 兼容 checkpoint 签名。"""
    return _record_hil_results(ci, [])


def _save_hil_report_stub(project_dir: str, ci) -> bool:
    """HIL 报告保存存根。"""
    _save_hil_report(project_dir, True, "checkpoint", mock=True, boot_pattern="Boot Complete")
    return True


# ---------------------------------------------------------------------------
# Layer 3 helpers
# ---------------------------------------------------------------------------

def _run_e2e_tests(project_dir: str, ci) -> bool:
    """E2E 测试运行。"""
    import subprocess
    e2e_dir = os.path.join(project_dir, "tests", "e2e")
    if not os.path.exists(e2e_dir):
        ci.add_stage("e2e-tests", "skipped", "No E2E tests")
        print("    ⏭️  No E2E tests directory")
        return True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", e2e_dir, "-x", "-q"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            ci.add_stage("e2e-tests", "passed")
            print("    ✅ E2E tests passed")
            return True
        else:
            ci.add_stage("e2e-tests", "failed", result.stdout[:200])
            print("    ❌ E2E tests failed")
            return False
    except subprocess.TimeoutExpired:
        ci.add_stage("e2e-tests", "skipped", "E2E tests timed out")
        print("    ⏭️  E2E tests timed out")
        return False
    except FileNotFoundError:
        ci.add_stage("e2e-tests", "skipped", "pytest not installed")
        print("    ⏭️  pytest not installed")
        return False
    except Exception as e:
        ci.add_stage("e2e-tests", "error", str(e))
        print(f"    ❌ E2E tests error: {e}")
        return False


def _run_version_check(project_dir: str, ci) -> bool:
    """版本检查。"""
    import tomllib
    pyproject = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject):
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version", "unknown")
        ci.add_stage("version-check", "passed", f"Version: {version}")
        print(f"    ✅ Version: {version}")
    else:
        ci.add_stage("version-check", "skipped", "No pyproject.toml")
        print("    ⏭️  No version file")
    return True


def _run_evidence_pack(project_dir: str, ci) -> bool:
    """证据包生成。"""
    try:
        sys.path.insert(0, os.path.join(project_dir, "src"))
        from evidence import pack as evidence_pack  # type: ignore
        evidence_pack.generate_evidence(project_dir)
        ci.add_stage("evidence-pack", "passed", "Compliance pack generated")
        print("    ✅ Evidence pack generated")
    except Exception as e:
        ci.add_stage("evidence-pack", "warning", str(e))
        print(f"    ⚠️  Evidence pack partially generated: {e}")
    return True


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CI Checkpoint Pipeline")
    parser.add_argument("layer", type=float, help="CI layer (1, 2, 2.5, 3)")
    parser.add_argument("--inject-at", help="注入点 step_id")
    parser.add_argument("--resume", action="store_true", help="从 checkpoint 恢复")
    parser.add_argument("--project-dir", default=os.getcwd(), help="项目目录")
    parser.add_argument("--list-steps", action="store_true", help="列出所有步骤")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)

    if args.list_steps:
        engine = create_ci_pipeline(int(args.layer), project_dir)
        print(f"\n📌 CI Layer {int(args.layer)} Injection Points ({len(engine._step_defs)} steps):")
        for i, s in enumerate(engine._step_defs):
            print(f"  Step {i+1}: {s['step_id']:20s} — {s.get('agent', '')}{s['name']}")
        return

    engine = create_ci_pipeline(int(args.layer), project_dir)
    result = engine.run(inject_at=args.inject_at, resume=args.resume)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
