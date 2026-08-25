# C 项目 CI 环境适配指南

> 适用：用 yuleOSH 审计 C/C++ 项目（如 yuleASR AUTOSAR BSW）时的环境配置与踩坑记录。
> 实证：2026-08-25 yuleASR 审计（CI Layer 1 全绿、Layer 2 部分）。

## 1. 环境清单

| 依赖 | 安装 | 用途 |
|------|------|------|
| arm-none-eabi-gcc | `brew install arm-none-eabi-gcc`（formula 版无需 sudo；cask 版需 sudo 且含 newlib） | L2 cross-compile |
| clang-tidy | `brew install llvm`（位于 /opt/homebrew/opt/llvm/bin） | L1 clang-tidy 阶段 |
| lxml | `yuleosh/.venv/bin/pip install lxml` | arxml-tool 测试依赖（系统 python 有、venv 没有 → L1 收集 ImportError） |

注意：brew formula 版 gcc 不含 newlib → `nano.specs` 缺失，链接带 newlib 依赖的模块（saferam 等）会失败。这是环境限制，非代码问题。

## 2. 运行姿势

```bash
cd <项目目录>
export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
export ARM_GCC_PATH=/opt/homebrew   # cross-compile 定位编译器
<yuleOSH>/.venv/bin/yuleosh ci run 1   # L1
<yuleOSH>/.venv/bin/yuleosh ci run 2   # L2
```

## 3. 已知坑与修复（全部实证）

### 3.1 Python-coverage 阶段 0% 误报
- 现象：`coverage: failed — Line coverage 0.0% < 40%`
- 根因：coverage 阶段跑 `coverage run pytest tests/` 测 src/ 下 Python，C 项目 Python 代码无覆盖 → 0%
- 修复：ci-config.yaml 加 `coverage.enabled: false`（需 yuleosh `CoverageConfig.enabled` 字段，2026-08-25 已加，默认 True 向后兼容）
- C 覆盖率由 c-coverage-gate/gcov 独立验证（91.6%）

### 3.2 clang-tidy USAGE 报错
- 现象：`clang-tidy failed — USAGE: clang-tidy [options]...`
- 根因：(a) llvm≥17 参数语法 `--` → `--extra-arg`；(b) 无 compile_commands.json 时 clang-tidy 打印帮助并 exit 1
- 修复：yuleosh 侧改 `--extra-arg=-std=c11` + 检测 "compilation database"/USAGE 输出 → 降级 skipped（非阻塞，环境限制而非代码问题）

### 3.3 misra-check "All C/C++ files excluded"
- 现象：misra-check skipped，配套测试断言失败
- 根因：delta 模式只扫最近 commit 改动文件；纯文档 commit 无生产 C 改动 → 全部被 exclude_paths 排除 → 合法跳过
- 修复：测试断言适配 skipped 状态（如 test_ci_layer1_misra_check）

### 3.4 methodology-gate 失败（CONTEXT.md）
- 现象：L1 methodology 硬门禁失败
- 根因：缺 CONTEXT.md（领域术语表）
- 修复：创建 CONTEXT.md — **纯术语表**（禁止 def/class/import/#include/代码块，否则视为实现细节）

### 3.5 cross-compile ARM_GCC_BIN_PATH-NOTFOUND
- 根因：toolchain 文件 find_path 不含 /opt/homebrew/bin
- 修复：`export ARM_GCC_PATH=/opt/homebrew`（toolchain 读 `$ENV{ARM_GCC_PATH}/bin`）+ 删 build-arm 清旧 CMake 缓存（否则 NOTFOUND 持久化）

### 3.6 yuleOSH 自身全量随机序测试污染
- 现象：全量 pytest（pytest-randomly）偶发失败，单独/小组跑通过
- 根因：全局单例按 env 派生路径缓存（`Store._instances` keyed by db_path，db 路径来自 OSH_HOME）跨测试泄漏；resolve_venv_dir 依赖 OSH_HOME
- 修复（tests/conftest.py）：autouse fixture 每测试后重置 `Store._instances`/`KGStore._instances`；project_venv 测试 monkeypatch OSH_HOME
- 注意：conftest 改动后必须全量验证（小组跑不复现）

## 4. 结果解读（避免误报）

- CI layer overall=failed **不代表代码坏**：看阶段状态，unit-tests/misra-check/c-coverage-gate/requirements-trace 通过才是真信号
- C 项目的 ground truth 是 `make test`/`ctest`（54/54），不是 CI 层摘要
- ev check "missing" 多是缺证据（无 passing-run 记录），不是缺实现 —— 跑 CI 层即生成记录
