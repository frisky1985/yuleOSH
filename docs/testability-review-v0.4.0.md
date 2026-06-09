# yuleOSH v0.4.0 — 可测试性审查报告 (Testability Review)

> **审查角色**: 小马 🐴 (质量架构师)
> **审查日期**: 2026-06-09
> **审查范围**: SIL 仿真测试方案 (QEMU SIL Runner, HAL Mock 框架, SIL 测试规范)
> **审查依据**: hw-testing-architecture.md, startup-analysis-hw-testing.md

---

## 1. 审查维度总览

| 审查维度 | 严重程度 | 结论 | 建议 |
|:---------|:--------:|:----|:-----|
| QEMU 版本锁定 | 🔴 高 | 需明确锁定 | 详见 §2 |
| 测试超时处理 | 🟡 中 | 基本覆盖，需增强 | 详见 §3 |
| 串口输出断言 | 🟢 低 | 设计合理 | 详见 §4 |
| 测试隔离 | 🟢 低 | 方案正确 | 详见 §5 |
| 硬件差异抽象 | 🟡 中 | 需补充规范 | 详见 §6 |
| QEMU 进程生命周期 | 🟡 中 | 需防僵尸进程 | 详见 §7 |
| 串口死锁防护 | 🔴 高 | 关键缺失 | 详见 §8 |
| 跨平台兼容性 | 🟡 中 | Mac/Linux 差异 | 详见 §9 |
| 可重复性 | 🟡 中 | 需防 flaky 测试 | 详见 §10 |
| 测试资源管理 | 🟡 中 | 并行执行限制 | 详见 §11 |

---

## 2. 🔴 QEMU 版本锁定

### 问题
QEMU 跨版本存在行为差异：
- `qemu-system-arm` 不同版本的 machine 类型兼容性不同
- `-chardev pipe` 行为在 v7.2+ 和 v8.x 之间有差异
- semihosting 实现细节随版本变化

### 审查发现
hw-testing-architecture.md 中提出了"必须固定版本"，但未指定具体版本。spec.md SWR-008.1 也未包含版本锁定条款。

### 建议
1. **明确锁定 QEMU 版本**：v8.2.x LTS 或 v9.0.x (当前最新稳定版)
2. **在 YAML 目标配置中声明 QEMU 版本兼容矩阵**：

```yaml
toolchain:
  qemu:
    min_version: "8.2.0"
    max_version: "9.0.0"
    verified_versions: ["8.2.2", "9.0.0"]
```

3. **启动时版本校验**：`QemuSilRunner.__init__()` 应调用 `qemu-system-XXX --version` 检查版本是否在兼容范围内
4. **Docker 镜像固化**：确保 CI Dockerfile 使用固定版本的 QEMU deb/rpm 包 (e.g. `apt-get install qemu-system-arm=1:8.2.2-*`)
5. **添加 SWR-008.1 补充条款**：
   - `The system SHALL verify the QEMU version at SIL runner startup`
   - `The system SHALL document the verified QEMU version range in the target configuration`

### 验收标准补充
```
验收项: QEMU 版本锁定
PASS 条件:
1. qemu-sil-runner 启动时检查 qemu-system-arm --version
2. 版本不在兼容范围时抛出 SilVersionError，明确提示期望版本
3. CI Dockerfile 中 QEMU 版本固定，不使用 latest
```

---

## 3. 🟡 测试超时处理

### 问题
现方案仅规定了"默认 30s timeout"。但未覆盖以下场景：

| 场景 | 风险 | 建议 |
|:-----|:----|:-----|
| 无限循环固件 | 超过 timeout 后 QEMU 进程不退出 | 需强制 SIGTERM + SIGKILL 回退 |
| 短测试被长测试阻塞 | 并行运行时资源等待 | 单测试 timeout ≤ 总资源超时 |
| QEMU 启动失败 | runner 挂起等待串口 | 串口 pipe 创建超时 |
| 串口数据被缓冲 | assert 永远等不到 | 串口 flush 检查 |
| CI L2 整体超时 | 多测试累积超时 | 总 SIL stage timeout 限制 |

### 建议
1. **三层超时机制**：

```
Layer 1: 单测试 timeout (可配置, 默认 30s)
Layer 2: 串口 expect 超时 (可配置, 默认 5s)
Layer 3: CI L2 SIL stage 总超时 (默认 600s = 10min)
```

2. **QEMU 进程强制终止**：
   ```
   1. timeout 触发 → SIGTERM → 等待 3s
   2. QEMU 未退出 → SIGKILL
   3. 记录 log: "QEMU process forcibly terminated after timeout"
   ```

3. **QEMU 启动单独超时**：QEMU 进程启动 + 第一个串口字符到达的时间，单独设置 10s 超时

4. **SWR-008.3 补充条款**：
   - `The system SHALL implement a three-level timeout hierarchy: per-test, per-assertion, per-stage`
   - `The system SHALL forcibly terminate QEMU processes that exceed their timeout by SIGTERM then SIGKILL`
   - `The system SHALL report QEMU process startup timeout as a distinct failure category`

### 验收标准补充
```
验收项: 三层超时机制
PASS 条件:
1. 单测试 timeout 触发 → SIGTERM → QEMU 在 3s 内退出
2. 如果 SIGTERM 未能终止 → SIGKILL 强制终止
3. CI L2 SIL stage 配置总超时 600s
4. QEMU 启动超时 10s → 报告 "QEMU_STARTUP_TIMEOUT" 错误
```

---

## 4. 🟢 串口输出断言

### 现状评估
hw-testing-architecture 中设计的 expect-like 模式是合理的，与业界 `pexpect` 模式一致。串口断言引擎设计较为完善。

### 潜在问题
| 问题 | 影响 | 缓解措施 |
|:-----|:----|:---------|
| 串口缓冲区满 → 日志截断 | 断言误判 | 增加 `serial.pipe_buffer_size` 配置，默认 64KB |
| expect 与异步输出竞争条件 | 预期字符串在检查后才到达 | 采用非消耗性搜索 (peek), 不消耗串口流 |
| 多行输出匹配 | 单行 expect 可能不全面 | 支持 `expect_multiline()` |
| binary 输出 | UART 可能传输非 ASCII 数据 | 提供 bin/text 两种捕获模式 |
| ANSI 转义序列 | 串口终端可能包含颜色控制符 | 默认 strip ANSI，可选保留 |
| 轮询间隔不合理 | expect 响应慢或 CPU 空转 | 串口轮询间隔 10ms (yield 设计) |

### 建议
1. **断言引擎应采用非消耗性缓冲区**：维护环形缓冲区 (ring buffer)，断言查询时不消耗原始数据
2. **默认 strip ANSI escape sequences**：避免 `\033[32mHello\033[0m` 导致 `expect("Hello")` 失败
3. **提供 expect_all() API**：等待多个预期串同时出现或超时
4. **log 去重**：相同串口输出重复多次时，可配置重复抑制

### 串口断言 API 建议
```python
class SerialAssert:
    def expect(self, pattern: str, timeout: float = 5.0, strip_ansi: bool = True) -> bool
    def expect_all(self, patterns: list[str], timeout: float = 10.0) -> dict[str, bool]
    def expect_regex(self, pattern: str, timeout: float = 5.0) -> re.Match | None
    def read_until(self, pattern: str, timeout: float = 30.0) -> str  # 返回包含 pattern 的积累
    def peek(self, n: int = 1024) -> str  # 非消耗性读取最新 n 字节
```

---

## 5. 🟢 测试隔离

### 现状评估
"每个测试独立 QEMU 实例"是正确的设计。无共享状态确保测试可重复。

### 补充建议
1. **端口隔离**：多个 QEMU 实例使用不同的 chardev pipe 路径/端口，避免竞争

```python
# 使用临时目录隔离
import tempfile
pipe_dir = tempfile.mkdtemp(prefix="qemu_sil_")
pipe_path = f"{pipe_dir}/serial0"
```

2. **临时文件清理**：QEMU 退出后删除 pipe 文件和临时目录
3. **PID 文件管理**：记录每个 QEMU 进程的 PID，`cleanup` 方法确保残留进程被清除
4. **并行冲突检测**：如果测试 A 使用 `tempdir_a`，测试 B 使用 `tempdir_b`，确保路径完全隔离

### 验收标准补充
```
验收项: 测试隔离验证
PASS 条件 (并行运行 2 个测试):
1. 两个 QEMU 进程具有不同的 PID
2. 各自使用不同的临时目录作为 pipe 路径
3. 测试 A 的预期串口输出仅在测试 A 的 log 中出现
4. 测试 B 的行为不受测试 A 影响
5. 所有临时文件在所有测试完成后被清理
```

---

## 6. 🟡 硬件差异抽象

### 问题
目前 YAML 配置抽象涵盖了 machine/cpu/serial/flash 参数，但存在以下不足：

| 不足 | 说明 |
|:-----|:-----|
| 缺少 MCU 核数/内存布局 | QEMU RAM base 地址不同影响 .elf 链接 |
| 缺少 QEMU 启动参数模板 | 每个机器可能有特定启动 flags |
| 缺少外设数量/地址 | GPIO port 数量、UART 实例数影响 mock 的生成 |
| 缺少时钟频率 | 影响 SIL 中的时序模拟 |
| 缺少默认断言超时 | 不同目标初始化速度不同 |

### 建议
扩展 YAML 配置：

```yaml
targets:
  stm32f4:
    mcu: cortex-m4
    arch: arm
    memory:
      ram_start: 0x20000000
      ram_size: 0x30000        # 192KB
      flash_start: 0x08000000
      flash_size: 0x100000     # 1MB
    peripherals:
      uart:
        - id: USART1
          base_addr: 0x40011000
          irq: 37
        - id: USART2
          base_addr: 0x40004400
          irq: 38
      gpio:
        - port: GPIOA
          base_addr: 0x40020000
        - port: GPIOB
          base_addr: 0x40020400
      spi:
        - id: SPI1
          base_addr: 0x40013000
          irq: 35
    qemu:
      machine: stm32vldiscovery
      cpu: cortex-m3
      serial: "-chardev stdio,id=serial0 -serial chardev:serial0"
      default_timeout: 30
      expect_timeout: 5
      ram_base: 0x20000000
```

这样 HAL Mock 框架可以自动生成外设寄存器地址映射，提供更精确的仿真。

---

## 7. 🟡 QEMU 进程生命周期管理

### 问题
QEMU 子进程管理是 SIL runner 最易出问题的环节：

| 问题场景 | 后果 |
|:---------|:-----|
| runner 异常退出，QEMU 成为孤儿进程 | 系统残留僵尸进程 |
| 多个 runner 并发，QEMU 进程堆积 | 内存耗尽 |
| QEMU crash 后 pipe 残留 | 后续测试端口冲突 |
| 测试超时后 QEMU 拒绝退出 | 进程积累 |

### 建议
1. **使用 context manager (`with` statement)**：`with QemuSilRunner(...) as runner:` 确保退出时清理
2. **死进程检测**：创建 QEMU 进程时记录 PID，启动独立 `reaper` 线程定期检查
3. **孤儿进程清理**：`cleanup()` 方法 `os.killpg(qemu_pid, signal.SIGKILL)`，使用进程组而非单进程
4. **超时 watchdog**：独立线程监控测试总时间，超时后强制 `os.killpg()` + `shutil.rmtree(pipe_dir)`
5. **Global cleanup hook**：CI stage 结束时，`pkill -f qemu-system-arm` 清理残留

```python
class QemuProcess:
    def __enter__(self):
        self.proc = subprocess.Popen(..., preexec_fn=os.setsid)  # 创建进程组
        return self
    
    def __exit__(self, *args):
        self._terminate()
    
    def _terminate(self, force: bool = False):
        if self.proc.poll() is None:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                self.proc.wait()
```

---

## 8. 🔴 串口死锁防护

### 问题
这是 SIL 测试中最隐蔽的 bug。当 QEMU 目标固件期望从串口接收交互输入 (e.g. shell 提示符等待命令)，但 QEMU 的 `-serial stdio` 管道仅被读取 (单向)，固件侧串口发送缓冲区满 → 写阻塞 → 目标停止执行 → 串口不再输出 → runner 永远等待 expect → 超时 → false FAIL。

### 识别
任何有以下特征的固件测试都可能触发死锁：
- 固件使用 `HAL_UART_Transmit()` 或 `printf()` 通过 UART 输出
- 固件在串口输出后等待外部输入 (如 `scanf()`)
- 固件串口中断处理程序中涉及 UART 状态寄存器检查

### 建议
1. **所有 SIL 测试默认开启 `-serial none` + `-chardev socket` 分离模式**：串口输出写入 socket，互不影响
2. **或者使用 `-semihosting`**：完全避开 UART，通过 semihosting 通道输出
3. **QEMU chardev 配置推荐**：
   ```bash
   -chardev socket,id=serial0,path=/tmp/qemu_serial.sock,server=on,wait=off
   -serial chardev:serial0
   ```
4. **如果使用 pipe，确保 pipe 缓冲区足够大** (64KB+)，且 runner 持续 drain pipe
5. **添加 serial drain daemon thread**：即使断言不活跃，持续从 pipe 读取数据防止缓冲区满

### 验收标准补充
```
验收项: 串口死锁防护
PASS 条件:
1. 固件持续输出串口数据 60s → 不出现死锁，所有数据被捕获
2. 固件输出 100KB+ 串口数据 → 全部捕获，无截断
3. pipe 模式 + drain thread 持续运行，pipe buffer 不填满
```

---

## 9. 🟡 跨平台兼容性

### 问题
QEMU SIL runner 需要在 CI Linux (Ubuntu) 和开发环境 (macOS) 上运行。

| 差异项 | Linux (CI Docker) | macOS (开发) |
|:-------|:-----------------|:-------------|
| QEMU 包名 | `qemu-system-arm` / `qemu-system-riscv64` | `qemu` (Homebrew 合并) |
| 安装路径 | `/usr/bin/` | `/opt/homebrew/bin/` |
| chardev 类型 | 支持 `socket` + `pipe` + `file` | 同上，路径差异 |
| 进程管理 | `pkill`, `ps aux` | 相同命令, 用户权限不同 |
| procfs | `/proc` 可用 | 不可用 |

### 建议
1. **QEMU 路径自动检测**：`which qemu-system-arm` / `brew --prefix qemu` 自动发现
2. **Docker 环境检测**：`/proc/1/cgroup` 或 `/.dockerenv` 判断，CI 环境使用固定安装路径
3. **测试标记**：pytest mark `@pytest.mark.sil` 用于筛选 SIL 测试，`@pytest.mark.skipif(not qemu_available, ...)` 在无 QEMU 环境跳过
4. **macOS 环境变量**：`YULEOSH_QEMU_PREFIX` 允许用户配置 QEMU 安装前缀

---

## 10. 🟡 可重复性 (Flaky Test 防护)

### 问题
SIL 测试因仿真不确定性有 flaky 风险：

| 来源 | 说明 | 概率 |
|:-----|:-----|:----:|
| QEMU 计时不确定性 | host 负载导致模拟速度变化 | 中 |
| 串口缓冲区延迟 | 数据到达时间不确定 | 中 |
| 信号到达顺序 | 中断、事件时序在仿真中不保证 | 低 |
| 文件描述符泄漏 | 多次运行后 fd 耗尽 | 低 |

### 建议
1. **允许 flaky 标记**：`@pytest.mark.flaky(reruns=2)` 对已知 flaky 测试自动重试
2. **断言宽限窗口**：expect 默认 +10% 超时宽限
3. **随机 seed**：如果固件行为有随机性，固定随机种子确保可重复
4. **运行次数验证**：P0 测试要求连续通过 3/3 次才标记为稳定通过
5. **CI flaky 检测**：统计 SIL 测试的 first-pass 成功率，< 90% 时发出告警

---

## 11. 🟡 测试资源管理

### 问题
QEMU 是资源密集型测试：

| 资源 | 单 QEMU 实例 | 4 并行实例 | 说明 |
|:-----|:-----------:|:----------:|:-----|
| CPU | ~1 CPU core | 4 cores | 取决于模拟精度 |
| 内存 | ~64-128 MB | 256-512 MB | 最小系统 |
| 临时磁盘 | ~10 MB (pipe) | 40 MB | |
| 文件描述符 | 3 (stdin+stdout+stderr) | 12+ | pipe 额外消耗 |

### 建议
1. **资源限制**：CI runner 配置内存限制，并行 SIL 实例数 = min(4, cpu_cores / 2)
2. **压力测试**：运行 8 并行 QEMU，验证不 OOM
3. **资源监控**：QEMU 启动前检查可用内存 > 256MB，否则串行执行
4. **降级策略**：高负载时自动降级为串行执行

---

## 12. 问题汇总与行动项

| # | 问题 | 严重程度 | 建议行动 | 责任人 | 优先级 |
|:-:|:-----|:--------:|:---------|:-----:|:-----:|
| 1 | QEMU 版本锁定 | 🔴 高 | spec 补充版本校验条款 + Docker 固化 | 小克 | P0 |
| 2 | 串口死锁 | 🔴 高 | chardev socket 模式 + drain thread | 小克 | P0 |
| 3 | 三层超时机制 | 🟡 中 | 实现三层 timeout hierarchy | 小克 | P0 |
| 4 | QEMU 进程生命周期 | 🟡 中 | context manager + orphan cleanup | 小克 | P0 |
| 5 | 串口断言鲁棒性 | 🟡 中 | 非消耗性 buffer + ANSI strip | 小克 | P1 |
| 6 | YAML 配置扩展 | 🟡 中 | 补充 memory/peripherals 描述 | 小克 | P1 |
| 7 | 跨平台兼容性 | 🟡 中 | 自动检测 QEMU 路径 | 小克 | P1 |
| 8 | Flaky 防护 | 🟡 中 | rerun 机制 + 重复性验证 | 小克 | P1 |
| 9 | 资源管理 | 🟡 中 | 并行实例限制 + OOM 保护 | 小克 | P1 |
| 10 | 多目标模板 | 🟢 低 | 预置目标 YAML 库 | 小克 | P2 |

### 关键风险 (Red Items)

> 🔴 **QEMU 版本锁定**：不锁定版本可能导致 CI 和非 CI 环境结果不一致，影响测试可重复性。SWR-008.1 必须补充版本校验条款。
>
> 🔴 **串口死锁**：管道模式串口死锁会导致 SIL 测试假失败，是最隐蔽的可靠性问题。必须使用 chardev socket 模式 + drain thread 防护。

---

## 13. 总评

| 维度 | 评分 | 说明 |
|:-----|:----:|:------|
| 测试框架设计 | 🟢 A | QEMU SIL + HAL Mock + 断言引擎三层架构合理 |
| 可重复性 | 🟡 B | 需补充版本锁定、超时机制、flaky 处理 |
| 资源与隔离 | 🟢 A | 独立 QEMU 进程 + 临时目录设计正确 |
| 鲁棒性 | 🟡 B | 串口死锁和进程生命周期管理需加强 |
| 跨平台 | 🟡 B | Linux 完美，macOS 需补充路径检测 |
| 可维护性 | 🟢 A | YAML 配置抽象 + 模块化 runner 设计可扩展 |

> **总体结论**：架构质量较好，建议在 Sprint 中优先处理 2 个 Red 项和 3 个 baseline Yellow 项。处理后可测试性评级为 🟢 A。
