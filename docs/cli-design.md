# OSH Platform · 平台入口

OSH-Fusion: OpenSpec + Superpowers + Harness Engineering

## 目录结构
```
src/
  spec/      — OpenSpec engine (parse/validate/diff)
  pipeline/  — Agent pipeline orchestrator
  ci/        — CI/CD 3-layer engine
  review/    — Agent review matrix
  evidence/  — Traceability + compliance
  ui/        — Web dashboard
```

## CLI 命令
- osh-cli init                  — 初始化项目
- osh-cli spec validate <file>  — 校验 spec
- osh-cli spec diff <old> <new> — diff spec
- osh-cli pipeline run <spec>   — 运行全流程
- osh-cli pipeline status       — 查看状态
- osh-cli ci run <layer>        — 运行 CI layer
- osh-cli evidence pack         — 生成合规包
