# Plan — yuleOSH v3.8.0（Track2 架构收敛）开发计划 / Checkpoint 记录

> 开发: 小克 · 契约: 小马（.osh/specs/v3.8.0/，HEAD=14d4af5）· 终审: 小明
> 基线: v3.7.0 (2e0eef5) — 9873 passed / 0 failed，覆盖率 84.10%
> 裁决: 附录 B 七项（B1 auth_extended 为基 / B2 删 ring / B3 仅 /api/ 入表 / B4 POST 405 保持 / B5 event_bus 持久化显式移除 / B6 前端产物不重建 / B7 复数资源注册）

## 批次设计（依赖驱动）

| 批次 | 内容 | 依赖 | 局部回归 | 状态 |
|------|------|------|----------|------|
| P0 | A1 Step 0-1（secret 单一来源 + F1） | 无 | auth/subscription/wizard 测试 | ⏳ |
| P1 | A1 Step 2（middleware verify 统一） | P0 | test_security + require_auth 面 | ⏳ |
| P2 | A1 Step 3-5（handler 委托 + 删重复 + 全量） | P1 | test_api_auth_* + 前端登录链 E2E | ⏳ |
| P3 | A2（审计统一）+ A3（路由去双轨） | 独立 | test_api_audit_ext + test_security | ⏳ |
| P4 | A4（Store 补方法） | 可与 A2 合并 | test_store_pg_deep + project/stats | ⏳ |
| P5 | A5（CLI 拆分）+ F3/F4 | 无 | test_cli_* + test_ui_server_deep | ⏳ |
| P6 | A6（dashboard 拆组件）+ F2 | A1 完成后 | npm build + tsc + 手工 | ✅ |

## Checkpoints

### P0 ✅（2026-08-03）A1 Step 0-1 + F1
- Commits: `15515f0`（Step 0 F1 subscription/wizard secret 单一来源）、`4c4c7e3`（Step 1 secret 单一来源，auth_extended 为基）
- 测试：auth/subscription/wizard 相关 96 passed；全量 auth 子集 548 passed

### P1 ✅（2026-08-03）A1 Step 2 middleware verify 统一
- Commit: `2848514`
- 新增 `ui/auth_extended.verify_token`（统一 verify，双格式兼容，判定与 v3.7.0 一致）
- middleware require_auth 改调 verify_token；`_decode_token` 退化为薄委托
- 测试：middleware/supplementary/v344/pipeline_trigger/onboarding 全绿（适配 patch 目标）

### P2 ✅（2026-08-03）A1 Step 3-5 handler 委托 + 删重复 + 全量
- Commits: `c5b2dd5`（Step 3-4）、`5959094`（Step 5 前置 T-A1 验收测试）、`536e1f1`（修复全量 8 项）
- auth_extended 新增统一 register；api/auth.py 重构为 v1 契约适配层；删除重复实现（T-A1-15 零命中）
- 新增 tests/test_v380_a1_auth_unify.py 18 用例（T-A1-01..15 含负例）
- 全量回归：**9891 passed / 0 failed**（基线 9873 +18）；`token_urlsafe(32)` grep 零命中

### P3 ⏳ A2 审计统一 + A3 路由去双轨
- 裁决：B2 删 ring / B3 仅 /api/ 入表 / B4 POST 405 保持 / B5 event_bus 显式移除

---

### P3 ✅（2026-08-03）A2 审计统一 + A3 路由去双轨（commit b7c9aff）
- A2：handler_helpers.log_audit 走 api.audit.log_request（DB 统一写路径），仅 /api/ 入表（B3）；删 server 内存 ring（B2）；event_bus 持久化分支显式移除（B5）；删 audit_routes.py（JSONL 死代码）；POST /api/v1/audit 保持 405（B4）
- A3：tenant/billing/projects 复数资源注册（B7）；删 _dispatch_legacy；handler_helpers 死分支清理
- 新增 T-A2-* 12 + T-A3-* 14；局部回归 607 passed

### P4 ✅（2026-08-03）A4 Store 补方法（commit ac5fc8b）
- store/store_pg/store_interface 三实现同步 +6 方法；api/project+stats 裸 SQL 清零
- 新增 T-A4-* 9；局部回归 444 passed；grep conn.execute 零命中

### P5 ✅（2026-08-03）A5 CLI 拆分 + F3/F4（commit 1334ead）
- cli/main.py 2873→851 行；4 命令组 + misc 拆分；tests/ 200 文件 sys.path.insert 清理
- F3 do_POST/DELETE _response_status=500；F4 _serve_file HTML no-cache
- 新增 T-A5-* 10 + T-F3/F4 6；**全量回归 9944 passed / 0 failed**（基线 9873 +71）

### P6 ✅（2026-08-03）A6 dashboard 拆组件 + F2（commit fa5131c）
- 5 叶子组件提取（MiniCoverageBar/SWECard/EvidenceModal/KnowledgeBaseTab/MisraTrendsTab）；page.tsx 1972→1160 行
- 清理 page.tsx 残留未使用 import（getKBArticles/getFMEAEntries/getMISRATrend）
- F2 _get_user_key 注释收敛（JWT 恒走 u:<user_id>）
- 新增 T-A6-* 6 + T-F2-* 4；tsc 零错误 + jest 29/29
- 注：小克 session 在 A6 测试适配前中断，小明收尾（删残留 import + 提交 fa5131c）

## 全量验证（2026-08-03 小明收尾）
- **全量回归：10019 passed / 0 failed**（本地全量收集口径；基线 9873 → P5 9944 → P6 10019，只增不减；119 skipped / 11 xfailed）
- **注（复验口径修正）**：小马独立复验 CI 等价口径 **9953 passed / 0 failed / 71 skipped**（= P5 9944 + A6 新增 9，数学自洽）；两口径差异为收集/skip 统计差异，0 failed 与覆盖率两项硬门禁均独立确认，不阻塞发布
- **覆盖率：84.14%**（≥84.10% 达标不降）
- 前端：tsc --noEmit 零错误 + jest 3 suites / 29 tests 全绿
- 架构债消失 grep 证据（待小马复验独立核对）：_dispatch_legacy 零命中 / api/auth.py 重复实现已删 / audit_routes 已删 / token_urlsafe(32) 兜底零命中 / tests/ sys.path.insert 清零
