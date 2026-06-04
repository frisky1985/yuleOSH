# yuleOSH 商业化路线图

> 内部讨论结论：从 MVP → 商业产品需要的 3 个核心差距

## Phase 3: Commercial MVP (目标: 可展示、可销售)

### P0 — 必须有
1. **产品落地页** — 不是 Dashboard，是 marketing site（介绍、功能、定价、注册）
2. **多租户认证** — 组织 + 项目 + 用户 + OAuth 登录
3. **新手引导** — 创建第一个项目 30 秒上手
4. **REST API** — 所有功能开放 API（当前只有 Dashboard 页面上有）

### P1 — 重要
5. **定价页面** — 免费版 / Pro 版 / Enterprise 版
6. **Helm Chart** — K8s 企业部署
7. **使用统计** — 项目数、用户数、Pipeline 运行数

### P2 — 加分
8. **邮件通知** — Pipeline 失败通知
9. **Plugin 示例** — 第一个第三方集成
10. **中文/英文双语**

## 执行顺序

Sprint 1: 落地页 + 多租户认证 (2d)
Sprint 2: 新手引导 + REST API (2d)
Sprint 3: Helm Chart + 定价 (2d)
Sprint 4: 统计 + 通知 + Plugin (2d)
