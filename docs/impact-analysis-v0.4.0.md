# yuleOSH v0.4.0 — 变更影响分析 (Impact Analysis)

> **分析角色**: 小马 🐴 (质量架构师)
> **分析日期**: 2026-06-09
> **分析范围**: RS-008 / SWR-008.x 对现有系统的变更影响
> **基线版本**: yuleOSH v0.3.0 (当前能力)

---

## 1. 影响全景图

```
                            ┌─────────────────────────────────────┐
                            │          yuleOSH v0.4.0             │
                            │         SIL 仿真测试能力              │
                            └─────────────────────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
   ┌────────────┐              ┌──────────────┐             ┌──────────────┐
   │ CI L2 影响  │             │ 证据链影响    │            │ Pipeline 影响 │
   │            │              │              │             │              │
   │ +sil-tests │              │ +SIL 报告     │            │ +L2 blocking  │
   │ stage      │              │ 纳入合规包    │            │ stage        │
   │ +QEMU 依赖 │              │ +扩展 trace  │             │ +run 步骤    │
   └────────────┘              └──────────────┘             └──────────────┘
          │                             │                             │
          ▼                             ▼                             ▼
   ┌────────────┐              ┌──────────────┐             ┌──────────────┐
   │ 文件系统   │              │ Spec 影响     │            │ 配置影响      │
   │ +sil/ 目录  │              │ +RS-008       │             │ +target YAML │
   │ +targets/  │              │ +SWR-008.x    │             │ +pipeline     │
   └────────────┘              └──────────────┘             └──────────────┘
```

---

## 2. CI L2 影响分析

### 2.1 当前 CI L2 结构 (v0.3.0)

```
L2: clang-tidy → cross-compile → integration-tests
```

### 2.2 计划 CI L2 结构 (v0.4.0)

```
L2: clang-tidy → cross-compile → sil-tests → integration-tests
                                        ↓
                                QEMU SIL Runner
                                + SIL 断言引擎
                                + SIL 测试报告
```

### 2.3 具体影响

| 影响项 | 详细说明 | 风险 | 缓解方案 |
|:-------|:---------|:----:|:---------|
| **新增 stage** | `sil-tests` 插入在 cross-compile 之后，integration-tests 之前 | 🟢低 | 标准 pipeline 扩展 |
| **QEMU Docker 依赖** | CI Docker 镜像需安装 `qemu-system-arm` `qemu-system-riscv64` | 🟡中 | Dockerfile 加入 apt 安装；包约 80MB |
| **stage 耗时增加** | 每个 SIL 测试 30s timeout，4 个测试 ~30-120s | 🟡中 | 并行执行 4 个 QEMU 实例，优化目标 |
| **阻塞性质** | SIL 失败阻断 pipeline，后续 integration-tests 和 L3 不执行 | 🟡中 | 设计如此，确保质量左移 |
| **构建产物传递** | cross-compile stage 生成的 .elf 需传递到 sil-tests stage | 🟡中 | CI 工件 (artifact) 传递，或共享 volume |
| **依赖顺序变更** | integration-tests 不再直接依赖 cross-compile，而是依赖 sil-tests | 🟡中 | pipeline DAG 需更新依赖声明 |

### 2.4 风险评估: 🟡 中等

**理由**：
- Stage 插入是标准 CI 操作
- QEMU 安装增加 Docker image 大小 (~80MB)
- 总 CI 耗时增加 30-120s (可通过并行化部分抵消)
- 需要 cross-compile → sil-tests 的 .elf 工件传递机制

---

## 3. Evidence 包影响

### 3.1 当前 Evidence 包结构 (v0.3.0)

```
compliance-pack/
├── traceability-matrix.json
├── review-records/
├── test-results/
│   ├── unit-test-report.json         (CI L1)
│   ├── integration-test-report.json  (CI L2)
│   └── system-test-report.json       (CI L3)
├── coverage/
├── static-analysis/
└── manifest.json
```

### 3.2 计划 Evidence 包结构 (v0.4.0)

```
compliance-pack/
├── traceability-matrix.json
├── review-records/
├── test-results/
│   ├── unit-test-report.json         (CI L1)
│   ├── sil-test-report.json          ★ 新增
│   ├── integration-test-report.json  (CI L2)
│   └── system-test-report.json       (CI L3)
├── coverage/
├── static-analysis/
└── manifest.json
```

### 3.3 具体影响

| 影响项 | 详细说明 | 风险 | 缓解方案 |
|:-------|:---------|:----:|:---------|
| **新增证据文件** | `sil-test-report.json` - per-test 粒度的 SIL 测试结果 | 🟢低 | 标准 JSON 格式，与现有报告结构对齐 |
| **格式规范** | 需定义 `sil-test-report.json` schema | 🟢低 | 参考现有 test-report JSON 格式 |
| **证据包版本升级** | evidence pack version bump (v1→v2 或 minor) | 🟢低 | 向后兼容设计 |
| **manifest 更新** | `manifest.json` 增加 `sil-test-report` 条目 | 🟢低 | 一行配置 |
| **追溯矩阵扩展** | SWR-008.x → SIL 测试用例 追溯链 | 🟡中 | 每条验收标准需映射到测试用例 ID |
| **ASPICE 合规增强** | SIL 测试覆盖 SWE.5 (软件集成测试) | 🟢正面 | 合规评分从 3/5 提至 4/5 |

### 3.4 sil-test-report.json Schema 建议

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "report_version": { "type": "string", "enum": ["1.0"] },
    "pipeline_run_id": { "type": "string" },
    "generated_at": { "type": "string", "format": "date-time" },
    "qemu_version": { "type": "string" },
    "summary": {
      "type": "object",
      "properties": {
        "total": { "type": "integer" },
        "passed": { "type": "integer" },
        "failed": { "type": "integer" },
        "skipped": { "type": "integer" },
        "duration_seconds": { "type": "number" }
      },
      "required": ["total", "passed", "failed", "duration_seconds"]
    },
    "tests": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "test_id": { "type": "string" },
          "test_name": { "type": "string" },
          "target_machine": { "type": "string" },
          "status": { "type": "string", "enum": ["PASS", "FAIL", "SKIP", "ERROR"] },
          "duration_seconds": { "type": "number" },
          "assertions": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "pattern": { "type": "string" },
                "matched": { "type": "boolean" },
                "timeout": { "type": "number" }
              }
            }
          },
          "log_snippet": { "type": "string", "maxLength": 4096 },
          "full_log_path": { "type": "string" },
          "error_message": { "type": "string" }
        },
        "required": ["test_id", "test_name", "status", "duration_seconds"]
      }
    }
  },
  "required": ["report_version", "pipeline_run_id", "summary", "tests"]
}
```

### 3.5 风险评估: 🟢 低

**理由**：
- 新增 JSON 报告与现存证据包结构兼容
- 追溯矩阵只需扩展映射关系，无需重写
- ASPICE 合规增强是正面影响

---

## 4. Pipeline Run 影响

### 4.1 CLI 影响

| 当前命令 | v0.4.0 变化 | 说明 |
|:---------|:------------|:-----|
| `yuleosh.sh pipeline run` | 增加 `--no-sil` 跳过 SIL 测试 | 开发环境可加速 |
| `yuleosh.sh pipeline run --stage` | 新增 `sil-tests` 合法 stage 值 | 可单独运行 SIL 阶段 |
| `yuleosh.sh pipeline status` | 新增 SIL 测试进度显示 | pipeline status 报告 SIL 测试状态 |
| (新增) | `yuleosh.sh sil test <test_name>` | 新子命令，运行单个 SIL 测试 |
| (新增) | `yuleosh.sh sil list` | 列出所有可用 SIL 测试 |
| (新增) | `yuleosh.sh sil targets` | 列出已配置的目标板 YAML |

### 4.2 Pipeline Config 影响

```yaml
# .yuleosh/pipeline.yaml (新增/变更字段)
pipeline:
  stages:
    - name: sil-tests
      after: cross-compile
      before: integration-tests
      blocking: true               # 失败阻断
      timeout: 600                  # 总超时 10min
      parallel: 4                   # 最大并行 QEMU 实例数
      retries: 0                    # SIL 失败不自动重试 (防 flaky 可配置 1)
      artifact_deps:
        - stage: cross-compile
          files:
            - "build/*.elf"         # 使用 cross-compile 产出的 .elf
```

### 4.3 运行流程影响

```
当前全流程:
  L1 单元测试 → L2 cross-compile → L2 integration → L3 system

v0.4.0 全流程:
  L1 单元测试 → L2 cross-compile → L2 SIL test → L2 integration → L3 system
  
  ★ 新增 SIL 决策点:
  ┌──────────┐
  │ SIL PASS │────→ L2 integration (继续)
  └────┬─────┘
       │ FAIL
       ▼
  Pipeline ABORT ❌ (不运行 L2 integration + L3 system)
```

### 4.4 输出产物影响

| 产物 | v0.4.0 变化 | 向后兼容 |
|:-----|:-----------|:--------:|
| `pipeline-run-report.json` | 增加 `sil_tests` 字段 | ✅ 兼容，不影响已有字段 |
| `compliance-pack.zip` | 内部增加 `sil-test-report.json` | ✅ 兼容，zip 新增文件 |
| `traceability-matrix.json` | 增加 SWR-008.x ↔ 测试 ID 映射 | ✅ 兼容 |
| `session-env/reports/` | 新增 `sil-test-report.json` | ✅ 新增目录/文件 |
| CI logs | QEMU console logs 作为 CI artifact | ✅ 新增 |

### 4.5 风险评估: 🟡 中等

**理由**：
- CLI 子命令新增不影响已有接口
- pipeline config 扩展向后兼容
- 主要影响：新增一个阻断 stage，需要 CI 环境预装 QEMU

---

## 5. 文件系统变更

### 5.1 新增目录/文件

```
yuleosh/
├── src/
│   └── cross/
│       ├── sil_runner.py          ★ 新增 - QEMU SIL Runner
│       ├── sil_assert.py          ★ 新增 - SIL 串口断言引擎
│       ├── target_config.py       ★ 新增 - 目标板 YAML 配置解析
│       └── hal_mock/              ★ 新增 - HAL Mock 框架
│           ├── mock_uart.c        ★ 新增
│           ├── mock_gpio.c        ★ 新增
│           ├── mock_timer.c       ★ 新增
│           ├── mock_i2c.c         ★ 新增 (P1)
│           ├── mock_spi.c         ★ 新增 (P1)
│           ├── mock_core.h        ★ 新增
│           └── CMakeLists.txt     ★ 新增
├── .yuleosh/
│   └── targets/
│       ├── lm3s6965evb.yaml       ★ 新增
│       ├── stm32vldiscovery.yaml  ★ 新增
│       ├── stm32f4.yaml           ★ 新增
│       └── riscv64-virt.yaml      ★ 新增
├── tests/
│   ├── test_sil_runner.py         ★ 新增
│   ├── test_sil_assert.py         ★ 新增
│   ├── test_target_config.py      ★ 新增
│   └── test_hal_mock.py           ★ 新增
├── examples/
│   └── sil-tests/
│       ├── hello-arm/             ★ 新增 - 最小 ARM SIL 测试 demo
│       └── hello-riscv/           ★ 新增 - RISC-V SIL 测试 demo
└── docs/
    ├── spec.md                    🔄 更新 (RS-008 + SWR-008.x)
    ├── acceptance-matrix-v0.4.0   ★ 新增
    ├── testability-review-v0.4.0  ★ 新增
    └── impact-analysis-v0.4.0     ★ 新增 (本文件)
```

### 5.2 风险评估: 🟢 低

**理由**：
- 所有新增文件独立目录，不破坏现有文件结构
- `src/cross/` 目录已有，新增模块自然扩展
- `tests/` 目录新增测试文件不冲突
- YAML 目标配置不覆盖现有配置

---

## 6. 单元测试影响

| 现有测试文件 | 影响 | 说明 |
|:------------|:----|:-----|
| `test_ci_engine.py` | 🔄 更新 | 需测试 `sil-tests` stage 的 pipeline 编排逻辑 |
| `test_ci_engine.py` | 🔄 更新 | 需测试 `sil-tests` blocking 机制 (失败阻断) |
| `test_evidence_engine.py` | 🔄 更新 | 需测试 `sil-test-report.json` 纳入 evidence 包 |
| `test_trace.py` (如存在) | 🔄 更新 | 需扩展追溯矩阵以包含 SWR-008.x |
| (新增) `test_sil_runner.py` | ★ 新增 | 36+ 测试 (QemuSilRunner 核心逻辑) |
| (新增) `test_sil_assert.py` | ★ 新增 | 12+ 测试 (串口断言引擎) |
| (新增) `test_target_config.py` | ★ 新增 | 8+ 测试 (YAML 配置解析) |
| (新增) `test_hal_mock.py` | ★ 新增 | 20+ 测试 (HAL Mock 框架) |

### 单元测试增量统计

| 指标 | v0.3.0 | v0.4.0 增量 | v0.4.0 合计 |
|:-----|:------:|:-----------:|:-----------:|
| 测试文件数 | ~10 | +4 | ~14 |
| 测试用例数 | ~85 | +76 | ~161 |
| 组件覆盖率增量 | — | +2 组件 (SIL/Assert) | 覆盖全组件 |

---

## 7. 外部依赖变更

| 依赖 | 版本要求 | 安装方式 | 增量大小 | 风险 |
|:-----|:---------|:---------|:--------:|:----:|
| `qemu-system-arm` | ≥ 8.2.x | apt/Homebrew | ~40 MB | 🟡中 |
| `qemu-system-riscv64` | ≥ 8.2.x | apt/Homebrew | ~20 MB | 🟢低 |
| `python3` (已有) | ≥ 3.10 | 已有 | 0 | 🟢低 |
| `pyyaml` | ≥ 6.0 | pip | <1 MB | 🟢低 |
| `pyserial` | ≥ 3.5 | pip | <1 MB | 🟢低 |

**Dockerfile 变更**
```dockerfile
# 当前 Dockerfile.cross
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi \
    gcc-riscv64-unknown-elf \
    cmake make

# v0.4.0 变更
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi \
    gcc-riscv64-unknown-elf \
    qemu-system-arm=1:8.2.2-* \       # ★ 新增，版本固定
    qemu-system-riscv64=1:8.2.2-* \   # ★ 新增，版本固定
    cmake make
RUN pip3 install pyyaml pyserial     # ★ 新增
```

### 风险评估: 🟡 中等

**理由**：
- Docker image 大小增加 ~60MB
- QEMU 版本锁定需要验证在 CI 环境中可获取固定版本包
- `pyyaml` 和 `pyserial` 是轻量级依赖

---

## 8. 兼容性影响矩阵

| 现有特性 | SIL 影响 | 兼容性 | 说明 |
|:---------|:---------|:------:|:-----|
| L1 单元测试 | 无影响 | ✅ | 独立运行 |
| cross-compile | .elf 被 SIL 消费 | ✅ 兼容 | 新增消费者，不改变 producer |
| integration-tests | 依赖 SIL 先行 | 🟡注意 | SIL 阻断时 integration 不运行 |
| L3 系统测试 | 依赖 SIL + integration | 🟡注意 | 间接依赖，单 SIL 失败就阻断 |
| evidence pack | 扩展包含 SIL 报告 | ✅ 兼容 | 向后兼容 |
| CI pipeline 配置 | 新增 sil-tests stage | ✅ 兼容 | 向后兼容 |
| CLI 子命令 | 新增 sil 子命令 | ✅ 兼容 | 不破坏现有命令 |
| 开发者工作流 | 本地可跳過 SIL (--no-sil) | ✅ 兼容 | 开发环境可选 |
| 第三方 toolchain | 无影响 | ✅ 兼容 | 不改变现有工具链 |

---

## 9. 风险评分矩阵

| 影响域 | 影响度 | 可能性 | 风险等级 | 缓解措施 |
|:-------|:------:|:------:|:--------:|:---------|
| CI L2 | 中 | 中 | 🟡 M | Docker 预装 QEMU + 版本锁定 |
| Evidence 包 | 低 | 低 | 🟢 L | 扩展 JSON schema |
| Pipeline run | 中 | 低 | 🟢 L | CLI 向后兼容 |
| 文件系统 | 低 | 低 | 🟢 L | 新文件独立目录 |
| 单元测试 | 低 | 低 | 🟢 L | 新增不影响现有 |
| 外部依赖 | 中 | 中 | 🟡 M | Dockerfile 版本固定 |
| 兼容性 | 低 | 低 | 🟢 L | 向后兼容为主 |
| **综合风险** | — | — | 🟡 **中等** | — |

---

## 10. 变更实施建议

### Sprint 实施顺序

```
Iteration 1:  依赖安装 (Dockerfile 更新 + QEMU 验证)
              ↓
Iteration 2:  sil_runner.py + target_config.py + YAML
              ↓
Iteration 3:  sil_assert.py + 串口断言引擎 + 测试
              ↓
Iteration 4:  CI 集成 (pipeline config + evidence pack)
              ↓
Iteration 5:  HAL Mock 框架 + 测试
              ↓
Iteration 6:  验收测试 + 合规审查
```

### 风险缓解行动项

| # | 行动 | 责任人 | 期限 |
|:-:|:-----|:------|:----:|
| 1 | 确认 CI Dockerfile 可以安装固定版本 QEMU (8.2.2) | 小克 | I1 |
| 2 | 验证 QEMU 跨版本兼容性 (8.0 vs 8.2 vs 9.0) | 小克 | I1 |
| 3 | 实现 .elf 工件跨 stage 传递 | 小克 | I2 |
| 4 | 定义 sil-test-report.json schema 并纳入 evidence 生成 | 小克 | I4 |
| 5 | 更新 pipeline status CLI 显示 SIL 进度 | 小克 | I4 |
| 6 | 验证 integration-tests 对 SIL 阶段阻断的依赖逻辑 | 小克 | I4 |
| 7 | 验证并行 QEMU 实例的端口/文件隔离 | 小克 | I4 |
| 8 | 检查现有 test_ci_engine.py 是否与 sil-tests stage 兼容 | 小克 | I4 |

---

## 11. 总结

| 影响维度 | 评估 | 关键发现 |
|:---------|:----|:---------|
| CI L2 | 🟡 中等 | 新增 sil-tests stage，Docker 需要预装 QEMU（+60MB），总耗时增加 30-120s |
| Evidence 包 | 🟢 低 | 新增 sil-test-report.json，兼容现有结构 |
| Pipeline run | 🟢 低 | CLI 向后兼容，新增 sil 子命令 |
| 文件系统 | 🟢 低 | 独立目录，不破坏现有结构 |
| 单元测试 | 🟢 低 | 新增 ~76 测试，不影响现有 ~85 测试 |
| 外部依赖 | 🟡 中等 | 增加 3 个依赖 (QEMU arm/riscv, pyyaml, pyserial) |
| 兼容性 | 🟢 高 | 全部向后兼容 |
| **综合** | **🟡 中等** | **可实施，建议按 Sprint 顺序推进** |
