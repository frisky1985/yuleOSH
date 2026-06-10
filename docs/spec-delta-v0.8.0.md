# yuleOSH v0.8.0 Spec-Delta — SaaS 商业化

> 版本: v0.7.0 → v0.8.0 | 日期: 2026-06-10 | 主题: 多租户 + 用户认证 + SaaS Dashboard

## 🔥 P0 — SaaS 底座（当前执行中）

### I1: 多租户存储隔离
- T1.1: Store 按 project_id / org_id 隔离数据
- T1.2: Evidence/pipeline session 按项目分片
- T1.3: 多租户集成测试

### I2: 用户认证系统
- T2.1: JWT token 签发/验证（替换 env API key）
- T2.2: 用户注册/登录 API
- T2.3: Password hashing (bcrypt) + session 管理

### I3: SaaS Dashboard 上线
- T3.1: 注册/登录页面
- T3.2: 项目 Dashboard（项目列表 + 创建）
- T3.3: Pipeline 状态实时展示

## 📦 P1 — 商业化补齐

### I4: 订阅 & 计费
### I5: 安全审查 (OWASP + deps)
### I6: 性能基线 & API 文档

---

## 变更日志

| 日期 | 事件 | 描述 |
|:-----|:-----|:-----|
| 2026-06-10 | v0.8.0 kickoff | Ralph Loop 启动 P0 I1/I2/I3 三线并行 |
