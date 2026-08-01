# Backlog — ultra-review v3.4.3 P1/P2（本轮不修）

> 创建: 2026-08-01 21:00 | 来源: `~/.openclaw/workspace/reports/ultra-review-2026-08-01/`（小马 ultra-review，6.2/10）
> 规则: 本轮只修 4×P0（见 sprint-ultrareview-p0-v3.4.3.md），P1/P2 全部进此 backlog 后续轮次处理。
> 状态图例: ⬜ 未开始 | 🟡 进行中 | ✅ 已修

## P1（11 项）

| # | 编号 | 问题 | 修复建议（implementation-plan.md） | 状态 |
|---|------|------|-----------------------------------|------|
| 1 | C/W-02 | `GET /api/v1/audit` 声称 "admin only" 但无角色校验 | audit RBAC 补齐：require_auth 后校验 current_user.role == admin | ⬜ |
| 2 | W-04 / S-P1-06 | signin 无密码用户可仅凭 email 登录（双系统行为矛盾：api/auth.py 拒绝 vs auth_extended 放行）；邮箱枚举 + 账号锁定 DoS | 无密码登录对齐（auth_extended 已随 P0-2 改 fail-closed，待复验）；signin 加防枚举/防锁定 DoS | 🟡 |
| 3 | W-06 | `_check_auth` 恒返回 True — legacy API 端点全部未鉴权 | `_check_auth` 委托真实实现（session/API key 校验） | ⬜ |
| 4 | W-03 / S-P1-01 | preview `_check_preview_rate_limit` 竞态 + `is_authed` 仅凭请求头存在性判定；进程内限流器 `_requests` 无锁且无界增长 | preview 限流加锁 + is_authed 实校验；ratelimit 加锁 + 定期清理 | ⬜ |
| 5 | W-08 / S-P1-04 | `read_body` / 各 `_read_body` Content-Length 无上限 + `int()` 可抛 ValueError（内存 DoS / 500） | 统一 read_body：Content-Length clamp（如 10MB）+ 异常处理 | ⬜ |
| 6 | S-P1-02 | JWT 明文存储于 `user_sessions.token`（DB 泄漏 = 会话劫持；api_keys 用 sha256，session 反而明文） | session 表迁移为哈希存储（低峰执行）；客户端 localStorage 问题见 P2-7 | ⬜ |
| 7 | S-P1-05 | 错误信息泄漏：kg_impact、server.do_POST、webhooks 把 `{e}` 直接回客户端（绕过 router 脱敏） | 统一错误脱敏（只回 generic message，细节进日志） | ⬜ |
| 8 | W-05 | async_runner 在 ImportError / signal 错误时"模拟通过" — CI 结果造假 | 失败必须显式失败，禁止静默模拟成功 | ⬜ |
| 9 | S-P1-07 | 通知配置可写入 SMTP 密码（进程内环境变量），GET 不返回但可被覆盖 | 密码字段仅写入时接受，读回时脱敏/拒绝覆盖 | ⬜ |
| 10 | S-P1-08 | `subprocess` 使用 `shell=True`（fault_inject `$(nproc)`） | 去掉 shell=True，参数列表化 | ⬜ |
| 11 | S-P1-09 | CORS OPTIONS 预检无条件 `Access-Control-Allow-Origin: *`（绕过 cors.py 白名单） | 预检也走 cors.py 白名单逻辑 | ⬜ |

## P2（8 项）

| # | 编号 | 问题 | 建议 | 状态 |
|---|------|------|------|------|
| 1 | A-P2-01 | `sys.path.insert` 模块体 hack（多处） | 确认 `pip install -e .` 后移除 | ⬜ |
| 2 | A-P2-02 / S-P2-02 | CORS 双实现；sandbox `_restricted_open` 路径前缀匹配可绕过 | 收敛为单一 CORS 实现；路径校验改 resolve+relative_to | ⬜ |
| 3 | A-P2-04 | `_run_full_pipeline` 是"脚本化演示"而非真实流水线 | 接入真实 pipeline 编排 | ⬜ |
| 4 | A-P2-05 | 测试命名/组织（CP-P2-02 未修） | 统一测试命名约定 | ⬜ |
| 5 | S-P2-01 | 残留 `print(traceback)` / 敏感日志 | 全部改 logging 并降噪 | ⬜ |
| 6 | S-P1-03 / zip 炸弹 | preview zip 解压无成员数/展开大小上限（zip-slip 已由 stdlib 缓解） | 加成员数/展开大小上限 | ⬜ |
| 7 | S-P2-03 | 前端 token 存 localStorage（已知，需配合 XSS 防护） | 迁移 httpOnly cookie / 短期 token | ⬜ |
| 8 | S-P2-04 / S-P2-05 | N+1 查询；缺省超时 | 批量查询优化；HTTP 客户端统一超时 | ⬜ |

## 其他记录（未进 11+8 计数，可并入上表处理）

- A-C-02 / S-03: 三套认证系统并存（api/auth.py vs ui/auth_extended.py vs api/middleware）→ 建议合并（与 P1-2/3 同批）
- A-W-01 / S-02: 三套审计系统并存；S-05: `except Exception: pass` 137 处；W-07: `json_error()` 传 dict 契约破坏
- S-01: 内存状态并发无锁（`_preview_request_log`、`_repo_cache`、`ratelimit._requests`）— 并入 P1-4
- S-06: `handle_status`/`handle_health` 返回 `osh_home` 绝对路径（信息泄漏，可并入 P1-7）
- S-07: `handle_org_create` 的 `session_token` 参数从未使用（已随 P0-2 连带修复，待复验）
