# Sprint Contract — v3.4.0 编码生成闭环 + Skills 模块

> 创建: 2026-07-31 23:50 | 负责人: 小克 👨‍💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: 老板要求补全 yuleOSH Harness Coding 能力缺口（D3 编码生成 + skills 模块）

---

## 1. Done 标准（验收矩阵）

### A. D3 编码生成闭环（P0）
- [ ] A1. `DevelopmentStep` 增加 `generate-code` 模式：按 spec/架构/PRD 直接产出目标语言代码文件
- [ ] A2. 生成的代码自动触发编译验证（python compile / gcc -fsyntax-only / 项目构建命令）
- [ ] A3. 编译失败 → 自动修复循环（最多 N 次，默认 3 次）→ 失败则记录原因到产物
- [ ] A4. 产物落盘：`artifacts/generated-code/` + 生成报告（文件清单/验证结果/修复轮次）
- [ ] A5. 覆盖场景：Python 模块生成 + C 函数生成（嵌入式）

### B. Skills 模块（P0）
- [ ] B1. `src/yuleosh/skills/` 变为真实技能库：Skill 数据模型 + 注册/查询 API
- [ ] B2. 内置 ≥3 个技能：`autosar-coding`（AUTOSAR C 规范）、`misra-fix`（MISRA 修复模式）、`python-testing`（pytest 最佳实践）
- [ ] B3. 技能内容可被 LLM prompt 引用（skills → prompt 拼接）
- [ ] B4. CLI: `yuleosh skills list` / `yuleosh skills show <name>`

### C. 测试与质量
- [ ] C1. 新增测试 ≥ 15 个（codegen 生成/验证/重试循环 + skills 注册/查询/引用）
- [ ] C2. 全部新测试通过；现有 9058 测试无回归
- [ ] C3. 覆盖率不下降（codegen/skills 模块 ≥ 60%）
- [ ] C4. 提交推送 origin/main，报告含 commit hash

### D. 文档
- [ ] D1. docs/ 更新：codegen 使用说明 + skills 扩展指南

## 2. 范围外（不做）
- 不改 pipeline 其他步骤行为（默认模式仍输出 planning）
- 不做多语言编译器沙箱（仅本机工具链）
- 不接入外部 agent 框架

## 3. 时间盒
- 开发 ≤ 2 小时（小克 sub-agent）
- 评估 ≤ 30 分钟（小马）

## 4. 验收方式
- 小马按 A/B/C/D 逐项验证 → 评分 → 小明终审 → 推远程
