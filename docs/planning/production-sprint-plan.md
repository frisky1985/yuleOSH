# yuleOSH 量产冲刺计划

> **日期**: 2026-06-29
> **目标**: yuleOSH v2.1 → 量产就绪 (Production Ready)
> **完成后**: 专家评审 → scm-pro 座椅模块demo 全流程验证

---

## 阶段概览

```
Phase 0: P0 阻塞修复 (3天)
Phase 1: P1 重要改进 (2天)
Phase 2: 专家评审 (1天)
Phase 3: scm-pro 座椅模块验证 (2天)
─────────────────────────────────
总计: ~8天
```

---

## Phase 0 — P0 阻塞修复（3天）

### P0-1: 覆盖率真实化
**问题**: `.coveragerc` 用 aggressive omit 冲 60% 门禁，实际全局覆盖率仅 ~11%
**目标**: 去掉作弊 omit，真实覆盖率 ≥60%
**子任务**:
1. 去掉非必要的 omit 条目（保留 third_party, templates 等合理排除）
2. 为核心低覆盖模块补充测试（store_pg, preview, ui/server, ci/stages）
3. 调低 `--cov-fail-under` 到合理值，先确保覆盖率是真数据
4. 更新 `.coveragerc` 和 `pyproject.toml` 一致
5. 验证：`pytest --cov` 输出真实覆盖率 ≥60%

### P0-2: preview/analyzer.py 976 行拆分
**目标**: 拆分为 coverage_predictor.py, compliance_analyzer.py, config_recommender.py
**子任务**:
1. 定义新模块接口
2. 提取逻辑到独立文件
3. 保证向后兼容（analyzer.py 作为 re-export）

### P0-3: ui/server.py 842 行拆分
**目标**: 拆分为 routers/ 目录结构（routes/auth.py, routes/pipeline.py, routes/...）
**子任务**:
1. 按功能拆分为独立路由模块
2. 保留 server.py 作为入口集成

### P0-4: 隐私政策/服务条款占位符替换
**目标**: 替换 `[...]` 占位符为明总的公司信息
**子任务**:
1. 确认公司名、联系邮箱、注册地址
2. 更新 docs/privacy-policy-template.md 和 docs/terms-of-service-template.md

---

## Phase 1 — P1 重要改进（2天）

### P1-1: 生产环境稳定性测试
**目标**: 在本地模拟生产环境运行 24h+
**子任务**:
1. docker compose up 全栈启动
2. 运行端到端回归测试
3. 检查日志、重启恢复、数据库持久化

### P1-2: MISRA FP 基准优化
**目标**: 降低 cppcheck MISRA 假阳性率（当前 100% FPR）
**子任务**:
1. 为 MMIO/RTOS/HAL 等已知模式添加 suppression 规则
2. 更新 misra-rules.yaml 差评规则
3. 重新运行 benchmark 验证改善

### P1-3: Onboarding 流程打磨
**目标**: 注册 → 新建项目 → 运行 pipeline 端到端流畅
**子任务**:
1. 创建新用户注册流程测试
2. 验证模板选择和项目创建 UX

### P1-4: Stripe Webhook 配置
**目标**: 打通生产环境支付回调
**子任务**:
1. 确认 webhook endpoint URL
2. 验证订阅创建/取消/续费全链路

---

## Phase 2 — 专家评审（1天）

### 评审范围
| 维度 | 评审人 | 标准 |
|------|--------|------|
| 代码质量 | 小马 🐴 | 模块大小合理，覆盖率真实≥60% |
| 架构设计 | 小马 🐴 + 老陈（行业专家） | ASPICE AL1+, 可扩展性 |
| 测试覆盖 | 小克 👨‍💻（自检）→ 小马 🐴（复审） | SHALL 100% 覆盖 |
| 部署就绪 | 小马 🐴 | Docker Compose 验证通过 |
| 产品化评估 | 老陈（行业专家） | 对标竞品，量产可行性 |

### 通过条件
- 无 P0/P1 未关闭项
- 综合评分 ≥80/100
- ASPICE SWE.4/SWE.5 ≥ AL2
- 部署验证 3 项全绿

---

## Phase 3 — scm-pro 座椅模块验证（2天）

### 验证流程
1. **用 yuleOSH 创建 scm-pro 项目**
   - 选用 `autosar-classic` 或 `generic-embedded-c` 模板
   - 导入现有 spec-contract.md 需求

2. **运行完整 Pipeline**
   - 验证 28 步 pipeline 能否自动执行
   - 重点是：spec → 架构 → 开发 → 测试 → 审查 → 证据

3. **验证产出完整性**
   - 测试报告（Unity 测试结果）
   - 覆盖率报告
   - 证据包
   - 追溯矩阵

4. **记录产品化可行性报告**
   - 哪些跑通了 ✅
   - 哪些有缺口 ❌
   - 客户/合作伙伴接入建议

---

## 交付物清单

| 阶段 | 交付物 | 负责人 |
|:----:|:-------|:------:|
| P0 | 覆盖率真实基线报告 | 小克 👨‍💻 |
| P0 | analyzer.py 拆分完成 | 小克 👨‍💻 |
| P0 | server.py 拆分完成 | 小克 👨‍💻 |
| P0 | 法律文书更新 | 小克 👨‍💻 |
| P1 | 生产环境验证报告 | 小克 👨‍💻 |
| P1 | MISRA FP 优化报告 | 小克 👨‍💻 |
| P1 | Onboarding E2E 测试 | 小克 👨‍💻 |
| P2 | 专家评审报告 | 小马 🐴 + 老陈 |
| P3 | scm-pro 全流程验证报告 | 小克 👨‍💻 / 小马 🐴 |
| 终 | **量产就绪最终报告** | 小明 🧑‍💼 |
