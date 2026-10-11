# 集成策略 (SWE.5)

## 集成方法

采用增量集成策略，按依赖关系自底向上逐步集成软件组件。

## 集成序列

### Phase 1: 基础层集成
- **组件**: compliance/profile.py + compliance/profiles/*.yaml
- **验证**: profile 加载与解析正确
- **桩/驱动**: 无外部依赖

### Phase 2: 引擎层集成
- **组件**: compliance/compliance_checker.py ← compliance/profile.py
- **验证**: ComplianceChecker 可执行单 profile 检查
- **桩/驱动**: Mock project_dir (临时目录)

### Phase 3: 多 Profile 合并集成
- **组件**: ComplianceChecker + _merge_profiles() + 3 个 ASPICE profiles
- **验证**: 单次遍历覆盖 SWE + SYS + SUP/MAN 全部 18 过程域
- **桩/驱动**: 临时目录含最小证据 (.git/)

### Phase 4: Evidence 层集成
- **组件**: evidence/aspice_check.py ← compliance/compliance_checker.py
- **验证**: aspice_gap_check() 输出完整 Gap 报告
- **桩/驱动**: 临时目录含部分证据

### Phase 5: API 层集成
- **组件**: api/dashboard_v2.py ← evidence/ + compliance/ + report/
- **验证**: API 端点返回正确合规状态
- **桩/驱动**: FastAPI TestClient

### Phase 6: Pipeline 全流程集成
- **组件**: pipeline/step_handlers/ ← compliance/ + evidence/ + report/
- **验证**: 完整 pipeline 执行生成合规证据包
- **桩/驱动**: 示例项目目录

## 桩/驱动识别

| 集成阶段 | 桩 (Stub) | 驱动 (Driver) |
|----------|-----------|---------------|
| Phase 1 | — | test_profile_loader |
| Phase 2 | Mock project_dir | test_compliance_checker |
| Phase 3 | 临时目录 + .git/ | test_multi_profile |
| Phase 4 | 临时目录 + 部分证据 | test_gap_check |
| Phase 5 | FastAPI TestClient | test_dashboard_api |
| Phase 6 | 示例项目 | test_pipeline_e2e |

## 集成入口准则

- 前一阶段全部测试通过
- 无 S1/S2 级别未关闭问题
- 代码审查已完成

## 集成出口准则

- 当前阶段全部集成测试通过
- 接口数据流验证正确
- 无新增 S1/S2 问题
