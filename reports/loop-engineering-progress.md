# Loop Engineering — Iteration 1 进度报告 🚀

> **生成时间**: 2026-07-17 13:30 CST  
> **工程师**: 小克 👨‍💻  
> **版本**: v2.5.0 (Iteration 1 完成)

---

## 1. 实现清单

| # | 文件 | 状态 | 说明 |
|:-:|:-----|:----:|:-----|
| 1 | `src/yuleosh/loop_engine/event_bus.py` | ✅ **完成** | SystemEventBus — 系统级事件总线 (7 事件类型, 优先级队列, 去重, 持久化, 重试) |
| 2 | `src/yuleosh/loop_engine/feedback_handlers/base.py` | ✅ **完成** | FeedbackHandler 抽象基类 + ActionResult + @register_handler |
| 3 | `src/yuleosh/loop_engine/feedback_handlers/loop1_defect_to_req.py` | ✅ **完成** | Loop 1 — 缺陷→需求回溯闭环 (CI_FAILURE→KG trace→spec-delta→needs_review) |
| 4 | `src/yuleosh/loop_engine/spec_delta_gen.py` | ✅ **完成** | SpecDeltaGenerator — 自动生成 spec-delta.md 格式 (4 变更类型, Markdown/JSON) |
| 5 | `src/yuleosh/loop_engine/cli.py` | ✅ **完成** | `yuleosh loop status|run|config` CLI 入口 |
| 6 | `src/yuleosh/loop_engine/__init__.py` | ✅ **完成** | LoopEngine 类 + 包导出 |
| 7 | CLI 集成 (`cli/main.py`) | ✅ **完成** | `yuleosh loop` 子命令注册到主 CLI |

## 2. 测试覆盖

| 测试文件 | 用例数 | 状态 |
|:---------|:------:|:----:|
| `tests/loop_engine/test_event_bus.py` | **16** | ✅ Pass |
| `tests/loop_engine/test_feedback_handlers.py` | **16** | ✅ Pass |
| `tests/loop_engine/test_spec_delta_gen.py` | **13** | ✅ Pass |
| `tests/loop_engine/test_loop1_defect_to_req.py` | **16** | ✅ Pass |
| **合计** | **61** | ✅ All Pass |

## 3. EventBus v2 核心能力

- **Pub/Sub**: on/off/emit, one_shot 支持
- **去重**: SHA256 dedup_key + 可配置窗口 (默认 300s)
- **优先级**: priority 0-9 + priority_filter 订阅过滤
- **持久化**: set_store() → Store 后端写入 `loop_events` 表
- **重试**: 自动重试最多 3 次 (失败时退避 1s)
- **异步**: emit_async() → 后台线程处理
- **历史**: 最多 2000 条事件历史, 支持类型筛选
- **统计**: stats() → emitted/handled/failed/deduped/retried

## 4. Loop 1 闭环流程

```
CI_FAILURE event
    │
    ├─→ can_handle(): 检查 test_name 存在
    │
    ├─→ KG trace_by_test_function(): 查找覆盖的需求
    │
    ├─→ SpecDeltaGenerator.generate_from_test_failure()
    │       → SpecDelta(change_type=needs_review)
    │
    ├─→ append_to_file(): 写入 spec-delta.md
    │
    ├─→ _mark_requirement_needs_review(): Store/JSON 持久化
    │
    └─→ ActionResult(success=True, evidence_ref=...)
```

## 5. CLI 使用示例

```bash
# 查看 Loop Engine 状态
yuleosh loop status

# 手动触发 Loop 1 (缺陷→需求回溯)
yuleosh loop run loop1_defect_to_req \
    --test test_brake_light_interrupt \
    --req RS-001

# 查看/修改配置
yuleosh loop config
yuleosh loop config --set dedup_window=600
```

## 6. SHALL 需求覆盖

| SHALL | 描述 | 状态 |
|:-----:|:-----|:----:|
| LE-001 | 系统级 EventBus (7 事件类型, Pub/Sub, 优先级, 去重, 持久化, 重试) | ✅ |
| LE-002 | FeedbackHandler 抽象接口 (can_handle/handle/rollback + @register_handler) | ✅ |
| LE-003 | Loop 1 Defect→Requirement (CI_FAILURE → KG trace → spec-delta → needs_review) | ✅ |
| LE-007 | 统一 CLI: `yuleosh loop {status\|run\|config}` | ✅ |
| LE-008 | 事件/行动/结果持久化 (Store + JSON 降级) | ✅ |

## 7. 向后兼容性

- ✅ `yuleosh.knowledge_graph.events.kg_events` 完全未修改
- ✅ `yuleosh.knowledge_graph.__init__` exports 不变
- ✅ 所有现有 `cli/main.py` 命令不受影响
- ✅ 新文件仅位于 `loop_engine/` 和 `tests/loop_engine/`

---

*Iteration 1 完成。Iteration 2 (Loop 3 + Loop 4) 和 Iteration 3 (Loop 2 + 审计日志) 可接续。*
