# 质量检视报告：Checkpoint Pipeline Engine

> **审查者**：小马 (Hermes) — 质量架构师  
> **审查日期**：2026-06-26  
> **审查范围**：CheckpointPipelineEngine 完整方案  
> **分支**：main

---

## 1. 审查结论

### 🔴 **有条件通过 — 需修复 A/B 级问题后合并**

**通过项：**
- 22 个引擎专有测试全部通过（1 个 skip 为设计决定）
- 3 种运行模式（全量/注入/恢复）功能逻辑正确
- 状态持久化（JSON）正确实现，序列化往返验证通过
- `__init__.py` 导出清晰，`__all__` 完备
- 修改文件未破坏现有 117 个存量测试（2 个 pre-existing 失败与引擎无关）

**阻却条件**：发现 **4 个 A 级问题** + **5 个 B 级问题**，建议在合并前修复。

---

## 2. 测试结果快照

```
# 引擎测试（22 passed, 1 skipped）
tests/engine/test_checkpoint_engine.py ................ 22/22 passed ✓

# 引擎 + CI + Pipeline 回归（117 passed, 1 skipped, 2 pre-existing failures）
tests/engine/ ...................... 22/23 ✓ (1 skip)
tests/test_ci_engine.py .......... 17/17 ✓
tests/test_pipeline_engine.py ... 78/80 ✓ (2 pre-existing failures)
```

两个 pre-existing 失败均在 `review_selftest.py:1364`，属于 `unpack` 错误，**与本次变更无关**。

---

## 3. 发现的问题 (按严重度排列)

| 严重度 | 数量 | 说明 |
|--------|------|------|
| **A** | 4 | 功能问题或工程实践违规，必须修复 |
| **B** | 5 | 设计缺陷或测试缺口，建议修复 |
| **C** | 4 | 代码整洁/文档建议 |

---

### 🔴 A 级问题 (4 项)

#### A1. 注入点不存在时 `run()` 返回 `True`（`checkpoint.py:201`）

**文件**：`src/yuleosh/engine/checkpoint.py` — `CheckpointEngine.run()`

```python
# test_inject_at_nonexistent — 当前断言：
assert result is True  # 注入点并不存在，却返回 True
```

**问题**：当 `inject_at` 指定的步骤不存在时，`_prepare_inject` 返回 `([], -1)`，
`run()` 遇到空列表就直接 `return True`。调用方得不到任何错误信号。

**影响**：CI/Agent pipeline CLI 会 `sys.exit(0)` 表示成功，掩盖配置错误。

**修复建议**：`_prepare_inject` 中 `except ValueError` 分支应让 `run()` 返回 `False`，
或在注入点缺失时直接 raise。

---

#### A2. CI Layer 2.5 通过 CLI 无法被调用（`ci_checkpoint.py:191`）

**文件**：`src/yuleosh/engine/ci_checkpoint.py` — `main()`

```python
def main():
    parser.add_argument("layer", type=float, ...)
    ...
    engine = create_ci_pipeline(int(args.layer), project_dir)
    #                                 ^^^ truncates 2.5 → 2
```

**问题**：CLI 参数 `layer` 声明为 `float`（因此 2.5 可解析），但传入
`create_ci_pipeline` 时用了 `int()` 强转，导致 `layer=2.5` 被截断为 `layer=2`。
Layer 2.5 的 pipeline 永远无法通过 CLI 触发。

**影响**：HIL（硬件在环）测试层不可达。

**修复建议**：`create_ci_pipeline` 的参数类型应改为 `float`，或增加一个 `int_layer` 映射：

```python
def create_ci_pipeline(layer: float, project_dir: str) -> CheckpointEngine:
```

---

#### A3. 默认 `pipeline run` 不经过 Checkpoint 引擎（`yuleosh.sh:36-47`）

**文件**：`src/yuleosh/cli/yuleosh.sh` — `cmd_pipeline_run()`

```bash
cmd_pipeline_run() {
  # ...
  if [ -n "$inject_at" ]; then
    python3 -m yuleosh.engine.agent_checkpoint run "$spec" --inject-at "$inject_at"
  elif [ "$resume" = true ]; then
    python3 -m yuleosh.engine.agent_checkpoint run "$spec" --resume
  else
    python3 -m yuleosh.pipeline.run "$spec"        # ← 旧 pipeline
  fi
}
```

**问题**：仅在 `--inject-at` 或 `--resume` 标志下才使用 Checkpoint 引擎。
默认的完整流水线仍走老路径 `yuleosh.pipeline.run`，**完全不创建 checkpoint 状态**。
这意味着：
1. 普通 `osh-cli pipeline run docs/spec.md` 执行完成后，`.yuleosh/checkpoint-state.json` 不存在
2. `--resume` 在完整体验中不可用（没有上一次的状态可恢复）
3. 用户必须先用 `--inject-at` 显式启动才能获得 checkpoint 功能，而注入点是用来跳过的

**修复建议**：默认 `pipeline run` 也应使用 Checkpoint 引擎（`agent_checkpoint run`），
才是完整的"支持恢复"的体验。

---

#### A4. `_execute_steps` 中无 handler 步骤的 duration 计算错误（`checkpoint.py:334`）

**文件**：`src/yuleosh/engine/checkpoint.py` — `CheckpointEngine._execute_steps()`

```python
def _execute_steps(self, steps_to_run: list[dict]) -> bool:
    all_passed = True
    t0 = datetime.now()       # ← 外层的 t0（进入函数时的时间）

    for i, step_def in enumerate(steps_to_run):
        ...
        if handler is None:
            record.status = StepStatus.PASSED
            record.completed_at = datetime.now().isoformat()
            record.duration_s = (datetime.now() - t0).total_seconds()
            #                                           ^^ 这里用的是外层的 t0
            continue

        try:
            t0 = datetime.now()      # ← 内层重置 t0
            output_path = handler()
            ...
            record.duration_s = (t1 - t0).total_seconds()   # 正确
```

**问题**：无 handler 步骤的 `duration_s` 计算使用的是函数入口处的 `t0`（上一次 handler 的结尾或函数起始时间），
而非步骤开始时间。结果值可能异常大或异常小。

**修复建议**：在每个循环迭代开始时重新计算 `t0`：

```python
for i, step_def in enumerate(steps_to_run):
    t0 = datetime.now()
    ...
```

---

### 🟠 B 级问题 (5 项)

#### B1. 缺失状态文件损坏的容错处理（`checkpoint.py:379`）

**文件**：`src/yuleosh/engine/checkpoint.py` — `_load_state()`

```python
def _load_state(self) -> Optional[CheckpointState]:
    if not self._state_path.exists():
        return None
    with open(self._state_path) as f:
        return CheckpointState.from_dict(json.load(f))   # ← 无 try/except
```

**问题**：如果 `.yuleosh/checkpoint-state.json` 被手动篡改、内容不完整、或包含非法 JSON，
`json.load(f)` 或 `from_dict()` 中的键访问（如 `s_data["step_id"]`）会抛出异常，
导致整个 pipeline 崩溃。

**影响**：特别在恢复模式中，用户无法绕过损坏的状态文件独立清理。

**修复建议**：`_load_state()` 增加 `try/except`，损坏时打印 warning 并返回 `None`。
同时增加「损坏文件自动备份 + clear_state」fallback。

---

#### B2. 缺少 `status()` 在 pipeline 执行中期的测试覆盖

**文件**：`tests/engine/test_checkpoint_engine.py`

**问题**：当前测试仅覆盖：
- 执行完后的 `status()`（已完成状态）
- 无 checkpoint 时的 `status()`（返回 None）

**未测试**：
- 在 `run()` 执行过程中调用 `status()`（多个 engine 实例并发读）
- 注入模式执行到一半时调用 `status()`
- 恢复模式执行中调用 `status()`

**影响**：`status()` 的 mid-pipeline 正确性未保障。如果另一个进程读取状态文件，
需要在半写状态下读到一致的数据。

**建议增加**：
```python
def test_status_mid_pipeline(self, project_dir):
    """中途读 status 可见 RUNNING 状态"""
    engine = CheckpointEngine("mid", project_dir)
    engine.add_step("s1", "Step 1", _delayed_handler(0.5))
    engine.add_step("s2", "Step 2", _make_step_handler("s2"))
    # 在另一个线程/进程中读 status()
```

---

#### B3. `agent_checkpoint.py` 中存在死代码 `_make_agent_handler`

**文件**：`src/yuleosh/engine/agent_checkpoint.py` — 行 19-31

```python
def _make_agent_handler(step_key: str, handler_fn) -> Callable:
    """将原始 handler 包装为无参 Callable。"""
    def _inner():
        return handler_fn()
    ...
```

**问题**：`create_agent_pipeline()` 不使用 `_make_agent_handler` —— 它直接传递 `PIPELINE_STEPS` 中的
handler，而这些 handler 已经是无参的。函数定义了但从未被调用。

**建议**：要么删除死代码，要么用其包装 handler 以统一签名检查。

---

#### B4. `ci_checkpoint.py` 中所有 stage 共享同一个 `CIResult` 实例

**文件**：`src/yuleosh/engine/ci_checkpoint.py` — 行 74-75

```python
ci = CIResult(layer, "checkpoint-run")
engine.add_step("yaml-validation", ..., _wrap(run_yaml_validation, project_dir, ci))
# ...
engine.add_step("misra-check", ..., _wrap(lambda pd, ci: run_misra_check(pd, ci, mode="delta"), project_dir, ci))
# ...
```

**问题**：同一个 `ci` 对象被所有 stage 共享。`run_yaml_validation` 和 `run_misra_check` 都会修改
`ci` 的内部 `_stages` 列表。虽然 CIResult 设计上允许追加 stage，但如果两个 step 并行执行
（目前是串行，所以理论上安全），或 `ci.to_dict()` 被外部读取时，数据可能不一致。

**影响**：当前串行执行模式下无实际影响，但为未来的并行扩展埋了隐患。

**建议**：每个 step 创建独立的 CIResult，或确保 CIResult 是 append-only 的。

---

#### B5. 缺失空引擎 `run()` 的测试

**文件**：`tests/engine/test_checkpoint_engine.py`

**问题**：`test_empty_engine` 只测试了 `get_step_ids() == []`，没有测试空引擎调用
`run()` 是否返回 `True`、状态是否为 `completed`。

```python
def test_empty_engine_run(self, project_dir):
    engine = CheckpointEngine("empty", project_dir)
    result = engine.run()
    assert result is True
    assert engine._state.status == "completed"
```

---

### 🟢 C 级问题 (4 项)

#### C1. `StepRecord` 的 `output_path` 类型与 None 约定不一致

**文件**：`src/yuleosh/engine/checkpoint.py` — 类定义

`output_path: Optional[str]` 在 `to_dict()` 中序列化为 null / None 正确，
但在 `_execute_steps` 中赋值时使用了：
```python
record.output_path = str(output_path) if output_path else None
```
当 handler 返回非 `str` 的值（如 `Path` 对象）时，`str()` 会强制转换路径，
但 `output_path` 的原始类型丢失，可接受但不够严谨。

**建议**：声明 `output_path: Optional[Union[str, Path]]` 或在赋值处统一用 `str()` 包装。

#### C2. `StepRecord` 状态变更缺少不可逆性检查

`StepStatus` 当前是一个 `str` Enum，没有约束状态迁移的合法性。
例如：`PASSED → PENDING` 或 `FAILED → SKIPPED` 都是合法赋值。
对于调试阶段的引擎这不是问题，但生产环境中可以增加校验。

#### C3. `_finalize` 的 `inject_at` 和 `resume` 参数未使用 `inject_at`

`_finalize()` 收到 `inject_at` 参数但仅在打印摘要时使用：
```python
if inject_at:
    print(f"  注入点: {inject_at}")
```
建议将 `inject_at` 也写入 `self._state.inject_at`（在非注入模式下可能为 None，但如果是恢复
模式且之前有 `inject_at`，这个值不被保留）。

#### C4. `_prepare_inject` 中注入点不存在的错误状态标记过于激进

当注入点不存在时，**所有**步骤被标记为 `FAILED`：
```python
status=StepStatus.FAILED,
error=f"Injection point '{inject_at}' not found",
```
建议改为全部标记为 `PENDING` 或 `SKIPPED`，因为步骤并未真正执行，标记为 FAILED 不准确。

---

## 4. 逐文件审查清单

### `src/yuleosh/engine/__init__.py` ✅ 通过

| 检查项 | 结果 |
|--------|------|
| 空包文件 | ✅ |
| `__all__` 声明 | ✅ (4 个符号均准确) |
| license header | ✅ |
| 导入路径正确 | ✅ |

### `src/yuleosh/engine/checkpoint.py` ⚠️ 4 个 A 级 + 4 个 B/C 级

| 检查项 | 结果 |
|--------|------|
| 类型提示 | ✅ 完整 |
| 文档字符串 | ✅ 类和方法级均有 |
| 异常处理 | ⚠️ A1: 注入点不存在返回 True；B1: 文件损坏无容错 |
| 状态迁移逻辑 | ✅ 正确 |
| 定时计算 | ❌ A4: no-handler 步骤 duration 错误 |
| 命名规范 | ✅ PascalCase for classes, snake_case for methods |
| 向后兼容 | ✅ `__init__.py` 不破坏现有导入 |

### `src/yuleosh/engine/ci_checkpoint.py` ⚠️ 2 个 A/B 级

| 检查项 | 结果 |
|--------|------|
| Layer 1 对齐 | ✅ 12 stages |
| Layer 2 对齐 | ✅ 5 stages |
| Layer 2.5 对齐 | ✅ 但 CLI 不可达 (A2) |
| Layer 3 对齐 | ✅ 3 stages, test skipped |
| 闭包签名 | ✅ `_wrap` / `_bool_wrap` 设计合理 |
| CLI 参数 | ❌ A2: `int()` 截断 layer=2.5 |

### `src/yuleosh/engine/agent_checkpoint.py` ⚠️ B 级

| 检查项 | 结果 |
|--------|------|
| PIPELINE_STEPS 对齐 | ✅ 29-30 steps |
| 死代码 | ⚠️ B3: `_make_agent_handler` 未使用 |
| CLI 支持 | ✅ `run` / `status` / `list-steps` / `clear` |
| 私有成员访问 | ⚠️ `list_injection_points` 用了 `engine._step_defs` |

### `tests/engine/test_checkpoint_engine.py` ⚠️ 测试覆盖缺口

| 测试维度 | 存在 | 需要补充 |
|----------|------|---------|
| 全量模式 | ✅ 2 个 | — |
| 注入模式 | ✅ 4 个 | — |
| 恢复模式 | ✅ 3 个 | — |
| 状态持久化 | ✅ 5 个 | — |
| CI pipeline 创建 | ✅ 4 个（1 skip） | Layer 3 不应 skip |
| Agent pipeline 创建 | ✅ 2 个 | — |
| 状态文件损坏 | ❌ | B1 |
| mid-pipeline status | ❌ | B2 |
| 空引擎 run() | ❌ | B5 |
| 并发读状态 | ❌ | — |

### `src/yuleosh/cli/yuleosh.sh` ⚠️ A 级设计问题

| 检查项 | 结果 |
|--------|------|
| `--inject-at` | ✅ 正确映射到 `agent_checkpoint run --inject-at` |
| `--resume` | ✅ 正确映射到 `agent_checkpoint run --resume` |
| `--checkpoint` | ✅ 正确映射到 `agent_checkpoint status` |
| `--inject-points` | ✅ 正确映射到 `agent_checkpoint list-steps` |
| 参数解析顺序 | ✅ `--inject-at` 带值 parse 正确 |
| 默认 path | ❌ A3: 默认仍走旧 pipeline |
| `cmd_ci_run` default | ⚠️ 同上：仅 inject/resume 时走 checkpoint |

---

## 5. 与现有架构兼容性

| 检查点 | 结果 |
|--------|------|
| `from yuleosh.pipeline.run import PipelineSession, run_pipeline` | ✅ 未受影响 |
| `from yuleosh.ci.run import run_layer1` | ✅ 未受影响 |
| `from yuleosh.engine import CheckpointEngine` | ✅ 新导入，无冲突 |
| `osh-cli pipeline run docs/spec.md`（无选项） | ✅ 仍走旧路径 |
| `osh-cli ci run 1`（无选项） | ✅ 仍走旧路径 |
| `test_pipeline_engine.py` 的 pipeline orchestrator 测试 | ✅ 未受影响（2 个 pre-existing 失败无关） |

**结论**：新引擎以独立模块 `yuleosh.engine.*` 引入，完全向后兼容。

---

## 6. 按优先级建议的修复顺序

```
P0 优先（合并前必须修复）
├── A1: inject_at 不存在时返回 False
├── A2: ci_checkpoint CLI 中 int() 截断 layer=2.5
└── A3: 默认 pipeline run 也应使用 agent_checkpoint

P1 建议修复
├── A4: no-handler 步骤 duration 计算错误
├── B1: 状态文件损坏容错
├── B5: 空引擎 run() 测试

P2 后续优化
├── B2: mid-pipeline status 测试
├── B3: 删除死代码 _make_agent_handler
├── B4: CIResult 实例共享问题
└── C1-C4: 代码整洁项
```

---

以上，小马签出。🫡
