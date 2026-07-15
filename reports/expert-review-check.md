# 专家评审准备 — 老陈 👨‍🏫 风格

> **审查框架**: 四轮递进审查大纲、评分维度、通过条件、已知风险标注
> **生成时间**: 2026-07-10
> **审查范围**:
>   1. Phase 2 — MISRA C:2023 规则库升级
>   2. Phase 3 — yuleASR 深度集成
>   3. Desktop v0.1.0-MVP
>   4. Phase 1 测试覆盖率
> **评审人风格**: 老陈 👨‍🏫（前博世汽车电子资深架构师，20+ 年嵌入式/ASPICE/ISO 26262 经验）
> **通过基线**: 85/100（CL2 标准下放）

---

## 总纲：老陈的审查哲学

> 「代码我只看结构，不看拼写。—— 老陈」

四轮审查的逻辑链：

```
R1 可追溯性（有没有）
  ↓
R2 可用性（能不能用）
  ↓
R3 合规深度（对不对）
  ↓
R4 系统韧性（抗不抗打）
```

**评分权重**: R1(15%) + R2(25%) + R3(35%) + R4(25%) = 100

**整体通过线**: **≥ 85/100**，且无 P0/P1 级以上未接受风险。

---

## R1: 可追溯性审查（Traceability & Completeness）— 有没有

> 老陈语：「先把摊子铺开，看看东西全不全。」

### 审查内容

| # | 维度 | 说明 | 评分（0-10） |
|:-|:-----|:------|:-----------:|
| 1.1 | 需求覆盖完整性 | 所有 SHALL/SHALL NOT 是否有对应实现/测试 | □ |
| 1.2 | 规则库完整性 | MISRA C:2023 180 条规则全量覆盖 | □ |
| 1.3 | 模块清单完备性 | yuleASR 模板中的 21+29+44 模块是否全部有对应的 spec/handler/config | □ |
| 1.4 | 接口契约完整度 | CLI 子命令参数定义、返回码、ABI 边界是否明确 | □ |
| 1.5 | 测试-需求双向追溯 | 每个测试用例是否可追溯到具体的 Req/SHALL/规则编号 | □ |
| 1.6 | CI gate 对齐度 | Pipeline 各 stage 的通过条件是否与验收矩阵对齐 | □ |
| 1.7 | 文档覆盖度 | 架构文挡、自测清单、验收矩阵是否无缺失章节 | □ |

### 评分标准

| 分数区间 | 定性 | 判定 |
|:--------:|:-----|:-----|
| 9-10 | 完整覆盖，无遗漏 | ✅ 优秀 |
| 7-8 | 主要覆盖，1-2 项轻微遗漏 | ⚠️ 可接受 |
| 5-6 | 关键部分覆盖，3+ 项遗漏 | 🔴 需补 |
| <5 | 覆盖不完整，结构性问题 | ❌ 不通过 |

### 加权：15%

### 通过条件
- 每项 ≥ 5 分
- 加权后 ≥ 12/15
- 无 P0 级遗漏

### 已知风险点

| 风险 | 等级 | 说明 |
|:-----|:----:|:------|
| 🔴 MISRA C:2023 规则全量覆盖未在测试套件中显式验证 | P1 | phase2 报告 30 个测试，验证了 143+37=180 条规则的映射存在性，但未逐条验证规则语义正确性 |
| 🟡 yuleASR 模板的 21+29+44 模块未全部生成单元测试框架 | P2 | 模板中 `tests/.gitkeep` 为空，仅 create_test_main 生成了一个简陋框架 |
| 🟡 Desktop 验收矩阵与自测清单条数未交叉引用 RTM | P2 | 自测 30 项与验收矩阵 7 章之间的 trace 关系未显式建立 |
| 🟢 Phase 1 覆盖率目标限定为「目标模块 ≥ 60%」，未对全项目设置 ≥ 60% | P3 | 全局覆盖率 30%，大量模块（evidence/engine/ci/pipeline）未覆盖 |

---

## R2: 可用性审查（Usability & Functionality）— 能不能用

> 老陈语：「你说你做完了，那给我跑一个看看。」

### 审查内容

| # | 维度 | 说明 | 评分（0-10） |
|:-|:-----|:------|:-----------:|
| 2.1 | CLI 命令可达性 | `yuleosh init-autosar` 是否可通过 `pip install` 后的 CLI 直接调用 | □ |
| 2.2 | 模板生成完整性 | `init-autosar` 产生的项目是否可直接 `make` 构建 | □ |
| 2.3 | 向后兼容性 | C:2012 遗留规则 ID 和 cppcheck 输出格式在 C:2023 升级后是否仍能解析 | □ |
| 2.4 | Desktop 启动时序 | Electron 启动 → spawn Python → 健康检查 → 加载 UI 的全链路是否正常 | □ |
| 2.5 | Desktop 错误处理 | Python 子进程崩溃/端口占用/Python 未安装的场景是否友好提示 | □ |
| 2.6 | CI pipeline 端到端 | `yuleosh ci run 2` 在 AUTOSAR 项目上是否可以完整执行 | □ |
| 2.7 | 跨平台 Desktop 构建 | macOS (.dmg) + Linux (.AppImage/.deb) 构建脚本是否可用 | □ |
| 2.8 | 规则 ID 多格式解析 | 8 种输入格式（c2023 规范/c2012 风格/裸数字/MISRA 前缀/年会/Directive 新旧/已删除规则）是否全部可解析 | □ |
| 2.9 | init-autosar 与 template 系统的搜寻优先级 | TG-REQ-002 规定的三层优先级（项目本地/用户本地/内置）是否全部生效 | □ |
| 2.10 | Desktop 单实例保护 | 快速双击是否只启动一个实例 | □ |

### 评分标准

| 分数区间 | 定性 | 判定 |
|:--------:|:-----|:-----|
| 9-10 | 完整可用，全链路验证通过 | ✅ 优秀 |
| 7-8 | 主要路径可用，边缘场景有轻微瑕疵 | ⚠️ 可接受 |
| 5-6 | 核心路径可用，但有阻塞性问题 | 🔴 需修复 |
| <5 | 不可用或关键路径断裂 | ❌ 不通过 |

### 加权：25%

### 通过条件
- 每项 ≥ 5 分
- 加权后 ≥ 20/25
- 2.1、2.4、2.6 中无 < 5 分项

### 已知风险点

| 风险 | 等级 | 说明 |
|:-----|:----:|:------|
| 🔴 `yuleosh init-autosar` 被实现在 `yuleosh_cli.py`（项目根目录）而非 `src/yuleosh/cli/` 包内 | P0 | `pip install` 后 `yuleosh init-autosar` 命令行不可达。根目录的 `yuleosh_cli.py` 是独立脚本，需要通过 entry_points 注册，当前缺少 `pyproject.toml` 入口点配置 |
| 🔴 `cmd_init_autosar` 中 `from yuleosh.templates import resolve_template` 的包内导入路径依赖 | P1 | 当 `yuleosh_cli.py` 作为独立脚本运行时，import 路径可能因 `PYTHONPATH` 未设置而失败 |
| 🟡 Desktop 的 `yuleosh_cli.py` 中缺少 init-autosar 的 Python callable entry point | P1 | phase 3 报告声称 CLI 可用，但实际包入口 `/src/yuleosh/cli/` 中找不到 `init-autosar` 命令 |
| 🟡 Desktop 未在生产模式测试「Python 后端启动竞争」场景 | P1 | 自测清单 7.5 项「前后端同时启动竞争」标记为 pass，但验证环境仅为 macOS arm64 |
| 🟢 Desktop Wayland 兼容性未实际验证 | P2 | 自测 5.2.5 项「兼容 Wayland 显示服务器」仅列显未验证 |
| 🟢 MISRA 规则库 YAML 文件路径不在 `src/yuleosh/ci/rulesets/` 下 | P2 | `misra-rules.yaml` 在项目根目录，与 `rulesets/` 目录分离，部署时需确认文件复制 |

---

## R3: 合规深度审查（Regulatory Depth & Specification Alignment）— 对不对

> 老陈语：「你说你过了 MISRA，那你告诉我 Rule 10.1 的 essential type 模型是怎么处理的。」

### 审查内容

| # | 维度 | 说明 | 评分（0-10） |
|:-|:-----|:------|:-----------:|
| 3.1 | MISRA C:2023 规则语义正确性 | 规则分类（M/R/A）是否与 MISRA C:2023 官方规范一致 | □ |
| 3.2 | AUTOSAR 规范对齐 | BSW 初始化序列、调度顺序、模块接口命名是否遵循 AUTOSAR 4.x 规范 | □ |
| 3.3 | cppcheck 覆盖率缺口管理 | cppcheck 仅覆盖 ~70% MISRA 规则，其余 30% 规则的补充审查策略 | □ |
| 3.4 | 关键安全规则（P0-CRITICAL）验证 | 8 条 P0 级规则是否有明确的超标处理流程 | □ |
| 3.5 | yuleASR 模板中的 MCAL 配置 stubs | 已提供 config stubs（Mcu/Dio/Port/Gpt/Can）与未提供的模块之间的配置空挡是否明确 | □ |
| 3.6 | ASPICE CL2 证据链 | pipeline 生成的 evidence 包是否覆盖 SWE.1-6 的 PA（工作产品） | □ |
| 3.7 | 模板 spec.md 的 SHALL 完整性 | 每个 yuleasr 模板 spec 的 SHALL 数是否满足 {项目名} 覆盖率要求 | □ |
| 3.8 | 默认规则配置合理性 | `misra-rules.yaml` 中的 exception/exclusion 配置是否有合理偏差理由 | □ |
| 3.9 | Desktop 安全性 | `contextIsolation=true`、`nodeIntegration=false`、`contextBridge` 是否全部启用，是否存在注入风险 | □ |
| 3.10 | 消除死代码/未定义行为 | 对于 cppcheck 检测不到的 Dir/MCU 特定规则，是否有替代方案 | □ |

### 评分标准

| 分数区间 | 定性 | 判定 |
|:--------:|:-----|:-----|
| 9-10 | 深度对齐，偏差有充分理由 | ✅ 优秀 |
| 7-8 | 主要对齐，轻微偏差可解释 | ⚠️ 可接受 |
| 5-6 | 有差距，需补充理由或文档 | 🔴 需修复 |
| <5 | 违反规范或未对齐 | ❌ 不通过 |

### 加权：35%

### 通过条件
- 每项 ≥ 5 分
- 加权后 ≥ 28/35
- 3.1、3.2、3.4 中无 < 6 分项
- P0-CRITICAL 级别的 MISRA 规则无遗漏

### 已知风险点

| 风险 | 等级 | 说明 |
|:-----|:----:|:------|
| 🔴 cppcheck 对 MISRA C:2023 的 essential type model 支持不完整 | P0 | C:2023 引入了 expanded essential type model，cppcheck 仍基于 C:2012 检测导致 Rule 10.x 系列误报和漏报。这是老陈在早期审查中已明确指出的关键短板 |
| 🔴 Directive 类规则（Dir 4.1, 4.2, 4.13, 4.14 等）无自动化检测 | P1 | 静态分析置信度（Dir 4.13）和防御性编程（Dir 4.14）需要人工审查。模板中没有对应的人工审查指引 |
| 🔴 v0.1.0-MVP 的 ARM MCAL 配置仅针对 S32K312 | P1 | 模板链接脚本和 config stub 仅适用于 NXP S32K312，缺少多 MCU 通用适配层 |
| 🟡 `yuleasr` 模板 autosar 目录的 `main.c` BSW 初始化序列顺序未做竞态条件验证 | P2 | 7 步初始化顺序（MCAL → ECUAL → Services → RTE → SWC）的依赖关系未显式验证 |
| 🟡 Desktop 使用 `child_process.spawn('python3', ...)` 依赖 PATH 环境变量 | P2 | 虚拟环境或非标准安装场景下可能找不到 python3 |
| 🟢 `misra-rules.yaml` 的 `backward_compat.mapping` 缺少对 Rule 5.6 (removed) 的变更说明 | P3 | 已删除规则只标记了 removed，但缺少对 C:2012 用户应替换为什么 C:2023 规则的指引 |

---

## R4: 系统韧性审查（Robustness & Production Readiness）— 抗不抗打

> 老陈语：「你代码写得再漂亮，生产里一跑就崩，有用吗？」

### 审查内容

| # | 维度 | 说明 | 评分（0-10） |
|:-|:-----|:------|:-----------:|
| 4.1 | 测试覆盖深度 | 目标模块 ≥ 60% 覆盖率外，边缘路径/异常路径是否覆盖 | □ |
| 4.2 | 错误传播与恢复 | Python 后端崩溃 → Desktop UI 是否优雅降级显示错误 | □ |
| 4.3 | 长期运行稳定性 | Desktop 后台运行 1h+ 后内存泄漏检测 | □ |
| 4.4 | 退化检测 | C:2012 → C:2023 升级是否导致 120 个已有测试全部保持通过 | □ |
| 4.5 | 重复初始化保护 | `init-autosar` 时目录已存在是否友好提示并退出 | □ |
| 4.6 | 构建产物大小监控 | Desktop 打包产物是否在预期范围内（<300MB） | □ |
| 4.7 | 启动超时保护 | Python 后端 30s+ 未就绪时 Electron 是否显示友好错误而非死等 | □ |
| 4.8 | 多格式兼容退化 | 新旧 cppcheck 输出格式是否在 regex 级别保持同时匹配 | □ |
| 4.9 | 反向依赖验证 | `misra.py` 的 `_DEFAULT_RULES_PATH` 路径层级修复是否有回归扫描 | □ |
| 4.10 | 残留文件清理 | 测试完成后 `/private/tmp/.yuleosh` 等临时目录是否被清理 | □ |
| 4.11 | 桌面版 Python 子进程优雅关闭 | SIGTERM → 5s → SIGKILL 流程是否确认无僵尸进程 | □ |
| 4.12 | sbom/第三方依赖审计 | Desktop npm 依赖是否有已知 CVE 扫描 | □ |

### 评分标准

| 分数区间 | 定性 | 判定 |
|:--------:|:-----|:-----|
| 9-10 | 生产就绪，韧性设计完整 | ✅ 优秀 |
| 7-8 | 主流场景稳定，少数边缘场景待完善 | ⚠️ 可接受 |
| 5-6 | 核心功能稳定，存在已知退化风险 | 🔴 需加固 |
| <5 | 脆弱，关键路径无保护 | ❌ 不通过 |

### 加权：25%

### 通过条件
- 每项 ≥ 5 分
- 加权后 ≥ 20/25
- 4.1、4.2、4.4 中无 < 6 分项
- 无僵尸进程、无测试退化

### 已知风险点

| 风险 | 等级 | 说明 |
|:-----|:----:|:------|
| 🔴 Phase 1 测试覆盖只达到全局 30% | P0 | 大量核心代码（evidence ~2500行、engine ~350行、ci ~3000行、pipeline ~1200行、review/run.py ~240行）无测试覆盖。虽然目标模块达成 60%+，但这意味着绝大部分运行时路径是盲测 |
| 🔴 `autosar/parser.py` Wave 5→6 覆盖率仍为 75% | P1 | 相比于其它已提至 95-100% 的模块，parser.py 仍留有 25% 的盲区 |
| 🟡 Desktop 缺乏集成测试（无 electron-builder 的 CI workflow） | P1 | `desktop/self-check.md` 列了 30+ 项目测项，但没有 CI 自动化测试 |
| 🟡 `test_cli_has_kpi_commands` 存在测试顺序敏感性 | P1 | CL2 回归审查已识别，根因为 import path 污染，尚未从根源修复 |
| 🟡 `test_get_project_stats_basic` mock target 未同步更新 | P1 | Track A/B 重构导致 stats.py mock 路径过期，1 个测试失败 |
| 🟢 Desktop 只有 macOS arm64 上验证，缺 x64/Linux/Wayland 实际测试 | P2 | electron-builder.yml 配置了 mac/linux/win 但是真实构建和运行只进行了 macOS |
| 🟢 `Makefile` 的 AUTOSAR 模板构建依赖 `YULEASR_HOME`，但环境变量未在 init 时自动设置 | P2 | 初用者需手动 export 才能构建 |

---

## 综合评分表

| 轮次 | 维度 | 满分 | 通过线 | 权重 | 加权通过线 |
|:----:|:-----|:----:|:------:|:----:|:----------:|
| R1 | 可追溯性 | 70 | 50 | 15% | 12/15 |
| R2 | 可用性 | 100 | 70 | 25% | 20/25 |
| R3 | 合规深度 | 100 | 70 | 35% | 28/35 |
| R4 | 系统韧性 | 120 | 70 | 25% | 20/25 |
| **汇总** | | **390** | **260** | **100%** | **≥ 85/100** |

### 黄牌条件（触犯任意一条 → 整审查不通过）

1. P0 级风险未接受且未提供 mitigation plan
2. 测试退化 > 5 条
3. 关键 CLI 命令不可用（init-autosar / ci run / template list）
4. Desktop 在任意支持平台上无法启动
5. MISRA P0-CRITICAL 规则未实现且无替代方案
6. `contextIsolation`/`nodeIntegration` 安全配置缺失

---

## 审查执行指引

### 前置准备工作

```bash
# 1. 确认测试环境
cd ~/.openclaw/workspace/tasks/yuleOSH
python3 -m pytest tests/ --tb=short -q 2>&1 | tail -5

# 2. 检查 MISRA 规则库全量
python3 -c "
from yuleosh.ci.rulesets.misra import MisraC2023RuleSet
rs = MisraC2023RuleSet()
print(f'Total rules: {len(rs.rules)}')
print(f'Backward compat mappings: {len(rs._backward_compat)}')
"

# 3. 验证 CLI 可用性
yuleosh init-autosar test-proj --dir /tmp/ 2>&1 && rm -rf /tmp/test-proj

# 4. 验证 Desktop 启动
cd desktop && timeout 10 npm start 2>&1 || true

# 5. 覆盖率报告生成
python3 -m pytest --cov=yuleosh --cov-report=term-missing tests/ 2>&1 | tail -20
```

### 审查打分模板

记录格式：

```
R1.1: __/10  — 证据：______________   →  通过/需补/不通过
R1.2: __/10  — 证据：______________   →  通过/需补/不通过
...

加权总分: __/100
判定: 通过 ⚠️ 条件通过 ❌ 不通过
红旗项: [列表]
```

### 定级说明

| 级别 | 含义 | 响应要求 |
|:----:|:-----|:---------|
| ✅ 通过（≥85） | 所有维度和加权分均达标，红旗项无 P0 | 正式签署报告 |
| ⚠️ 条件通过（75-84） | 加权分达标但有 ≤ 3 个 P1 风险未修复 | 提供修复 deadline |
| ❌ 不通过（<75 或触犯黄牌） | 加权分不达标或触犯黄牌条件 | 修复后重新审查 |

---

## 附录：审查问题清单（审什么、怎么审）

### 给审查者的快速对照表

```
┌────────────────────────────────────────────────┐
│          专家审查 — 快速对照表                    │
├────────────────────────────────────────────────┤
│                                                │
│  R1 — 有没有                                   │
│  ┌─────────────────────────────────────────┐   │
│  │ □ 180 条 MISRA 规则全在了吗？           │   │
│  │ □ 21+29+44 模块清单都在 spec 中？       │   │
│  │ □ CLI 子命令参数说明完整吗？             │   │
│  │ □ 测试 → 需求追溯表建了吗？             │   │
│  │ □ CI gate 验收条件对齐了吗？             │   │
│  └─────────────────────────────────────────┘   │
│                                                │
│  R2 — 能不能用                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ □ `init-autosar` 跑通了吗？              │   │
│  │ □ 旧格式规则 ID 还能解析吗？             │   │
│  │ □ Desktop 启动后能看到首页吗？           │   │
│  │ □ Desktop 关了还活着（托盘）吗？          │   │
│  │ □ 8 种规则输入格式都能解析吗？            │   │
│  └─────────────────────────────────────────┘   │
│                                                │
│  R3 — 对不对                                   │
│  ┌─────────────────────────────────────────┐   │
│  │ □ Rule 10.x essential type 模型查了吗？  │   │
│  │ □ BSW 初始化顺序符合 AUTOSAR 4.x？      │   │
│  │ □ cppcheck 管不了的那 30% 怎么办？      │   │
│  │ □ 安全规则（P0-CRITICAL）有超标流程？   │   │
│  │ □ Desktop contextIsolation 开了吗？     │   │
│  └─────────────────────────────────────────┘   │
│                                                │
│  R4 — 抗不抗打                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ □ 目标模块 ≥ 60% 是真的吗？              │   │
│  │ □ Python 崩了 UI 会怎样？               │   │
│  │ □ 120 个旧测试都在绿吗？                │   │
│  │ □ 构建产物 < 300MB？                    │   │
│  │ □ 残留僵尸进程查了吗？                   │   │
│  └─────────────────────────────────────────┘   │
│                                                │
│  综合                                         │
│  □ 加权 ≥ 85/100                              │
│  □ 无 P0 未接受风险                            │
│  □ 无黄牌触发                                  │
└────────────────────────────────────────────────┘
```

### 审查拒绝标签（Red Flags）

以下情况建议直接推迟审查：

- 🚩 `yuleosh init-autosar` CLI 命令未通过 `pip install -e .` 后的 PATH 可见性测试
- 🚩 Desktop 在生产模式 (npm start, isDev=false) 下白屏
- 🚩 MISRA YAML 文件路径在打包后（`pip install`）不可达
- 🚩 测试套件在 clean install 环境下有 > 5 条失败
- 🚩 Desktop 退出后残留 Python 僵尸进程
