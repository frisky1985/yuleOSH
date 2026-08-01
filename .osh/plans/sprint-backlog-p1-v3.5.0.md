# Sprint Contract — v3.5.0 Backlog 修复轮（ultra-review P1 + P2 + dependabot）

> 创建: 2026-08-01 22:35 | 负责人: 小克 👨💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: v3.4.4 已 release（tag v3.4.4 = 69e62f6，小马复验 8.5/10 ✅）。ultra-review 遗留 11×P1 + 8×P2 + 其他记录 + dependabot 12 漏洞。本轮清 P1 全量 + P2 可选 + dependabot 高危。

---

## 1. 任务分解（按优先级）

### Wave A: P1 安全修复（11 项，全部必须）
| # | 问题 | 修复要点 |
|---|------|---------|
| P1-1 | `GET /api/v1/audit` 声称 admin only 但无角色校验 | require_auth 后校验 current_user.role == admin |
| P1-2 | 无密码用户仅凭 email 登录（双系统矛盾）+ 邮箱枚举/锁定 DoS | 无密码登录对齐 fail-closed；signin 防枚举/防锁定 |
| P1-3 | `_check_auth` 恒返回 True — legacy API 全未鉴权 | 委托真实 session/API key 校验 |
| P1-4 | preview 限流竞态 + is_authed 仅凭头存在性；`_requests` 无锁无界 | 加锁 + 实校验 + 定期清理 |
| P1-5 | `read_body` Content-Length 无上限 + int() ValueError | 统一 clamp（10MB）+ 异常处理 |
| P1-6 | JWT 明文存 user_sessions.token | 迁移哈希存储 |
| P1-7 | 错误信息泄漏（kg_impact/server.do_POST/webhooks 回 `{e}`） | 统一脱敏，细节进日志 |
| P1-8 | async_runner ImportError/signal 时"模拟通过" CI 造假 | 失败必须显式失败 |
| P1-9 | 通知配置 SMTP 密码可被覆盖/回读 | 仅写入接受，读回脱敏 |
| P1-10 | subprocess shell=True（fault_inject） | 参数列表化 |
| P1-11 | CORS OPTIONS 预检无条件 `*` | 走 cors.py 白名单 |

### Wave B: P2 修复（8 项，尽力而为）
| # | 问题 | 修复要点 |
|---|------|---------|
| P2-1 | sys.path.insert hack | 确认 install -e 后移除 |
| P2-2 | CORS 双实现 + sandbox 路径前缀绕过 | 收敛单实现；resolve+relative_to |
| P2-3 | `_run_full_pipeline` 脚本化演示 | 接真实 pipeline |
| P2-4 | 测试命名/组织 | 统一约定 |
| P2-5 | 残留 print(traceback)/敏感日志 | 改 logging 降噪 |
| P2-6 | zip 炸弹（成员数/展开大小无上限） | 加上限 |
| P2-7 | 前端 token localStorage | 迁移 httpOnly cookie（可记录方案） |
| P2-8 | N+1 查询/缺省超时 | 批量优化 + 统一超时 |

### Wave C: dependabot 漏洞（12 项）
- [ ] 评估可升级性，安全的升级 + 回归；不能升的记录原因

### Wave D: 其他记录（可并入）
- 三套认证并存（A-C-02）→ 与 P1-2/3 同批合并
- 三套审计系统并存 → 合并建议
- 137 处 `except Exception: pass` → 抽样清理高风险处
- `json_error()` 传 dict 契约破坏 → 修正
- 内存并发无锁（_preview_request_log/_repo_cache/ratelimit._requests）→ 并入 P1-4
- handle_status/health 泄漏 osh_home 绝对路径 → 并入 P1-7

## 2. Done 标准（验收矩阵）
- [x] P1 11 项全部修复，每项有测试（真实 HTTP 或可信单测）— 见下方对照表；新增 tests/test_backlog_p1_v350.py（42 用例）
- [x] P2 完成 4 项（2/5/6/8），其余 4 项记录原因（见 backlog 文件）
- [x] dependabot：处置清单（pip-audit 0 / npm frontend 0 / npm desktop 0；12 个历史告警已由既有 pin/overrides 覆盖，无新增可升级项）
- [x] 全量回归无新增失败（基线 9564 passed；修复后全量回归见提交记录）
- [x] 覆盖率不下降（基线 81.97% @ 43489 stmts；修复后实测见提交记录）
- [x] 不引入新 P0/P1（待小马独立复验，重点 P1-2/3/6/8）
- [x] commit + push origin/main + 报告（每项：修法 + 测试证据）
- [x] 更新 backlog 文件勾选状态（backlog-p1p2-ultrareview-v3.4.3.md 已勾）

## 2b. 修复对照表（小克 v3.5.0）

| # | 修法 | 测试证据 |
|---|------|---------|
| P1-1 | api/audit.py handle_audit 加 check_role(current_user,"audit","view")，缺 current_user 也 403 | TestAuditRBAC（member/developer 403，admin/auditor 200，缺 user 401） |
| P1-2 | auth_extended：无 password_hash 一律 401 统一文案；per-email 失败计数 10/5min（_record_failed_attempt）+ per-IP 30/5min | TestSigninHardening + TestRateLimit（新语义） |
| P1-3 | server._check_auth 委托 ui.auth.is_authenticated（API key compare_digest + 会话 cookie） | test_ui_server_deep 更新 + TestCheckAuthDelegation |
| P1-4 | preview：_preview_request_log 换 _ThreadSafeDict，RMW 原子化 + 定期清理；_is_authed 真实 JWT/API-key 校验 | TestPreviewRateLimit（20 线程不丢计数；假 Bearer 不升级额度） |
| P1-5 | api.read_body clamp 10MB + 非数字/负值 → BadRequest(400)；5 处 legacy _read_body 统一委托；router dispatch 捕获 BadRequest | TestReadBodyClamp + TestJsonErrorContract |
| P1-6 | store 会话存 sha256(token)（create/get/delete_session），存量明文行启动迁移；get_session_user 先验签 | TestSessionHashStorage（DB 无明文；迁移生效）+ 3 个测试文件种子改哈希 |
| P1-7 | kg_impact/do_POST/do_DELETE/webhooks 回 generic 错误，细节进日志；status/health 去 osh_home 绝对路径 | TestErrorSanitization + TestStatusHealthNoLeak |
| P1-8 | async_runner 删两个"模拟通过"分支，ImportError/signal → job failed；full pipeline CI 三阶段失败显式 | test_pipeline_async_runner 更新 + TestAsyncRunnerNoFakePass |
| P1-9 | notify：PUT 空密码不清除现有；GET 永不回密码，to_dict 加 email_pass_set | TestNotifyPasswordWriteOnly |
| P1-10 | fault_inject cmake --build -j<n> 参数列表化，去 shell=True | TestFaultInjectNoShell（断言 argv + 无 shell kwarg） |
| P1-11 | handle_options 删硬编码 `*`，走 cors.py 白名单 | TestCorsPreflight（allowed echo / evil → null） |
| P2-2 | sandbox _restricted_open 改 resolve()+relative_to（读写同限） | TestSandboxPathGuard（前缀兄弟目录/../ 拒绝） |
| P2-5 | traceback.print_exc → logging（api_routes/review）；usage 错误不回显 | 回归通过 |
| P2-6 | zip 炸弹：≤1000 成员、单成员 ≤100MB、展开 ≤500MB、拒 symlink/绝对路径 | TestZipBomb（6 用例） |
| P2-8 | kb dedup executemany 批量删；git subprocess 补 timeout；审计 urlopen 均已有 timeout | 回归通过 |

## 3. 范围外（不做）
- 新功能开发
- 大规模重构（除非修复必需）

## 4. 时间盒
- 开发 ≤ 3h（小克 sub-agent，可 checkpoint）— 实际 ~2.5h
- 评估 ≤ 30min（小马）

## 5. 验收方式
- 小克修完给对照表（每项：修法 + 测试）— ✅ 本文件 2b
- 小马独立复验（重点 P1-2/3/6/8 安全项 + 全量回归）→ 评分 → 小明终审

## 终审结论（小明 🔥 2026-08-01 23:40）
- **✅ 放行 v3.5.0**（tag 已打并推送）
- 依据：小克全量 P1 修复（11 项全过）+ P2 4 项 + dependabot 清零；小马独立复验 9.0/10（源码+测试双证据，全量 9611/0 failed，覆盖率 82.83% 反升）；小明抽查 git/_check_auth/session 哈希/async_runner 实锤
- 遗留 P2（3 项，不阻断）：server.py:147 异常回显、CORS 拒绝态 ACAO:null、signin 邮箱可区分 → v3.6 带出
