# yuleOSH 系统自检计划 — Self-Bootstrapping

> 目标：用 yuleOSH 自身的 OpenSpec + Superpowers + Harness Engineering 体系来梳理自身
> 方法论：三位一体自举检查

---

## 参与角色

| 角色 | Agent | 职责 | 工具集 |
|:-----|:------|:-----|:--------|
| 🧑‍💼 项目经理 | 小明 | 需求入口 + 终审 + 裁决 | OpenClaw |
| 🐴 质量架构师 | 小马 | Spec契约层审查 + 验收矩阵 + 前置审查 | hermes-agent |
| 👨‍💻 编码/架构 | 小克 | 全量系统扫描 + 技术债务分析 + 架构审查 | claude-agent |

## 检查维度

### Track A: 小马 🐴 — 规范与质量审查

1. **Spec 自我审查**
   - yuleOSH 自身能否用 OpenSpec 写自身 spec？
   - SHALL/SHOULD/MAY 文体是否贯穿全员？
   - spec-delta 管理是否规范？
   - 验收矩阵是否完整？

2. **ASPICE 成熟度再评估**
   - SWE.4/SWE.5/SWE.6 各域等级
   - 过程文档完整性
   - 追溯矩阵健壮性

3. **合规性检查**
   - MIT 许可证合规
   - CI/CD 门禁有效性
   - 安全基线

### Track B: 小克 👨‍💻 — 全量系统扫描

1. **健康检查**
   - 所有模块可导入
   - 无残留 broken import
   - Docker Compose 可启动

2. **安全扫描**
   - 密钥/Token 硬编码
   - 依赖漏洞
   - CSP/Security Headers 配置
   - JWT/Stripe Key 安全存储

3. **代码异味**
   - 循环复杂度
   - 重复代码
   - 未使用 import/变量
   - 类型注解覆盖率

4. **部署健康**
   - Nginx 配置有效性
   - Dockerfile 构建测试
   - 环境变量完整性

### Track C: 小明 🧑‍💼 — 汇总分析与规则映射

1. **三位一体融合分析**
   - OpenSpec 规则在 yuleOSH 自身的使用度
   - Superpowers 启动分析框架测试
   - Harness Engineering Pipeline 自闭合测试

2. **发布就绪矩阵**
   - Launch Checklist 逐项确认
   - 工程就绪 vs 运营就绪 分离
   - Go/No-Go 最终判定

3. **自检报告** — 用 yuleOSH 自己的 Pipeline 流程产出最终诊断
