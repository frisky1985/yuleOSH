# Sprint Contract — v3.4.2 覆盖率 Wave 0 + Wave 1 攻坚

> 创建: 2026-08-01 18:55 | 负责人: 小克 👨💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: v3.4.1 已放行（tag v3.4.1）。真实覆盖率基线 76%（小马事实修正），按 Phase 2 计划（76→85）开 Wave 0 快赢 + Wave 1 清零。计划全文: `~/.openclaw/workspace/reports/yuleOSH-coverage-phase2-plan.md`

---

## 1. Done 标准（验收矩阵）

### A. 前置：2 个 kg 测试全量豁免（P1，终审附带措施）
- [ ] A1. `test_kg_ci_append_without_files` + `test_ci_hook_fallback_no_osh_home`：全量跑时加豁免（perf 标记 或 更高 timeout 配置），单跑仍可验证
- [ ] A2. 说明豁免方式并验证（全量 CI 口径不再误报）

### B. Wave 0 快赢（≤1 天，清 0% 小模块，约 +1.1pp）
- [ ] B1. `audit/model.py` (122 stmts, 0%) → `test_audit_model_unit.py` ≥80% (10–12 tests)
- [ ] B2. `billing/metering.py` (161, 0%) → `test_billing_metering_unit.py` ≥80% (12–15)
- [ ] B3. `rbac/model.py` (82, 0%) → `test_rbac_model_unit.py` ≥80% (8–10)
- [ ] B4. `tenant/model.py` (139, 32.9%) → `test_tenant_model_unit.py` ≥80% (10–12)
- [ ] B5. 小计 508 stmts / 4 文件 → ~80%，40–50 测试

### C. Wave 1 0% 大文件清零（约 +3pp）
- [ ] C1. `api/loops.py` (52, 0%) → ≥85% (8–10 tests)
- [ ] C2. `cli/commands/init.py` (40, 0%) → ≥80% (8–10)
- [ ] C3. `cli/commands/template.py` (36, 0%) → ≥80% (8–10)
- [ ] C4. `pipeline/config_validator.py` (137, 0%) → ≥85% (15–18)
- [ ] C5. 其他 Wave 1 清单 0% 文件（按计划表补完）

### D. 质量门禁
- [ ] D1. 新增测试全部通过；全量回归无新增失败（对比基线 8961 passed）
- [ ] D2. 覆盖率验证：整体 ≥76% 且有提升；目标模块达标（用 --cov 分模块确认）
- [ ] D3. 提交推送 origin/main，报告含 commit hash + 每模块覆盖率前后对比

## 2. 范围外（不做）
- Wave 2（大文件攻坚 cli/main.py 等）/ Wave 3（补漏）——下一轮
- 不改生产逻辑（纯补测试；如发现真实 bug 记录不擅自重构）

## 3. 时间盒
- 开发 ≤ 3h（小克 sub-agent，可 checkpoint）
- 评估 ≤ 30min（小马）

## 4. 验收方式
- 小克给覆盖率前后对比表 + commit
- 小马独立验证目标模块覆盖率 + 全量无回归 → 评分 → 小明终审
