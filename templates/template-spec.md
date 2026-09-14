# yuleOSH 模板规范 — template-spec.md

> 定义所有模板必须满足的 GIVEN/WHEN/THEN 验收条件。
> **构建系统无关**：模板可用 CMake 或 Makefile（或任意构建系统），pipeline 门禁不挑构建系统。

---

## 通用条件（所有模板，构建系统无关）

### GIVEN-1: 目录结构完整
GIVEN 一个模板目录
WHEN 检查目录结构
THEN 必须包含：
- `docs/spec.md` — OpenSpec 规范（供 `spec-check` 门禁）
- `src/` — 源码头文件与实现
- `tests/` — 单元测试
- 构建系统文件 `CMakeLists.txt` **或** `Makefile`（二选一，**不强制特定结构**；CMake 与 Makefile 模板一视同仁）

### GIVEN-2: spec 契约
GIVEN 模板的 `docs/spec.md`
WHEN 校验 spec 内容
THEN 必须：
- 含 **≥3 条** `The system SHALL ...` 语句（供 `spec-check` 门禁；硬约束）
- 含 `## 2. Acceptance Scenarios`（或等价段）及 `GIVEN/WHEN/THEN` 场景（供 G10 合格性门禁做 coverage 匹配）

### GIVEN-3: 系统级合格性测试（SWE.6 — G10 Gate）
GIVEN 模板目录
WHEN 运行 `test-qualification` 门禁
THEN 必须存在 system 级测试源（以下任一命名均可被发现）：
- `tests/system/*.c` / `tests/system/*.cpp`
- `tests/e2e/*.c` / `tests/e2e/*.cpp`
- `**/scenario_test*.c` / `**/scenario_test*.cpp`
- `**/test_qualification*.c|cpp` / `e2e_test*` / `acceptance_test*`

且源文件内容须覆盖 spec 场景关键词（每个场景 ≥ `max(2, 关键词数//3)` 个关键词命中），使 coverage = 100%。

> **构建系统无关说明**：门禁优先用构建产物二进制（`build/`、`cmake-build*`、`tests/build`、`build_sys`、`out` 等）；
> 若缺失，对**自包含（主机可模拟）**的 system 测试源自动**即时编译**执行（`g++`/`cc` → `.yuleosh/qualification/<stem>`）。
> 故 CMake 模板（产出 `build/<stem>`）与 Makefile / 新项目（无 build 二进制）**一视同仁**，统一走通 G10。
> 依赖硬件寄存器或需交叉编译、无法主机模拟的源会编译失败 → 保持 `incomplete`（合理边界，需真实硬件/交叉构建）。

### GIVEN-4: 可构建 + 单元测试
GIVEN 模板目录
WHEN 执行 `cmake --build` 或 `make` / `make test`
THEN 模板须能构建，且单元测试（ctest / `make test` / `pytest`）可执行并全绿。

### GIVEN-5: pipeline 门禁整体
GIVEN 模板副本
WHEN 跑 `run_pipeline(docs/spec.md)`（真实编排器）
THEN 硬门禁（`spec-check` / `claude-review` / `review-critical-safety` / `merge-gate` / `test-qualification` 等）须全 `passed` 或按计划 `skipped`，pipeline 整体非 RED。

---

## 各模板验收状态

| 模板 | 构建系统 | 语言 | G10 系统测试 | 真实 E2E | 备注 |
|------|----------|------|-------------|----------|------|
| `esp-idf-blinky` | CMake | C | ⏳ 待补 | ⏳ 需硬件 | 仅静态结构检查通过 |
| `gpio-led-chaser` | CMake | C | ✅ `tests/system/scenario_test.c` | ✅ **GREEN (2026-09-14)** | 24 步真实 DeepSeek E2E 全绿 |
| `mcu-firmware` | Makefile | C++ | ✅ `tests/system/scenario_test.cpp`（即时编译） | ⏳ 待真实 E2E 复跑 | G10 门禁已证 `passed` (2026-09-14) |
| `ble-sensor` | Makefile | C | ⏳ 待补 | ⏳ | 需补 `tests/system` 场景测试 |
| `can-bus` | Makefile | C | ⏳ 待补 | ⏳ | 需补 `tests/system` 场景测试 |
| `autosar` | arxml + BSW | C | ⏳ 待补 | ⏳ | 复杂 BSW，需补 system 测试 + 构建适配 |

> ✅ = 已验证通过　⏳ = 待补 / 需运行时验证　❌ = 未通过

---

## 统一新项目创建与验证流程

1. **创建**：`yuleosh template init <name> --from templates/<base>` 复制基线模板（或通用 Python 起始项目）。
2. **写 spec**：编辑 `docs/spec.md`——≥3 条 `SHALL` + `## 2. Acceptance Scenarios`（GIVEN/WHEN/THEN）。
3. **实现 + 测试**：实现 `src/`；写 `tests/` 单元测试 + `tests/system/scenario_test.c|cpp`
   （自包含主机模拟，注释/字符串覆盖 spec 场景关键词，使 G10 coverage=100%）。
4. **选构建系统**：CMake（产出 `build/<stem>`）或 Makefile（门禁即时编译 fallback 兜底）——二者等价。
5. **验证**：`run_pipeline(docs/spec.md)`（真实编排器）或 `yuleosh ci run <L1/L2/L3>`，
   确认硬门禁全 `passed`/`skipped`，pipeline 非 RED。

> 注意：复制模板时 `template init` 会清掉 `.git` / `build` / `__pycache__` 等残留，但不强制结构统一——
> 统一由本规范的 GIVEN-1~5 约束，任何符合本规范的模板都能被同一套 pipeline 门禁走通。
