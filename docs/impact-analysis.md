# 影响分析 (SWE.1.BP3)

## 影响分析方法

每次需求变更时执行以下分析：
1. **范围识别**: 确定受影响的下游工作产品（设计/代码/测试）
2. **进度评估**: 估算变更实施所需工时
3. **资源评估**: 识别所需人力与工具资源
4. **风险评估**: 评估变更引入的新风险

## 变更记录与影响分析

### CR-001: 新增 SUP/MAN 评估域 (2026-10-09)

**变更描述**: 引入 aspice_support_mgmt_v3.1.yaml，新增 SUP.1/8/9/10 + MAN.1/2/3 共 7 个过程域

**影响范围**:
- **需求**: 新增 7 个过程域文档要求（qa-plan, known-issues, change-requests, project-plan, risk-register 等）
- **设计**: aspice_check.py _FIX_GUIDANCE 新增 15 条修复指引
- **代码**: compliance_checker.py 新增 _merge_profiles() 多 profile 合并功能
- **测试**: 新增 test_evidence_aspice_check_ext.py 15 个测试用例
- **证据**: 需创建 SUP/MAN 层文档以满足合规要求

**进度影响**: +3 工作日（profile 编写 1d + 代码实现 1d + 测试验证 1d）
**资源影响**: 需系统工程师参与 SYS/SUP 过程域对齐
**风险**: 低风险 — 新增 profile 顶层键与现有 SWE/SYS 不冲突

### CR-002: 默认 profile 切换 (2026-10-10)

**变更描述**: aspice_gap_check() 默认使用 ASPICE_FULL_PROFILES 替代单 profile

**影响范围**:
- **代码**: aspice_check.py 默认参数变更
- **向后兼容**: 显式 profile_name/profile_names 参数仍生效
- **测试**: 默认配置测试用例更新
- **用户**: 用户无需手动指定 profile 即可覆盖全 V 模型

**进度影响**: +0.5 工作日
**资源影响**: 无额外资源
**风险**: 低风险 — 向后兼容，显式参数优先

### CR-003: SWE.6.BP2 反假绿修复 (2026-10-08)

**变更描述**: 禁止单元测试顶替"目标环境执行"，SWE.6.BP2 改用 _has_sil_results()

**影响范围**:
- **代码**: compliance_checker.py 新增 _has_sil_results() 方法
- **测试**: test_compliance_checker.py 新增反假绿测试
- **用户**: 用户需提供 SIL/HIL 结果才能通过 SWE.6.BP2

**进度影响**: +1 工作日
**资源影响**: 需 QA 团队验证反假绿规则不误杀
**风险**: 中风险 — 可能影响无 SIL 环境用户的合规评估

## 影响分析模板

每次需求变更时复制以下模板填写：

```
### CR-xxx: [变更标题] ([日期])
**变更描述**: ...
**影响范围**:
- 需求: ...
- 设计: ...
- 代码: ...
- 测试: ...
**进度影响**: ...
**资源影响**: ...
**风险**: ...
```
