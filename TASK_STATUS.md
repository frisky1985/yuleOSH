# yuleOSH — 项目状态与待办（TASK_STATUS）

> 最后更新: 2026-08-03 00:45 | 当前版本: v3.7.0 ✅ 已发布 | v3.8.0 规划中
> 仓库: frisky1985/yuleOSH | 基线: v3.7.0 (2e0eef5)

---

## 🏆 版本状态总览

| 版本 | 状态 | 关键数字 | 备注 |
|------|------|---------|------|
| v3.6.1 | ✅ 已发布 (08-02) | 9794 passed / 0 failed, 覆盖 84.10% | GitHub Pages 已部署 |
| v3.7.0 | ✅ 已发布 (08-03) | 9873 passed / 0 failed, 覆盖 84.10% | Track1 7 项 + Track4 5 项；小马复验 9.0/10；tag 已推送 |
| v3.8.0 | 📋 规划中 | — | Track2 架构收敛（6 项） |

---

## 📌 v3.7.0 发布记录（2026-08-03 00:45）

- ✅ 小马独立复验 9.0/10 放行（报告 reports/yuleOSH-v370-track14-assessment.md）
- ✅ tag v3.7.0（lightweight @2e0eef5）已 push origin
- ✅ 前端产物未变（v3.7.0 纯后端），GitHub Pages 无需重建，线上 200 健康
- ✅ 残留 pytest 并发进程已清理（0 残留）
- 复验发现 P1（共享工作区并发会话治理）：防重复 spawn 规则已固化（AGENTS.md + MEMORY.md #7），后续派活前查重

---

## ✅ v3.7.0 已完成（commit 2e0eef5，已 push）

| 项 | 内容 | 测试 |
|----|------|------|
| W1 | do_GET 异常分流（API→JSON 500 / 页面→500 页 + exc_info） | T-W1-01~07 |
| W2 | signin 限流 _ThreadSafeDict 原子化 + IP 表 >2000 概率清理 | T-W2-01~07 |
| W3 | swe6 check 去模拟化（parse_spec 真实计数 + ci-config 存在性 + probe 标注） | T-W3-01~08 |
| W4 | session 迁移 hex 校验（re.fullmatch 64 位，明文 JWT 不再漏网） | T-W4-01~05 |
| W5 | sandbox extra_read_dirs 读白名单（附录 A 审计：零内置插件需外部读） | T-W5-01~07 |
| W6 | preview 缓存 owner 隔离（user_key+url_hash） | T-W6-01~06 |
| W7 | 批量 subprocess timeout + demo_uart 去 shell | T-W7-01~07 |
| M1 | 后端 XSS 消毒换 html.parser 白名单（路线 A，含 void 标签深度 bug 修复） | T-M1-01~07 |
| M2 | 静态资源 Cache-Control immutable | T-M2-01~05 |
| M3 | AUTH_ENABLED 单一来源（server 导入 ui.auth） | T-M3-01~06 |
| M4 | 白名单 query 剥离匹配（非公开路径任何 query 仍 401） | T-M4-01~05 |
| M5 | SEC-W3 治理锁定（无硬编码 JWT 默认值，fail-fast 已核实） | T-M5-01~04 |

---

## ⏳ 遗留待办（P1/P2 级）

### yuleOSH v3.7.0 复验注意项（小克报告，待小马确认）
1. **M4 契约差异**：验收矩阵示例 `/api/project/list` 实为白名单项（租户 JWT 自鉴权），负例改用真实 gated 的 `/api/evidence`、`/api/ci-results` 验证"query 不放行非公开路径" — 待复验判定 SHALL-M4.3 语义
2. **W6 匿名用户缓存维度为 IP**（NAT 同 IP 互见）— 已知限制，Track2 认证收敛后换 user_id
3. **subscription/wizard 每次调用生成新随机 secret** → 跨调用验签失败（既有行为，非本版引入；建议 Track2 统一走 auth.py 单一来源）
4. **test_phase0_coverage_boost.py::test_ui_auth_import** 为既有顺序依赖测试（依赖 test_ui_server.py 模块缓存；全量套件通过，非本版回归，未改动）
5. **W2 限流仍为进程内**（S-P2-02），多 worker 部署需共享存储 — 既有 NOTE

### v3.8.0 架构收敛（Track2，已排期 ~4-5 天）
- A1 认证三套合一（auth_extended 为基，middleware 同一 verify，A-C-02，2d）
- A2 审计统一（DB 为主，ring 降级，A-W-01，1.5d）
- A3 路由去 legacy 双轨（tenant/billing/projects 新式签名，ARC-W1，1d）
- A4 Store 抽象补方法（project/stats 走接口，ARC-W3，1d）
- A5 cli/main.py 拆分命令组 + sys.path.insert 清理（A-P2-01/05，2d）
- A6 dashboard/page.tsx 拆组件（ARC-W5，1d）
- 附：subscription/wizard secret 单一来源（见上 3）

### v3.9.0 前端安全（Track3，已排期 ~4 天）
- T1 token cookie 迁移（双 Cookie HttpOnly access+refresh，S-P2-03，2.5d）
- T2 CSP Phase 1（清遗留放行，'unsafe-inline' 场景最小化，1.5d）

### 其他项目
- **yuleASR-Configurator**: macOS 签名发布阻塞（P0-2，需 Apple Developer 证书，指南 docs/macos-code-signing-guide.md，内测未签名包可顶）+ ultra-full 8 critical 安全项待排期（reviews/ultra-full-2026-08-01/review-security-perf.md）
- **yuleDKCS**: 2b-F ICCOA/ICCE SM4 完成度核对 / 2b-I 后台 BLE / 4.4 物理机 E2E（等真机）/ 2b-G/H UWB/NFC（等真机）

---

## 📋 方法论备注
- 流程: OpenSpec（spec.md+spec-delta.md+startup-analysis.md+acceptance-matrix.md，v3.7.0 契约在 .osh/specs/v3.7.0/）+ Superpowers + Harness Engineering
- 全量回归命令: `python3 -m pytest tests/ -q --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py`
- 覆盖率门禁: ≥84.10%（里程碑 76→80→85→90）
