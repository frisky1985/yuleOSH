# Sprint Contract: yuleOSH CI 方向1 — Profile 反转为增量装配

## Scope
- What: 把 Pipeline Profile 从「黑名单裁减」（全量 − exclude）反转为「增量装配」（最小基线 + 按需叠加）
- In Scope:
  - `src/yuleosh/ci/profile.py`：新增 `minimal` 内置 profile（白名单基线）+ Profile 叠加/继承语法 + `filter_steps_for_profile` 语义修正
  - `src/yuleosh/ci/config.py`：修复 `exclude_steps` 死代码 bug（MisraProfile 缺字段）
  - `tests/test_profile.py`：适配新语义 + 3 条不变量测试
  - sprint-contract + checkpoint
- Out of Scope:
  - 不改 PIPELINE_STEPS 注册表形状（四元组不变）
  - 不改 gate_policy.py（方向3 已交付）
  - 不做 diff 裁剪（方向2 暂缓）
  - 不改 profiles.py（CI 环境档 development/ci/production，与 pipeline profile 是两套概念）

## 现状证据（三角色讨论 + 代码确认，2026-08-11）
1. `filter_steps_for_profile`（profile.py:145）**已有白名单分支**：`include_steps` 非 None 时按 include 过滤（L187-190），但 4 个内置 profile 全是黑名单模式（`include_steps=None` + `exclude_steps=[...]`）
2. **死代码 bug**（Evaluator 发现）：profile.py:179 检查 `hasattr(custom_profile, 'exclude_steps')`，但 config.py 的 `MisraProfile` dataclass **没有 exclude_steps 字段** → 自定义 profile 的步骤过滤配置**静默失效**（外层 `except Exception: pass` 吞错）——这是现成的假绿先例
3. **假绿陷阱**（Evaluator 警告）：黑名单语义下新增步骤自动进所有档（fail-safe）；白名单语义下新增步骤默认不进任何档 → 若策略是 "unlisted = 不跑"，新 P0 门禁会静默消失
4. safety 默认 = 全量（向后兼容约束）

## Architecture Decision
- architect-lead: 小明 (Hermes)
- 反装策略（Evaluator 三条不变量约束）:
  - **safety 恒等于 PIPELINE_STEPS 全集**（不变量1）
  - **unlisted 步骤默认全档运行**（不变量2）—— 白名单只对显式声明的步骤生效，未声明的默认跑（fail-safe，防新步骤静默消失）
  - **反装后各档差集与原黑名单档等价**（不变量3）—— ci 档反装前后排除的步骤集合一致
- 新增 `minimal` profile：白名单基线 = 核心步骤（spec-check / 编译 / 单测 / 覆盖率 / P0 GATE）
- 新增叠加语法：`extends`（继承另一 profile）+ `include_steps`（追加）+ `exclude_steps`（剔除）
- 修复死代码：MisraProfile 增加 `exclude_steps: list[str]` 字段，profile.py 的 hasattr 检查改为真实字段访问

## Testable Behaviors
- [ ] B1: `minimal` profile 存在，含 spec-check + c-unit-test + 覆盖率门禁 + P0 GATE
- [ ] B2: 不变量1：safety 过滤后 == PIPELINE_STEPS 全集
- [ ] B3: 不变量2：未在 include_steps 声明的步骤默认保留（fail-safe）
- [ ] B4: 不变量3：ci 档反装前后排除步骤差集一致
- [ ] B5: extends 叠加：minimal+review-linker 比 minimal 多 review-linker
- [ ] B6: exclude_steps 叠加：minimal 显式剔除某步骤生效
- [ ] B7: 死代码修复：自定义 profile 配 exclude_steps 实际生效（不再静默失效）
- [ ] B8: 现有 26 步注册表形状不变
- [ ] B9: 现有测试套件不回归（关键 profile/orchestrator 测试）

## Acceptance Criteria
| ID | Criterion | Pass Condition | Fail Condition | Priority | Owner |
|----|-----------|----------------|----------------|----------|-------|
| AC1 | minimal profile | 存在且含核心步骤 | 缺失 | P0 | 小明 |
| AC2 | 不变量1 (safety=全集) | 单测通过 | safety 过滤丢步骤 | P0 | 小明 |
| AC3 | 不变量2 (unlisted=run) | 单测通过 | 新步骤静默消失 | P0 | 小明 |
| AC4 | 不变量3 (差集等价) | 单测通过 | 反装改变行为 | P0 | 小明 |
| AC5 | extends 叠加 | 单测通过 | 叠加无效 | P1 | 小明 |
| AC6 | 死代码修复 | 自定义 exclude_steps 生效 | 仍静默失效 | P0 | 小明 |
| AC7 | 无回归 | profile/orchestrator 相关测试全绿 | 新红 | P0 | 小明 |

## Responsibility Matrix
| Criterion | Responsible | Fallback |
|-----------|-------------|----------|
| profile.py 反装设计 | 小明 | — |
| config.py 死代码修复 | 小明 | — |
| 测试 + 验收 | 小明（Evaluator 角色） | — |

## Negotiation Log
| Round | Party | Action | Notes |
|-------|-------|--------|-------|
| 1 | 三角色 | 讨论 | 方向1 评分 3.5-4.5；Evaluator 强调 3 条不变量防假绿 |
| 2 | 老板 | 拍板 | "开始"（2026-08-11，方向3 完成后） |
| 3 | Evaluator | 约束 | unlisted=run 防静默丢步骤；差集等价防迁移丢步骤 |
