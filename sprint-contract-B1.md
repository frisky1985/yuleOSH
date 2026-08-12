# Sprint Contract: Pipeline 优化 B1 — 确定性步骤内容寻址缓存

> 谈判方：Generator (Hermes) / Evaluator (Hermes 自评) / architect-lead (Hermes)
> 日期：2026-08-12
> 背景：上一 sprint 完成审查锚定（6 errors → 1，token 省 56%）。老板确认
> 方案 C（自动 hash 缓存）值得做，本期实施 **B1：确定性步骤缓存**
> （LLM 步骤不缓存——避免固化 LLM 输出，与「测试即契约」冲突）。

## Scope

### What（本期范围）
yuleOSH pipeline 自动内容寻址缓存，**只缓存确定性步骤**：
1. `step_cache.py` — 输入指纹计算（spec + artifacts + src 树 + generated-code 树 + ci-config）
2. 缓存存储 `.osh/cache/<step_key>/<fingerprint>/`（产物文件复制）
3. orchestrator 集成 — 命中拦截（标记 cached 不执行）+ 执行后入库
4. `OSH_NO_CACHE=1` 禁用开关 + cached 步骤显式标记（禁静默）
5. LLM 步骤显式排除（永不缓存）

### In Scope
- `src/yuleosh/pipeline/step_cache.py`（新建）
- `src/yuleosh/pipeline/orchestrator.py`（集成）
- 单测 `tests/test_pipeline_step_cache.py`（新建）

### Out of Scope
- LLM 步骤缓存（B2 opt-in，留接口不做）
- 跨 session 缓存清理/配额管理（.osh/cache 手动清即可）
- window-anti-pinch 项目代码

## Architecture Decision
- **可缓存步骤清单**（显式配置，确定性 = verdict 由确定性逻辑决定、无 LLM 主调用）：
  `spec-check, codegen-deploy, c-unit-test, misra-review, coverage-review,
   integration-test, qemu-run, c-coverage-gate, review-linker, review-startup,
   review-rtos, review-memory, review-bsp, review-build, review-power,
   review-stack, review-mmio, review-critical-safety, fault-injection,
   merge-gate, test-qualification`
  （嵌入式 review-* 的 LLM 附加字段不影响 verdict——产物含 llm_review 但
   status 由静态扫描决定；缓存标记 cached 且提示）
- **统一指纹**（保守）：`sha256(spec + 全部 session.artifacts + src/ 树 + generated-code 树 + ci-config.yaml)` — 任何前置变化自然失效（隐式 DAG，无需显式依赖传播）
- **缓存命中**：复制缓存产物到 session dir + `session.steps[i]["cached"]=True` + 打印 ♻️
- **执行后入库**：把输出文件复制进缓存目录
- LLM 步骤（super-analysis/prd/architecture/development/arch-review/devplan-review/internal-code-review/test-planning/self-test/self-test-review/code-review/final-report）→ 永不缓存

## Testable Behaviors
- B1.1: 相同输入重跑 → 确定性步骤全部 cached（不重编译/重扫描）
- B1.2: 改 src 文件 → 依赖步骤缓存失效重跑，其余 cached
- B1.3: `OSH_NO_CACHE=1` → 全部重跑
- B1.4: cached 产物与首次运行逐字节一致
- B1.5: LLM 步骤即使输入相同也重跑（不缓存）
- B1.6: cached 步骤在 session.json 显式标记，不静默

## Acceptance Criteria
| ID | Criterion | Pass Condition | Fail Condition | Priority | Owner |
|----|-----------|----------------|----------------|----------|-------|
| A1 | 缓存命中 | 同输入重跑确定性步骤 cached | 重跑重编译/重扫描 | P0 | Hermes |
| A2 | 失效传播 | 改 src 后相关步骤重跑 | 复用过期产物 | P0 | Hermes |
| A3 | 禁用开关 | OSH_NO_CACHE=1 全部重跑 | 开关无效 | P1 | Hermes |
| A4 | LLM 排除 | LLM 步骤永不 cached | LLM 步骤被缓存 | P0 | Hermes |
| A5 | 产物一致 | cached 产物 = 首次输出 | 内容不一致 | P0 | Hermes |
| A6 | 单测+回归 | 新增单测全绿 + 全量回归不破坏 | 红 | P0 | Hermes |

## Responsibility Matrix
| Criterion | Responsible | Fallback |
|-----------|-------------|----------|
| A1-A5 | step_cache + orchestrator | Hermes |
| A6 | Hermes | -- |

## Negotiation Log
| Round | Party | Action | Notes |
|-------|-------|--------|-------|
| 1 | Generator | 提案 B1 | 老板确认「可行」，B2 留接口 |

## Done Definition
- A1-A6 全过
- window-anti-pinch 或构造场景端到端验证：第二次 run 确定性步骤 cached
- git 推送
