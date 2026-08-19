# B 项评估结论：模型路由与 prompt 优化空间 (2026-08-19)

## 背景
B 项原计划 = development/claude-review 模型路由 + prompt 压缩。
基线数据：development median 156s（单次生成，无 repair 循环）、
claude-review median 132s（单次评审，40 turns 上限通常用不到）。

## 结论 1：模型路由无安全下钻空间（已实证）

- 内部 LLM 步骤 `deepseek-v4` 逻辑名 → DeepSeek API 层映射为
  `deepseek-chat`（providers/deepseek.py MODEL_ALIASES）——**已经是
  DeepSeek API 标准模型**，无更小可用。
- 外部 agent（codex/claude CLI）实际用 deepseek-v4-flash（更快）。
- 2026-08-08 评审硬规则：L3/L4 判定任务（审查/设计决策）禁止下钻
  SMALL_MODELS（deepseek-chat/v3/haiku/4o-mini）。当前 AGENT_MODEL_ROUTES
  全部 agent 路由 L3/L4 → **路由表内无安全降级路径**。
- 换 provider（anthropic/openai）是成本/质量决策，不是性能优化。

## 结论 2：prompt 压缩已有两轮，剩余空间需真实质量验证

已完成：
- `truncate_with_reference_marker`（头尾保留 + 省略标记 + 文件路径提示，
  外部 agent 可自主读全文）——claude-review/codex-verify 均接入
- `_official_shall_block`（SHALL 单一事实来源，最多 40 条）
- codex prompt 第 5 条「发现即停止」（A 项，已提交 21ca408）

剩余可选（需真实 pipeline 验证质量，花钱）：
- development prompt：只喂 spec + SHALL 清单 + architecture 摘要，省略
  PRD 全文 → 预计省 30-60s，但风险 = 开发计划脱离 PRD 细节
- claude-review prompt：省略 test-planning 全文（评审对象是方案不是
  测试计划）→ 预计省 10-20s，风险低

## 建议
- B 项收敛为「claude-review 省略 test-planning」低风险压缩（可做可不做，
  收益 10-20s）；
- development 的 PRD 摘要化风险较高，不建议默认做，除非老板接受
  真实 pipeline 验证成本。
- 性能大头已由 A 项覆盖（codex-verify 失败路径 900-1800s → 预期大幅
  缩短）。整条 pipeline 预期从 ~17min 降到 ~12min（A 生效后）。

## 复现数据
```bash
python3 scripts/profile_pipeline_steps.py --dir ~/workspace/window-anti-pinch/window-anti-pinch
```
