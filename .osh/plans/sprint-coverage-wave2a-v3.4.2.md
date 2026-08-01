# Sprint Contract — v3.4.2b 覆盖率 Wave 2a（大文件攻坚，除 cli/main.py）

> 创建: 2026-08-01 19:30 | 负责人: 小克 👨💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: Wave 0+1 已完成（4f3be2f，覆盖率 76%→79.31%，276 新测试）。Wave 2 按计划拆 2a/2b：2a 处理 7 个文件（除 cli/main.py），2b 单独攻坚 cli/main.py（1416 stmts）。计划全文: `~/.openclaw/workspace/reports/yuleOSH-coverage-phase2-plan.md`（Wave 2 在 146-157 行）

---

## 1. Done 标准（验收矩阵）

### B. Wave 2a 七文件攻坚（约 +4pp）
| 文件 | 基线 | 目标 | **实测（全量回归）** | 新测试文件 | 实际测试数 |
|---|---|---|---|---|---|
| api/dashboard.py (321) | 7.8% | 70% | **93%** | `test_api_dashboard_unit.py` | 51 |
| api/preview.py (329) | 56.8% | 80% | **86%** | `test_api_preview_unit.py` | 58 |
| loop_engine/cli.py (425) | 11.0% | 70% | **95%** | `test_loop_engine_cli_unit.py` | 60 |
| knowledge_graph/kg_cli.py (409) | 33.6% | 75% | **93%** | `test_kg_cli_unit.py` | 44 |
| knowledge_graph/queries_pg.py (164) | 6.2% | 70% | **95%** | `test_kg_queries_pg_unit.py` | 29 |
| knowledge_graph/store_pg.py (263) | 14.6% | 70% | **98%** | `test_kg_store_pg_unit.py` | 49 |
| autosar/stubgen.py (351) | 17.7% | 75% | **98%** | `test_autosar_stubgen_unit.py` | 52 |

- [x] B1. 七文件全部达标（全量回归 --cov 实测：dashboard 93% / preview 86% / loop_cli 95% / kg_cli 93% / queries_pg 95% / store_pg 98% / stubgen 98%）
- [x] B2. 新增测试 343 个（计划 175–235，超目标），全部通过

### D. 质量门禁
- [x] D1. 新增测试全过；全量回归无新增失败 — 9512 passed / 0 failed（基线 9169）
- [x] D2. 整体覆盖率 79.31% → **83%**（目标 ~83%）
- [x] D3. 提交推送 origin/main（cb11ab3），报告含每模块覆盖率前后对比
- [x] D4. 纯补测试为主；真实 bug 小修 3 处（store_pg 去重 / preview 死 cgi import / preview json_ok 202 崩溃），未重构

## 执行记录（小克，2026-08-01）
- commit `cb11ab3`（后续 contract 勾选提交随附）
- 全量回归命令：`python3 -m pytest tests/ -q --ignore=...（CI 等价，跳过 e2e/alpha/onboarding）` — 346s，9512 passed / 0 failed / 71 skipped / 11 xfailed
- 真实 bug 清单：
  1. `store_pg.impact_analysis` 间接需求去重按整个 dict 比较（含 confidence），同需求 direct+indirect 重复 → 改按 req_id 去重
  2. `preview._extract_zip_from_multipart` 死代码 `import cgi`（Py3.13 移除该模块）→ ZIP 上传必崩 → 删死 import
  3. `preview._handle_zip_upload/_handle_git_url` 调用 `json_ok(data, 202)`（json_ok 仅接受 1 参数）→ 202 响应必崩 → 改直接返回 (dict, 202)
- 已记录未改：`dashboard.MOCK_GAP_ANALYSIS['summary']` 死数据与实际 item 统计不一致（critical 3 vs 4 / minor 5 vs 4），代码动态计算 summary 不受影响

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

## v3.4.4 P0-A/B 终审（小明 2026-08-01 21:45）
- ✅ 通过（可发布），tag v3.4.4
- P0-A token 双格式回退 + P0-B legacy 路由回落，小马 8.5/10 复验通过
- 全量 9564 passed / 0 failed，覆盖率 82.77%，无 fail-open
