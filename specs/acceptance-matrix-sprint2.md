# Sprint 2 验收矩阵 — Acceptance Matrix

> **版本**: v1.0.0 | **基于**: specs/spec-delta-sprint2.md  
> **维护人**: 小马 🐴 (质量架构师)  
> **规范文体**: RFC 2119 (SHALL / SHOULD / MAY)  
> **门禁模式**: CI 自动化 + 人工审阅

---

## 审查摘要

| # | 发现 | 类型 | 严重度 | 状态 |
|:--|:-----|:----|:------:|:----:|
| R-01 | AC-01 "覆盖率"定义模糊（行/分支/步骤？） | 歧义 | 🟡 中 | ⚠️ 待作者确认 |
| R-02 | AC-04 "不退化"缺少量化指标 | 不完整 | 🟡 中 | ⚠️ 已补充 |
| R-03 | 模块拆分缺少接口合约要求 | 缺失 | 🟡 中 | ⚠️ 已补充 |
| R-04 | E2E 测试缺少运行时间门禁 | 缺失 | 🟢 低 | ⚠️ 已补充为 SHOULD |
| R-05 | AC-01 缺少场景路径清单 | 粒度不足 | 🟡 中 | ⚠️ 已细化 |
| R-06 | AC-02/03 缺少代码质量门禁（圈复杂度） | 缺失 | 🟢 低 | ⚠️ 已补充 |

---

## S2-REQ-001: E2E 全流程集成测试

| 需求 ID | 类型 | SHALL/SHOULD/MAY 语句 | 验收条件 ID | 场景路径 | 验证方式 | 门禁 | 状态 |
|:--------|:---:|:----------------------|:-----------:|:---------|:---------|:----:|:----:|
| S2-REQ-001.1 | SHALL | 提供全 mock 的 E2E 测试，从 spec 输入到 evidence pack 产出 | AC-01-01 | 正常路径：有效 OpenSpec → pipeline 全流程 → evidence 产出 | `pytest tests/test_e2e_pipeline.py -v` CI 门禁 | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-001.2 | SHALL | mock 所有外部依赖（LLM, subprocess, 文件系统 IO） | AC-01-02 | 隔离验证：确认无真实外部调用 | `pytest --coverage` + 人工审阅 monkeypatch 清单 | 🟡 警告 | ⚪ 未开始 |
| S2-REQ-001.3 | SHOULD | 覆盖至少 80% pipeline 步骤（指步骤数覆盖，非行覆盖） | AC-01-03 | — | CI 输出步骤覆盖率日志 | 🟢 参考 | ⚪ 未开始 |
| S2-REQ-001.4 | SHALL | 无效 spec 输入场景：E2E 测试 SHALL 包含无效 spec 路径 | AC-01-04 | 异常路径：无效/空 spec → 报错且不崩溃 | `pytest` 异常断言 | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-001.5 | SHALL | mock 失败场景：E2E 测试 SHALL 包含依赖 mock 返回异常的场景 | AC-01-05 | 异常路径：LLM call mock 抛出异常 → pipeline 优雅降级 | `pytest` 异常断言 | 🟡 警告 | ⚪ 未开始 |
| S2-REQ-001.6 | SHOULD | E2E 测试全流程执行时间不超过 30 秒 | AC-01-06 | 性能门禁 | CI 计时断言 | 🟢 参考 | ⚪ 未开始 |

### GIVEN/WHEN/THEN 映射

| # | GIVEN | WHEN | THEN | 关联 AC |
|:--|:------|:-----|:-----|:-------:|
| GWT-01 | 有效 OpenSpec 文件作为输入 | pipeline 以 mock 依赖全流程运行 | 每步产出成功/失败状态 | AC-01-01 |
| GWT-02 | 配置了所有 3 个 CI Layer 的测试 spec | CI runner 执行 L1/L2/L3 | 每层产出 PASS/FAIL 状态 | AC-01-01 |
| GWT-03 | 已完成 pipeline session | 触发 evidence pack 步骤 | 产出 evidence 摘要 | AC-01-01 |
| GWT-04 | 输入为无效 spec 文件 | pipeline 启动 | 报错且进程不崩溃 | AC-01-04 |
| GWT-05 | LLM 调用 mock 抛出异常 | pipeline 执行到 review 步骤 | 优雅降级（捕获异常，标记失败） | AC-01-05 |

---

## S2-REQ-002: pipeline/run.py 模块拆分

| 需求 ID | 类型 | SHALL/SHOULD/MAY 语句 | 验收条件 ID | 验证方式 | 门禁 | 状态 |
|:--------|:---:|:----------------------|:-----------:|:---------|:----:|:----:|
| S2-REQ-002.1 | SHALL | 拆分为至少 3 个模块：orchestrator, steps, session | AC-02-01 | `python -c "import yuleosh.pipeline.orchestrator, yuleosh.pipeline.steps, yuleosh.pipeline.session"` + 人工审阅 | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-002.2 | SHALL | 各模块 ≤500 行（含注释和空行） | AC-02-02 | `find src/yuleosh/pipeline -name '*.py' -exec wc -l {} + | awk '$1 <= 500'` CI 门禁 | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-002.3 | SHALL | 所有现有测试不退化，通过率 100% | AC-04-01 | `pytest tests/ -q --ignore=tests/test_e2e.py` 100% PASS | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-002.4 | SHOULD | 公共 API 保持向后兼容 | AC-02-04 | 对比拆分前后的 `__all__` 或公开函数签名 | 🟡 警告 | ⚪ 未开始 |
| S2-REQ-002.5 | SHOULD | 模块间接口应有形式化定义（参数类型/返回值/异常） | AC-02-05 | 人工审阅接口文档/类型注解 | 🟡 警告 | ⚪ 未开始 |
| S2-REQ-002.6 | SHOULD | 拆分后模块的圈复杂度不高于拆分前 | AC-02-06 | `radon cc src/yuleosh/pipeline/` 对比 | 🟢 参考 | ⚪ 未开始 |
| S2-REQ-002.7 | MAY | 通过 re-export 保留原有 import 路径 | AC-02-07 | `python -c "from yuleosh.pipeline import run"` 能正常导入 | 🟢 参考 | ⚪ 未开始 |

---

## S2-REQ-003: ci/run.py 模块拆分

| 需求 ID | 类型 | SHALL/SHOULD/MAY 语句 | 验收条件 ID | 验证方式 | 门禁 | 状态 |
|:--------|:---:|:----------------------|:-----------:|:---------|:----:|:----:|
| S2-REQ-003.1 | SHALL | 拆分为至少 3 个模块：runner, layers, config | AC-03-01 | `python -c "import yuleosh.ci.runner, yuleosh.ci.layers, yuleosh.ci.config"` + 人工审阅 | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-003.2 | SHALL | 各模块 ≤500 行 | AC-03-02 | `find src/yuleosh/ci -name '*.py' -exec wc -l {} + | awk '$1 <= 500'` CI 门禁 | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-003.3 | SHALL | 所有现有 CI 测试不退化，通过率 100% | AC-04-02 | `pytest tests/ -q -k "ci"` 100% PASS | 🔴 阻塞 | ⚪ 未开始 |
| S2-REQ-003.4 | SHOULD | Layer 专用逻辑隔离到 layers.py | AC-03-04 | 人工审阅 layers.py 中是否包含 L0/L1/L2/L2.5/L3 逻辑 | 🟡 警告 | ⚪ 未开始 |
| S2-REQ-003.5 | SHOULD | 模块间接口应有形式化定义 | AC-03-05 | 人工审阅接口文档/类型注解 | 🟡 警告 | ⚪ 未开始 |
| S2-REQ-003.6 | SHOULD | 拆分后模块圈复杂度不高于拆分前 | AC-03-06 | `radon cc src/yuleosh/ci/` 对比 | 🟢 参考 | ⚪ 未开始 |

---

## 验收条件总表

| AC ID | 描述 | SHALL/SHOULD/MAY | 关联需求 | 门禁类型 | 门禁值 | 负责人 |
|:------|:-----|:--------------:|:---------|:--------:|:------:|:------|
| AC-01-01 | E2E mock 测试通过，spec→pipeline→evidence 全链路 | SHALL | S2-REQ-001.1 | CI pytest | 100% PASS | 小克 |
| AC-01-02 | 所有外部依赖已 mock（无真实 LLM/subprocess/IO 调用） | SHALL | S2-REQ-001.2 | 人工审阅 + CI 桩 | 零真实调用 | 小克 |
| AC-01-03 | Pipeline 步骤覆盖率 ≥80% | SHOULD | S2-REQ-001.3 | CI 日志输出 | ≥80% | 小克 |
| AC-01-04 | 无效 spec 输入异常路径覆盖 | SHALL | S2-REQ-001.4 | CI pytest | 100% PASS | 小克 |
| AC-01-05 | Mock 失败优雅降级路径覆盖 | SHALL | S2-REQ-001.5 | CI pytest | 100% PASS | 小克 |
| AC-01-06 | E2E 测试执行时间 ≤30s | SHOULD | S2-REQ-001.6 | CI 计时 | ≤30s | 小克 |
| AC-02-01 | pipeline 拆为 3 模块 | SHALL | S2-REQ-002.1 | 人工审阅 | 3 模块 | 小克 |
| AC-02-02 | pipeline 各模块 ≤500 行 | SHALL | S2-REQ-002.2 | CI 行数门禁 | ≤500 | 小克 |
| AC-02-04 | pipeline 公共 API 向后兼容 | SHOULD | S2-REQ-002.4 | 人工审阅 | 兼容 | 小克 |
| AC-02-05 | pipeline 模块间接口形式化定义 | SHOULD | S2-REQ-002.5 | 人工审阅 | 有文档 | 小克 |
| AC-02-06 | pipeline 圈复杂度不增长 | SHOULD | S2-REQ-002.6 | radon CI | ≤原值 | 小克 |
| AC-02-07 | pipeline 保留 re-export 兼容 | MAY | S2-REQ-002.7 | CI 导入测试 | 可导入 | 小克 |
| AC-03-01 | ci 拆为 3 模块 | SHALL | S2-REQ-003.1 | 人工审阅 | 3 模块 | 小克 |
| AC-03-02 | ci 各模块 ≤500 行 | SHALL | S2-REQ-003.2 | CI 行数门禁 | ≤500 | 小克 |
| AC-03-04 | ci Layer 逻辑隔离到 layers.py | SHOULD | S2-REQ-003.4 | 人工审阅 | 隔离 | 小克 |
| AC-03-05 | ci 模块间接口形式化定义 | SHOULD | S2-REQ-003.5 | 人工审阅 | 有文档 | 小克 |
| AC-03-06 | ci 圈复杂度不增长 | SHOULD | S2-REQ-003.6 | radon CI | ≤原值 | 小克 |
| AC-04-01 | pipeline 拆分后所有现有测试 100% PASS | SHALL | S2-REQ-002.3 | CI pytest | 100% | 小克 |
| AC-04-02 | ci 拆分后所有 CI 测试 100% PASS | SHALL | S2-REQ-003.3 | CI pytest | 100% | 小克 |

---

## 审查意见汇总（回复小明）

| # | 位置 | 意见 | 建议 |
|:--|:-----|:-----|:-----|
| ① | AC-01 | "覆盖率≥80%"定义不明确 | 已在我的验收矩阵中明确为"**步骤数覆盖率**"，建议 spec 原文同步注明 |
| ② | AC-04 | "所有现有测试不退化"缺少量化 | 已补充"100% PASS"和分模块拆解（AC-04-01/02） |
| ③ | S2-REQ-002/003 | 模块拆分后接口合约无要求 | 已补充 SHOULD 级接口形式化定义要求（AC-02-05 / AC-03-05） |
| ④ | S2-REQ-001 | E2E 缺少异常场景 | 已补充无效 spec 和 mock 失败两个异常路径（AC-01-04/05） |
| ⑤ | AC-02/03 | 仅行数要求不够 | 已补充圈复杂度不增长门禁（AC-02-06 / AC-03-06） |

---

## 版本历史

| 版本 | 日期 | 变更说明 | 审批人 |
|:----|:----|:---------|:------|
| v1.0.0 | 2026-06-14 | 初始版本：基于 spec-delta-sprint2.md 的完整验收矩阵 + 审查意见 | 小马 🐴 |

---

*本文档使用 RFC 2119 规范语言。SHALL 级条件阻塞 Sprint 验收，SHOULD 级优先完成，MAY 级可选。*
