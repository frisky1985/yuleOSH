# Onboarding Wizard Report — 方向三

## 概述

**功能**: 交互式 CLI Wizard: `yuleosh onboard --repo <git-url>`

**目标**: 从下载到看到第一个 Dashboard 面板，不超过 15 分钟。

## 文件变更

| 文件 | 操作 | 说明 |
|:-----|:-----|:------|
| `src/yuleosh/cli/onboard.py` | **新建** | Wizard 核心逻辑 (6 步流程) |
| `src/yuleosh/cli/main.py` | **修改** | 注册 `yuleosh onboard` 子命令 |
| `tests/test_onboard.py` | **新建** | 5 个测试类 + 边界用例 |

## 架构设计

### CLI 接口

```
yuleosh onboard --name "BCM Demo" --project-type new --oem-template generic
yuleosh onboard --repo /path/to/existing/project --project-type migration
yuleosh onboard --repo git@github.com:user/project.git
```

### Wizard 流程 (6 步)

| Step | 名称 | 函数 | 功能 |
|:----:|:-----|:-----|:------|
| 1 | 项目基本信息 | `_step_project_info()` | 收集/确认 name, type, oem template |
| 2 | 代码分析 | `_step_code_analysis()` | 扫描结构、检测框架 |
| 3 | KG 初始化 | `_step_kg_bootstrap()` | 调用 KG importer 构建图谱 |
| 4 | 合规基线 | `_step_compliance_check()` | 运行 Compliance Checker (SWE.1~SWE.6) |
| 5 | Dashboard | `_step_dashboard()` | 生成证据包、注册面板 |
| 6 | 下一步 | `_step_summary()` | 打印摘要、next-actions |

### 自动检测逻辑 (`_detect_project_type`)

- **AUTOSAR CP**: 检测 `Std_Types.h` / `arxml` / `BswM_` / `EcuM_` 等 BSW 模式
- **MCU**: 检测 `S32K312` / `STM32` / `TC3` 等 MCU 标识
- **C project**: 检测 `.c` / `.h` 文件
- **Python**: 检测 `.py` 文件（无 C/C++ 源文件）
- **测试框架**: 自动识别 CUnit, cmocka, pytest

### 进度显示

纯 `print` 方式，无外部依赖。含步骤标题、进度状态、完成标记。

## CLI 注册

在 `main.py` 中：

1. `_build_parser()` — 新增 `build_onboard_parser(sub)` 注册
2. `main()` — 新增 `args.command == "onboard"` 分发

## 测试

| 测试 | 描述 | 状态 |
|:-----|:------|:------|
| `test_onboard_new_project` | 全新项目 wizard 完整流程 | ✅ |
| `test_onboard_migration_project` | 迁移项目 wizard 流程 + 文件保护 | ✅ |
| `test_onboard_detects_project_type` | 自动检测 AUTOSAR/C/Python 类型 + CUnit 框架 | ✅ |
| `test_onboard_cli_registered` | `yuleosh onboard --help` 可运行 + 参数完整 | ✅ |
| `test_onboard_no_clobber` | 已存在的 `.osh/` 配置不被覆盖 | ✅ |
| 额外边界用例 | 空目录、OEM 模板列表、目录树创建 | ✅ |

### 运行测试

```bash
cd /path/to/yuleOSH
python -m pytest tests/test_onboard.py -v
```

## 向后兼容性

- 不影响现有 CLI 命令 (`init`, `spec`, `pipeline`, `ci`, `ev`, `evidence`, 等)
- `_ensure_osh_project()` 仅创建缺失目录，不会覆盖已有文件
- Wizard 读取但不修改已有 `.osh/` 配置（不覆盖 `dashboard.json`, `ci/*.json` 等）

## 依赖

无新增依赖。使用标准库 `argparse`, `json`, `os`, `shutil`, `subprocess`, `sys`, `time`, `datetime`, `pathlib`。

## 限速风险与安全

- `git clone` 通过 `subprocess.run` 执行，含 stderr 捕获和错误处理
- 所有文件操作使用 `pathlib`，路径规范化

---

**报告生成时间**: 2026-07-16  
**作者**: Claude Agent (Subagent)
