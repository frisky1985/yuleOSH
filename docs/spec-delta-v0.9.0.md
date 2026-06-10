# yuleOSH v0.9.0 Spec-Delta — 产品体验 + 变现

> v0.8.0 → v0.9.0 | 2026-06-10 | 全并行执行

## 🔥 P0 — 当前执行中

### I1: Onboarding 向导
| Task | 描述 |
|:-----|:-----|
| T1.1 | 注册后自动弹窗引导 "创建你的第一个项目" |
| T1.2 | Step-by-step: 起名→写 spec → 跑 Pipeline → 看证据 |
| T1.3 | Welcome 页面重构：快速操作卡片 + 进度条 |

### I2: Async Pipeline 调度
| Task | 描述 |
|:-----|:-----|
| T2.1 | Pipeline 改为后台异步执行（thread pool） |
| T2.2 | 状态推送 API（`GET /api/v1/pipeline/status/{id}`） |
| T2.3 | Dashboard 轮询/WebSocket 实时更新 |

### I3: 用量计量
| Task | 描述 |
|:-----|:-----|
| T3.1 | Pipeline 运行计数（per org per month） |
| T3.2 | LLM Token 消耗汇总 |
| T3.3 | 存储用量统计 |
| T3.4 | 用量 Dashboard + 用量超限告警 |

### I4: Stripe 支付集成
| Task | 描述 |
|:-----|:-----|
| T4.1 | Stripe Checkout Session 创建 |
| T4.2 | Webhook 处理（checkout.completed / subscription.updated / payment.failed） |
| T4.3 | 订阅状态管理（active/canceled/past_due/trialing） |
| T4.4 | API 返回订阅状态 + 计费信息 |

### I5: Free Trial + Tier
| Task | 描述 |
|:-----|:-----|
| T5.1 | 新注册用户自动 14 天 Pro trial |
| T5.2 | Tier 限制生效（Community: 1 project, Pro: 10, Enterprise: unlimited） |
| T5.3 | Trial 到期降级 + 通知 |

### I6: Dashboard 升级
| Task | 描述 |
|:-----|:-----|
| T6.1 | 项目卡片式主页（项目列表 + 状态指示） |
| T6.2 | 最近 Pipeline 活动流 |
| T6.3 | 快速操作：新建项目 / 运行 CI / 查看证据 |

---

## 变更日志

| 日期 | 事件 |
|:-----|:-----|
| 2026-06-10 | v0.9.0 kickoff — 6 track 全并行 Ralph Loop |
