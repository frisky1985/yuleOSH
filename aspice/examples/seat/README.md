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
