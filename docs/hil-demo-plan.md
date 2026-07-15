# HIL Demo 展示规划

> **编制**: 小马 🐴（质量架构师）
> **日期**: 2026-07-05
> **版本**: v1.0
> **状态**: DRAFT — 建议 P3 优先级
> **关联文档**: `docs/hil-strategy.md`, `docs/mvp-demo-script.md`, `docs/mvp-demo-flow.md`

---

## 1. 目标

### 1.1 Demo 定位

制作一个 **5 分钟的演示视频**，展示 yuleOSH 全流程从"代码改动"到"硬件验证"的端到端能力，特别突出 HIL（Hardware-in-the-Loop）测试在合规证据链中的角色。

### 1.2 目标观众

| 角色 | 关注点 |
|:-----|:--------|
| **质量经理** | 合规证据链完整、可审计 |
| **嵌入式工程师** | 硬件验证闭环、可复现 |
| **技术决策者** | 全流程自动化程度、投资回报 |

### 1.3 核心价值主张

> **"从代码提交到硬件验证到证据包生成，5 分钟完成。传统流程需要 2 天。"**

---

## 2. Demo 流程分镜（10 个场景）

### 场景 1: 开场（30 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | PC 桌面 + STM32F4 Discovery 板特写 |
| **旁白** | "传统的嵌入式合规测试，从代码更改到硬件验证需要 2 天时间。下面演示 yuleOSH 如何将这个过程缩短到 5 分钟。" |
| **动作** | 旁白同时手拿 STM32F4 Discovery 板，接入 USB 线 |
| **字幕** | "yuleOSH HIL Demo — 5 分钟全流程" |

### 场景 2: 代码改动（30 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | VS Code 打开 `flash/tests/stm32f4_demo/blinky.c` |
| **旁白** | "这是我们需要修改的 LED 控制代码。假设我们需要更改 PWM 频率和闪烁模式。" |
| **动作** | 修改 PWM 计时器配置（TIM3->ARR = 999 → 1999），修改闪烁模式 |
| **字幕** | "LED 闪烁频率更改" |

### 场景 3: Git commit + Pre-commit Hook（30 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | Terminal 执行 `git add . && git commit -m "feat: update LED blink pattern"` |
| **旁白** | "提交代码时，yuleOSH 的 pre-commit hook 自动触发 MISRA 静态分析。" |
| **动作** | 显示 git commit 输出：cppcheck 检查通过，0 新增 Required 违规 |
| **字幕** | "Pre-commit Hook — MISRA 自动检查" |

### 场景 4: CI Pipeline — 流水线触发（30 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | 浏览器打开 yuleOSH Dashboard → Pipeline 页面 |
| **旁白** | "Push 后 CI 自动启动完整的流水线：MISRA 全量检查 → C 单元测试 → HIL 部署 → 证据包生成。" |
| **动作** | 点击 Pipeline run，展示流水线 4 阶段正在运行 |
| **字幕** | "CI Pipeline — 四阶段自动化" |

### 场景 5: HIL 刷写（40 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | Terminal 执行 `yuleosh hil flash --device stm32f4_demo --firmware build/blinky.bin` |
| **旁白** | "yuleOSH 通过 OpenOCD 自动将固件刷写到 STM32F4 开发板。" |
| **动作** | 显示 OpenOCD 刷写输出（erasing, flashing, verifying）→ 绿色 OK |
| **字幕** | "HIL Flash — OpenOCD 刷写完成 (1.2s)" |

### 场景 6: HIL 监控 — 硬件验证（40 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | 分屏：左侧 Terminal `yuleosh hil monitor --device stm32f4_demo`，右侧开发板 LED 物理闪烁 |
| **旁白** | "刷写完成后，yuleOSH 自动复位开发板并监控串口输出。同时你可以看到 LED 物理闪烁的效果。" |
| **动作** | 左侧显示 UART 输出 "Blink started: period=500ms"，右侧开发板 LED 闪烁（肉眼可见） |
| **字幕** | "HIL Monitor — 串口输出 & 物理验证" |

### 场景 7: HIL 自动化断言（40 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | Terminal 执行 `yuleosh hil test --device stm32f4_demo --scenario blink_test.yaml` |
| **旁白** | "yuleOSH 还能自动执行硬件测试场景：验证 LED 频率是否符合预期，GPIO 电平是否正确。" |
| **动作** | 测试输出：`PASS: toggle_rate=498ms (expect 500ms±50ms)`、`PASS: gpio_pin_PA5_level=1` |
| **字幕** | "HIL Auto Test — 6/6 测试通过 ✅" |

### 场景 8: Dashboard 趋势与证据（40 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | yuleOSH Dashboard → Evidence Pack → 最新构建 |
| **旁白** | "所有 HIL 测试结果自动汇入 Dashboard，成为 ASPICE SWE.6（合格性测试）的合规证据。" |
| **动作** | 展示：MISRA 趋势图（34→30→28 违规）、HIL 测试历史折线图（6/6 连续通过）、覆盖率趋势 |
| **字幕** | "Dashboard — 趋势追踪 & 可视化" |

### 场景 9: 证据包导出（30 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | Terminal 执行 `yuleosh ev pack --build-id latest` → 显示打包过程 |
| **旁白** | "一键导出包含 HIL 测试结果的合规证据包。包含 SHA-256 签名，审计就绪。" |
| **动作** | 展开 ZIP 包 → 显示 `hil/` 目录下的测试报告、串口日志、时间戳 |
| **字幕** | "Evidence Pack — 一键导出 ✅ valid: True" |

### 场景 10: 总结收尾（20 秒）

| 元素 | 内容 |
|:-----|:------|
| **画面** | 回到开场画面 — STM32F4 Discovery + PC |
| **旁白** | "yuleOSH — 从代码改动到硬件验证到合规证据，全流程 5 分钟。竞品流程需要 2 天，成本低 100 倍。" |
| **动作** | 屏幕淡出到 yuleOSH Logo + 定价页 |
| **字幕** | "yuleOSH —— 嵌入式软件合规开发自动化平台" + "¥599/月 起" |

---

## 3. 所需硬件

| 硬件 | 数量 | 预估成本 | 用途 |
|:-----|:-----|:---------|:------|
| **STM32F4 Discovery** (STM32F407VGT6) | 1 块 | ¥150-200 | 主控开发板，LED/按键/USART 外设演示 |
| **USB-A → Mini-B 线** | 1 根 | ¥10-20 | OpenOCD 刷写 + USART 串口通信 |
| **USB-A → USB-C 适配器**（如需要） | 1 个 | ¥10-20 | 接入 Mac mini（2024+ USB-C only） |
| **杜邦线（母对母）** | 4 根 | ¥5 | 连接逻辑分析仪（可选） |
| **逻辑分析仪** (Saleae clone, 8ch 24MHz) | 1 个（可选） | ¥30-60 | 用于 PWM 频率 / GPIO 时序验证（增强可信度） |
| **合计** | | **¥175-300** | |

> **注**: STM32F4 Discovery 自带 ST-LINK/V2 调试器，无需额外调试/刷写硬件。

### 硬件就绪检查清单

- [ ] STM32F4 Discovery 板外观完好
- [ ] Mini-B USB 线连接后 PC 可识别（`lsusb` → `0483:3748 STMicroelectronics ST-LINK/V2`）
- [ ] 板载 LED（LD3/LD4/LD5/LD6）可被 GPIO 控制
- [ ] 板载 USART（USART2 via PA2/PA3）可收发
- [ ] OpenOCD 可连接调试目标（`openocd -f board/stm32f4discovery.cfg -c "init"`）

---

## 4. 所需软件

### 4.1 核心工具链

| 软件 | 版本要求 | 用途 |
|:-----|:---------|:------|
| **arm-none-eabi-gcc** | ≥ 12.2 | ARM Cortex-M 交叉编译器 |
| **OpenOCD** | ≥ 0.12 | 调试器 + 刷写工具（ST-LINK/V2） |
| **GNU Make** | ≥ 4.3 | 构建系统 |
| **Python** | ≥ 3.10 | yuleOSH HIL 适配器运行环境 |

### 4.2 yuleOSH 模块

| 模块 | 路径 | 用途 |
|:-----|:------|:------|
| Hardware Adapter | `src/yuleosh/hardware/` | STM32F4 适配器（flash/reset/monitor） |
| HIL CLI | `src/yuleosh/cli/hil.py` | `yuleosh hil flash/monitor/test` 命令 |
| Evidence Pack | `src/yuleosh/evidence/` | 自动汇入 HIL 测试结果 |
| Dashboard | `frontend/` | 趋势追踪与可视化 |

### 4.3 安装与配置

```bash
# 工具链安装（macOS Homebrew）
brew install arm-none-eabi-gcc openocd make

# 验证工具链
arm-none-eabi-gcc --version    # ≥ 12.2
openocd --version              # ≥ 0.12

# ST-LINK/V2 驱动（macOS 通常免驱，验证连接）
lsusb | grep "ST-LINK/V2"     # 应显示 0483:3748

# yuleOSH 硬件适配器（当前实现状态检查）
python3 -c "from yuleosh.hardware.stm32f4 import STM32F4Adapter; print('✅ Adapter import OK')"
```

### 4.4 Demo 固件

Demo 使用最低可行固件，包含：

| 文件 | 行数 | 说明 |
|:-----|:-----|:------|
| `flash/tests/stm32f4_demo/main.c` | ~80 | 主循环：LED 闪烁 + UART 状态输出 |
| `flash/tests/stm32f4_demo/blinky.c` | ~60 | LED GPIO + PWM 配置 |
| `flash/tests/stm32f4_demo/uart.c` | ~40 | USART2 初始化 + 格式化输出 |
| `flash/tests/stm32f4_demo/Makefile` | ~15 | 构建配置 |
| `flash/tests/stm32f4_demo/linker.ld` | ~30 | STM32F407VG 链接脚本 |
| `flash/tests/stm32f4_demo/openocd.cfg` | ~5 | OpenOCD 目标配置 |
| **合计** | **~230** | |

---

## 5. 预计制作时间

### 5.1 时间估算

| 阶段 | 工作内容 | 预估时长 | 负责人 |
|:-----|:---------|:--------:|:-------|
| **准备阶段（1 天）** | | | |
| A | 硬件准备 + 工具链搭建 | 2 小时 | 小克 |
| B | Demo 固件编写/调试 | 4 小时 | 小克 |
| C | HIL adapter 验证（stm32f4 flash/monitor） | 2 小时 | 小克 |
| **录制阶段（0.5 天）** | | | |
| D | 场景 1-10 分镜录制 | 2 小时 | 小克/小明 |
| E | 屏幕录制 + 硬件视频 | 1 小时 | 小克/小明 |
| **后期阶段（0.5-1 天）** | | | |
| F | 视频剪辑 + 旁白录制 | 2 小时 | 小明 |
| G | 字幕 + 剪辑精修 + 输出 | 2 小时 | 小明 |
| **最终审查（0.5 天）** | | | |
| H | 小马审查 + 小明终审 | 2 小时 | 小马/小明 |
| **合计** | | **2-3 天** | |

### 5.2 并行优化

硬件准备（A）和 HIL adapter 验证（C）可以在工具链安装（B）的同时进行 → 实际日历时间可压缩到 **1.5-2 天**。

### 5.3 视频规格

| 项目 | 规格 |
|:-----|:------|
| 分辨率 | 1920×1080 (1080p) |
| 帧率 | 30fps |
| 编码 | H.264 |
| 音频 | 16-bit 48kHz PCM |
| 时长 | 5:00 ± 30s |
| 输出格式 | MP4 |

---

## 6. 优先级判断

### 6.1 优先级：P3

**建议在满足以下条件后制作：**

1. ✅ **已有第一个签约客户**（客户案例是最大加分项，优先级高于 HIL Demo）
2. ✅ **C 覆盖率 ≥30%**（全局覆盖数字更硬）
3. ✅ **Dashboard 产品化完成**（HIL 结果汇入 Dashboard 展示）

### 6.2 为什么是 P3 不是 P2

| 理由 | 说明 |
|:-----|:------|
| **客户还未要求 HIL 展示** | 当前阶段客户更关心 MISRA 覆盖和证据包可信度 |
| **HIL 不是核心卖点** | Demo 的核心卖点（5 分钟 vs 2 天）通过纯软件流程也可以展示 |
| **制作需要完整的一天** | 团队成员当前全部投入在 P0/P1 任务上 |
| **有替代方案** | QEMU SystemC SIL 模拟可以展示同样的"硬件验证"概念，无需物理硬件 |

### 6.3 触发升级到 P2 的条件

如果以下任意条件满足，建议升级到 **P2**：
- 有客户明确问"你们能演示 HIL 吗？"
- 竞品在其 Demo 中展示了 HIL 能力
- 客户演示中 HIL 被列为 TOP-3 关心点

### 6.4 建议的后续推广路径

| 阶段 | 动作 | 时间点 |
|:-----|:------|:-------|
| **现在** | 本规划文档就绪，硬件采购 | 本周 |
| **硬件准备** | STM32F4 采购 + 固件调试 | 硬件到货后 |
| **第一个客户后** | HIL Demo 开始制作 | 客户签约后 |
| **制作完成** | 发布公开 Demo + Landing Page | P3 优先级执行时 |
| **后续** | 增加更多硬件平台（STM32G4, NXP S32K） | 产品路线图 |

---

## 附录：QEMU SIL 替代方案（降级选项）

如果硬件采购或工具链搭建出现问题，可以用 QEMU SystemC SIL 作为替代方案展示相同的概念：

| 对比维度 | HIL（物理硬件） | QEMU SIL（仿真） |
|:---------|:---------------|:----------------|
| **视觉冲击力** | ⭐⭐⭐ 物理 LED 闪烁 | ⭐ 纯命令行输出 |
| **可信度** | ⭐⭐⭐ 真实硬件 | ⭐⭐ 仿真环境 |
| **开发时间** | 2-3 天 | 1 天 |
| **硬件成本** | ¥175-300 | ¥0 |
| **串口输出** | ✅ UART 真实输出 | ✅ QEMU serial |
| **GPIO 验证** | ✅ 物理逻辑分析仪 | ❌ 不支持（QEMU 不模拟 GPIO） |
| **审计认可** | ✅ HIL 满足 ASPICE SWE.6 | ⚠️ SIL 也满足，但 HIL 更有说服力 |

**建议**：优先 HIL。如果时间紧迫，QEMU SIL 可以作为 v0.9 过渡方案，HIL 作为 v1.0 正式版。
