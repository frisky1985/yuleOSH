# D2 头脑风暴：orchestrator 并行执行框架

> 2026-08-19 · 状态：**已决策 → 方案 A** · 前置：D1+D3 已落地（620e3b9）
> 决策记录：[ADR-002](../adr/ADR-002-pipeline-parallel-groups.md)

## 0. 目标与约束

- **目标**：24 步 pipeline 墙钟 ~17min → ~15.5min（并行化收益 ~8-9%）
- **硬约束（老板钦定）**：不破坏 pipeline 过程——步骤顺序/产物/verdict/gate 判定语义不变
- 并行只改变**墙钟重叠**，不改变**逻辑执行序**

## 1. 依赖图（真实源码核实，2026-08-19）

```
spec-check ──► super-analysis ──► prd ──► prd-review ──┐
                                                       ├──► development ──► development-review ─┐
spec-check ──► architecture ──► arch-review ────────────┘                                      ├──► internal-code-review
                                                                                                ├──► codegen-deploy
                                                                                                ├──► claude-review
                                                                                                ▼
                                                              test-planning ◄── claude-review 结论注入
                                                                              ▼
                                                              verify-loop (self-test→codex-verify→self-test-review)
                                                                              ▼
                                                              c-unit-test → code-review → misra-review → integration-test
                                                                              → qemu-verify → coverage-review
                                                                              → review-critical-safety → fault-injection
                                                                              → merge-gate → test-qualification → final-report
```

**关键事实**（逐条源码核实）：
1. `architecture` 只读 spec + 扫描 src/**（execution.py:86-117），**不读 prd** → prd ∥ architecture 可行
2. `arch-review` 只读 architecture（review_arch.py:80）→ development 不读 arch-review（execution.py:221-223 只读 architecture/prd/super-analysis）→ arch-review ∥ development 可行
3. `development-review`/`codegen-deploy`/`internal-code-review`/`claude-review` 四者都只依赖 development 产物，互不依赖 → G3 下游四步并行可行
4. `misra-review`/`integration-test`/`qemu-verify` 都是读 codegen-deploy 后的 src，互不依赖 → 可并行（但都 <10s，收益小）
5. `test-planning` 依赖 claude-review 结论注入（2026-08-19 三轮决策）→ 不可提前
6. `verify-loop` 内部 self-test 产物喂给 codex-verify（_collect_spec_and_artifacts 含 self-test）→ 内部不可并行（self-test 仅 1.5s，无收益）
7. `review-critical-safety` 是 P0 门禁（block gate）→ 不与其后 fault-injection 并行（失败则浪费）

## 2. 并行候选与收益估算

| # | 并行组 | 串行耗时 | 并行耗时 | 收益 | 风险 |
|---|---|---|---|---|---|
| P1 | prd ∥ architecture | 55+30=85s | ~55s | **~30s** | 低（无共享写） |
| P2 | arch-review ∥ development | 17+156=173s | ~156s | **~17s** | 低 |
| P3 | development-review ∥ codegen-deploy ∥ internal-code-review ∥ claude-review | 20+5+10+133=168s | ~133s | **~35s** | 中（session 状态并发） |
| P4 | misra-review ∥ integration-test ∥ qemu-verify | ~15s | ~8s | ~7s | 低 |
| 合计 | | | | **~80-90s（8-9%）** | |

> 注：真实收益需 24 步时代基线验证（当前基线是 36 步时代的，D1/A/B 已改变耗时分布）。

## 3. 方案选项

### 方案 A（推荐）：选择性并行——只并行 P1+P2+P3 三个高收益组
- orchestrator 主循环改为「按依赖序推进，遇到并行组用 ThreadPoolExecutor 并发跑组内步骤」
- 并行组内步骤写入**不同 artifact key**（天然无写冲突）
- session 状态更新（add_step/start_step/complete_step/_save）加 `threading.Lock`
- **失败语义**：组内任一 failed/block → 等待组内全部结束 → 按最差状态聚合（与 verify-loop 合并语义一致）→ 中断后续
- 改动面：orchestrator.py 循环改造 + session.py 加锁 + 新增并行组声明表
- 测试：mock pipeline 全绿 + 新增并行组单元测试

### 方案 B（激进）：完整 DAG 调度器
- 每步声明 reads/writes，拓扑排序 + 就绪队列
- 收益最大化，但改动面大、回归风险高、违背"不破坏"精神 → 不推荐现在做

### 方案 C（保守）：先观测再决定
- D1/D3 落地后跑 1-2 条真实 pipeline，拿 24 步基线 + 验证 A/B/D1 实际收益
- 用数据确认并行收益是否值得改造 → 数据驱动

## 4. 并发安全清单（方案 A 必须处理）

1. `session.steps` append/索引 → 加锁；并行组步骤的 step_idx 在主线程预分配
2. `session.artifacts` dict 写 → 不同 key 无冲突，但 dict 本身加锁
3. `session._save()` 写 session.json → 加锁；并行组内只保存各自 step 状态
4. LLM 调用并发 → DeepSeek API 限流需确认（YULEOSH_LLM_GATEWAY_STEPS 已有 token 预算）
5. codegen-deploy 写 src/ → 并行组内其他步骤只读 artifact 文件，不碰 src/ → 安全
6. step_cache 并发 → P3 组内步骤都是 LLM 步骤（永不缓存）→ 无冲突

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 并发 LLM 调用触发 API 限流 | 并行组最多 4 个并发；gateway 已有预算检查；失败按串行重试 |
| session.json 竞态写坏 | 全局锁 + 并行组内不写共享字段 |
| 失败语义变化 | 组内等待全部结束再聚合（不提前 kill），与 verify-loop 一致 |
| 真实收益低于估算 | 方案 C 的观测先跑，验证后再实施 |

## 6. 建议

**先做方案 C 的观测**（跑 1 条真实 pipeline 拿 24 步基线），同时**准备方案 A 的并行组声明表**（P1+P2+P3）。基线确认收益后，方案 A 落地（改动集中在 orchestrator.py + session.py，约 1 天）。

不推荐方案 B（完整 DAG）——当前 24 步已是最小合理下限，DAG 调度器的复杂度不值得 8-9% 的收益。
