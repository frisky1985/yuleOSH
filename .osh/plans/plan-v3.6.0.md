# v3.6.0 版本规划 — 覆盖率收官 + 架构收敛 + 前端安全

> 创建: 2026-08-01 23:59 | 规划人: 小明 🔥 | 基线: v3.5.0（369c1c4，全量 9611 passed / 覆盖率 82.83%）
> 目标: 达到"可以去接触第一个真实客户"的成熟度（老板 2026-08-01 定调）

---

## 1. 版本定位

v3.5.0 已清空 P1 + dependabot。v3.6 聚焦四件事：
1. **覆盖率收官**：82.83% → 90%（完成 Wave 2b + Wave 3，CI 门禁 30→60→70）
2. **架构收敛**：三套认证/审计并存 → 合并；4 个大模块拆分（技术债）
3. **前端安全轮**：token localStorage → httpOnly cookie（P2-7 落地方案）
4. **P2 收尾**：剩余 4 项 + 演示性质代码接入真实编排

## 2. 任务分解

### Track 1: 覆盖率收官（P0，主力）
| 波次 | 内容 | 目标 | 工作量 |
|---|---|---|---|
| 2b | cli/main.py (1416 stmts, 53.6%) — 按命令组拆 2 测试文件 | ≥75% | 3d |
| 3 | 13-15 个补漏文件（handler_base/async_runner/tenant_routes/handler_helpers/plan/kb/ci 系列等，见覆盖率计划 §Wave 3） | 每文件 70-85% | 10d |
| 门禁 | CI fail_under 30→60（M2）→ 70（M3）；coverage 回归告警 5%→2% | — | 0.5d |
| 验收 | 全量 --cov-fail-under=85 本地通过；无模块 <40%；无文件 0% | — | — |

### Track 2: 架构收敛（P1）
| 项 | 内容 | 工作量 |
|---|---|---|
| A-C-02 | 三套认证并存（api/auth.py vs ui/auth_extended.py vs api/middleware）→ 合并单一认证模块（依赖 v3.5.0 P1-2/3 铺垫） | 2d |
| A-W-01 | 三套审计系统并存 → 统一 audit 模块 | 1.5d |
| TD-003 | preview/analyzer.py (976 行) 拆分 | 1d |
| TD-004 | ui/server.py (842 行) 拆分 routers/ | 1d |
| TD-005 | ci/stages.py (1200+ 行) 拆分 stages/ | 1d |
| TD-011 | kpi.py (800+ 行) 拆分 | 0.5d |
| A-P2-04 | `_run_full_pipeline` 脚本化演示 → 接真实 orchestrator 编排 | 1.5d |

### Track 3: 前端安全轮（P1，配合客户接触）
| 项 | 内容 | 工作量 |
|---|---|---|
| S-P2-03 | token localStorage → httpOnly cookie（短期 token + 刷新机制）| 2d |
| CSP | 加 Content-Security-Policy 头（配合 cookie 迁移） | 1d |
| XSS 面 | 前端输入/渲染消毒检查 | 1d |

### Track 4: P2 收尾 + 清理（P2）
| 项 | 内容 | 工作量 |
|---|---|---|
| A-P2-01 | sys.path.insert 13 处清理（pythonpath=src 已配，确认后移除） | 0.5d |
| A-P2-05 | 测试命名/组织统一 | 1d |
| S-P2-01 | 残留 print(traceback)/敏感日志 → logging | 0.5d |
| S-05 | 137 处 except pass 高风险抽样清理 | 1d |

## 3. 里程碑

| 里程碑 | 时间 | 验收 |
|---|---|---|
| M1（第 1 周）| Wave 2b 完成 | cli/main.py ≥75%，覆盖率 ≥85%，门禁 60 |
| M2（第 2-3 周）| Wave 3 + 架构收敛 | 覆盖率 ≥88%，认证/审计合并上线，模块拆分完成 |
| M3（第 4 周）| 前端安全 + P2 收尾 | 覆盖率 ≥90%，cookie 迁移 + CSP 上线，全量 0 新增失败 |
| GA 判定 | 第 4 周末 | 小马终审 + ultra-review 复跑 ≥8 分 → **可接触第一个真实客户** |

## 4. 范围外（v4.0+）
- 云/多区域托管
- TCL2 认证（€75K-150K，建议拿到种子客户后再启动）
- 插件市场

## 5. 风险
- R1: cli/main.py 1416 stmts 测试工作量大（计划 60-80 测试），若卡住可先做 Wave 3 低垂果实
- R2: 认证合并可能引回归 → 合并后必须跑全量 + 小马复验
- R3: 前端 cookie 迁移需要改 Next.js 登录/API 客户端，需小克小马前后端协同

## 6. 团队分配
- 小克 👨💻: Track 1 + Track 2 开发
- 小马 🐴: Track 3 前端安全审查 + 各 Track 独立复验
- 小明 🔥: 编排 + 终审 + GA 判定
