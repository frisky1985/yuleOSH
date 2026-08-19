# Pipeline 性能基线报告 (2026-08-19)

## 数据来源
- 74 条 window-anti-pinch 真实运行 session（`.osh/sessions/*/session.json`，含 36 步时代的历史数据）+ 1 条当前 24 步 mock 运行
- 提取方式：`scripts/profile_pipeline_steps.py`（只读 session.json 的 started_at/completed_at，零侵入）

## 每步耗时分布（真实运行，按 median 降序）

| step_key | n | median(s) | mean(s) | p95(s) | max(s) | 类型 |
|---|---|---|---|---|---|---|
| **codex-verify** | 24 | **510.9** | 608.8 | 1671.5 | 1800.0 | 外部 agent |
| **development** | 51 | **156.5** | 133.5 | 257.0 | 282.0 | LLM |
| **claude-review** | 48 | **133.2** | 150.6 | 273.6 | 304.5 | 外部 agent |
| **prd** | 53 | 54.9 | 69.1 | 178.2 | 203.2 | LLM |
| test-planning | 55 | 31.3 | 34.4 | 54.0 | 56.6 | LLM |
| super-analysis | 52 | 30.2 | 30.3 | 42.0 | 45.3 | LLM |
| architecture | 51 | 30.2 | 29.6 | 39.3 | 42.7 | LLM |
| arch-review | 51 | 17.3 | 17.1 | 21.8 | 38.7 | LLM |
| final-report | 10 | 8.8 | 8.2 | 12.7 | 12.7 | LLM |
| self-test-review | 17 | 6.1 | 5.4 | 20.1 | 20.1 | LLM(并入 verify-loop) |
| code-review | 18 | 3.8 | 8.8 | 42.3 | 42.3 | LLM |
| self-test | 27 | 1.5 | 1.2 | 2.1 | 2.5 | 确定性(并入 verify-loop) |
| c-coverage-gate | 17 | 1.4 | 2.1 | 4.4 | 4.4 | 确定性(并入 qemu-verify) |
| review-bsp | 13 | 0.0* | 5.3 | 16.2 | 16.2 | LLM(36步时代) |
| 其余确定性步骤 | — | <1.0 | <1.0 | <5.0 | <5.0 | 确定性 |

*review-bsp median 显示 0.0 但 mean 5.3 — 大部分 run 无 BSP 报告(0s)，少数真实扫描 16s。

## 关键洞察

1. **LLM/外部 agent 步骤占整条 pipeline 耗时 99%+**。确定性步骤（spec-check 0.1s、review-critical-safety 0.2s、merge-gate 0.0s、qemu 0.0s）合计 <10s，可忽略。
2. **codex-verify 是绝对瓶颈**：median 8.5 分钟，p95 28 分钟，max 30 分钟（= 超时上限，即部分 run 被超时掐断）。单步占整条 pipeline 预估 60-70%。
3. **top 3 步（codex-verify + development + claude-review）合计 ~800s**，占整条运行 ~80%。
4. 合并后的 verify-loop（= self-test 1.5s + codex-verify 511s + self-test-review 6.1s）估算 ~520s；qemu-verify（= qemu-run + c-coverage-gate）<5s。
5. 整条真实 pipeline 预期墙钟：**~17 分钟**（1000s+），其中 LLM/agent 步骤 ~990s。

## 优化建议（按数据优先级）

| 优先级 | 优化 | 依据 | 预期收益 |
|---|---|---|---|
| P0 | codex-verify 超时/往返治理 | max=1800s(超时掐断), p95=1671s | 尾部 28min → 15min |
| P0 | self-test ∥ codex-verify 并行 | self-test 1.5s 与 codex-verify 511s 无依赖 | verify-loop -1.5s(边际)但验证链提前 |
| P1 | development 模型路由/repair 轮治理 | 156s median, max 282s | -30-60s |
| P1 | claude-review prompt 压缩 | 133s median, 304s max | -30-60s |
| P2 | 确定性步骤已可忽略 — 无需优化 | 全部 <10s | — |

## 复现
```bash
python3 scripts/profile_pipeline_steps.py --dir ~/workspace/window-anti-pinch/window-anti-pinch
# 新增基线: 跑一条 pipeline 后重跑脚本即可对比
```
