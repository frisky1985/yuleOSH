# yuleOSH v0.8.0 Spec-Delta — SaaS 商业化

> 版本: v0.7.0 → v0.8.0 | 日期: 2026-06-10 | 主题: 多租户 + 用户认证 + SaaS Dashboard

## 🎉 v0.8.0 Ralph Loop — 全部完成

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

### I4: 密码认证 ✅
| Task | 描述 | 状态 |
|:-----|:-----|:----:|
| T4.1 | bcrypt 密码哈希 (12 rounds) | ✅ |
| T4.2 | Rate limiting (10/5min per email) | ✅ |
| T4.3 | 密码验证错误路径 (wrong/no-password) | ✅ |

### I5: 部署 & 文档 ✅
| Task | 描述 | 状态 |
|:-----|:-----|:----:|
| T5.1 | Docker Compose + Nginx SSL 部署指南 | ✅ |
| T5.2 | 安全 Headers 审计 (CSP/X-Frame/CORS) | ✅ |
| T5.3 | API 路由文档 (14 resources) | ✅ |

### I6: 数据库 ✅
| Task | 描述 | 状态 |
|:-----|:-----|:----:|
| T6.1 | Migration v6 (password_hash column) | ✅ |
| T6.2 | DB 文档更新 | ✅ |

---

## 变更日志

| 日期 | 事件 | 描述 |
|:-----|:-----|:-----|
| 2026-06-10 | v0.8.0 Ralph Loop 完成 | P0+P1 全部交付: 密码认证 + JWT + 部署指南 + 安全审计 + 最终报告 |
