# ASPICE 4.0 座椅控制器 Demo（主驾 SCM）

> **示例数据，仅用于演示填写方式与追溯闭环，不得作为项目证据。**
> 场景为主驾座椅控制器（Seat Control Module, SCM）：4 路电机八向调节、3 组位置记忆、
> 加热/通风、防夹保护、LIN 通信与 UDS 诊断。需求、ID、代码路径与测试结果均为演示数据。

## 1. 产物清单

| 文件 | 内容 |
| --- | --- |
| `SYS.2_系统需求规格说明书_座椅控制器示例_V1.0.xlsx` | 5 条涉众需求对应的 8 条系统需求（功能/非功能），含验证阶段与验证准则 |
| `SYS.3_系统架构设计说明书_座椅控制器示例_V1.0.xlsx` | 5 个系统架构元素、总体上下文框图、物理架构框图、电源状态说明与状态机图 |
| `SWE.1_软件需求规格说明书_座椅控制器示例_V1.0.xlsx` | 8 条软件需求（电机控制、记忆、热舒适、防夹、LIN、诊断、低压保护） |
| `SWE.2_软件架构设计说明书_座椅控制器示例_V1.0.xlsx` | 6 个软件模块、分层架构框图、组件接口、动态行为、安全/资源设计，含状态机图 |
| `SWE.3_软件详细设计说明书_座椅控制器示例_V1.0.xlsx` | 7 个函数的详设（参数、返回值、算法、调用与实现文件） |
| `HWE.1_硬件需求规格说明书_座椅控制器示例_V1.0.xlsx` | 4 条硬件需求 + 4 条硬件非功能指标 |
| `HWE.2_硬件设计说明书_座椅控制器示例_V1.0.xlsx` | 硬件框图、3 个硬件设计元素、接口、电源状态说明与状态机图、时序与详细设计 |
| `ENG_需求追踪表_座椅控制器示例_V1.0.xlsx` | 8 张清单共 46 个节点，上下游双向回指 |
| `ENG_测试规范_座椅控制器示例_V1.0.xlsx` | 8 条系统级测试用例（`SYS-SEAT-xxx-TC-01`） |
| `trace_report_座椅控制器示例.md` / `.json` | `trace_check.py --bidirectional` 的校验报告 |
| `evidence/`（8 份 md + `evidence_manifest.json`） | pipeline 产物原型：每份产物 frontmatter 自声明填充的模板槽位，清单记录 sha256 基线 |
| `slots.yaml` | 模板槽位规格：sheet/表头定位/行键列/证据列/字段映射/受控词表，check 与 render 共用 |
| `HWE.2_原理图占位说明_座椅控制器示例_V1.0.docx` | HWE.2 第 3 章三处原理图占位框的规格化说明（分块清单/器件选型/接口信号/EDA 注意事项） |

## 2. 追溯链

```text
STK-SEAT-001..005 涉众需求
   └─ SYS-SEAT-001..008 系统需求
        └─ SYS-ARCH-SEAT-001..005 系统架构元素
             ├─ HW-SEAT-001..004 硬件需求 ── HW-DES-SEAT-001..003 硬件设计元素（链尾）
             └─ SW-SEAT-001..008 软件需求
                  └─ SW-ARCH-SEAT-001..006 软件架构元素
                       └─ SW-DD-SEAT-001..007 软件详设（链尾）
```

主要覆盖关系：

- `SYS-SEAT-001` 八向调节 → `SYS-ARCH-002` 电机驱动 + `SYS-ARCH-003` 开关/位置输入
- `SYS-SEAT-002` 位置记忆 → `SYS-ARCH-001/002/003`
- `SYS-SEAT-003/004` 加热/通风 → `SYS-ARCH-004` 热舒适执行单元
- `SYS-SEAT-005` 防夹 → `SYS-ARCH-002/003`
- `SYS-SEAT-006/008` 诊断/LIN → `SYS-ARCH-001/005`

每条「下游元素」在目标行的「上游元素」中均有回指，满足双向闭环。

## 3. 复现校验

```bash
cd /workspace/aspice
python3 tools/trace_check.py \
  --trace "examples/seat/ENG_需求追踪表_座椅控制器示例_V1.0.xlsx" \
  --cases "examples/seat/ENG_测试规范_座椅控制器示例_V1.0.xlsx" \
  --bidirectional \
  --out "examples/seat/trace_report_座椅控制器示例.md" --json
```

## 4. 实测结果（基线模式，退出码 0）

| 指标 | 数值 |
| --- | --- |
| 有效行 / 全库唯一 ID | 46 / 46 |
| 下游引用 / 断链 | 61 / **0** |
| 孤儿节点 | **0** |
| ERROR / WARN / INFO | **0 / 3 / 0** |
| 测试用例引用覆盖率 | 8/8（**100%**） |
| 双向闭环 | **开启且一致** |
| 设计文档对齐 | SWE.2 6 模块 / SWE.3 7 函数 / HWE.2 3 元素，ID 与名称与追踪表 100% 一致 |
| 框图与状态机 | 框图 4 张（总体上下文 / 系统物理 / 软件分层 / 硬件）+ 状态机 3 张，均与同页文字对应 |

3 条 WARN 均来自模板既有结构，不是链路缺陷：

1. `0.示例声明`：声明页无表头，校验器按非清单页跳过；
2. `网络安全需求`：原模板该页没有独立 ID 列，无法建立索引；
3. `软件详设清单`：原模板没有“下游元素”列，按链尾处理（其“上游元素”已补齐）。

启用 `--strict` 时上述 WARN 会使退出码变为 1，建议模板层面补齐后再用于门禁。

## 5. 证据链原型（pipeline 产物 ↔ 模板槽位）

`evidence/` 演示了「yuleOSH pipeline 产物按 ASPICE 模板槽位填写」的最小闭环：

- **槽位**：`文档别名::用例ID::列名`，由模板枚举（测试规范第 1 轮 实际结果/测试日志链接/判定结论 × 8 用例 = 24 槽位）；
- **产物自声明**：每份 pipeline 产物（md）在 frontmatter 声明 `stage` 与 `fills` 槽位列表；
- **清单基线**：`evidence_manifest.json` 记录每份产物 sha256，作为 SUP.8 配置项基线；
- **双向闭合 + 防篡改校验**：

```bash
cd /workspace/aspice
python3 tools/evidence_check.py \
  --cases "examples/seat/ENG_测试规范_座椅控制器示例_V1.0.xlsx" \
  --evidence examples/seat/evidence --write-manifest   # 建/更新基线
python3 tools/evidence_check.py \
  --cases "examples/seat/ENG_测试规范_座椅控制器示例_V1.0.xlsx" \
  --evidence examples/seat/evidence                    # 日常校验（CI 门禁）
```

fail-closed 规则：槽位未填充（E-SLOT-UNFILLED）、产物孤儿（E-SLOT-UNKNOWN）、
空壳产物（E-ARTIFACT-EMPTY）、哈希不符（E-HASH-MISMATCH）、产物消失（E-MANIFEST-STALE）、
缺字段（E-FIELD-MISSING）、越受控词表（E-VOCAB）均为 ERROR，退出码 1。
已验证：24/24 槽位填充 PASS → 篡改单文件 FAIL → 删除单文件 FAIL → `verdict: PASSED`
越词表 FAIL → 恢复 PASS。

**槽位规格化（slots.yaml）**：`slots.yaml` 把模板的 sheet/表头定位/行键列/证据列/
frontmatter 字段映射/受控词表全部数据化，evidence_check 与 evidence_render 共用此
唯一依据；新增模板只需新增一段 yaml，工具零改动。

**渲染回写（evidence_render.py）**：manifest 是真源，xlsx 是渲染视图。渲染器先过
evidence_check 门禁（有 ERROR 即中止），再按槽位把 frontmatter 字段写回单元格，
写后自动重读校验；目标格已有不同内容即冲突 ERROR（`--force` 可覆盖）。

```bash
python3 tools/evidence_render.py \
  --cases "examples/seat/ENG_测试规范_座椅控制器示例_V1.0.xlsx" \
  --evidence examples/seat/evidence --slots examples/seat/slots.yaml [--dry-run]
```

已验证：24 单元格回写 PASS → 幂等复渲染 0 写入 PASS → trace_check 回归 0 ERROR。
完整闭环：pipeline 产物(md) → evidence_check 门禁 → evidence_render 回写 → xlsx 交付视图。

**真实 stage 接入（SUP.1）**：`evidence_stage/` 演示了 yuleOSH 真实 pipeline 产物的接入——
对 yuleOSH 仓库本体运行 `ComplianceChecker`（ASPICE v3.1，18 BP），原始输出存为
`compliance_raw.json`，由 `adapter_compliance.py` 完成两件事：① 在 SUP.1_评审记录
「2.评审检查单」按 BP 幂等建立 18 行检查项骨架；② 每个 BP 生成一份 frontmatter 产物
（verdict 映射 ✅→通过，⚠️/❌→不通过，部分通过不算通过）。随后走同一套门禁与渲染：

```bash
python3 tools/evidence_check.py --cases "examples/seat/SUP.1_评审记录_座椅控制器示例_V1.0.xlsx" \
  --evidence examples/seat/evidence_stage --slots examples/seat/slots.yaml \
  --doc-alias SUP.1_评审记录 --write-manifest
python3 tools/evidence_render.py --cases "examples/seat/SUP.1_评审记录_座椅控制器示例_V1.0.xlsx" \
  --evidence examples/seat/evidence_stage --slots examples/seat/slots.yaml --doc-alias SUP.1_评审记录
```

已验证：36 槽位（18 BP × 2 列）全闭合 PASS，36 单元格回写 PASS，
真实判定 4 通过 / 14 不通过 原样落表（不造假绿）。
接入新 stage 的完整步骤：跑 stage 存原始输出 → 适配器生成 frontmatter 产物 →
slots.yaml 加文档段 → check + render。

**跨文档一致性（consistency_check）**：`consistency.yaml` 声明两类检查，由
`tools/consistency_check.py` 执行（fail-closed）：
- **实体名一致性**：同一 ID 在 SWE.2/HWE.2/SYS.3 与需求追踪表（名称真源）中的名称必须一致
  （本 demo 14 个架构实体全部一致，机械化了原先的人工核对）；
- **数值事实一致性**：欠压 8.5V、休眠电流 ≤1mA、PWM 10kHz、LIN 19.2kbps、3 组记忆、
  单路 2A/5A、整机 8A/12A 等关键数值在所有文档中的取值必须一致。

```bash
python3 tools/consistency_check.py --spec examples/seat/consistency.yaml [--strict]
```

已验证：27 处数值 + 14 实体全绿；篡改 HWE.1 欠压 8.5V→8.0V 后精确报出
`E-FACT-MISMATCH`（定位到文件/sheet/单元格/原文），恢复后回绿。
实施中的一次真实裁决：检查器把 HWE.2 的「连续 8A/峰值 12A」判为与「单路 2A/5A」不一致——
这是整机合计与单通道两类不同事实，已拆成独立事实条目（机器标记 → 人裁决 → 规格精化）。

**资源使用事实（4.0.1 扩展清单）**：consistency.yaml 另有 7 条资源事实
（CPU 峰值 62%/目标 ≤70%、Flash 62/128KB、RAM 7/16KB、主频 48MHz、晶振 8MHz），
模块 CPU 均值与峰值是不同口径、不求和（规格注释已记）；数值比较按 float 等价（7.0==7），
晶振与主频是两个事实（模式精化的又一实例）。

**产品配置（variant_check）**：`variant.yaml` 定义 8 特性 ↔ 8 SYS 需求 ↔ 3 变体
（SC-BASE/SC-MEM/SC-COMFORT），`产品配置_变体需求矩阵_座椅控制器示例_V1.0.xlsx` 为渲染矩阵，
已接入 gate_sync 第八校验器。门禁：`E-VAR-DUP` / `E-VAR-FEATURE` / `E-VAR-REQ`（映射需求在
SYS.2 不存在）/ `E-VAR-ORPHAN-REQ`（需求无变体承接）/ `E-VAR-EMPTY`。
实测：删除加热/通风特性 → 精确报出 SYS-SEAT-003/004 孤儿需求 → 自动开单 → 恢复关闭。

**SUP.8 配置管理（cm_registry）**：`cm_registry.yaml` 是本目录的配置项注册表（真源），
`SUP.8_项目配置项清单及状态报告_座椅控制器示例_V1.0.xlsx` 是从注册表渲染的视图，
由 `tools/cm_registry.py` 驱动（fail-closed）：

```bash
python3 tools/cm_registry.py --root examples/seat --verify    # 哈希/覆盖性校验
python3 tools/cm_registry.py --root examples/seat --update    # 变更后刷新基线
python3 tools/cm_registry.py --root examples/seat --render    # 重新生成 SUP.8 清单
```

- 三条门禁规则：`E-HASH-MISMATCH`（文件与基线哈希不符）/ `E-ITEM-MISSING`（已注册文件丢失）/
  `E-FILE-UNREGISTERED`（工作产品未受控，SUP.8 要求 100% 覆盖）；
- 已验证：47 个配置项（10+ 文档、规格 yaml、证据目录、工具脚本、SUP.8 清单自身）基线
  SEAT-DEMO-BL1 全绿；篡改 consistency.yaml 后精确报出哈希不符（注册值 ≠ 实际值），恢复回绿；
- 与 evidence manifest 的分工：manifest 管「pipeline 产物 ↔ 模板槽位」，
  cm_registry 管「工作产品文档本身」的受控与防篡改，两者共同构成 SUP.8 证据。

**SUP.9/10 自动闭环（gate_sync）**：`gate_registry.yaml` 是问题单/变更请求的真源，
SUP.9_缺陷问题管理表 与 SUP.10_项目变更跟踪表 是渲染视图，由 `tools/gate_sync.py` 驱动：

```bash
python3 tools/gate_sync.py --root examples/seat --sync-problems   # 五校验器 → 问题单
python3 tools/gate_sync.py --root examples/seat --sync-changes    # cm changelog → 变更请求
python3 tools/gate_sync.py --root examples/seat --render          # 渲染 SUP.9/SUP.10
```

- **问题单（SUP.9）**：每次同步运行 trace/evidence×2/consistency/cm_registry 五个校验器，
  每条 ERROR 按内容哈希开立 PR-SEAT-xxx（去重）；不再出现的 ERROR 自动关闭并记「门禁自动复测」；
- **变更请求（SUP.10）**：cm_registry --update 会把每次哈希刷新/新增写入 changelog，
  gate_sync 据此登记 CR-SEAT-xxx（去重），变更原因 = 哈希前后值；
- 实测闭环：注入欠压 8.0V → 自动开立 PR（consistency + cm_registry 双视角各一条）→
  恢复后自动关闭；基线过期、新文件未受控也会被自动开立（本系统上线首日即抓到
  README 基线过期与 gate_registry.yaml 未注册两个真实问题）；
- **活文档建模**（解决自引用振荡）：gate_registry.yaml 与 SUP.9/SUP.10 视图既是受控项、
  内容又随登记行为自身变化，若按普通文件做哈希基线会永远振荡。建模为「活文档」：
  必须注册受控（存在性强制），哈希仅信息记录，其自身变化不产生变更请求——
  登记表记录自身不是「变更」。修复后两轮循环即收敛到不动点（第二轮零变化）。

**MAN.1 度量（metrics_collect）**：`metrics.yaml` 定义 9 个度量项（M-SEAT-01..09，
数据源即五个校验器的 JSON 输出 + gate_registry），`metrics_history.jsonl` 为时间序列
（活文档），`横切_过程度量与目标定义_座椅控制器示例_V1.0.xlsx` 为渲染视图：

```bash
python3 tools/metrics_collect.py --root examples/seat --collect   # 采集+判定（FAIL 退出码 1）
python3 tools/metrics_collect.py --root examples/seat --render    # 渲染度量文档
```

- 度量定义含 extract 点路径（支持 `[k=v]` 过滤与 `.count`）或 expr 表达式，
  规则 eq/gte/lte/info；**metrics_collect --verify 已作为第六校验器接入 gate_sync**：
  度量红 → 自动开 PR，复采回绿 → 自动关闭；
- 实测：首次采集即抓到 M-SEAT-07 FAIL（metrics.yaml 未注册）；注入欠压 8.0V →
  M-SEAT-05 红 + 自动开单；恢复 → 自动关闭；
- **设计教训（自锁环）**：M-SEAT-08「打开问题数」初设 `lte 0`，度量红会自动开单、
  打开数恒 ≥1、度量恒红——度量若镜像门禁自身状态，只能做 info 趋势项，
  升级动作留人裁决。已修正并留注释；
- **深化 ①**：metrics.yaml 定义本身进门禁（`E-METRIC-DEF`：重复 ID / 非法 rule /
  非 info 缺 target / extract 与 expr 互斥）；
- **深化 ②**：同一度量连续 ≥2 次采集 FAIL 触发 `E-METRIC-STREAK` 趋势升级
  （区分单次抖动与持续恶化），实测 M-SEAT-05/07 双 streak 开火 → 6 单齐开 → 恢复齐关。

**MAN.5 风险 + MAN.3 计划（man_check）**：`risk_registry.yaml`（5 风险）与
`plan.yaml`（5 里程碑 + 8 WBS）为真源，MAN.5_风险登记册 / MAN.3_项目进度计划
为渲染视图，`tools/man_check.py --verify` 已作为第七校验器接入 gate_sync：

- 风险门禁：`E-RISK-VOCAB`（P/I∈1-5、状态/策略词表）/ `E-RISK-EXPOSURE`（登记值≠P×I）/
  `E-RISK-NO-MITIGATION`（exposure≥6 缺应对或复审日期）/ `E-RISK-EXPIRED`（复审逾期）；
- 计划门禁：`E-PLAN-DATE` / `E-PLAN-PRED` / `E-MILESTONE-SLIP`（里程碑逾期无实际日期）/
  `E-WP-NO-CI`（WBS 产出物不在配置库）/ `E-CI-NO-WP`（顶层文档无 WBS 认领）；
- 实测：注入复审逾期 + 里程碑滑期 → 门禁精确报红并自动开单；**未注入也被抓到
  两条真问题**——MAN.3/MAN.5 渲染视图自身是顶层文档却无 WBS 认领
  （E-CI-NO-WP），已在 WP-SEAT-08 补登记。计划↔配置库双向闭合是 MAN.3 机械化的核心价值。

## 6. 范围边界

- 本次 Demo 已覆盖 **V 模型左半（需求 → 架构 → 软硬件需求 → 软件架构 → 详设）** 与
  **系统级验证用例**；SWE.2/SWE.3/HWE.2 三份设计文档已补齐，模块/函数/硬件元素 ID
  与名称和追踪表逐项对齐。
- SYS.3 的总体上下文图、系统物理架构图，SWE.2 的软件分层架构图，HWE.2 的硬件框图，以及
  三份文档的电源/工作状态机图，均已用 Graphviz 绘制并内嵌；状态与迁移条件同页对应。
- 其余流程图、时序图沿用模板自带示意图；HWE.2 第 3 章的三处“原理图片段”仍是占位框，
  需在 Altium/KiCad 等 EDA 工具中完成实际电路原理图，框图不能替代原理图。
- 未包含 MAN.3 计划、SUP.1 评审、SUP.8 配置、SUP.9/10 问题与变更、度量采集等过程证据；
  这些模板已在 `templates_clean/` 与 `templates_new/` 中提供，可按项目实际补充。
- 测试用例只证明“引用关系完整”，不代表测试已执行或通过。
