# Sprint Contract — v3.4.2b 覆盖率 Wave 2a（大文件攻坚，除 cli/main.py）

> 创建: 2026-08-01 19:30 | 负责人: 小克 👨💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: Wave 0+1 已完成（4f3be2f，覆盖率 76%→79.31%，276 新测试）。Wave 2 按计划拆 2a/2b：2a 处理 7 个文件（除 cli/main.py），2b 单独攻坚 cli/main.py（1416 stmts）。计划全文: `~/.openclaw/workspace/reports/yuleOSH-coverage-phase2-plan.md`（Wave 2 在 146-157 行）

---

## 1. Done 标准（验收矩阵）

### B. Wave 2a 七文件攻坚（约 +4pp）
| 文件 | 基线 | 目标 | 新测试文件 | 预估测试 |
|---|---|---|---|---|
| api/dashboard.py (321) | 7.8% | 70% | `test_api_dashboard_unit.py` | 30–40 |
| api/preview.py (329) | 56.8% | 80% | `test_api_preview_unit.py` | 20–30 |
| loop_engine/cli.py (425) | 11.0% | 70% | `test_loop_engine_cli_unit.py` | 30–40 |
| knowledge_graph/kg_cli.py (409) | 33.6% | 75% | `test_kg_cli_unit.py` | 30–40 |
| knowledge_graph/queries_pg.py (164) | 6.2% | 70% | `test_kg_queries_pg_unit.py` | 15–20 |
| knowledge_graph/store_pg.py (263) | 14.6% | 70% | `test_kg_store_pg_unit.py` | 20–25 |
| autosar/stubgen.py (351) | 17.7% | 75% | `test_autosar_stubgen_unit.py` | 30–40 |

- [ ] B1. 七文件全部达标（全量回归 --cov 实测，非单测口径）
- [ ] B2. 新增测试 175–235 个，全部通过

### D. 质量门禁
- [ ] D1. 新增测试全过；全量回归无新增失败（基线 9169 passed / 0 failed）
- [ ] D2. 整体覆盖率 ≥79.31% 且有提升（目标 ~83%）
- [ ] D3. 提交推送 origin/main，报告含每模块覆盖率前后对比
- [ ] D4. 纯补测试为主；发现真实 bug 可小修（记录），不重构

## 2. 范围外（不做）
- cli/main.py（Wave 2b 单独攻坚，下一轮）
- Wave 3 补漏
- 生产逻辑重构

## 3. 时间盒
- 开发 ≤ 2.5h（小克 sub-agent，可 checkpoint）
- 评估 ≤ 30min（小马，Wave 2a+2b 合并评估或 2a 单独）

## 4. 验收方式
- 小克给覆盖率前后对比表 + commit
- 小马独立验证 → 评分 → 小明终审
