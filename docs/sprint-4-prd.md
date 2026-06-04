# Sprint 4: 生态 + 多语言 + 企业级加固 (Ralph Loop 自动迭代)

## 目标
完成 yuleOSH 商业化最后的 P2 缺口，使其具备国际化和生态扩展能力。

## 任务清单

- [ ] T4-1: 国际化 (i18n) — 英文版落地页 + 英文版文档
  - 产出: src/ui/marketing/en/ 目录, 英文 index.html, 英文 pricing.html
  - 验收: curl http://localhost:8080/en 返回英文页面
  
- [ ] T4-2: Admin API Key 管理页面
  - 产出: Dashboard 内 API Key 管理 UI (生成/吊销/列表)
  - 验收: 页面可生成新 API Key, 可吊销, 列表展示

- [ ] T4-3: 系统健康检查页
  - 产出: /api/v1/health 扩展为完整状态页, 含各模块运行状态
  - 验收: curl 返回 DB/Store/Pipeline/CI 各模块健康状态

- [ ] T4-4: 首次使用引导 wizard
  - 产出: 首次登录时的 5 步引导 (创建组织→创建项目→写 Spec→跑 Pipeline→看结果)
  - 验收: 全新用户登录后自动跳转引导流程

- [ ] T4-5: Plugin 示例 — GitHub Webhook 集成
  - 产出: 接收 GitHub push webhook 自动触发 CI
  - 验收: curl POST 模拟 push 事件, CI 自动触发

## 验证标准
- 所有 33+ 测试通过
- Dashboard 可访问
- 无回归
