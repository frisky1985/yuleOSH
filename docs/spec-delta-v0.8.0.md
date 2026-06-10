# yuleOSH v0.8.0 Spec-Delta — SaaS 商业化

> 版本: v0.7.0 → v0.8.0 | 日期: 2026-06-10 | 主题: 多租户 + 用户认证 + SaaS Dashboard

## 🔥 P0 — SaaS 底座 ✅ (已完成主体)

| T2.1 | JWT token 签发/验证（PyJWT + HS256） | ✅ |
| T2.2 | 用户注册/登录 API（signin + org create 全流程） | ✅ |
| T2.3 | Session 管理 + Token 过期 | ✅ |
| T3.1 | 注册/登录/org 创建/项目选择 HTML 页面 | ✅ |
| T3.2 | 项目 Dashboard（Dashboard + API 路由） | ✅ |
| T3.3 | API v1 路由（14 资源） | ✅ |

### I1: 多租户存储隔离
| Task | 描述 | 状态 |
|:-----|:-----|:----:|
| T1.1 | Store 按 org_id 隔离（organizations/users/projects 表） | ✅ |
| T1.2 | Evidence/pipeline session 按项目分片 | ✅ |
| T1.3 | 多租户集成测试 | 🔄 |

## 📦 P1 — 商业化补齐（下一波）

### I4: 密码认证 + 安全加固
- 添加 bcrypt 密码哈希到 signin 流程
- OWASP 安全审查
- 依赖漏洞扫描

### I5: 部署 & 文档
- 阿里云 ECS 部署指南
- API 文档页
- Onboarding 向导

### I6: 性能基线
- API 性能测试
- Pipeline 调度优化

---

## 变更日志

| 日期 | 事件 | 描述 |
|:-----|:-----|:-----|
| 2026-06-10 | v0.8.0 P0 SaaS底座 | JWT + 多租户 + Dashboard + API Router → commit 1f9d08d |
