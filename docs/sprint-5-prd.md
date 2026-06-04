# Sprint 5: 线上化 + DK Hub 发版 + 深度打磨 (Ralph Loop)

## 目标
把 yuleOSH 部署到真实服务器（可公网访问），同时确保 DK Hub 06/13 准时发版。

## 任务清单

- [ ] T5-1: yuleOSH 公网部署
  - 写 deploy/cloud-deploy.md 部署指南 (阿里云/腾讯云/AWS)
  - 支持 docker compose 一键远程部署
  - 支持 HTTPS (Caddy/Caddyfile 自动 TLS)
  - 产出: deploy/caddy/Caddyfile + deploy/cloud-deploy.md

- [ ] T5-2: DK Hub Release 06/13 验证
  - 完整的 end-to-end smoke test
  - go build + go vet + go test 全绿
  - Docker compose 端到端验证
  - 产出: docs/release-final-report.md (发版确认)

- [ ] T5-3: yuleOSH 自举验证
  - 用 yuleOSH 管 yuleOSH 开发 (之前 dogfooding B+)
  - 创建一个 OpenSpec 规范覆盖未完成的功能
  - 跑 pipeline + CI + evidence 全链路
  - 产出: docs/dogfooding-v2.md

- [ ] T5-4: Dashboard 首页统计面板
  - 在 Dashboard 顶部加统计摘要行
  - 总 Pipeline 数 / CI 通过率 / 审查数 / 证据包数
  - 近 7 天趋势概览
  - 产出: 修改 dashboard.html

## 验证标准
- 所有测试通过
- DK Hub go test 全绿
- Docker compose 可正常构建
