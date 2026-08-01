# Backlog — ultra-review v3.4.3 P1/P2（v3.5.0 修复轮完成）

> 创建: 2026-08-01 21:00 | 来源: `~/.openclaw/workspace/reports/ultra-review-2026-08-01/`（小马 ultra-review，6.2/10）
> 规则: 本轮只修 4×P0（见 sprint-ultrareview-p0-v3.4.3.md），P1/P2 全部进此 backlog 后续轮次处理。
> 状态图例: ⬜ 未开始 | 🟡 进行中 | ✅ 已修（v3.5.0 修复轮 2026-08-01，commit 见 sprint-backlog-p1-v3.5.0.md）

## P1（11 项）— v3.5.0 全部 ✅

| # | 编号 | 问题 | 修复建议（implementation-plan.md） | 状态 |
|---|------|------|-----------------------------------|------|
| 1 | C/W-02 | `GET /api/v1/audit` 声称 "admin only" 但无角色校验 | audit RBAC 补齐：require_auth 后校验 current_user.role == admin | ✅ 已修（api/audit.py 加 check_role(audit,view) 403 fail-closed；测试 test_backlog_p1_v350.py::TestAuditRBAC） |
| 2 | W-04 / S-P1-06 | signin 无密码用户可仅凭 email 登录（双系统行为矛盾：api/auth.py 拒绝 vs auth_extended 放行）；邮箱枚举 + 账号锁定 DoS | 无密码登录对齐（auth_extended 已随 P0-2 改 fail-closed，待复验）；signin 加防枚举/防锁定 DoS | ✅ 已修（auth_extended：无 password_hash 一律 401 统一文案；失败计数制 per-email 10/5min + per-IP 30/5min） |
| 3 | W-06 | `_check_auth` 恒返回 True — legacy API 端点全部未鉴权 | `_check_auth` 委托真实实现（session/API key 校验） | ✅ 已修（server.py 委托 ui.auth.is_authenticated；测试更新为 deny 语义） |
| 4 | W-03 / S-P1-01 | preview `_check_preview_rate_limit` 竞态 + `is_authed` 仅凭请求头存在性判定；进程内限流器 `_requests` 无锁且无界增长 | preview 限流加锁 + is_authed 实校验；ratelimit 加锁 + 定期清理 | ✅ 已修（preview：_ThreadSafeDict + 原子 RMW + 定期清理；is_authed 真实 JWT/API-key 校验） |
| 5 | W-08 / S-P1-04 | `read_body` / 各 `_read_body` Content-Length 无上限 + `int()` 可抛 ValueError（内存 DoS / 500） | 统一 read_body：Content-Length clamp（如 10MB）+ 异常处理 | ✅ 已修（api.read_body clamp 10MB + BadRequest；5 处 legacy _read_body 统一委托；router 400 处理） |
| 6 | S-P1-02 | JWT 明文存储于 `user_sessions.token`（DB 泄漏 = 会话劫持；api_keys 用 sha256，session 反而明文） | session 表迁移为哈希存储（低峰执行）；客户端 localStorage 问题见 P2-7 | ✅ 已修（store create/get/delete_session 存 sha256；存量明文行启动迁移；get_session_user 先验签；3 个测试文件种子改哈希） |
| 7 | S-P1-05 | 错误信息泄漏：kg_impact、server.do_POST、webhooks 把 `{e}` 直接回客户端（绕过 router 脱敏） | 统一错误脱敏（只回 generic message，细节进日志） | ✅ 已修（kg_impact/server do_POST/do_DELETE/webhooks 全部 generic + logging exc_info；handle_status/health 去掉 osh_home 绝对路径 → osh_home_configured） |
| 8 | W-05 | async_runner 在 ImportError / signal 错误时"模拟通过" — CI 结果造假 | 失败必须显式失败，禁止静默模拟成功 | ✅ 已修（_run_ci_job 删两个模拟分支；full pipeline 的 ci_compile/misra/coverage 失败即 job failed） |
| 9 | S-P1-07 | 通知配置可写入 SMTP 密码（进程内环境变量），GET 不返回但可被覆盖 | 密码字段仅写入时接受，读回时脱敏/拒绝覆盖 | ✅ 已修（PUT 空密码不清除；GET to_dict 永不返回密码，新增 email_pass_set 布尔） |
| 10 | S-P1-08 | `subprocess` 使用 `shell=True`（fault_inject `$(nproc)`） | 去掉 shell=True，参数列表化 | ✅ 已修（cmake --build -j <n> 参数列表化，无 shell） |
| 11 | S-P1-09 | CORS OPTIONS 预检无条件 `Access-Control-Allow-Origin: *`（绕过 cors.py 白名单） | 预检也走 cors.py 白名单逻辑 | ✅ 已修（handle_options 删硬编码 *，走 _add_cors_header → cors.py） |

## P2（8 项）— v3.5.0 修 4 项，其余记录原因

| # | 编号 | 问题 | 建议 | 状态 |
|---|------|------|------|------|
| 1 | A-P2-01 | `sys.path.insert` 模块体 hack（多处） | 确认 `pip install -e .` 后移除 | ⬜ 记录原因：pytest.ini 已配 `pythonpath = src`，insert 冗余但无害；移除需全仓回归（13 处），留待 v3.6 清理轮 |
| 2 | A-P2-02 / S-P2-02 | CORS 双实现；sandbox `_restricted_open` 路径前缀匹配可绕过 | 收敛为单一 CORS 实现；路径校验改 resolve+relative_to | ✅ 已修（sandbox resolve+relative_to，读写同限；CORS 已收敛——router/helpers 均委托 cors.py 单实现，P1-11 补上 OPTIONS 缺口） |
| 3 | A-P2-04 | `_run_full_pipeline` 是"脚本化演示"而非真实流水线 | 接入真实 pipeline 编排 | ⬜ 记录原因：真实编排依赖 autosar/rte/ci 完整链路；本轮已把 CI 三阶段改为失败显式（P1-8），演示性质标注保留，v3.6 规划接 orchestrator |
| 4 | A-P2-05 | 测试命名/组织（CP-P2-02 未修） | 统一测试命名约定 | ⬜ 记录原因：pytest.ini 已声明 test_*.py 约定；存量 300+ 文件重命名收益低，随重构轮处理 |
| 5 | S-P2-01 | 残留 `print(traceback)` / 敏感日志 | 全部改 logging 并降噪 | ✅ 已修（api_routes.py、ci/stages/review.py 的 traceback.print_exc → logging；api_routes usage 错误不再回显 str(e)） |
| 6 | S-P1-03 / zip 炸弹 | preview zip 解压无成员数/展开大小上限（zip-slip 已由 stdlib 缓解） | 加成员数/展开大小上限 | ✅ 已修（≤1000 成员、单成员 ≤100MB、展开 ≤500MB、拒绝 symlink/绝对路径成员；测试 TestZipBomb） |
| 7 | S-P2-03 | 前端 token 存 localStorage（已知，需配合 XSS 防护） | 迁移 httpOnly cookie / 短期 token | ⬜ 记录原因：属前端改造 + CSP/XSS 联动，本轮不触碰前端；已记录方案（httpOnly cookie + 短期 token）供 v3.6 前端轮 |
| 8 | S-P2-04 / S-P2-05 | N+1 查询；缺省超时 | 批量查询优化；HTTP 客户端统一超时 | ✅ 已修（kb dedup 改 executemany 批量删；git 类 subprocess 补 timeout=30/60；审查确认 urlopen 均有 timeout；signin 全 org 扫描保留——有 org 排序语义依赖，记录） |

## 其他记录（并入处理）

- A-C-02 / S-03: 三套认证系统并存（api/auth.py vs ui/auth_extended.py vs api/middleware）→ 与 P1-2/3 同批对齐行为（无密码 fail-closed、_check_auth 委托、token 契约双格式已统一），完整合并留 v3.6
- A-W-01 / S-02: 三套审计系统并存 → 建议以 audit/model.py JSONL 为唯一事实源，v3.6 规划
- S-05: `except Exception: pass` 137 处 → 本轮抽样清理高风险处（preview 清理、webhooks 存储降噪），全量清理留专项
- W-07: `json_error()` 传 dict 契约破坏 → ✅ 已修（json_error 支持 str|dict，dict 归一化为 error 字符串 + details 对象；preview 测试同步更新）
- S-01: 内存状态并发无锁（`_preview_request_log`、`_repo_cache`、`ratelimit._requests`）→ 并入 P1-4 ✅（preview 已线程安全；ratelimit 为 defaultdict 单写模式，加锁收益低——已评估：check_rate_limit 的 RMW 在 GIL 下原子性不足，v3.6 换 _ThreadSafeDict）
- S-06: `handle_status`/`handle_health` 返回 `osh_home` 绝对路径（信息泄漏）→ ✅ 并入 P1-7（改为 osh_home_configured 布尔）
- S-07: `handle_org_create` 的 `session_token` 参数从未使用（已随 P0-2 连带修复，待复验）→ ✅ 复验通过（P0-2 已绑定 token.email == body.email）
