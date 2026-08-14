# yuleOSH 技术债务清单

> 上次更新: 2026-06-29
> 当前状态: 1944 tests, 61% 覆盖, 0 failed
> 目标: 专家评审 ≥80/100

---

## P0 — 关键问题（阻塞性，必须修复）

### P0-1: 模块大小严重超限（~6.0K LOC）
多个核心模块远超健康阈值（500-800行），导致可维护性下降。

| 文件 | 行数 | 函数数 | 健康阈值 | 超限 |
|------|------|--------|---------|------|
| `pipeline/step_handlers/review_selftest.py` | 1,365 | 16 | <500 | **+865** |
| `pipeline/step_handlers/review_bsp.py` | 1,261 | 17 | <500 | **+761** |
| `ci/misra_report/core.py` | 1,160 | 26 | <500 | **+660** |

**影响**:
- 单文件认知负担过高，难以快速定位bug
- PR review 困难（diff 上下文动辄数百行）
- 被测模块过大导致测试复杂度上升

### P0-2: `_call_llm` 作为私有 API 被 20+ 模块依赖
`stages.py` 中的 `_call_llm`（以下划线开头=私有）被 20 个 step handler 直接导入。

**影响**:
- 重构 `stages.py` 时将波及 20+ 消费者
- 违反封装原则：私有 API 成为 de facto 公共接口
- 任何对 `_call_llm` 签名的修改都需要跨文件追踪

### P0-3: 覆盖率配置排除关键模块
`.coveragerc` 中 `omit` 排除了:

```
*/templates/*
*/hardware/*
*/cross/*
*/sil/*
*/plugins/sandbox.py
*/llm/client.py
*/_entry.py
```

这些模块合计约 **5K+ 行**完全未被测试覆盖。实际可执行代码覆盖率低于报告的 61%。

**影响**:
- 报告覆盖率具有误导性
- `hardware/*`, `cross/*`, `sil/*` 属于嵌入式工具链核心模块，测试空白风险高
- `llm/client.py` 是 AI 交互核心，零覆盖

### P0-4: `pipeline/stages.py` 模块过大（322行）且职责混杂
该模块同时承担：
- 装饰器定义（`timed_step`）
- LLM 调用（`_call_llm`）
- Spec 解析（`_parse_spec`）
- Spec 缓存管理
- 多个 `_parse_*` 辅助函数

**影响**:
- 单模块违反单一职责原则
- 被 step_handlers 广泛 import
- 导致 `from yuleosh.pipeline.stages import ...` 类型长链条 import 模式

---

## P1 — 重要问题（应在本迭代修复）

### P1-1: 16个 Step Handler 存在大量重复模式
每个 `review_*.py` 独立实现了相似的基础设施:

- JSON 序列化/反序列化
- `datetime` 时间戳格式化
- LLM Prompt 构建逻辑
- 报告生成（markdown输出）
- Error handling / 日志模式
- `@timed_step` 装饰器用法

**重复代码量估算**: 每个 handler ~80-120行样板代码 × 16文件 ≈ **1,280-1,920行冗余代码**

### P1-2: Review 模块覆盖率两极分化严重
尽管整体覆盖率达 61%，部分模块覆盖率极低：

| 模块 | 预估覆盖率 | 行数 |
|------|-----------|------|
| `review/run.py` | ~8% | 464 |
| `review/c_review.py` | ~8% | 462 |
| `report/card_generator.py` | ~6% | 283 |
| `report/trend_exporter.py` | ~0% | 457 |
| `report/feishu_notifier.py` | ~25% | 186 |

### P1-3: ASPICE 映射定义重复
相同的 ASPICE_MAP 结构在 2 个模块重复定义:

- `pipeline/step_handlers/review_selftest.py`
- `ci/misra_report/core.py`

**影响**:
- ASPICE 基线下一次更新时需要搜索修改多个文件
- 不一致风险（可能某些 handler 使用旧版本映射）

### P1-4: `ci/misra_report/core.py` 模块过大（1,160行）
该模块已从 `misra_report.py`（1,659行）拆分出 `deviation.py`, `traceability.py`, `cli.py`, `models.py`，
但 `core.py` 本身仍有 1,160 行，是二次拆分的候选人。

**影响**:
- 单一文件有 26 个函数/方法
- 同时承担 report generation, serialization, markdown rendering 等多职责

### P1-5: 测试文件也存在大型问题
| 测试文件 | 行数 |
|----------|------|
| `tests/test_ci_run_deep.py` | 2,232 |
| `tests/test_api.py` | 1,906 |
| `tests/test_hardware.py` | 1,155 |
| `tests/test_pipeline_engine.py` | 1,129 |

大型测试文件的维护成本高，且不易于针对性运行。

---

## P2 — 一般问题（后续迭代修复）

### P2-1: `from yuleosh.pipeline.stages import _try_parse_hermes_json` 依赖私有函数
`review_selftest.py` 依赖 `_try_parse_hermes_json`（私有函数）。如果该函数被重构/重命名，将破坏
review_selftest 功能。

### P2-2: `Store` 全局单例在 `stages.py` 中延迟初始化
```python
try:
    from store import Store
    _store = Store()
except Exception:
    _store = None
finally:
    # cleanup sys.path
```
这种模式在 `stages.py` 加载时即执行，且忽略异常，可能导致静默失败。

### P2-3: LLM 调用缺乏统一中间件/重试策略
`_call_llm` 在每个 handler 中被直接调用，缺乏:
- 统一的重试机制
- 速率限制
- 调用审计 / 日志
- Token 消耗追踪

### P2-4: 部分模块 import 链过长
常见 import 链:
```
orchestrator → stages → session
steps → stages (for _call_llm, _parse_spec)
```
`stages.py` 作为 hub 模块，承载了过多的跨模块职责。

### P2-5: 报告的 HTML/Markdown 生成逻辑与业务逻辑耦合
- `review_selftest.py` 中 `_generate_selftest_markdown()`（~320行）
- `misra_report/core.py` 中 `generate_markdown_report()`（~250行）
- `excel_writer.py`（815行，包含格式和导出逻辑）

报告渲染应拆分为独立的 template/renderer 层。

---

## P3 — 低优先级 / 改进建议

### P3-1: 部分模块 import 排序不一致
检查中发现部分模块 import 未遵循 PEP8 分组规范（stdlib → third-party → local）。

### P3-2: `__init__.py` 职责不统一
- 部分 `__init__.py` 有实质逻辑（如 `plugins/__init__.py` 293行）
- 部分仅为空文件（如 `cli/__init__.py` 4行）
- 建议统一为仅做 namespace 或导出公共 API

### P3-3: 测试命名需规范
测试文件名既有 `test_<module>.py` 也有 `test_<module>_deep.py` 和 `test_<module>_extended.py`，
`_deep` 和 `_extended` 后缀含义模糊，建议规范为统一标记系统（如 `[slow]` 标记）。

### P3-4: 硬编码常量和路径
各 step handler 中散落着硬编码的路径、正则表达式、错误消息，建议提取为配置文件或常量模块。

---

## 债务优先级汇总

| 优先级 | 数量 | 示例 | 建议修复时机 |
|--------|------|------|------------|
| **P0** | 4 | 模块超限, 私有API滥用, 覆盖率配置排除, stages.py 职责混杂 | **立即** |
| **P1** | 5 | 重复代码, 覆盖率两极分化, ASPICE重复, core.py二次拆分, 测试文件过大 | **本迭代** |
| **P2** | 5 | 私有函数依赖, 全局单例, LLM中间件缺失, import链, 渲染耦合 | **下个迭代** |
| **P3** | 4 | import规范, __init__统一, 测试命名, 硬编码常量 | **积压** |
