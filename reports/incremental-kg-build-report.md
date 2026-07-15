# 增量知识图谱构建引擎 — 实现报告

> 日期: 2026-07-15  
> 项目: yuleOSH Traceability Knowledge Graph (TKG)  
> 范围: P0 CI pipeline 增量 vs 全量 bootstrap

---

## 1. 摘要

在 `importer.py` 中新增 `incremental_bootstrap()` 函数，支持基于变更文件列表的增量知识图谱构建。全量构建约 17s（11K 节点），增量构建 1-3 个文件预计 < 2s。

## 2. 实现细节

### 2.1 新函数: `incremental_bootstrap()`

```python
def incremental_bootstrap(
    store: KGStore,
    project_dir: str,
    changed_files: Optional[list[str]] = None,
    create_snapshot: bool = True,
    build_id: Optional[str] = None,
    snapshot_meta: Optional[dict] = None,
) -> dict:
```

**行为模式:**

| `changed_files` | 行为 |
|:----------------|:------|
| `None` | 全量 `bootstrap()`（完全向后兼容） |
| `[]` | 仅更新 snapshot，不重新导入 |
| `['src/xxx.py', ...]` | 增量：删除旧节点 → 重新扫描 → 重建边 |

### 2.2 三步增量逻辑

1. **Checkpoint** (`_save_checkpoint`):  
   - 对每个变更文件，保存其 code_file/test_file 节点 + 所有包含的 function 节点 + 所有关联边  
   - 数据结构可 JSON 序列化，用于出错回滚

2. **删除与扫描** (`_delete_changed_file_nodes` + `scan_single_file`):  
   - 软删除旧节点，硬删除旧边  
   - AST 解析重新扫描变更文件

3. **边重建** (所有步骤均为幂等):  
   - `import_coverage_from_default` — 重新导入覆盖率数据  
   - `_merge_test_functions` — 合并重复 test_function  
   - `_annotate_covers_layer` — 标记测试层级  
   - `_build_implements_edges` — 重建 implements 边  
   - `_build_validates_edges` — 重建 validates 边  
   - `_fallback_code_file_matching` — 启发式匹配  
   - `_fix_orphan_test_files` — 孤立测试文件自动关联

### 2.3 安全设计

| 特性 | 实现 |
|:-----|:------|
| Checkpoint 备份 | `_save_checkpoint()` 在删除前序列化节点+边 |
| 出错回滚 | `_restore_checkpoint()` 从 backup 恢复 |
| 幂等性 | 所有 upsert_node/upsert_edge 基于 UNIQUE 约束去重 |
| 强行全量 | `changed_files=None` 直接调用 `bootstrap()` |

### 2.4 文件变更

| 文件 | 变更 |
|:-----|:------|
| `importer.py` | 新增 `incremental_bootstrap()`, `_save_checkpoint()`, `_restore_checkpoint()`, `_delete_changed_file_nodes()` |
| `code_scanner.py` | 新增 `scan_single_file()` — 单文件 AST 扫描 |
| `ci_hook.py` | `kg_ci_append()` 增加增量路由：传 `changed_files` 且文件存在时走增量路径 |
| `__init__.py` | 导出 `incremental_bootstrap` 和 `scan_single_file` |

## 3. 测试结果

### 3.1 TestIncrementalBuild（新增 9 个）

| 测试 | 验证内容 | 状态 |
|:-----|:---------|:-----|
| `test_incremental_no_changed_files` | 空列表 → 仅 snapshot 更新 | ✅ |
| `test_incremental_new_file` | 新增文件 → 节点创建 + 边重建 | ✅ |
| `test_incremental_existing_file` | 修改文件 → 旧节点删除 + 重新扫描 | ✅ |
| `test_incremental_idempotent` | 重复增量运行 → 不产生重复 | ✅ |
| `test_incremental_rollback_on_error` | 出错 → 回滚到 checkpoint | ✅ |
| `test_incremental_vs_full_consistency` | 增量结果 = 全量结果（数据一致性验证）| ✅ |
| `test_ci_hook_changed_files_param` | CI hook 传入 changed_files → 走增量路径 | ✅ |
| `test_incremental_only_snapshot_no_import` | KG CI hook 空文件列表 → snapshot 创建 | ✅ |
| `test_incremental_empty_changed_files_no_snapshot` | create_snapshot=False → 无 snapshot | ✅ |

### 3.2 回归测试

- 原有 137 测试：全部通过 ✅  
- 跳过：1 个 (postgres 模式条件跳过)  

## 4. 性能预期

| 场景 | 预计耗时 | 对比全量 |
|:-----|:---------|:---------|
| 1-3 个文件变更 | < 2s | 全量 17s → **快 8.5x+** |
| 10+ 文件批量变更 | < 5s | 全量 17s → **快 3.4x+** |
| 纯 snapshot 更新 | < 0.5s | 全量 17s → **快 34x+** |

实际性能取决于：
- AST 解析复杂度（单文件大小）
- .coverage 文件大小（覆盖率导入）
- 当前边重建的范围

## 5. 使用方式

### CLI (python -m)

```bash
# 增量构建（指定变更文件）
python -m yuleosh.knowledge_graph.ci_hook \
  --build-id ci-001 \
  --changed-files src/yuleosh/engine.py,tests/test_engine.py

# 自动检测 git 变更
python -m yuleosh.knowledge_graph.ci_hook \
  --auto

# 全量构建（无 --changed-files）
python -m yuleosh.knowledge_graph.ci_hook \
  --build-id ci-001
```

### Python API

```python
from yuleosh.knowledge_graph import get_store, incremental_bootstrap

store = get_store()
result = incremental_bootstrap(
    store,
    project_dir="/my/project",
    changed_files=["src/yuleosh/engine.py"],
    create_snapshot=True,
    build_id="ci-incr-001",
)

# 强制全量
result = incremental_bootstrap(
    store,
    project_dir="/my/project",
    changed_files=None,  # 或直接调用 bootstrap()
)
```

### CI Pipeline 集成

```python
from yuleosh.knowledge_graph.ci_hook import kg_ci_append

# 有变更文件 → 自动走增量
result = kg_ci_append(
    store,
    build_id="ci-20260715-001",
    changed_files=["src/yuleosh/engine.py", "tests/test_engine.py"],
)

# 无变更文件 → 全量
result = kg_ci_append(
    store,
    build_id="ci-20260715-001",
)
```

## 6. 限制与注意事项

1. **RTM/JSON 变更**: 当前增量仅处理源码文件变更。如果需求追溯矩阵 (RTM) 或 JSON mapping 发生变化（即 `docs/requirement-traceability-matrix.md` 或 `reports/req-test-mapping.json` 变更），应触发全量重建。
2. **边重建覆盖**: 当前实现中，边重建步骤 (`_build_implements_edges` 等) 会在整个图上运行以保持一致性。对于非常大型图（>100K 节点），可进一步优化为仅处理受影响的需求子图。
3. **覆盖率数据**: 每次增量都会重新导入 `.coverage`。如果覆盖率数据文件很大，可增加缓存机制。
