# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Knowledge Graph Incremental Orchestrator (P2-7).

串联 checkpoint → incremental_bootstrap → ci_hook → verify_delta，
并在任一环节失败时回滚到检查点（fail-closed）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from yuleosh.knowledge_graph.checkpoint import (
    _restore_checkpoint,
    _save_checkpoint,
)
from yuleosh.knowledge_graph.ci_hook import kg_ci_append
from yuleosh.knowledge_graph.incremental import incremental_bootstrap
from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.verify_delta import apply_test_results, load_test_results

log = logging.getLogger("yuleosh.knowledge_graph.incremental_run")


def kg_incremental_run(
    store: KGStore,
    project_dir: str,
    changed_files: Optional[list[str]],
    build_id: Optional[str] = None,
    test_json: Optional[str] = None,
    junit: Optional[str] = None,
    with_verify: bool = True,
    create_snapshot: bool = True,
) -> dict:
    """一键执行知识图谱增量链。

    Args:
        store: KGStore 实例
        project_dir: 项目根目录
        changed_files: 变更文件（None 表示全量 bootstrap）
        build_id: 构建 ID（缺省自动生成）
        test_json / junit: 显式测试报告路径
        with_verify: 是否把测试结果写回 verifies/covers 边
        create_snapshot: 是否创建快照

    Returns:
        汇总 dict：build_id / changed_files / incremental / ci_hook / verify_delta

    Raises:
        任一环节异常时先回滚检查点，再向上抛出（不吞错）。
    """
    changed = [f.replace("\\", "/") for f in (changed_files or [])]
    build_id = build_id or "kg-inc-" + datetime.now().strftime("%Y%m%d-%H%M%S")

    checkpoint = _save_checkpoint(store, changed) if changed else None

    try:
        incremental = incremental_bootstrap(
            store,
            project_dir=project_dir,
            changed_files=changed or None,
            create_snapshot=create_snapshot,
            build_id=build_id,
        )

        ci_hook = kg_ci_append(
            store,
            build_id,
            changed or None,
            meta={"project_dir": project_dir},
        )

        verify_delta = None
        if with_verify:
            test_results = load_test_results(
                project_dir, json_path=test_json, junit_path=junit)
            if test_results:
                verify_delta = apply_test_results(store, test_results)

        return {
            "build_id": build_id,
            "changed_files": len(changed),
            "incremental": incremental,
            "ci_hook": ci_hook,
            "verify_delta": verify_delta,
            "rolled_back": False,
        }
    except Exception as e:
        log.error("KG 增量链失败（build_id=%s）：%s，开始回滚", build_id, e)
        if checkpoint:
            _restore_checkpoint(store, checkpoint)
            log.info("已回滚检查点（%d nodes / %d edges）",
                     len(checkpoint.get("nodes", [])),
                     len(checkpoint.get("edges", [])))
        raise
