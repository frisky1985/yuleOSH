# 软件需求规格 — Pipeline 模块 (SWE.1.BP2)

## 功能区域: Pipeline Runner

### REQ-PR-001: 步骤执行
- **SHALL** 按顺序执行 pipeline 各步骤处理器
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-001, SYS-REQ-003

### REQ-PR-002: 上下文传递
- **SHALL** 在步骤间传递执行上下文 (project_dir, spec, results)
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-001, SYS-REQ-003

## 功能区域: Step Handlers

### REQ-SH-001: 系统层处理
- **SHALL** 处理 SYS.1~SYS.5 步骤，生成 docs/system-*.md
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-003, SYS-REQ-006

### REQ-SH-002: 软件层处理
- **SHALL** 处理 SWE.1~SWE.6 步骤，生成合规证据
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-003, SYS-REQ-006

### REQ-SH-003: 过程域感知
- **SHALL** 区分 SYS/SWE 语义，避免跨域误判
- **优先级**: P0 | **状态**: 已实现
- **追溯**: REQ-005, SYS-REQ-008
