# yuleOSH 全流程开发使用说明

> 适用版本: v3.13+ | 更新: 2026-08-11
>
> 本文档面向「用 yuleOSH 把一个需求跑成完整交付物」的实际操作。
> 从安装、项目初始化、写 spec，到跑流水线、看产物、出合规证据，一整个闭环。

---

## 0. 全流程总览

```
写需求 spec → 初始化项目 → 配置 LLM → 跑 pipeline → 审查产物 → 出证据包
   (docs/spec.md)   (yuleosh init)  (环境变量)   (yuleosh pipeline run)
```

yuleOSH 把一个自然语言需求转换成: 架构设计 + 代码 + 测试 + 审查记录 + ASPICE 追溯证据。
核心入口是 **OpenSpec 格式的需求文件** 和 **Agent Pipeline**。

---

## 1. 安装

```bash
# 前提: Python ≥ 3.10, Git
pip install yuleosh

# 验证
yuleosh --help          # 看到命令树即成功
yuleosh template list   # 列出 12 个内置工程模板
```

**从源码安装（开发模式，推荐）**:

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
pip install -e ".[dev]"     # dev 额外装 pytest/pytest-cov
```

---

## 2. 初始化项目

### 2.1 最简方式（无模板）

```bash
yuleosh init my-project
cd my-project
```

生成最小骨架: `docs/`（放 spec）、`src/`、`tests/`。

### 2.2 用 ECU 模板（嵌入式，推荐）

```bash
# 选 MCU + ASIL 等级
yuleosh init my-bcm --template bcm --mcu S32K312 --asil ASIL_B
# 可用模板: bcm / dcu / vcu / bms / eps
# 可用 MCU:  S32K312 / S32K344 / S32K324 / S32K314
# 可用 ASIL: QM / ASIL_B / ASIL_C / ASIL_D
```

### 2.3 用工程模板（通用）

```bash
yuleosh template list                                   # 看全部模板
yuleosh template init my-fw --from generic-embedded-c   # 通用嵌入式 C
yuleosh template init my-py --from generic-python       # 通用 Python
```

常用模板: `generic-embedded-c`、`generic-python`、`stm32-hal`、`freertos-misra`、
`zephyr-rtos`、`autosar-classic`、`esp32-idf`、`arm-cmsis`、`baremetal-safety`。

### 2.4 一键 Demo（体验用）

```bash
yuleosh demo wow                    # 刹车灯 / 雨刮 demo（D3 代码生成）
yuleosh demo uart                   # STM32F4 ↔ ESP32 UART 通信 demo
yuleosh demo quick "做一个温度采集"  # 一句话需求直接跑 pipeline
```

---

## 3. 写需求文档（OpenSpec 格式）

pipeline 的输入是 **spec 文件**（默认 `docs/spec.md`），必须是 OpenSpec 结构:

```markdown
# 项目名

> Version: 1.0.0

## 1. Requirements

### REQ-001: 需求标题
- The system SHALL <能力描述>          # RFC 2119 关键词: SHALL / SHOULD / MAY
- The system SHALL <另一条能力>

#### Reason
为什么有这个需求

## 2. Scenarios

### Scenario: 主场景
- GIVEN 前置条件
- WHEN 触发动作
- THEN 预期结果
```

**格式要点**:
- 需求编号 `REQ-001`、`REQ-002` …（也支持 `TR-001` 等自定义前缀）
- 必须用 `SHALL`（必须）/ `SHOULD`（应该）/ `MAY`（可以）描述约束
- 场景用 `GIVEN` / `WHEN` / `THEN` 三段式
- 可以用 `## 2. Scenarios` 之后任意小节补充设计约束

**校验**:

```bash
yuleosh spec validate docs/spec.md      # 合规检查，通过再进 pipeline
yuleosh spec diff old.md new.md         # 两个 spec 差异
yuleosh spec merge delta.md             # 合并 spec-delta 到主 spec
```

---

## 4. 配置 LLM

pipeline 是 AI 驱动的，需要配置 LLM API（默认 DeepSeek，OpenAI 兼容协议）:

```bash
export LLM_API_KEY="sk-xxx"                          # 必填
export LLM_BASE_URL="https://api.deepseek.com"       # 默认 DeepSeek，可换任意 OpenAI 兼容端点
export LLM_MODEL="deepseek-chat"                     # 默认 deepseek-chat
```

也兼容 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`（按顺序读取）。

**不想连真实 LLM?** 用 mock 模式:

```bash
yuleosh pipeline run --mock docs/spec.md   # 假 LLM，纯流程验证，不需要 key
```

---

## 5. 跑全流程 Pipeline

### 5.1 一键跑

```bash
cd my-project
yuleosh pipeline run docs/spec.md
```

跑完 exit code 0 = 成功。完整 pipeline 有 30+ 步:

```
spec-check          OpenSpec 合规检查
super-analysis      S.U.P.E.R 启动分析
prd / prd-review    产品需求分析 + 审查
architecture / arch-review     架构设计 + 审查
development / devplan-review   开发计划与代码实现 + 审查
internal-code-review           代码实现预审
test-planning                  测试规划
self-test / self-test-review   自测验证 + 审查
c-unit-test         C 单元测试 (Unity)
code-review         集成代码审查
integration-test    接口集成测试
misra-review        MISRA 合规审查
coverage-review     测试覆盖审查
qemu-run            QEMU 仿真测试
c-coverage-gate     C 覆盖率门禁
review-linker/startup/rtos/memory/bsp/build/power/stack/mmio
                    嵌入式专项审查
review-critical-safety   ⛔ P0 关键安全门禁（不可跳过）
fault-injection     故障注入测试
merge-gate          KG Merge Gate（图一致性门禁）
test-qualification  SWE.6 合格性测试
final-report        最终报告（session 置 completed）
```

### 5.2 Profile 档位

Profile 通过项目配置文件 `.yuleosh/ci-config.yaml` 切换（CLI 无 `--profile`
参数，该参数仅存在于 Python API `run_pipeline(profile=...)`）:

```yaml
# .yuleosh/ci-config.yaml
misra:
  active_profile: minimal   # 默认档位: minimal / safety / ci ...
```

| 档位 | 语义 | 步骤数 |
|------|------|--------|
| `minimal` | 白名单基线: spec-check / c-unit-test / integration-test / c-coverage-gate / review-critical-safety / merge-gate | 6 |
| `safety` | 全量 pipeline（默认） | 33 |
| `ci` / `performance` / `testing` | 黑名单裁剪 | 视配置 |

> **P0 保护集**: `review-critical-safety` 和 `merge-gate` 是语义上不可绕过的
> 门禁，任何档位（含 minimal）都强制保留。通过 `.yuleosh/ci-config.yaml`
> 的 `misra.active_profile` 切换默认档位。

### 5.3 diff 智能裁剪（增量开发）

只改了少量文件时，跳过不相关步骤，省 token:

```bash
OSH_DIFF_SKIP=1 yuleosh pipeline run docs/spec.md
```

- 自动分析 git diff → 只跑受影响的步骤（如只改 `.c` 文件就不跑 linker/startup 审查）
- 空 diff / 非 git 目录自动 fail-safe 不裁剪
- 每次裁剪决策显式打印 + 写入 session，不静默消失

### 5.4 查看进度 / 产物

```bash
yuleosh pipeline status              # 列出所有 session
yuleosh pipeline status run-xxx      # 查看指定 session 状态
```

产物在项目 `.osh/` 目录:

```
.osh/
├── sessions/<run_id>/        # 每次运行的完整记录
│   ├── session.json          # 步骤状态 / 产物路径 / token 用量
│   ├── final-report.md       # 最终报告
│   └── ...各步骤产物
├── evidence/                 # 合规证据
│   ├── acceptance-matrix.md  # 验收矩阵
│   ├── traceability-matrix.* # 追溯矩阵
│   ├── review-log-summary.md # 审查日志
│   └── compliance-pack.zip   # 一键证据包
└── reports/                  # 各类报告（MISRA、覆盖率等）
```

---

## 6. 项目常用命令

### 审查与合规

```bash
yuleosh review auto                    # 自动审查最近改动
yuleosh review task my-task            # 审查指定任务
yuleosh misra report                   # MISRA 合规报告
yuleosh misra trend                    # 违规趋势
yuleosh misra profile                  # 管理 MISRA profile
yuleosh misra deviate                  # 管理偏差记录
yuleosh traceability report            # 全量追溯报告
yuleosh traceability check             # 追溯完整性检查（CI 门禁）
```

### 证据与 ASPICE

```bash
yuleosh evidence pack                  # 生成证据包 (compliance-pack.zip)
yuleosh evidence check                 # 校验证据包完整性
yuleosh ev check --save                # ASPICE 差距分析 → .osh/evidence/aspice-gap-report.md
yuleosh gap close                      # 差距 → 改进工单（需人工确认）
yuleosh audit verify                   # 审计日志完整性（防篡改链）
```

### 其他

```bash
yuleosh ci run 1                       # 手动跑 CI Layer 1（单元+覆盖）
yuleosh ci run 2                       # Layer 2（交叉编译+静态分析）
yuleosh ci run 3                       # Layer 3（系统验证+证据）
yuleosh plan "需求文本"                 # Ultra-Plan 实现计划
yuleosh skills list                    # 技能库（autosar-coding / misra-fix ...）
yuleosh onboard                       # 交互式 Onboarding（新项目/迁移）
yuleosh ui                            # 启动 Web 控制台
```

---

## 7. 典型工作流

### 场景 A: 新项目全流程（2 分钟）

```bash
yuleosh init my-fw --template bcm --mcu S32K312 --asil ASIL_B
cd my-fw
# 编辑 docs/spec.md 写需求
export LLM_API_KEY="sk-xxx"
yuleosh pipeline run docs/spec.md
yuleosh evidence pack
# 交付: .osh/evidence/compliance-pack.zip
```

### 场景 B: 增量迭代（改代码再验证）

```bash
# 改完 src/xxx.c 后
OSH_DIFF_SKIP=1 yuleosh pipeline run docs/spec.md   # 只跑受影响步骤
yuleosh review auto                                 # 增量审查
```

### 场景 C: 纯流程验证（无 LLM key）

```bash
yuleosh init demo-test
cd demo-test
# 写一个简单 spec
yuleosh pipeline run --mock docs/spec.md            # mock 模式
yuleosh pipeline status                             # 看步骤执行情况
```

---

## 8. 配置参考

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_API_KEY` | — | LLM API Key（必填，非 mock 模式） |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `OSH_HOME` | 当前目录 | 项目根（决定 `.osh/` 位置） |
| `OSH_DIFF_SKIP` | 关闭 | `1` 开启 diff 智能裁剪 |
| `OSH_DEVELOPMENT_MODE` | — | `generate-code` 开启 D3 代码生成模式 |
| `YULEOSH_LLM_UNIFIED` | 关闭 | `1` 走 LLMClient 统一入口（预算/回退/审计） |

### 项目结构约定

```
项目根/
├── docs/spec.md              # OpenSpec 需求（pipeline 输入）
├── src/                      # 源码
├── tests/                    # 测试
├── .yuleosh/ci-config.yaml   # profile / MISRA / 门禁配置
├── .osh/                     # 运行产物（session、evidence、reports）
└── .git/                     # diff 裁剪依赖 git
```

---

## 9. 常见问题

**Q: pipeline run 报 "No LLM API key found"**
→ 没配 key。设 `LLM_API_KEY`，或加 `--mock`。

**Q: 跑完 status 是 failed / created?**
→ failed = 有步骤失败（看 session.errors）；created 只在未跑完时出现
（正常跑完无 final-report 的白名单档也会正确置 completed，v3.13+ 修复）。

**Q: 想跳过 MISRA / 覆盖率门禁?**
→ 用 `--profile minimal` 或改 `.yuleosh/ci-config.yaml` 的 profile 定义；
P0 门禁（review-critical-safety / merge-gate）不可跳过，是设计约束。

**Q: 产物在哪里?**
→ 全部在项目 `.osh/` 下：sessions/ 每次运行记录，evidence/ 合规证据，
reports/ 各类报告。

**Q: 如何对接 CI?**
→ 仓库自带 GitHub Actions（lint/detect/frontend-build/cve-scan/code-quality/
evidence/quality-report/test 全链路），按路径分流；`yuleosh ci run <layer>`
可手动触发任意层。

---

## 10. 更多资源

- `README.md` — 项目总览与特性
- `docs/architecture.md` — 4 层架构详解
- `docs/quick-start.md` — UI 控制台快速开始
- `yuleosh <cmd> --help` — 每个子命令的完整参数
