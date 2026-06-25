# yuleOSH 全阶段冲刺计划

> 启动时间: 2026-06-25 | 老板指令：按推荐路线冲刺，团队协作，专家评审，直至达标

---

## 总体路线图

```
Phase 1 (P0) — 验证 + 测试 + 架构
   ↓ 审查通过
Phase 2 (P1) — CI集成 + 轻量产品化
   ↓ 审查通过
Phase 3 (P1→P2) — 仪表盘 + 多项目 + E2E
   ↓ 审查通过
Phase 4 (P2) — 自建Dashboard + 用户系统 + 认证
```

## Phase 1 — 验证落地 + 测试框架化 + 架构抽象 (P0)

### A: 验证落地
- A1: cppcheck 真实输出验证（找开源项目跑 cppcheck）
- A2: pytest 真实输出验证（从 yuleOSH 自身抓 --junitxml）
- A3: unique_files 解析修复（多行格式解析）

### F: 测试框架化
- F1: Pipeline 单元测试（mock 外部工具）
- F2: 报告渲染 Snapshot 测试（golden file）
- F3: 模拟数据生成器（各种 cppcheck/pytest 变体）

### E: 架构抽象
- E1: ReportPipeline 通用化（DataAdapter + TemplateRegistry）
- E2: 插件式规则集（MISRA 作为第一个插件）

### 审查点
- 小马 🐴: Spec 契约层 + 验收矩阵
- 老陈 👨‍🏫: 专家评审
- 小明 🧑‍💼: 终审

## Phase 2 — CI集成 + 轻量产品化 (P1)

### A4: CI 自动生成报告 + 飞书/S3 上传
### B1: 报告摘要卡片（群消息嵌入）
### C: 报告模板默认预置 + Docker 部署文档增强
### E: 插件式规则集完成

## Phase 3 — 仪表盘 + 多项目 + 扩展 (P1→P2)

### B2: 飞书仪表盘 / 趋势图表
### C: 多项目/多版本对比
### D: clang-tidy driver 接入
### F: E2E 集成测试 + 模拟数据生成器

## Phase 4 — 产品化底座 + 认证 (P2)

### B3: 自建 Dashboard
### C: 用户系统 + 权限
### D: ISO 26262 工具认证 + ASPICE CL2
### D: 商业工具接入（Coverity/Klocwork）
