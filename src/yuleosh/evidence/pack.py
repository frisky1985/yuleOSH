"""
yuleOSH Evidence Engine — Backwards-compatible re-export module.

P1 渐进执行模式改造 (2026-10-18):
  原来的 generate_evidence() 是同步阻塞一把梭；现在拆成 5 个可独立调用的 stage：
    1. stage_wait_pipeline  — 等待 pipeline 完成（原 _check_pipeline_not_running）
    2. stage_collect       — 收集需求/评审/CI/SIL
    3. stage_reports       — 生成 5 份 Markdown 报告
    4. stage_pack          — pack_compliance_zip 打包
  每个 stage 开始读 .state.json、结尾写 .state.json，支持 pause/resume。
  桌面程序崩溃重启也能从最后一个已完成 stage 继续。

一键模式保留（generate_evidence）加 increment=False 参数，默认走渐进模式。
"""

from yuleosh.evidence.generator import EvidenceCollector
from yuleosh.evidence.compliance import pack_compliance_zip, _check_pipeline_not_running
from yuleosh.evidence.analysis import (
    parse_scenario_refs,
    parse_module_covers,
    parse_comment_covers,
    parse_function_covers,
    infer_covers_from_function_names,
    parse_covers_from_file,
    categorize_uncovered,
)
from yuleosh.evidence.report import (
    format_maturity_label,
    format_status_icon,
    format_coverage_summary,
    make_table_row,
    make_header_row,
    make_acceptance_row,
    make_coverage_table_row,
    dedent,
    generate_timestamp,
)

import json
import os
import sys
import time as _time
from datetime import datetime
from pathlib import Path


# ---------- P1 渐进执行：状态持久化 ----------

# 渐进执行的 5 个 stage 顺序（wait_pipeline / collect / reports / pack / done）
STAGE_ORDER = ("wait_pipeline", "collect", "reports", "pack", "done")
STAGE_LABELS = {
    "wait_pipeline": "等待 Pipeline 完成",
    "collect": "收集证据源（需求/评审/CI/SIL）",
    "reports": "渲染合规报告（追溯矩阵 / ASPICE 清单）",
    "pack": "打包归档证据包",
    "done": "完成",
}

# .osh/evidence/.state.json —— 渐进执行状态
def _state_path(project_dir: str | os.PathLike) -> Path:
    return Path(project_dir) / ".osh" / "evidence" / ".state.json"


def _load_state(project_dir: str | os.PathLike) -> dict:
    """读渐进执行状态；文件不存在返回初始状态。"""
    p = _state_path(project_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return _initial_state()
    return _initial_state()


def _save_state(project_dir: str | os.PathLike, state: dict) -> None:
    p = _state_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _initial_state() -> dict:
    """新建一次渐进执行的初始状态。"""
    return {
        "stage": "wait_pipeline",
        "status": "pending",          # pending → running → waiting_confirm → done | failed
        "started_at": None,            # 本次 session 开始时间（ISO）
        "current_stage_started_at": None,
        "completed_stages": [],        # 已完成 stage 列表
        "artifacts_so_far": [],       # 已生成 artifacts 路径
        "error": None,
        "version": "1",
    }


def _advance_state(state: dict, next_stage: str, status: str = "waiting_confirm") -> dict:
    """stage 完成后推进状态。"""
    if state["stage"] != next_stage and state["status"] != "waiting_confirm":
        # 正常流程：当前 stage → next stage
        if state["stage"] not in state["completed_stages"]:
            state["completed_stages"].append(state["stage"])
    state["stage"] = next_stage
    state["status"] = status
    state["current_stage_started_at"] = datetime.now().isoformat()
    return state


# ---------- P1 渐进执行：stage 函数 ----------

def _stage_wait_pipeline(project_dir: str, state: dict, max_wait: int = 30) -> dict:
    """Stage 1: 等待 pipeline 完成。"""
    state["current_stage_started_at"] = datetime.now().isoformat()
    state["status"] = "running"

    waited = 0
    while not _check_pipeline_not_running(project_dir) and waited < max_wait:
        sleep = min(2, max_wait - waited)
        _time.sleep(sleep)
        waited += sleep

    if waited >= max_wait:
        state["error"] = f"pipeline 等待超时 ({max_wait}s)，继续执行但数据可能不完整"
    else:
        state["error"] = None

    _advance_state(state, "collect", status="waiting_confirm")
    return state


def _stage_collect(project_dir: str, state: dict, spec_path: str | None = None) -> dict:
    """Stage 2: 收集证据源。"""
    state["current_stage_started_at"] = datetime.now().isoformat()
    state["status"] = "running"

    collector = EvidenceCollector(project_dir)
    collector.collect_requirements(spec_path=spec_path)
    collector.collect_reviews()
    collector.collect_ci_results()
    collector.collect_sil_reports()

    # 把 collector 序列化信息存进 state（供后续 stage 恢复时重建）
    # collector 本身不能 JSON 化，存 project_dir 和已收集数据的量级指标
    state["collector_project_dir"] = project_dir
    state["collector_metrics"] = {
        "requirements": len(collector.requirements),
        "reviews": len(collector.reviews),
        "ci_results": len(collector.ci_results),
        "sil_reports": len(collector.sil_reports),
    }
    # collector 引用通过 evidence_dir 路径共享
    state["collector_evidence_dir"] = str(collector.evidence_dir)

    # 存一份 collector 快照到 .osh/evidence/.collector.pkl，供后续 stage 恢复
    import pickle
    _pickle_path = Path(project_dir) / ".osh" / "evidence" / ".collector.pkl"
    _pickle_path.parent.mkdir(parents=True, exist_ok=True)
    _pickle_path.write_bytes(pickle.dumps(collector))

    _advance_state(state, "reports", status="waiting_confirm")
    return state


def _stage_reports(project_dir: str, state: dict) -> dict:
    """Stage 3: 生成 5 份 Markdown 报告。"""
    import pickle
    state["current_stage_started_at"] = datetime.now().isoformat()
    state["status"] = "running"

    _pickle_path = Path(project_dir) / ".osh" / "evidence" / ".collector.pkl"
    collector: EvidenceCollector = pickle.loads(_pickle_path.read_bytes())

    artifacts = []
    artifacts.append(collector.generate_traceability_matrix())
    artifacts.append(collector.generate_requirement_coverage())
    artifacts.append(collector.generate_code_coverage_report())
    artifacts.append(collector.generate_acceptance_matrix())
    artifacts.append(collector.aggregate_review_logs())

    state["artifacts_so_far"] = artifacts

    # 更新 pickle（reports 阶段也可能在 collector 上追加了数据）
    _pickle_path.write_bytes(pickle.dumps(collector))

    _advance_state(state, "pack", status="waiting_confirm")
    return state


def _stage_pack(project_dir: str, state: dict, formats=None) -> dict:
    """Stage 4: 打包合规 ZIP。"""
    import pickle
    state["current_stage_started_at"] = datetime.now().isoformat()
    state["status"] = "running"

    _pickle_path = Path(project_dir) / ".osh" / "evidence" / ".collector.pkl"
    collector: EvidenceCollector = pickle.loads(_pickle_path.read_bytes())

    zip_path = pack_compliance_zip(collector, formats=formats)
    # 派生格式产物（html/xlsx/pdf）会在 pack 阶段生成
    for p in sorted(collector.evidence_dir.iterdir()):
        if p.suffix in (".html", ".xlsx", ".pdf"):
            state["artifacts_so_far"].append(str(p))
    state["artifacts_so_far"].append(zip_path)

    _advance_state(state, "done", status="done")
    return state


# ---------- P1 渐进执行：对外 API ----------

def run_incremental_stage(
    project_dir: str,
    target_stage: str | None = None,
    spec_path: str | None = None,
    formats=None,
    confirm: bool = False,
) -> dict:
    """渐进执行：跑指定 stage，或自动推进到 target_stage。

    Args:
        project_dir: OSH 项目目录。
        target_stage: 要跑到哪个 stage（None = 只跑当前 stage 一个）。
        spec_path: 可选需求规格路径。
        formats: 输出格式列表。
        confirm: 若当前处于 waiting_confirm，True 表示"确认推进下一阶段"。

    Returns:
        更新后的 state dict。
    """
    project_dir = project_dir or os.environ.get("OSH_HOME", os.getcwd())
    state = _load_state(project_dir)

    # 首次启动 → 初始化
    if state["status"] in ("pending", None):
        state = _initial_state()
        state["started_at"] = datetime.now().isoformat()

    # target_stage 校验 —— 不管什么状态都先做（防止 waiting_confirm 早退绕过）
    if target_stage is not None:
        cur_idx = STAGE_ORDER.index(state["stage"])
        tgt_idx = STAGE_ORDER.index(target_stage)
        if tgt_idx < cur_idx:
            raise ValueError(f"target_stage {target_stage} 不能早于当前 stage {state['stage']}")

    # 如果正在 waiting_confirm 且 confirm=False 且没指定 target_stage，
    # 直接返回当前状态（仅查询，不推进）
    if state["status"] == "waiting_confirm" and not confirm and target_stage is None:
        return state

    # 如果 confirm=True，先推进状态（让当前 stage 正式进入 completed_stages）
    if confirm and state["status"] == "waiting_confirm":
        # 找到下一个要跑的 stage
        idx = STAGE_ORDER.index(state["stage"])
        if idx + 1 < len(STAGE_ORDER):
            state["completed_stages"].append(state["stage"])
            state["stage"] = STAGE_ORDER[idx + 1]
            state["status"] = "running"
            state["current_stage_started_at"] = datetime.now().isoformat()
        else:
            state["status"] = "done"
            _save_state(project_dir, state)
            return state

    # 确定要跑哪些 stage
    stages_to_run: list[str] = []
    if target_stage is None:
        # 只跑当前一个
        stages_to_run = [state["stage"]]
    else:
        cur_idx = STAGE_ORDER.index(state["stage"])
        tgt_idx = STAGE_ORDER.index(target_stage)
        stages_to_run = list(STAGE_ORDER[cur_idx:tgt_idx + 1])

    try:
        for stg in stages_to_run:
            state["stage"] = stg
            state["status"] = "running"
            _save_state(project_dir, state)

            if stg == "wait_pipeline":
                state = _stage_wait_pipeline(project_dir, state)
            elif stg == "collect":
                state = _stage_collect(project_dir, state, spec_path=spec_path)
            elif stg == "reports":
                state = _stage_reports(project_dir, state)
            elif stg == "pack":
                state = _stage_pack(project_dir, state, formats=formats)
            elif stg == "done":
                state["status"] = "done"
                break

            _save_state(project_dir, state)
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
        _save_state(project_dir, state)
        raise

    _save_state(project_dir, state)
    return state


def get_incremental_status(project_dir: str | None = None) -> dict:
    """读取当前渐进执行状态（供 GET /api/v1/evidence/status 轮询）。"""
    project_dir = project_dir or os.environ.get("OSH_HOME", os.getcwd())
    state = _load_state(project_dir)
    # 加上 stage 进度百分比（用于前端展示）
    idx = STAGE_ORDER.index(state["stage"]) if state["stage"] in STAGE_ORDER else 0
    state["progress_pct"] = int(idx / (len(STAGE_ORDER) - 1) * 100)
    state["stage_label"] = STAGE_LABELS.get(state["stage"], state["stage"])
    return state


def reset_incremental_state(project_dir: str | None = None) -> dict:
    """重置渐进执行状态（放弃当前 session，从头开始）。"""
    project_dir = project_dir or os.environ.get("OSH_HOME", os.getcwd())
    _state_path(project_dir).unlink(missing_ok=True)
    # 清理 collector pickle
    _pickle_path = Path(project_dir) / ".osh" / "evidence" / ".collector.pkl"
    _pickle_path.unlink(missing_ok=True)
    return _initial_state()


# ---------- 原有一键模式入口（向后兼容） ----------

def generate_evidence(project_dir: str = None, spec_path: str = None, formats=None, incremental: bool = False):
    """Generate full evidence chain.

    P1 渐进执行模式改造：默认 incremental=False（原有一键跑完行为，向后兼容）。
    设 incremental=True 进入渐进模式（每阶段可 pause/resume，状态落盘到
    .osh/evidence/.state.json，桌面程序崩溃重启可恢复）。

    ``formats`` 选择人类可读产物格式（md/html/xlsx/pdf，逗号分隔或列表）；
    缺省只产 Markdown，保持既有行为。派生格式在打包阶段生成，确保合规 ZIP
    与 manifest 覆盖全部所选格式。
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    if incremental:
        # 渐进模式：一口气跑到 done，但每个 stage 之间不留停
        state = run_incremental_stage(
            project_dir,
            target_stage="done",
            spec_path=spec_path,
            formats=formats.split(",") if isinstance(formats, str) else formats,
        )
        return state.get("artifacts_so_far", [])

    # ---------- 原有一键模式（incremental=False）----------
    print(f"\n📦 OSH Evidence Generation")
    print(f"{'='*50}")

    _max_wait = 30
    _waited = 0
    while not _check_pipeline_not_running(project_dir) and _waited < _max_wait:
        _sleep = min(2, _max_wait - _waited)
        print(f"  ⏳ Waiting for pipeline to finish... ({_waited}s elapsed)")
        _time.sleep(_sleep)
        _waited += _sleep
    if _waited >= _max_wait:
        print(f"  ⚠️  Timed out waiting for pipeline (waited {_waited}s). Collecting anyway — data may be incomplete.")

    collector = EvidenceCollector(project_dir)
    collector.collect_requirements(spec_path=spec_path)
    collector.collect_reviews()
    collector.collect_ci_results()
    collector.collect_sil_reports()

    print(f"\n{'='*50}")

    artifacts = []
    artifacts.append(collector.generate_traceability_matrix())
    artifacts.append(collector.generate_requirement_coverage())
    artifacts.append(collector.generate_code_coverage_report())
    artifacts.append(collector.generate_acceptance_matrix())
    artifacts.append(collector.aggregate_review_logs())

    # 派生格式（HTML/Excel/PDF）在 pack_compliance_zip 内生成：
    # process-capability-map / capability-statement 由打包函数末尾补齐，
    # 派生必须发生在它们之后、ZIP 打开之前，否则这两份报告没有对应格式。
    zip_path = pack_compliance_zip(collector, formats=formats)
    for p in sorted(collector.evidence_dir.iterdir()):
        if p.suffix in (".html", ".xlsx", ".pdf"):
            artifacts.append(str(p))
    artifacts.append(zip_path)

    print(f"\n{'='*50}")
    print(f"✅ Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print()
    return artifacts


def main():
    """CLI entry point for evidence generation.

    用法::
        python -m yuleosh.evidence.pack pack [--formats md,html,xlsx,pdf] [spec_path]

    新增渐进执行 CLI::
        python -m yuleosh.evidence.pack status
        python -m yuleosh.evidence.pack stage [wait_pipeline|collect|reports|pack]
        python -m yuleosh.evidence.pack resume [--confirm]
        python -m yuleosh.evidence.pack reset

    project_dir 优先用 ``OSH_HOME`` 环境变量，回退到 ``os.getcwd()``。
    """
    project_dir = os.environ.get("OSH_HOME", os.getcwd())
    args = [a for a in sys.argv[1:] if a != "pack"]
    if not args:
        generate_evidence(project_dir=project_dir)
        return

    cmd = args[0]
    rest = args[1:]

    if cmd == "status":
        state = get_incremental_status(project_dir)
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    if cmd == "reset":
        state = reset_incremental_state(project_dir)
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    if cmd == "stage":
        target = rest[0] if rest else None
        formats = None
        spec_path = None
        # 先剥掉 --formats 和它的值
        if "--formats" in rest:
            idx = rest.index("--formats")
            if idx + 1 < len(rest):
                formats = rest[idx + 1].split(",")
            rest = rest[:idx] + rest[idx + 2:]
        # 剩余 positional arg 作为 spec_path（跳过第一个 target）
        remaining = [a for a in rest if not a.startswith("--")]
        # target 也是 positional，跳过它
        if target and target in remaining:
            remaining.remove(target)
        if remaining:
            spec_path = remaining[0]
        try:
            state = run_incremental_stage(project_dir, target_stage=target, spec_path=spec_path, formats=formats)
            print(json.dumps(state, indent=2, ensure_ascii=False))
        except ValueError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            sys.exit(2)
        return

    if cmd == "resume":
        confirm = "--confirm" in rest
        state = run_incremental_stage(project_dir, confirm=confirm)
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    # 默认：一键模式（CLI 保持原有行为）
    # 无 stage/resume/status/reset 子命令 → 把 cmd + rest 全当 positional
    spec_path = None
    formats = None
    all_args = [cmd] + rest
    if "--formats" in all_args:
        idx = all_args.index("--formats")
        if idx + 1 >= len(all_args):
            raise SystemExit("--formats requires a value, e.g. --formats md,html,xlsx,pdf")
        formats = all_args[idx + 1]
        del all_args[idx:idx + 2]
    if all_args and not all_args[0].startswith("--"):
        spec_path = all_args[0]
    # 不传 incremental，用默认 False（原有一键行为）
    if formats is None:
        generate_evidence(spec_path=spec_path)
    else:
        generate_evidence(spec_path=spec_path, formats=formats)


if __name__ == "__main__":
    # 假绿修复 (2026-08-07): CI 用 `python -m yuleosh.evidence.pack` 调用本模块，
    # 但此前缺入口，导入即静默退出 0 → .osh/evidence/ 从未生成 →
    # 下一步 upload-artifact (if-no-files-found: error) 失败。
    # 与 evidence/check.py、compliance.py 等模块保持一致，补 __main__ 入口。
    main()
