# 软件需求规格 — 合规引擎模块 (SWE.1.BP2)

## 功能区域: Compliance Engine

### REQ-CE-001: Profile 加载
- **SHALL** 从 yaml 文件加载合规标准 profile
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-001, SYS-REQ-003

### REQ-CE-002: 多 Profile 合并
- **SHALL** 支持多个 profile 合并评估，顶层键互不冲突
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-001, SYS-REQ-010

### REQ-CE-003: 合规检查执行
- **SHALL** 遍历项目目录，比对 profile 模板，输出合规报告
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-004, SYS-REQ-007

### REQ-CE-004: 反假绿验证
- **SHALL** 严格验证证据真实性，杜绝空模板/跨域误判
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-005, SYS-REQ-008

## 功能区域: Evidence Generation

### REQ-EG-001: Gap Check
- **SHALL** 以缺口导向格式输出合规评估结果
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-005, SYS-REQ-008

### REQ-EG-002: 追溯矩阵生成
- **SHALL** 自动生成需求→设计→代码→测试双向追溯矩阵
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-005, SYS-REQ-008

### REQ-EG-003: 证据包归档
- **SHALL** 将合规证据打包归档至 .osh/evidence/
- **优先级**: P1 | **状态**: 已实现
- **追溯**: REQ-008, SYS-REQ-013
