# CHECKPOINT — 2026-08-12 Pipeline 优化 Sprint (B1 完成)

## Session Info
- Repo: /Users/stefan/workspace/tasks/yuleOSH-check (main)
- Commits: f0f7d92a (A 批: 审查锚定+INCOMPLETE+resume+diff+三色) → e3a8e320 (B1: 步骤缓存)

## Current Task
B1 确定性步骤缓存 ✅ 完成 (sprint-contract-B1.md 全部验收通过)

## Work Completed
### A 批 (上一轮, f0f7d92a 已推)
- 审查锚定 13 handler + INCOMPLETE 传播 + --from-step + diff 聚焦 + 三色报告
- window-anti-pinch 重跑验证: 6 errors → 1, token 89K → 39.6K

### B1 (本轮, e3a8e320 已推)
- [x] step_cache.py (指纹=代码/配置/状态, 不含文档; OSH_NO_CACHE=1; 21 可缓存步骤)
- [x] orchestrator 集成 (命中→cached 标记+复用; 执行后入库; 故障回退)
- [x] 修复 review_critical_safety 返回 dict → 路径 (破坏 verdict 传播+缓存)
- [x] 修复 _tree_hash 跳过 .yuleosh 的 bug
- [x] 修复 4 个过时断言 (33→34)
- [x] 单测 +14 (test_pipeline_step_cache.py), critical-safety 测试更新
- [x] mock 端到端: 21/21 确定性步骤命中; 改 src 全失效; LLM 不缓存
- [x] 全量 12473 passed (13 failed = pre-existing coverage 环境, base 同样失败)
- [x] git push e3a8e320

## Next Steps
- B2 (LLM 步骤 opt-in 缓存, OSH_CACHE_LLM=1) 留接口, 老板需要时再开
- 真实 run 验证 B1 (非 mock): window-anti-pinch 第二次 run 应命中缓存
- 汇报老板

## 待办 (老板后续决策)
- Feishu webhook 通知: 需要老板提供 YULEOSH_NOTIFY_FEISHU_URL
- 13 个 pre-existing coverage 测试失败 (Python 3.13 环境) — 建议后续排查
