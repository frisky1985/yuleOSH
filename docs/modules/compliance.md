# 模块设计速写：compliance（ASPCIE 合规检查模块）

> 包：`src/yuleosh/compliance/` ｜ 规模：3 .py ≈ 1762 行 + 1 yaml
> 关联：**HTTP `/api/v1/compliance/*` 是另一套子系统**（见偏差 D1）

## 职责
对工程目录做 ASPICE v3.1（SWE.1~SWE.6）合规检查：遍历工程产物、对照检查点模板，把每个 Base Practice 标记为 ✅/⚠️/❌ 并产出报告。
证据：`compliance/__init__.py:1-9`、`compliance/compliance_checker.py:1-7`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `compliance/__init__.py` (9) | 包入口 | re-export `ComplianceChecker` `:9` |
| `compliance/compliance_checker.py` (1398) | 检查引擎 | `ComplianceChecker` `:46`；`run()` `:1250`；`generate_report_markdown()` `:1310`；`run_and_save()` `:1389`；`_check_bp()` `:967` |
| `compliance/profile.py` (355) | 多标准 profile 模型 | `StandardProfile` `:64`；`to_template_dict()` `:117`；`load_profile()` `:336`；`ProfileError` `:188` |
| `compliance/profiles/aspice_v3.1.yaml` | 默认检查点定义 | 数据文件（Glob 确认存在） |

## 公共 API / 入口点
- `ComplianceChecker(project_dir, template_path=None, profile=None)` → `run()` / `generate_report_markdown()` / `run_and_save()`（`compliance_checker.py:46,1250,1310,1389`）
- `load_profile(name, profile_dir=None) -> StandardProfile`（`profile.py:336`）
- 私有但被外部调用的 `_extract_req_ids()`（`compliance_checker.py:38`）

## 生产接线（真实调用方，均在 CLI）
- `evidence/aspice_check.py:25-26` 导入 `ComplianceChecker` + `load_profile/ProfileNotFoundError/ProfileError`；`aspice_gap_check()` `:137` 内 `load_profile` `:182` + `ComplianceChecker` `:183` + `run()` `:184`（缺口报告封装层）
- `cli/commands/compliance.py:24-29`；`cmd_compliance_check()` `:36`（命令 `yuleosh compliance check`）
- `cli/main.py:710`（`yuleosh ev check`）、`cli/commands/gap.py:51`、`cli/onboard.py:318,322`

## 运行时触发方式
**无 HTTP 路由接线**。仅通过 CLI 触发：`yuleosh compliance check` / `yuleosh ev check` / `yuleosh gap` / onboarding。注意 `evidence/aspice_check.py` 是「缺口报告」封装，由 CLI 调用而非 API。

## 环境变量 / 配置
- **模块本身不读取任何环境变量**（`compliance/**` 中 `os.environ/getenv` 搜索为空）。profile 搜索目录由 `__file__` 推导（`profile.py:174-175`）。
- 调用方读 `OSH_HOME`：`evidence/aspice_check.py:173`、`cli/commands/compliance.py:43-44`。
- 假绿防护（fail-closed）：`compliance_checker.py:788,830,904,1069`（如空层不算验收证据、未知检查类型直接判失败 `:1220-1224`）。

## 偏差 / 死代码 / 待注意（设计文档必记）
- **D1（重大反直觉）**：HTTP 命名空间 `/api/v1/compliance/overview`（`api/router.py:102` → `api/compliance.py:handle_compliance`）**与本模块完全无关**。该路由读 `.yuleosh/reports/gscr-extended-compliance.json` / `misra-report.json` 并用 `ci.rulesets.RulesetRegistry`（`api/compliance.py:58,75,95,136`）做 MISRA/GSCR 概览，**从不 import 或调用 `yuleosh.compliance`**。「compliance」是两套并行子系统，文档须区分。
- 双加载路径并存（yaml `template_path` + `profile` 注入）：`compliance_checker.py:58-70`。
- `cli/stats.py:193` 调用了**私有**函数 `_extract_req_ids`（命名越界用法）。

## 规模
3 .py（1762 行）+ 1 yaml。
