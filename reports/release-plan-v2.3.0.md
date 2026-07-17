# yuleOSH v2.3.0 — 并行发版规划

> **日期**: 2026-07-17  
> **编制**: 小明 🔥  
> **当前版本**: v2.2.0  
> **上游版本**: v2.2.1 (集成本阶段并行产出后发布)

---

## 📋 发布概览

| 项目 | 内容 |
|:-----|:------|
| **版本号** | v2.3.0 |
| **类型** | 功能+质量混合发布 |
| **核心主题** | 技术债修复 + KG 深化 + 竞品对标 + ASPICE 加固 |
| **距上次发布** | 10 天 (v2.2.0: 07-07 → v2.3.0: ~07-17) |
| **RBAC 判定** | 🟢 GA 级发布 |

---

## 🔄 自 v2.2.0 以来的新增功能 (07-07 ~ 07-17 已完成部分)

### 1. KG 知识图谱 v1.0 (P0)
| 功能 | 模块 | 状态 |
|:-----|:-----|:----:|
| 增量构建引擎 | `knowledge_graph/incremental_bootstrap.py` | ✅ |
| 100K Stress Test 通过 | 全量构建 99.7s, 查询 0.1ms, 增量 12ms | ✅ |
| 置信度标签 (8 种边类型) | `knowledge_graph/confidence.py` | ✅ |
| 内存优化 -50.5% | RSS 535→264MB, tracemalloc 211→53MB | ✅ |
| 双后端支持 | SQLite(Python BFS) / PostgreSQL(RECURSIVE CTE) | ✅ |

### 2. yuleASR 集成 Phase 3 (P0)
| 功能 | 状态 |
|:-----|:----:|
| `--template autosar` 模板 | ✅ |
| Pipeline AUTOSAR CI 支持 | ✅ |
| 交叉编译 ARM Cortex-M/R | ✅ |
| ARXML 合规验证 | ✅ |
| MISRA-C:2023 检查复用 | ✅ |

### 3. MISRA C:2023 Phase 2 (P1)
| 功能 | 状态 |
|:-----|:----:|
| cppcheck 2.17.1 C:2023 验证 | ✅ |
| MisraC2023RuleSet 适配 | ✅ |
| C:2012→C:2023 规则映射 | ✅ |
| 试点模块扫描 (6 个 C 文件) | ✅ |

### 4. 文档与易用性 (P0)
| 文档 | 行数 | 状态 |
|:-----|:----:|:----:|
| `docs/architecture.md` | 685 | ✅ |
| `docs/impact-analysis.md` | 1,045 | ✅ |
| `docs/integration-strategy.md` | 450 | ✅ |
| `docs/architecture-review.md` | — | ✅ |
| `docs/design-review.md` | — | ✅ |
| Onboarding Wizard (`yuleosh onboard`) | — | ✅ |

### 5. OEM 模板兼容性 (P1)
| 模板 | 状态 |
|:-----|:----:|
| VW | ✅ |
| BMW | ✅ |
| Mercedes | ✅ |
| Generic | ✅ |
| OEM Common | ✅ |
| 导出测试 (31 tests) | ✅ |

---

## 🔧 本阶段并行任务产出 (07-17 进行中)

### Task A: 技术债覆盖攻坚 — 小克 👨‍💻
- **目标模块**: `ci/kpi/` (0%), `evidence/` (0-15%)
- **目标覆盖率**: ≥ 60%
- **验收标准**: 测试通过 + 不破坏现有逻辑 + 覆盖率数据更新

### Task B: KG 下一阶段深化 — 小马 🐴
- **方向**: ASPICE 审计可视化 / 追溯矩阵自动生成 / Dashboard 集成
- **验收标准**: 新 spec-delta + 2-3 个功能实现 + 测试验证

### Task C: 竞品对标更新 — 小明 🔥
- **产出**: 已写入 `reports/competitive-analysis-v2.3.md`
- **关键发现**: KG 置信度标签是竞品盲区，AutoC 是最大新威胁

---

## 📦 v2.3.0 发布清单

### Release Engineering

| 步骤 | 描述 | 负责人 |
|:-----|:------|:-------|
| 1. 代码合并 | 收集小克 + 小马的分支 | 小明 |
| 2. 回归测试 | 全量 pytest + coverage check | CI |
| 3. spec 更新 | `docs/spec.md` 版本声明 2.2.0→2.3.0 | 小马 |
| 4. RELEASE_NOTES 更新 | 追加 v2.3.0 章节 | 小明 |
| 5. 老陈验收 | 行业专家快速验收 | 老陈 |
| 6. 打 Tag | `git tag v2.3.0` + `git push --tags` | 小明 |
| 7. 发布 | PyPI + Docker 更新 | CI |

### 版本号规划

```
v2.2.0 ──── 质量加固 (07-07)
      │
      ├── v2.2.1 (可选, 并行产出热修复)
      │
      └── v2.3.0 ──── 功能+质量混合发布 (预计 07-17~07-18)
                    │
                    └── 包含: KG v1 + yuleASR Phase3 + MISRA C2023 + 技术债 + 竞品指引
```

---

## 📊 发布质量门禁

| 门禁项 | 最低标准 | 当前状态 |
|:-------|:--------:|:--------:|
| 回归测试 | ≥ 250 passed | ⏳ 等产出 |
| 覆盖率 fail_under | ≥ 50% | 确认中 |
| P0 问题 | 0 遗留 | ⏳ 等产出 |
| spec 一致性 | SHALL 100% 覆盖 | ⏳ 等产出 |
| 行业评审 | ≥ 80/100 | ✅ 上一轮 85/100 |

---

## 🚀 发布后 Roadmap 建议

### v2.4.0 (下一迭代)
- **KG Dashboard 可视化** — 追溯矩阵可视化、SWE 状态图
- **ASPICE 4.0 MLE** — 机器学习工程过程组支持
- **SaaS 起步** — Web Dashboard 多用户
- **AutoC 竞争应对** — AUTOSAR 配置深度集成

### v2.5.0 (中长期)
- 插件生态 / 第三方集成
- 硬件在环 / 仿真对接
- 认证体系联合
- ISO 26262 功能安全集成

---

*规划: 小明 🔥 | 日期: 2026-07-17 | 版本: v2.3.0 Draft*
