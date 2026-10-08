# 左半 V（SYS 侧）缺陷修复 —— 需求规格 (Requirements Specification)

> 起草日期：2026-10-08
> 流程：按 ASPICE V 模型左下行 —— **涉众需求 → 系统需求(SYS.1) → 验收/验证准则**
> 上游来源：`docs/planning/product-vmodel-gap-assessment-v2-10-08.md` §4.1 / §4.2 / §4.3 / §4.5 / §4.6
> 被修复对象：`main @ 6075aa90`

---

## 0. 范围边界

| | 内容 |
|---|---|
| **本轮范围（左侧）** | §4.1 语义倒置、§4.2 SYS→SWE 不强制、§4.3 checker 不识 SYS、§4.5 追溯不实质、§4.6 文档漂移 |
| **不在本轮** | §4.4 SWE.6/HIL 假绿 —— 属右半 SWE.6，风险机制不同，**另立需求单独立项**（已记牵引 TODO） |
| **不变更** | 现有默认行为（向后兼容优先，见 §4 约束） |

---

## 1. 涉众需求 (Stakeholder Requirements)

> 涉众 = 产品负责人（明总）+ 外部客户/审计方视角。以下为**需求来源**，非解决方案。

| ID | 涉众需求 | 动因（痛点） |
|---|---|---|
| STAKE-01 | 左半 V 必须是**真正的需求驱动**：系统需求应来自涉众需求，而不是由软件 spec 反推出来装样子 | 当前 `sys_layer.py` 从 spec 标题派生 SYS-REQ，审计方一问"涉众需求在哪"即暴露 |
| STAKE-02 | V 两侧之间的链接必须**可被门禁强制执行**，不能只是"记录一下、照样放行" | 当前 SYS→SWE.1 对齐缺失仅 WARNING，脱节也全绿 |
| STAKE-03 | 合规判定必须**真实反映被测内容**：不许"有证据但不知道怎么判"，也不许拿别的信号冒充 | SYS.3/5 大量 `unknown check type`；SYS.2 文档 595B 判不出实质内容 |
| STAKE-04 | 追溯矩阵必须**实质存在且指标达标**，可直接作为对外证据 | 6 个 BP 报 `no substantive traceability matrix`；v1 快照自注不可交付 |
| STAKE-05 | 对外文档必须与实现一致，不得存在步数等基本事实漂移 | blueprint 写 36 步，实际 30 步 |

---

## 2. 系统需求 (System Requirements — SYS.1)

每条需求均含**可验证验收准则**（这正是本轮要补的能力：需求可追溯、可验证）。

### SYS-REQ-001（追溯 STAKE-01）涉众需求源与派生方向正位
系统须支持**涉众需求输入源**（约定 `docs/stakeholder-requirements.md`），SYS.1 由其派生系统需求；
当该文件缺失时，须**显式降级标注**（在产物与 trace sidecar 中记录 `source=spec-derived`），不得静默把 spec 反推结果伪装成系统需求。

- **验收**：① 提供含 `STAKE-xx` 的涉众需求文件时，生成的 SYS-REQ 含到 STAKE-ID 的映射且数量/标题可核；
  ② 缺失该文件时，`system-requirements.md` 与 `sys-to-swe-trace.json` 明确标注降级来源，且交出可机读字段 `source`。
- **验证方式**：单元/契约测试 + 实跑 `step_sys_requirements` 双场景（有/无涉众需求）。

### SYS-REQ-002（追溯 STAKE-02）SYS→SWE 对齐可配置为阻断
`_check_sys_requirements_aligned` 的结果须能被提升为**步骤失败**，通过显式开关控制（默认放行以保兼容）。

- **验收**：开启严格开关后，SYS 需求未对齐时 SWE.1 步骤返回非 `completed`；关闭时行为与现状一致。
- **验证方式**：测试双开关场景（strict / default）。

### SYS-REQ-003（追溯 STAKE-03a）合规引擎须识别 SYS 交付物内容
checker 对 SYS check items 必须给出**明确判定**（✅/❌），不得返回 `unknown check type — not recognized`。

- **验收**：对 `aspice_sys_v3.1` 实跑后，报告中出现 `unknown check type` 的条目数为 **0**。
- **验证方式**：实跑合规引擎逐 BP 扫描（复用 `/tmp/sys_compliance_probe.py` 思路，需入库为可复现脚本）。

### SYS-REQ-004（追溯 STAKE-03b）SYS 交付物须达实质内容阈值
SYS 生成的 architecture / verification / validation 文档须包含结构性实质内容（元素边界、接口定义、验收准则矩阵），达到 checker 实质阈值。

- **验收**：SYS.2 不再出现 `no substantive architecture doc found`；接口表与验收矩阵可被 checker 探到。
- **验证方式**：实跑合规引擎 + 文档结构断言。

### SYS-REQ-005（追溯 STAKE-04）追溯矩阵默认落盘且指标达标
流水线须默认产出 checker 可读的权威追溯产物：`.osh/evidence/traceability-matrix.json`（及 `.md`），且需求→测试映射覆盖率 **≥60%**。

- **验收**：checker 报告中 `no substantive traceability matrix` 条目数归零；`_traceability_metrics_met()` 为 True。
- **验证方式**：实跑 + 断言 `.osh/evidence/traceability-matrix.json` 存在且覆盖率达标。

### SYS-REQ-006（追溯 STAKE-05）对外文档与实现一致
`docs/product/yuleOSH-product-blueprint.md` 中的流水线步数描述须与 `PIPELINE_STEPS` 实际长度一致（当前 30）。

- **验收**：文档不再出现与实际不符的步数宣称（或改为从代码自动派生/注明实测值）。
- **验证方式**：grep 断言一致性。

---

## 3. 验证 / 确认准则 (Verification & Validation)

- **V&V-01**：每条 SYS-REQ 必须有对应的自动化验证（测试或可复现实跑脚本），不接受"仅人眼确认"。
- **V&V-02**：所有改动须通过**零回归证明**：影响闭包 A/B（改动前后同命令对照）+ 相关测试全绿。
- **V&V-03**：最终确认由产品负责人（明总）在浏览器/本机侧复核关键渲染与文档产出。

---

## 4. 约束（跨切面）

| 约束 | 说明 |
|---|---|
| 向后兼容 | 新能力默认不改变既有行为，严格模式须由显式开关启用 |
| 异常安全 | 所有新增读取/写入须 `try/except`，任何失败不得阻断既有流水线 |
| 确定性优先 | 沿用 M1 做法：确定性生成/判定，避免 LLM 判绿带来的不可复现 |
| 零污染 | 采用附加字段/新文件方式，不破坏既有数据结构 |
| 提交纪律 | 分笔提交（不混合），本地提交，**推送待明总指示** |
| 证据可机读 | 新增产物须为 JSON/Markdown 结构化，供 checker 与审计消费 |
