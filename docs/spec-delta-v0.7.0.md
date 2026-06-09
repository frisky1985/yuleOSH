# Spec-Delta: v0.6.0 → v0.7.0

> OpenSpec 变更追踪 | 生成: 2026-06-09

---

## 版本变更

| 属性 | v0.6.0 | v0.7.0 |
|:-----|:-------|:-------|
| pyproject.toml | 0.5.0 | 0.7.0 |
| 模块 | 10 RS | + 发布/真实HIL/模板/Dashboard/LLM/多租户 |
| CI 层 | L1→L2→L2.5→L3 | 同上 + Docker CI |

---

## 迭代计划

```
I1(发布) ──→ I2(真实HIL) ──→ I4(Dashboard 2.0) ──→ I5(LLM) ──→ I6(多租户)
              └─→ I3(模板市场) ────────────────────┘
```

---

## 🔥 P0 — 核心闭环

### I1: 发布打包 (估 1-2天)

**目标:** 用户能 `pip install yuleosh` 一键安装

| Task | 内容 |
|:-----|:-----|
| T1.1 | 完善 `setup.py` / `pyproject.toml`，含 CLI entry point `yuleosh` |
| T1.2 | Dockerfile — 含所有工具链（arm-gcc/riscv-gcc/QEMU） |
| T1.3 | `yuleosh init <project>` — 脚手架生成项目模板 |
| T1.4 | CI 发布流水线 — tag 自动构建推 PyPI + Docker Hub |
| T1.5 | `make release` — 一键构建、测试、打包 |

**验收:** `pip install yuleosh && yuleosh init my-project && cd my-project && make ci` 全绿

---

### I2: 真实硬件 HIL (估 2-3天)

**目标:** L2.5 从 mock 模式 → 真实硬件连接

| Task | 内容 |
|:-----|:-----|
| T2.1 | `FlashRunner` — 对接 OpenOCD / JLink / pyOCD 三种烧录后端 |
| T2.2 | `SerialMonitor` 物理端口版 — 基于 `serial` 库的真实串口读写 |
| T2.3 | `HilTestRunner` — flash → wait boot → read serial → assert pattern |
| T2.4 | `target_config.yaml` 增加硬件连接参数（serial_port / baud / programmer） |
| T2.5 | 端到端 HIL 测试 — STM32F4 开发板 boot 实测 |

**验收:** 插上 STM32F4 → `make ci-layer25` → flash → boot → assert "Boot Complete" ✅

---

### I3: 模板市场 v1 (估 2天)

**目标:** 覆盖主流 MCU，`yuleosh init --template esp32`

| Task | 内容 |
|:-----|:-----|
| T3.1 | ESP32-IDF 模板 — FreeRTOS + WiFi + spec/pipeline/ci 完整骨架 |
| T3.2 | nRF52 (Zephyr) 模板 — BLE 从机示例 |
| T3.3 | RPi Pico (Pico-SDK) 模板 — GPIO + UART |
| T3.4 | `yuleosh template list` — 列出可用模板 |
| T3.5 | 模板市场索引 `templates/index.yaml` |

**验收:** 三个模板 `make ci` 全绿 + 交叉编译通过

---

## 📦 P1 — 体验升级

### I4: Dashboard 2.0 (估 2-3天)

**目标:** CI 流水线可视化 + DevOps 面板

| Task | 内容 |
|:-----|:-----|
| T4.1 | CI Pipeline 可视化 — 四层流水线实时状态 + 甘特图 |
| T4.2 | 覆盖率趋势图 — 按 commit 历史展示覆盖率变化 |
| T4.3 | HIL 测试结果面板 — 硬件测试通过/失败明细 |
| T4.4 | Dashboard 首页 — 项目总览卡片（测试/覆盖/CI/最近提交） |
| T4.5 | WebSocket 实时推送 CI 状态更新 |

**验收:** Dashboard 上能看到 CI 实时跑、覆盖率趋势、HIL 结果

---

### I5: LLM 后端接入 (估 2天)

**目标:** Agent 流水线对接真实 LLM，实现 Spec→Code→Test 自动执行

| Task | 内容 |
|:-----|:-----|
| T5.1 | `LLMClient` 抽象 — 支持 OpenAI / DeepSeek / 本地模型 |
| T5.2 | Agent Pipeline 对接 — SDD / DDD / TDD 三步各自调用 LLM |
| T5.3 | Prompt 模板系统 — 嵌入式 C 代码生成 / 测试用例生成 |
| T5.4 | Token 用量统计 + 成本估算 |
| T5.5 | `yuleosh agent run --task "blink LED on PA5"` 端到端演示 |

**验收:** 给一句需求 → Agent 自动生成 spec → code → test → CI 验证全链

---

## 🏗️ P2 — SaaS 底座

### I6: 多租户 v1 (估 2天)

**目标:** 支持 Org → Project → Member 层级

| Task | 内容 |
|:-----|:-----|
| T6.1 | `Org` 模型 — org create / list / delete + member 管理 |
| T6.2 | `Project` 归属 — project 绑定 org，租户隔离 |
| T6.3 | RBAC — Owner / Admin / Developer / Viewer 四角色 |
| T6.4 | 用量统计 — API 调用次数 / CI 运行次数 / 存储用量 |
| T6.5 | 租户级 Dashboard 隔离 |

**验收:** 创建 org → 加成员 → 创建 project → 成员按角色操作 → 用量可见

---

## 汇总

| Iter | 模块 | 优先级 | 估时 | 依赖 |
|:-----|:-----|:------:|:-----|:-----|
| I1 | 发布打包 | 🔥 P0 | 1-2天 | — |
| I2 | 真实 HIL | 🔥 P0 | 2-3天 | I1 |
| I3 | 模板市场 | 🔥 P0 | 2天 | I1 |
| I4 | Dashboard 2.0 | 📦 P1 | 2-3天 | I2, I3 |
| I5 | LLM 后端 | 📦 P1 | 2天 | I4 |
| I6 | 多租户 v1 | 🏗️ P2 | 2天 | I5 |

**总估时: 11-14 天 | I2+I3 可并行**

---

## 新增需求预览

### RS-011: 发布与分发 (I1)
- The system SHALL support `pip install yuleosh`
- The system SHALL provide Docker image with full toolchain
- The system SHALL provide `yuleosh init` project scaffolding

### RS-012: 真实 HIL 硬件测试 (I2)
- The system SHALL support OpenOCD / JLink / pyOCD flash backends
- The system SHALL support real serial port monitoring via pyserial
- The system SHALL perform flash → boot → assert lifecycle on real hardware

### RS-013: MCU 模板市场 (I3)
- The system SHALL provide ESP32 / nRF52 / RPi Pico project templates
- The system SHALL support `yuleosh template list` discovery

### RS-014: Dashboard 2.0 (I4)
- The system SHALL visualize CI pipeline status in real-time
- The system SHALL display coverage trend charts
- The system SHALL push CI status updates via WebSocket

### RS-015: LLM Agent 后端 (I5)
- The system SHALL support OpenAI / DeepSeek / local model backends
- The system SHALL execute SDD → DDD → TDD via LLM agent pipeline

### RS-016: 多租户 (I6)
- The system SHALL support Org → Project → Member hierarchy
- The system SHALL enforce RBAC with 4 roles
- The system SHALL track usage metrics per tenant
