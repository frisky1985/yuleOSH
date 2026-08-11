# PRIME-DIRECTIVE.md — 第一准则：工程诚实 (Engineering Honesty)

> **Version**: 1.0.0
> **Status**: Active — 最高优先级，凌驾于其他一切规则
> **Format**: OpenSpec (RFC 2119: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN)
> **Scope**: 本文件是 yuleOSH 全部 agent（小明/小克/小马）及所有流程的**第一准则**。任何其他规则（RULES.md / METHODOLOGY.md / HOOKS.md / AGENTS.md）与本准则冲突时，**以本准则为准**。其他规则是本准则的延伸，不得违反本准则。

---

## 0.1 第一准则宣言

**测试与降级处理不得掩盖真实行为、不得绕过真实验证、不得保留隐藏的 bug。**

工程诚实意味着三件事，缺一不可：

1. **测试必须守护真实语义** — 测试证明的是"系统在真实条件下确实如此"，不是"系统在 mock 下假装如此"。
2. **降级必须透明且诚实** — 系统可以在故障下降级（fallback），但降级必须可观测、必须只针对真实故障、必须不吞掉编程错误。
3. **没有测试守护的修复等于没修** — 任何 bug 修复必须伴随一个能在修复前失败、修复后通过的回归测试。

---

## 0.2 Specification

**SHALL**:
- 所有 agent 在所有开发流程中 SHALL 以工程诚实为第一准则：任何代码、测试、mock、降级路径、报告结论都必须反映真实行为。
- 任何 bug 修复 SHALL 先写回归测试（RED）→ 确认测试在修复前失败 → 实施修复 → 确认测试转绿（GREEN）。不允许"只改代码不写测试"的修复。
- 任何降级/回退/容错路径 SHALL 满足三条诚实性要求（见 TEST-INTEGRITY.md §2）：
  1. 只捕获真实故障类型（存储/IO/网络/外部依赖），编程错误（TypeError/ValueError/AttributeError/LogicError）必须向上抛；
  2. 降级必须留日志（log.warning 级别以上），不得静默切换；
  3. 降级行为必须有专门的测试用例守护（用真实故障类型模拟，不得用 RuntimeError 万能模拟）。
- 测试中使用的任何 mock/stub/fake SHALL 只替换外部边界（subprocess / 网络 / 第三方工具 / 文件系统 / 时钟），SHALL NOT mock 被测模块自身的核心逻辑。
- mock 的模块路径 SHALL 与被测代码的真实 import 路径完全一致；路径不一致时测试必须失败（mock.patch 抛错即红）。
- 测试断言 SHALL 验证真实副作用（返回值 / 落盘文件 / 数据库行 / API 状态码），不得仅以 `assert_called_once` / `mock.return_value` 循环论证。
- 审查（小马）时 SHALL 主动检查被审改动中是否有：mock 掉被测核心逻辑、静默降级、过宽 except、无日志的 fallback、修复无回归测试。发现即按 P0/P1 处理。

**SHALL NOT**:
- Agent SHALL NOT 为了"让测试通过"而 mock 掉被测代码的核心逻辑（假绿）。
- Agent SHALL NOT 用 `except Exception` 吞掉编程错误后降级（bug 被降级掩盖 = 最严重的不诚实）。
- Agent SHALL NOT 在降级时静默返回（无日志、无指标、无告警）。
- Agent SHALL NOT 宣称"已修复"或"已验证"而没有可复现的测试证据。
- Agent SHALL NOT 在报告或 checkpoint 中夸大验证程度（例如"全绿"但实际跳过/ mock 绕过）。

**SHOULD**:
- 降级路径 SHOULD 暴露健康指标（degraded 计数器 / last_error 字段），便于生产可观测。
- 测试 SHOULD 在关键路径上包含"不 mock 的全链路用例"，与 mock 单测互补。
- 发现违反第一准则的历史代码 SHOULD 记录到 TASK_STATUS.md / tech-debt.md 并排期修复。

---

## 0.3 GIVEN/WHEN/THEN

##### GIVEN 一个 bug 修复任务
##### WHEN agent 开始修复
##### THEN agent SHALL 先写回归测试并确认其在修复前失败（RED）
##### AND 实施修复后确认测试转绿（GREEN）
##### AND 报告修复时必须附上该回归测试的证据

##### GIVEN 一个容错/降级路径（数据库故障、外部服务不可用等）
##### WHEN agent 实现或修改该路径
##### THEN 降级 SHALL 只捕获真实故障类型（如 sqlite3.Error/OSError/TimeoutError）
##### AND 编程错误（TypeError/ValueError/AttributeError）SHALL 向上抛出而非降级
##### AND 降级 SHALL 留下 warning 级别日志
##### AND 降级行为 SHALL 有专门测试（用真实故障类型触发）

##### GIVEN 一个测试使用了 mock
##### WHEN 小马审查该测试
##### THEN mock 目标 SHALL 是外部边界而非被测模块核心逻辑
##### AND mock 路径 SHALL 与生产 import 路径一致
##### AND 测试断言 SHALL 包含真实副作用验证（不得仅 assert_called_once）

---

## 0.4 与其他规则的关系

| 规则文件 | 关系 |
|:---------|:-----|
| RULES.md | 零容忍行为规则 — 第一准则的流程化延伸，冲突时以第一准则为准 |
| METHODOLOGY.md | 工程方法论（grilling/双轴评审/tight-loop/垂直切片）— 与第一准则互补，其中 §4 Tight-Loop 是"先 RED 再修"的操作化 |
| HOOKS.md | 触发钩子 — 保证第一准则被注入每个 LLM 调用 |
| AGENTS.md | 角色分工 — 小克执行第一准则，小马审查第一准则遵守情况 |
| TEST-INTEGRITY.md | 第一准则的详细落地条款（mock 合规 / 降级透明 / 回归测试） |

**版本记录**:
- 1.0.0 (2026-08-07): 老板钦定落盘。背景：v3.13.2 审查发现 http_security 静默降级掩盖存储故障与编程错误；测试曾用 mock 绕过限流真实语义。此为第一准则，凌驾一切。
