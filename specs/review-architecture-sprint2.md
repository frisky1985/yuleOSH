# Sprint 2 架构审查报告

> **审阅人**: 小马 🐴 (质量架构师)  
> **审阅对象**: specs/architecture-sprint2.md v1.0.0  
> **基于**: specs/acceptance-matrix-sprint2.md  
> **审查重点**: 可测试性、接口契约一致性、SHALL/SHOULD/MAY 对齐  
> **审查结论**: **有条件通过** — 3 个 SHALL 级阻塞项已在架构层面解决，2 个 SHOULD 级建议可在编码阶段处理

---

## 1. 审查概要

| 维度 | 评分 | 评语 |
|:-----|:----:|:------|
| 可测试性 | ⭐⭐⭐⭐⭐ | 模块隔离清晰，依赖注入到位，mock 策略全面。**亮点：** session.py 零外部依赖，完美可隔离测试 |
| 接口契约一致性 | ⭐⭐⭐⭐ | 模块边界和导出清单明确，但缺正式函数签名文档（AC-02/03-05 SHOULD 级） |
| SHALL 对齐 | ⭐⭐⭐⭐⭐ | 全部 SHALL 级要求已覆盖，4 模块拆分方案理由充分（原 3 模块超 900 行） |
| 向后兼容 | ⭐⭐⭐⭐⭐ | re-export 全覆盖，测试文件零修改。old/new 双导入路径均验证 |
| 风险识别 | ⭐⭐⭐⭐⭐ | 循环依赖风险已识别并缓解（共享类型→session.py），行数超限有备选方案 |

---

## 2. 可测试性审查

### ✅ 通过项

| 检查项 | 判定 | 理由 |
|:-------|:----:|:------|
| 模块是否可独立测试 | ✅ | session.py 零外部依赖，steps.py 仅依赖 session.py，orchestrator.py 依赖 session+steps |
| 是否支持 mock | ✅ | ExitStack 批量 mock + tmp_path fixture，LLM/subprocess/IO 全可 mock |
| 异常路径是否可测 | ✅ | TestE2EError 覆盖无效 spec 和 LLM 异常路径 |
| 性能门禁是否可测 | ✅ | 30s 断言 + pytest-timeout 或 time.monotonic |
| 拆分后 cross-module 测试保障 | ✅ | Phase 4 全量回归 + 不退化验证 |

### ⚠️ 建议

| # | 位置 | 建议 | 级别 |
|:--|:-----|:-----|:----:|
| T-01 | `_call_llm` | 被 orchestrator 和 steps 同时导入。考虑提到 prompts.py 或 session.py 避免跨模块拆解模糊 | 🟢 SHOULD |

---

## 3. 接口契约一致性审查

### ✅ 通过项

| 检查项 | 判定 | 理由 |
|:-------|:----:|:------|
| 模块职责是否明确 | ✅ | 每个模块有"职责"+"导出"+"不导出"三栏定义 |
| 依赖图是否无环 | ✅ | pipeline: orchestrator→steps→session, ci: runner→layers→stages→config, 均无循环 |
| 是否保留向后兼容 | ✅ | re-export 全覆盖，支持新路径和旧路径双导入 |
| re-export 是否覆盖所有 API 消费者 | ✅ | 列出了每种导入路径的验证测试 |

### ⚠️ 建议

| # | 位置 | 建议 | 级别 |
|:--|:-----|:-----|:----:|
| I-01 | AC-02/03-05 | 接口形式化定义（函数签名/类型/异常）未在架构文档中体现。建议在代码层强制 type annotation + docstring 覆盖导出函数，编码后 CI 门禁可验证 | 🟡 SHOULD |

---

## 4. SHALL/SHOULD/MAY 对齐矩阵

| 验收条件 | 对齐判定 | 架构中对应 | 备注 |
|:---------|:--------:|:-----------|:-----|
| AC-01-01 | ✅ SHALL | TestE2ENormal: spec→pipeline→evidence 全链路 | 10 个 step 全覆盖 |
| AC-01-01a | ✅ SHALL | — | 分支覆盖 ≥70% 为全局 CI 门禁，非 E2E 单测门禁（已在验收矩阵说明） |
| AC-01-01b | ✅ SHOULD | — | 同上，行覆盖 ≥80% 全局 CI 门禁 |
| AC-01-02 | ✅ SHALL | mock 策略表全覆盖 5 项依赖 | LLM/subprocess/IO/Store/Notify |
| AC-01-03 | ✅ SHOULD | 步骤数覆盖率记录在 TestE2ENormal | 断言 `session.steps` 全部 completed |
| AC-01-04 | ✅ SHALL | TestE2EError: 无效 spec 路径 | 异常捕获 + 不崩溃 |
| AC-01-05 | ✅ SHALL | TestE2EError: LLM mock 异常 | step failed + session failed + 不抛未捕获异常 |
| AC-01-06 | ✅ SHOULD | TestE2EPerformance: 30s 断言 | 使用 ExitStack 批量 mock 控制开销 |
| AC-02-01 | ✅ SHALL | orchestrator/steps/session 3 模块 | — |
| AC-02-02 | ✅ SHALL | 各模块预估 ≤500 行 | 最大 steps.py ~450 行 |
| AC-02-04 | ✅ SHOULD | re-export 保留导入兼容 | 11 条导入路径已验证 |
| AC-02-05 | ⚠️ SHOULD | 接口导出已定义，形式化签名缺失 | 见 I-01 |
| AC-02-06 | ⚠️ SHOULD | 圈复杂度门禁未在架构中体现 | 编码后 radon 检查即可 |
| AC-02-07 | ✅ MAY | run.py re-export + __init__.py | — |
| AC-03-01 | ✅ SHALL | runner/layers/stages/config 4 模块 | 超 spec 原 3 模块，理由充分 |
| AC-03-02 | ✅ SHALL | 各模块预估 ≤500 行 | 最大 layers.py ~480 行 |
| AC-03-04 | ✅ SHOULD | Layer 逻辑隔离在 layers.py | — |
| AC-03-05 | ⚠️ SHOULD | 接口导出已定义，形式化签名缺失 | 见 I-01 |
| AC-03-06 | ⚠️ SHOULD | 圈复杂度门禁未在架构中体现 | 编码后 radon 检查即可 |
| AC-04-01 | ✅ SHALL | Phase 2: 全量 pytest 不退化验证 | — |
| AC-04-02 | ✅ SHALL | Phase 3: pytest -k "ci" 不退化验证 | — |

**对齐率**: 22/22 条全部有对应方案 ✅  
**其中 SHOULD 级未在架构层完整落地**: 3 条（AC-02-05, AC-03-05 接口文档, AC-02/03-06 圈复杂度），均可编码阶段补齐

---

## 5. 关键发现

### 🟢 亮点：ci 4 模块拆分决策

> 小克主动将 ci/run.py 从 spec 原定的 3 模块改为 4 模块（stages.py + layers.py 拆分），理由充分：若只拆 3 块，layers.py 含所有 stage 函数将超 900 行 >500 约束。这是对 ≤500 行约束的正确延伸，属质量合规范围内的弹性调整。记入架构决策日志。

### 🟢 亮点：实施顺序设计

> Phase 1 E2E 测试完全不依赖拆分工作，可并行推进。这是良好的并行化策略，Phase 1 可以独立 CI 验证。建议小克优先跑 Phase 1 获取 E2E 基线。

### 🟡 待关注：AC-02/03-05 接口形式化定义

> 架构中写了"导出/不导出"清单，但缺少每个导出函数的签名定义（参数类型、返回值类型、异常类型）。SHOULD 级要求，编码时强制 type annotation + docstring 即可，不需要为此阻塞架构审查。

---

## 6. 结论

**审查结论: 有条件通过 ✅**

| 类别 | 数量 | 详情 |
|:-----|:----:|:------|
| 🟢 通过 | 20/22 | 所有 SHALL 级 + 17 条 SHOULD/MAY 已对齐 |
| 🟡 建议 | 3 | T-01 (_call_llm 位置), I-01 (接口签名文档), radon 圈复杂度 |
| 🔴 阻塞 | 0 | 架构层面无影响质量门禁的阻塞项 |

**实施建议：**
1. 优先跑 Phase 1（E2E 测试），独立于拆分并行进行
2. 编码时对每个导出函数加完整 type annotation + docstring
3. 拆分完成后跑 `radon cc` 检查圈复杂度基线
4. 全量回归通过后即可关闭 Sprint 2 验收矩阵

---

*审查人: 小马 🐴 | 2026-06-14 | 修改记录可追溯至 git commit*
