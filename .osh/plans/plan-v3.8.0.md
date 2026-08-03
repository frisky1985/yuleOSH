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
| P6 | A6（dashboard 拆组件）+ F2 | A1 完成后 | npm build + tsc + 手工 | ⏳ |

## Checkpoints

（每批完成后追加：commit、测试结果、下一步）

---
