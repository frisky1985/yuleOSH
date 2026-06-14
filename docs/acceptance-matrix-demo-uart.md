# yuleOSH Demo UART — 验收判定矩阵

> **迭代**: v1.0.0 — Demo UART (快速演示能力)
> **角色**: 小马 🐴 (质量架构师)
> **日期**: 2026-06-13
> **覆盖范围**: DEMO-UART-001 ~ DEMO-UART-005
> **前置文档**: [spec-contract.md](spec-contract.md)

---

## 矩阵说明

- **方法**: `A`=自动化测试, `C`=代码审查, `R`=人工评审, `M`=手动测试, `I`=CI集成验证, `S`=SIL仿真测试
- **优先级**: P0=必须通过才能发布, P1=建议通过, P2=可选
- **PASS 条件**: 每个验收标准的判定条件，可客观验证
- **验收守门人**: 小马 🐴

---

## DEMO-UART-001: 演示初始化

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-001.1 | `yuleosh demo uart` CLI 子命令存在 | C + A | `yuleosh --help` 输出包含 `demo` 子命令；`yuleosh demo uart` 执行成功返回 exit code 0 | P0 |
| DEMO-UART-001.2 | 创建 uart-demo/ 目录 | A | 执行后目录存在；包含 `CMakeLists.txt`、`main/main.c`、`main/CMakeLists.txt`、`README.md` | P0 |
| DEMO-UART-001.3 | CMakeLists.txt 语法正确 | A | `cmake -S uart-demo -B uart-demo/build` 语法检查通过（在 IDF 环境中） | P0 |
| DEMO-UART-001.4 | main/main.c 包含 `app_main()` | C | 代码审查确认 `main.c` 中存在 `void app_main(void)` 函数定义 | P0 |
| DEMO-UART-001.5 | CMakeLists.txt 引用 IDF | C | `include($ENV{IDF_PATH}/tools/cmake/project.cmake)` 存在 | P0 |
| DEMO-UART-001.6 | main/CMakeLists.txt 注册组件 | C | `idf_component_register(SRCS main.c ...)` 存在且合法 | P0 |
| DEMO-UART-001.7 | `--target` 参数解析 (MAY) | C | 选项声明存在但不强制工作 | P2 |

### GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-001.S1 | GIVEN 空目录 → `yuleosh demo uart` → 目录创建 + CMake有效 + app_main 存在 | A | 全部文件存在且可构建 | P0 |

---

## DEMO-UART-002: UART 串口发送

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-002.1 | UART 默认 115200 8N1 配置 | C | `main.c` 中 UART 配置代码设置 baud=115200, data_bits=8, parity=N, stop_bits=1 | P0 |
| DEMO-UART-002.2 | 启动输出 "Hello from yuleOSH Demo UART" | S + M | QEMU SIL 运行后 serial log 包含该字符串；真实硬件串口输出也包含 | P0 |
| DEMO-UART-002.3 | 每 5s 心跳输出 | S + M | SIL 运行 15s 后 serial log 包含至少两个 `[yuleOSH] alive — \d+s` 匹配行 | P0 |
| DEMO-UART-002.4 | 启动完成输出 ready 提示 | S + M | SIL 运行后 serial log 包含 "Demo UART ready" | P0 |
| DEMO-UART-002.5 | 可配波特率 (MAY) | C | `#define UART_BAUD` 或 sdkconfig `CONFIG_UART_BAUD` 存在且可修改 | P2 |

### GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-002.S1 | GIVEN 固件运行 → 串口包含 Hello + ready 消息 | S | SIL 测试同时断言两个字符串存在 | P0 |
| DEMO-UART-002.S2 | GIVEN 连续运行 12s → 至少 2 次心跳 | S | SIL 测试 timeout=15, expect regex 匹配 2 次心跳 | P0 |

---

## DEMO-UART-003: UART 串口接收与回显

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-003.1 | UART RX 配置 | C | `main.c` 中配置 UART RX GPIO (默认 GPIO3) 和接收中断/轮询 | P0 |
| DEMO-UART-003.2 | 单字符回显 "Echo: {char}" | S + A | SIL 测试通过 pipe 发送 `A`，serial log 包含 `"Echo: A"` | P0 |
| DEMO-UART-003.3 | 字符串回显 "Line: {string}" | S + A | SIL 测试通过 pipe 发送 `hello\n`，serial log 包含 `"Line: hello"` | P0 |
| DEMO-UART-003.4 | 64 字节 RX 缓冲区 | C | `main.c` 中 RX 缓冲区大小定义为 64 或更大 | P0 |
| DEMO-UART-003.5 | 长字符串不丢数据 | S + A | 发送 63 字符 + `\n`，serial log 完整回显全部 63 字符 | P1 |
| DEMO-UART-003.6 | 可配 RX 缓冲区 (MAY) | C | `#define RX_BUF_SIZE` 存在且可修改 | P2 |

### GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-003.S1 | GIVEN 固件就绪 → 发送 'A' → 响应 Echo: A | S | pipe 输入 'A'，断言 serial log 包含 "Echo: A" | P0 |
| DEMO-UART-003.S2 | GIVEN 固件就绪 → 发送 "hello\n" → 响应 Line: hello | S | pipe 输入 "hello\n"，断言 serial log 包含 "Line: hello" | P0 |

---

## DEMO-UART-004: 演示清理

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-004.1 | `--clean` 标志存在 | C + A | `yuleosh demo uart --help` 包含 `--clean` 说明；`--clean` 执行 exit code 0 | P0 |
| DEMO-UART-004.2 | 删除前确认提示 | A | `yuleosh demo uart --clean` 输出包含 "Remove uart-demo/? [y/N]" | P0 |
| DEMO-UART-004.3 | 确认后目录被删除 | A | 输入 y 后 `uart-demo/` 目录不复存在 | P0 |
| DEMO-UART-004.4 | 拒绝后目录保留 | A | 输入 N 后 `uart-demo/` 目录仍然存在 | P0 |
| DEMO-UART-004.5 | 无 demo 目录时提示不存在 | A | 没有 `uart-demo/` 时运行 `--clean`，输出 "No demo project found" 或类似提示 | P1 |

---

## DEMO-UART-005: SIL 测试兼容

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-005.1 | QEMU ESP32 兼容固件 | I + S | `idf.py build` 成功后 `.elf` 可在 QEMU ESP32 环境中加载 | P0 |
| DEMO-UART-005.2 | CI L2 SIL 测试集成 | I | CI L2 pipeline 配置中包含 demo-uart SIL 测试 stage | P0 |
| DEMO-UART-005.3 | Hello 断言 SIL 测试 | S | `qemu-sil-runner` 执行后 `passed=False` 仅当串口无 Hello 输出 | P0 |
| DEMO-UART-005.4 | Echo 回显 SIL 测试 | S | SIL 测试通过 pipe 输入字符并断言回显正确 | P0 |
| DEMO-UART-005.5 | SIL 测试报告纳入证据包 | I | `sil-test-report.json` 包含 demo-uart 的 per-test PASS/FAIL 记录 | P1 |

### GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| DEMO-UART-005.S1 | GIVEN 编译后 .elf → CI L2 SIL 执行 → passed=True + 串口日志包含 Hello | I + S | 完整 CI L2 流水线通过，evidence 包含 SIL 报告 | P0 |
| DEMO-UART-005.S2 | GIVEN SIL 回显测试 → pipe I/O → 断言 Echo 和 Line 回显 | S | 两个断言均 PASS，无超时失败 | P0 |

---

## 总体验收统计

| 分类 | 总数 | P0 | P1 | P2 | 说明 |
|------|:----:|:--:|:--:|:--:|:-----|
| DEMO-UART-001: 演示初始化 | 8 | 6 | 0 | 2 | CLI + 项目脚手架 |
| DEMO-UART-002: UART 串口发送 | 6 | 4 | 0 | 2 | 启动 + 心跳 + ready |
| DEMO-UART-003: UART 回显 | 8 | 5 | 1 | 2 | 字符回显 + 字符串回显 |
| DEMO-UART-004: 演示清理 | 5 | 4 | 1 | 0 | --clean 生命周期 |
| DEMO-UART-005: SIL 兼容 | 7 | 5 | 2 | 0 | QEMU SIL + CI 集成 |
| **合计** | **34** | **24** | **4** | **6** | P0 占比 71% |

### P0 门禁清单 (Demo UART 发布必须通过)

1. DEMO-UART-001.1 — CLI 子命令存在
2. DEMO-UART-001.2 — 文件目录创建
3. DEMO-UART-001.3 — CMake 语法正确
4. DEMO-UART-001.4 — app_main 存在
5. DEMO-UART-001.5 — CMake IDF 引用
6. DEMO-UART-001.6 — 组件注册
7. DEMO-UART-002.1 — UART 115200 8N1
8. DEMO-UART-002.2 — Hello 输出
9. DEMO-UART-002.3 — 心跳输出
10. DEMO-UART-002.4 — Ready 提示
11. DEMO-UART-003.1 — RX 配置
12. DEMO-UART-003.2 — 单字符回显
13. DEMO-UART-003.3 — 字符串回显
14. DEMO-UART-003.4 — 64 字节缓冲区
15. DEMO-UART-004.1 — --clean 标志
16. DEMO-UART-004.2 — 确认提示
17. DEMO-UART-004.3 — 确认后删除
18. DEMO-UART-004.4 — 拒绝后保留
19. DEMO-UART-005.1 — QEMU 兼容
20. DEMO-UART-005.2 — CI L2 集成
21. DEMO-UART-005.3 — Hello 断言 SIL
22. DEMO-UART-005.4 — Echo 回显 SIL
23. DEMO-UART-001.S1 — 场景：空目录初始化
24. DEMO-UART-002.S1 — 场景：Hello + ready
25. DEMO-UART-002.S2 — 场景：心跳
26. DEMO-UART-003.S1 — 场景：字符回显
27. DEMO-UART-003.S2 — 场景：字符串回显
28. DEMO-UART-005.S1 — 场景：CI L2 SIL
29. DEMO-UART-005.S2 — 场景：SIL 回显

> 🟢 **29 项 P0 全部通过** = Demo UART 发布就绪
