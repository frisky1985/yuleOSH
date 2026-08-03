# yuleOSH — 项目状态与待办（TASK_STATUS）

> 最后更新: 2026-08-04 06:30 | 当前版本: v3.9.1 🔧 修复中 | v3.9.0 ✅ 已发布
> 仓库: frisky1985/yuleOSH | 基线: v3.9.0 (2ec102c) → v3.9.1 分支修复中

---

## 🏆 版本状态总览

| 版本 | 状态 | 关键数字 | 备注 |
|------|------|---------|------|
| v3.6.1 | ✅ 已发布 (08-02) | 9794 passed / 0 failed, 覆盖 84.10% | GitHub Pages 已部署 |
| v3.7.0 | ✅ 已发布 (08-03) | 9873 passed / 0 failed, 覆盖 84.10% | Track1 7 项 + Track4 5 项；小马复验 9.0/10；tag 已推送 |
| v3.8.0 | ✅ 已发布 (08-03) | 9953 passed / 0 failed, 覆盖 84.14% | 架构收敛 7 项裁决全落地；小马复验 9.0/10；tag v3.8.0 @7e864e2 |
| v3.9.0 | ✅ 已发布 (08-03) | 10017 passed / 0 failed, 覆盖 84.17% | Track3 前端安全（cookie 迁移 + CSP）；小马复验 97/100；tag v3.9.0 @2ec102c |
| v3.9.1 | 🔧 修复中 (08-04) | 待回归 | 复验 P2×3 观察项闭环（refresh 限流 / build 链 CSP / org-setup 去 localStorage） |

---

## 📌 v3.9.0 发布记录（2026-08-03 22:04-23:30）

- ✅ 契约 8 项裁决全部「按推荐」（老板 22:04 确认）
- ✅ 小克开发 6 批次（bf17275→2ec102c）：T1 双 cookie（yuleosh_at 0.5h / yuleosh_rt 7d）+ refresh 轮换 + 前端去 localStorage；T2 每请求 nonce CSP + unsafe-eval 移除 + nginx 单一来源；F1 产物重建 + gh-pages 发布（63e1178，35 页零丢失）
- ✅ 附赠修复 4 个既有 bug：_handle_api 双响应 / 自动建组织 401 / refresh 轮换 jti 根因 / _serve_file 双 Content-Length
- ✅ 小马独立复验 97/100 放行（17 分钟）：10017/0，cov 84.17%，前端 jest 33/33 + tsc + build 35 页，负例 11 项全绿
- ✅ tag v3.9.0（lightweight @2ec102c）已 push origin
- 复验报告: `reports/yuleOSH-v390-assessment.md`（main=8f7364e）

---

## 🔧 v3.9.1 进行中（2026-08-04，复验 P2×3 闭环）

复验遗留 3 项 P2 观察项（报告 §5）逐项闭环：

| # | 问题 | 修复 | 测试 |
|----|------|------|------|
| P2-1 | refresh 端点无显式限流器 | `auth_routes.py` refresh 分支加 per-IP 限流（复用 server.check_rate_limit，429 + 拒绝处理） | test_v391_p2_fixes.py::TestP21RefreshRateLimit（路径写入 / 超限 429 / 未超限放行） |
| P2-2 | `npm run build` 不自动注入 meta CSP | `frontend/package.json` build 链上 `python3 scripts/inject-meta-csp.py` | TestP22BuildChainsCsp（build 脚本含 inject + 脚本存在性） |
| P2-3 | /org/setup 静态页仍读 localStorage('osh_token') | 源模板 + out 产物 `handleOrgCreate` 改 cookie 认证（credentials same-origin，401 回登录页），零 localStorage | TestP23OrgSetupNoLocalStorage（源/产物无 localStorage + 无 Authorization Bearer） |

**状态**: 代码修复 ✅ / 新测试 7 个 ✅ / 全量回归运行中（预期 10017+ passed）
**下一步**: 全量回归绿 → commit + tag v3.9.1 → push → 推进新开发

---

## ⏳ 遗留待办

### 技术债 / 优化（非阻塞）
1. **W6 匿名用户缓存维度为 IP**（NAT 同 IP 互见）— Track2 认证收敛后换 user_id
2. **subscription/wizard 每次调用生成新随机 secret** → 跨调用验签失败（既有行为，建议统一走 auth.py 单一来源）
3. **W2 限流仍为进程内**（S-P2-02），多 worker 部署需共享存储 — 既有 NOTE
4. **TD-003/004/005 模块过大**：preview/analyzer（976 行）、ui/server（842 行）、ci/stages（1000+ 行）待拆分
5. **test_phase0_coverage_boost.py::test_ui_auth_import** 为既有顺序依赖测试（全量套件通过，非回归）

### 覆盖率攻坚（里程碑 76→80→85→90）
- 当前真实基线 ~84.17%（v3.9.0 复验口径），目标 85% → 90%
- Phase 1 已完成（76%→79.31%），后续按 ci/coverage 报告继续

### 其他项目
- **yuleASR-Configurator**: macOS 签名发布阻塞（P0-2，需 Apple Developer 证书，指南 docs/macos-code-signing-guide.md，内测未签名包可顶）+ ultra-full 8 critical 安全项待排期
- **yuleDKCS**: 2b-F ICCOA/ICCE SM4 完成度核对 / 2b-I 后台 BLE / 4.4 物理机 E2E（等真机）/ 2b-G/H UWB/NFC（等真机）

---

## 📋 方法论备注
- 流程: OpenSpec（spec.md+spec-delta.md+startup-analysis.md+acceptance-matrix.md）+ Superpowers + Harness Engineering
- 全量回归命令: `python3 -m pytest tests/ -q --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py`
- 覆盖率门禁: ≥84.10%（里程碑 76→80→85→90）
