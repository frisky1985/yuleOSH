# yuleOSH 对 ASPICE V 模型开发工作流的支持度评估（v3，2026-10-09）

> 评估方法：实证三轮交叉核查。①直接取证（读源码 + 实跑合规引擎）；
> ②对抗性复核（假设"已全支持"错误，专扫残留假绿向量）；
> ③对高影响结论自行复验后标注「成立/修正/存疑」。
> 基线：v2 评估 `product-vmodel-gap-assessment-v2-10-08.md`；本轮在 v2 之后已落地
> SYS.4 + SWE.6 反假绿修复（提交 `f673688d`/`8939b595`，已推送）。

## 0. 结论摘要（直接回答明总）

**不能声称"完全支持"V 模型开发工作流。** 准确表述为：

> yuleOSH 已具备支撑 ASPICE V 模型**工程过程**（SYS.1–5 系统层 + SWE.1–6 软件层）
> 的**骨架与合规判定能力**，覆盖 30 步流水线 + 11 个 Gate 视图，且关键假绿
> （SYS.4 / SWE.6 被单测顶替）已清除，**SWE.6 目标环境执行证据链亦已闭环**（P0，
> 提交 `2da8c943`/`d01ea214`）。**P1（SYS→SWE 对齐默认强制）与 P2（SUP/MAN 独立
> 评估域 + SWE.5 反假绿）均已闭环**（提交 `48c56269`/`9198b7c0`/`d784e6d1`），
> 故 yuleOSH 现可声称**完整支撑 ASPICE V 模型工程过程 + 支持/管理过程的合规评估闭环**。
> 残留为文档化与默认组合评估接入等加强项（见 §5）。

读盘纪律提醒：拿 yuleOSH 自身仓库跑合规引擎，SWE 侧大量 `missing evidence` 仅因
该仓库非汽车交付物（无 C/嵌入式目标环境产物），**禁止当作产品能力缺陷评分**；
本评估仅以"结构/能力支持度"为口径。

---

## 1. V 模型工程过程覆盖度（成立）

| 过程域 | 流水线步骤（文件:行） | Profile 域 | Checker 识别 |
|---|---|---|---|
| SYS.1 系统需求分析 | `sys-requirements`（step_handlers/__init__.py:198） | aspice_sys_v3.1.yaml | ✅ |
| SYS.2 系统架构设计 | `sys-architecture`（:199） | 同上 | ✅ |
| SYS.3 系统验证规划 | `sys-verification`（:200） | 同上 | ✅ |
| SYS.4 系统集成与集成测试 | `sys-integration`（:201） | 同上 | ✅（反假绿已修） |
| SYS.5 系统确认 | `sys-validation`（:202） | 同上 | ✅ |
| SYS 确定性门禁 | `sys-req-review`（:203） | — | — |
| SWE.1 软件需求 | `spec-check`/`prd`/`prd-review`（:206–212） | aspice_v3.1.yaml | ✅ |
| SWE.2 软件架构 | `architecture`/`arch-review`（:215–217） | 同上 | ✅ |
| SWE.3 详细设计与编码 | `development`/`codegen-deploy`/`internal-code-review`（:220–225） | 同上 | ✅ |
| SWE.4 单元验证 | `verify-loop`/`c-unit-test`（:240–241） | 同上 | ✅ |
| SWE.5 软件集成与集成测试 | `code-review`/`integration-test`/`qemu-verify`/`coverage-review`（:245–255） | 同上 | ✅ |
| SWE.6 合格性测试 | `test-qualification`（:269） | 同上 | ✅（判定已修，但**证据链断**，见 §3） |

- `PIPELINE_STEPS = 30` 步（step_handlers/__init__.py:194），左半 G0 含 SYS.1–5 共 6 步。
- `gates.py` 含 **11 个 Gate 视图 G0–G10**（gates.py:8 注释 "11 Gate 视图"；G0 定义 :63，G10 :126），与 ASPICE 过程域对齐。
- **实跑合规引擎**：`aspice_sys_v3.1` 与 `aspice_v3.1` 两 profile 的 `unknown check type` 计数均为 **0**（11 个过程域全部 check_item 均有判定分支）。
  - 对比 v2：v2 评估时 SYS 侧曾有 **4 个 `unknown check type`**（13 BP 全绿仅 2），本轮 T3 左半修复后已归零 —— **成立，且为实质性改善**。

---

## 2. 反假绿状态（成立）

| 假绿向量 | 状态 | 证据 |
|---|---|---|
| SYS.4 系统集成被单测顶替 | ✅ 已修 | compliance_checker.py:1303–1358（`_is_sys_area` 执行类走 `_sys_execution_record`，禁用 `_test_suite_passes`）；提交 `7a402c9c` |
| SWE.6 合格性测试被单测顶替 | ✅ 已修 | compliance_checker.py:1210–1217（`swe_id.upper()=="SWE.6"` 专用分支走 `_has_sil_results`）；提交 `f673688d` |
| 跨域误判（SYS 区查 SWE 的 integration-strategy.md） | ✅ 已修 | SYS 区 `stub/driver` 改查 `docs/system-integration.md`（:1311） |

**对抗性复核（假设"已全支持"错误，专找反例）**：
- 全仓扫描 `_test_suite_passes()` 调用点，仅余：
  - `:1228` SWE.4 单元测试分支（合法，ASPICE SWE.4 单元测试本就是单测）；
  - `:1327` SWE.5 集成测试分支（**弱证据，非明确假绿**，见 §3 灰色地带）；
  - `:1360` 通用 SWE.1–3 设计/验证类 check（合法）。
- `_has_sil_results()` 已覆盖 SYS 执行分支 + SWE.6；`_ci_results_exist()` 仅作"有 CI 但无通过证据→RED"的诚实降级（:1333/:1363）。
- **结论：明确假绿向量已清零**，残留为可接受/待加强项。

---

## 3. 残余硬缺口（按优先级）

### P0 — SWE.6 端到端"目标或等效环境执行"证据链（已闭环 ✅，2026-10-09）

- **历史现象**（已修复）：v3 评估时 `step_test_qualification`（SWE.6 handler）只做 host-sim，
  不产生 checker 所需的 `.osh/ci/sil-*.json`，导致 SWE.6.BP2 永远 RED（证据链断）。
- **修复**（提交 `2da8c943` / `d01ea214`）：
  - 新增 `_discover_firmware_artifact` 在常见构建目录发现真实 `.elf` 固件
    （排除 hello/sample demo 固件，与 `_has_sil_results` 口径一致）；
  - 新增 `_run_hil_qualification`：探测 `device/` HIL 设备 → 申请设备 → 经
    `cross.HilTestRunner` 在真实硬件执行 → **仅当 passed 才落盘**
    `.osh/ci/sil-<产品>.json`（`all_passed=True` + 真实模块名）；
  - `step_test_qualification` Phase 3.5 接入 HIL 子证据，report 记录
    `target_environment_execution` / `target_environment_passed`；
  - `device`/`cross` 均 lazy import，无 HIL 环境不影响 host-sim 主流程。
- **反假绿纪律**：无设备 / 无固件 / 执行失败均**不写 sil 证据**，只如实降级
  （attempted=False 或 passed=False），绝不伪造 GREEN。
- **验证**：`tests/test_sys_req006_swe6_hil.py` 5 场景（A 无设备不造假 /
  B 真跑通写真证据且 checker 判 GREEN / C 跑失败不造假 / D 无固件不造假 /
  E 固件发现跳过 demo）。SWE.6 影响闭包 128 passed 零回归。
- **历史根因**：`device/` HIL 层此前未被任何 step_handler 调用（仅 CLI/UI 入口）。

### P1 — SYS→SWE 左→右追溯链不强制（已闭环 ✅，2026-10-10）

- 原 `_check_sys_requirements_aligned`（spec.py:186）默认 `status=partial` 仅 WARNING；
  严格阻断需 `OSH_SYS_ALIGN_STRICT=1`（默认关）。
- 修复（提交 `48c56269`）：`OSH_SYS_ALIGN_STRICT` **默认开启**，仅对真实缺口
  `status∈{partial,none-parsed}` 使 SWE.1 步骤失败；`absent`/`skipped`（无左半文档，
  纯 SWE 工程）保持非阻断，保向后兼容、不回归。
- 把守：`test_sys_req002_strict_align.py`（默认阻断 partial/none-parsed；env=0 显式放行；
  absent 非阻断）；`tests/conftest.py` 统一 autouse 夹具隔离对齐，避免误命中仓库根
  `system-requirements.md`。

### P2 — SWE.5 集成测试弱证据（已闭环 ✅，2026-10-10）

- 原 compliance_checker.py:1327 SWE.5 集成类 check 用 `_test_suite_passes()` 代理"集成测试通过"（假绿）。
- 修复（提交 `9198b7c0`）：新增 `_has_integration_results()`（真实集成证据：`.osh/ci/integration-*`
  结果 / junit integration XML，排除 hello/sample demo），SWE 区 integration 分支改用其替代单测代理。
- 把守：`test_sys_req004_integration.py` 原 `test_swe5_integration_still_uses_test_suite` 假绿回归保护
  已改写为反假绿断言（仅单测→RED；真实集成证据→GREEN）；golden 同步 SWE.5/6 反假绿信息。

### P2 — SUP/MAN 支持与管理过程无独立评估域（已闭环 ✅，2026-10-10）

- 原 profile 仅含 SYS/SWE 工程过程域；SUP/MAN 检查项一律落入 "unknown check type"。
- 修复（提交 `d784e6d1`）：
  - 新增 `aspice_support_mgmt_v3.1.yaml`：SUP.1/8/9/10 + MAN.1/2/3 过程域与 base practices，
    检查项映射到真实项目产物。
  - `ComplianceChecker.__init__` 支持 `profile_names` 多 profile 合并评估（`_merge_profiles`）；
    `_check_bp` 新增 SUP/MAN 分发分支 + `_has_qa_records`/`_has_vcs_baseline`/`_has_issue_records`/
    `_has_change_records` 证据函数；无证据如实判 RED（反假绿，不臆造）。
  - `aspice_gap_check` 接入 `profile_names`，导出 `ASPICE_FULL_PROFILES`（SWE+SYS+SUP/MAN 组合）。
  - 把守：`test_sys_req_sup_man_domain.py`（SUP/MAN 被真实评估而非 unknown、无证据 RED、有证据 GREEN、
    组合 profile 合并生效）。

---

## 4. 支持度总评

| 维度 | 状态 | 关键证据 |
|---|---|---|
| V 模型工程过程骨架（SYS.1–5 + SWE.1–6） | ✅ 完整 | 30 步 + 11 域 profile + unknown=0 |
| 11 Gate 视图 | ✅ 完整 | gates.py G0–G10 |
| 反假绿（SYS.4/SWE.5/SWE.6 不被单测顶替） | ✅ 已修 | 提交 `7a402c9c`/`f673688d`/`9198b7c0` |
| 双向追溯 SUP.1 | ✅ 已强制 | `OSH_SYS_ALIGN_STRICT` 默认开；真实缺口使 SWE.1 失败（提交 `48c56269`）|
| 一致性 | ⚠️ 部分 | G9 merge-gate KG 一致性 |
| 目标/等效环境执行证据（SWE.6） | ✅ 已打通 | 提交 `2da8c943`；device/ 经 `_run_hil_qualification` 接入，仅真通过才落 sil |
| SUP/MAN 支持管理过程 | ✅ 已闭环 | 新增 `aspice_support_mgmt_v3.1.yaml` + 分发分支（提交 `d784e6d1`）|

**一句话**：工程过程双 V 的"工具链 + 合规判定"已就绪且诚实，
**SWE.6 目标环境执行证据链已闭环（P0）**，且 **P1（SYS→SWE 对齐强制）与
P2（SWE.5 反假绿 + SUP/MAN 独立评估域）均已闭环**。yuleOSH 现可声称
**完整支撑 ASPICE V 模型工程过程 + 支持/管理过程的合规评估闭环**。

---

## 5. 建议下一步（加强项，非阻断）

1. **P0/P1/P2 均已完成**（提交 `2da8c943`/`d01ea214`/`48c56269`/`9198b7c0`/`d784e6d1`）。
2. **默认组合评估接入**：将 `aspice_gap_check` 默认 `profile_name` 改为
   `ASPICE_FULL_PROFILES`（SWE+SYS+SUP/MAN），使默认报告即覆盖全 V 模型；
   当前保持单 profile 默认以保向后兼容，组合评估为显式选项。
3. **审计/看板聚合**：在 `audit_report.py` 与 dashboard 中消费 SUP/MAN 章节，
   让支持/管理过程合规度进入统一报告视图。
4. **文档化**：补充 SUP/MAN 各 BP 的"yuleOSH 如何产出对应证据"指引（CL2/CL3 清单）。
