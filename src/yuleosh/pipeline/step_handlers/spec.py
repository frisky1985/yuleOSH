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
from typing import Optional

import yuleosh

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.spec_contracts import contracts_check, contracts_check_dir

log = logging.getLogger("pipeline.step_handlers.spec")

__all__ = ["step_spec_check"]


# ── SYS-REQ-002: V 左半连续性可强制 ─────────────────────────────────────
# M1.5 链路B 只把 SYS→SWE.1 对齐「记录」下来（缺失仅 WARNING）：V 两侧脱节
# 时流水线仍全绿，审计无法证伪。本开关把该能力升级为「可强制」——开启后
# 未对齐（含左半完全缺失）将使 SWE.1 步骤失败。默认关闭以保持向后兼容。
_SYS_ALIGN_STRICT_ENV = "OSH_SYS_ALIGN_STRICT"


def _sys_align_strict_enabled() -> bool:
    """是否启用 SYS→SWE.1 对齐的严格阻断模式（默认关闭）。

    显式设置 ``OSH_SYS_ALIGN_STRICT=1|true|yes|on`` 时启用。
    """
    return os.environ.get(_SYS_ALIGN_STRICT_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _spec_validator_env() -> dict:
    """Build env so the spec-validator subprocess can import yuleosh.

    yuleosh CLI may be invoked by absolute path from an arbitrary cwd;
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
        spec_target = session.spec_path
        spec_dir_mode = Path(spec_target).is_dir()
        log.info(f"Validating spec: {spec_target} (directory_mode={spec_dir_mode})")
        result = subprocess.run(
            [sys.executable, "-m", "yuleosh.spec.validate", spec_target, "--json"],
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
        # 防回归从 LLM 人审迁移到机器检查。目录模式 (OpenSpec) 聚合校验。
        try:
            if spec_dir_mode:
                check = contracts_check_dir(spec_target)
            else:
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

        # 目录模式: 记录聚合的 spec 文件清单供下游 (codegen/评审) 定位
        if spec_dir_mode:
            try:
                agg_files = check.get("contracts", {}).get("files", [])
                if agg_files:
                    idx = session.session_dir / "spec-files.json"
                    idx.write_text(
                        json.dumps(agg_files, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    session.set_artifact("spec_files", str(idx))
            except Exception:  # pragma: no cover - defensive
                pass

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

        # M1.5 链路B: SWE.1 消费 SYS 上游需求 (确定性校验)
        # SYS-REQ-002: 默认放行(向后兼容); strict 开关下未对齐即阻断,
        # 使 V 左半→右半链接由「被记录」升级为「被强制」。
        align_report = _check_sys_requirements_aligned(session)
        if align_report and _sys_align_strict_enabled():
            status = align_report.get("status")
            if status != "aligned":
                missing = align_report.get("missing_in_spec", [])
                total = align_report.get("total_sys_reqs", 0)
                detail = (", ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")) if missing else "左半缺失或未解析到 SYS-REQ"
                raise PipelineStepError(
                    f"[SYS→SWE.1 strict] V 左半链路断裂 (status={status}, "
                    f"total={total}): {detail}. "
                    f"请补齐 spec 对 SYS 需求的引用, 或关闭 {_SYS_ALIGN_STRICT_ENV} 放行。"
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


def _check_sys_requirements_aligned(session: PipelineSession) -> Optional[dict]:
    """M1.5 链路B: SWE.1 消费 SYS 上游需求 (确定性校验)。

    读 ``docs/system-requirements.md`` 提取 SYS-REQ-NNN，检查 spec
    (SWE.1 输入) 是否显式引用，确保 V 模型左半「系统需求 → 软件需求」
    链路连续。

    **返回对齐报告 dict**（而非副作用式 None），使调用方可结合
    :func:`_sys_align_strict_enabled` 决定是否升级为阻断；本函数自身
    绝不 raise（内部异常被兜底，返回 None）。status 取值：

    - ``aligned``     — spec 已引用全部系统需求
    - ``partial``     — 部分未引用（左半链路有缺口）
    - ``absent``      — 无 docs/system-requirements.md（左半未生成）
    - ``none-parsed`` — 文档存在但解析不到 SYS-REQ-NNN
    """
    try:
        import re
        from pathlib import Path

        sys_req_path = Path(session.project_dir) / "docs" / "system-requirements.md"
        if not sys_req_path.exists():
            # 左半完全缺失: 不改变任何磁盘行为, 仅向调用方报告状态
            # (供 strict 模式判定是否阻断)
            return {
                "total_sys_reqs": 0,
                "aligned": [],
                "missing_in_spec": [],
                "status": "absent",
            }
        text = sys_req_path.read_text(encoding="utf-8")
        sys_reqs = sorted(set(re.findall(r"SYS-REQ-\d+", text)))
        if not sys_reqs:
            return {
                "total_sys_reqs": 0,
                "aligned": [],
                "missing_in_spec": [],
                "status": "none-parsed",
            }

        spec_path = Path(session.spec_path)
        spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        missing = [rid for rid in sys_reqs if rid not in spec_text]
        aligned = [rid for rid in sys_reqs if rid in spec_text]

        report = {
            "total_sys_reqs": len(sys_reqs),
            "aligned": aligned,
            "missing_in_spec": missing,
            "status": "aligned" if not missing else "partial",
        }
        out = session.session_dir / "sys-spec-alignment.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        session.set_artifact("sys_spec_alignment", str(out))

        if missing:
            log.warning(
                f"[链路B] spec 未引用 {len(missing)} 条系统需求 (SYS→SWE.1 对齐缺口): "
                f"{missing[:10]}{'...' if len(missing) > 10 else ''}"
            )
        else:
            log.info(f"[链路B] spec 已覆盖全部 {len(sys_reqs)} 条系统需求 (SYS→SWE.1 对齐)")
        return report
    except Exception as e:  # 防御: 绝不阻断 SWE.1 主流程
        log.warning(f"[链路B] SYS 需求对齐检查跳过 (non-fatal): {e}")
        return {"total_sys_reqs": 0, "aligned": [], "missing_in_spec": [], "status": "skipped"}
