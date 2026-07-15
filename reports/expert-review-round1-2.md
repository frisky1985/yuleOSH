# Expert Review Round 1 & 2 — 老陈 👨‍🏫 Style

> 评审日期: 2026-07-11
> 评审阶段: Round 1 (Desktop v0.1.0-MVP + Phase 2 MISRA C:2023) + Round 2 (Phase 3 yuleASR + Phase 1 Coverage + Tech Debt)
> 评审框架参照: expert-review-check.md
> 评审人风格: 老陈 👨‍🏫（前博世汽车电子资深架构师）

---

## Round 1: Desktop v0.1.0-MVP + Phase 2 MISRA C:2023

### Part A — Desktop v0.1.0-MVP 架构合理性审查

#### 架构合理性（Architecture Rationality）— 72/100

| 维度 | 评分 | 评语 |
|------|:----:|:------|
| 进程模型设计 | 75 | 三层进程隔离（Electron Main / Renderer / Python Backend）设计清晰。但 `_entry.py` 桥接方案脆弱：`yuleosh._entry:main` 通过查找项目根目录来导入 `yuleosh_cli.py`，这在 pip install 后（site-packages 环境）路径计算逻辑会断裂。setup.py 使用 `yuleosh=yuleosh_cli:main`，pyproject.toml 使用 `yuleosh=yuleosh._entry:main`，两个入口点冲突。 |
| 模块职责划分 | 80 | main.js/server-manager.js/tray.js/preload.js 四文件职责清晰。server-manager.js 的 EventEmitter 架构合理，自动重启逻辑（2 次重试）适中。 |
| 健康检查竞争条件 | 65 | **P0: 超时不一致** — spec.md SHALL-2.1.3 规定 15 秒超时，但 main.js `waitForBackend()` 硬编码 `timeoutMs = 10000`（10 秒）。server-manager.js 内部有 15s 超时。两个组件在同一个 electron 进程内有两种不同的超时策略，违反了 SHALL-2.1.3。 |
| 后端路径解析 | 70 | server-manager.js `_resolveBackendDir()` 硬编码 `desktop/../src/` 相对路径。当 Desktop AppImage 部署后（electron-builder 打包），这个路径不再有效，因为 Python 后端不在 electron-builder 的 extraResources 中。 |
| 构建配置完整性 | 70 | electron-builder.yml 配置完整（mac/Linux/Windows），但 extraResources 只包含 frontend/out/，未包含 Python 后端运行时或 PyInstaller 打包产物。AC-5.1.4 明确说 "MVP 版本用户需自行安装 Python 3.10+"，这是有意识的设计决策，但意味着 Desktop 不是 self-contained 应用。 |

#### 安全性（Security）— 85/100

| 维度 | 评分 | 评语 |
|------|:----:|:------|
| contextIsolation / nodeIntegration | 95 | main.js 57-58 设置 `contextIsolation: true`, `nodeIntegration: false` ✅ |
| preload 安全桥接 | 90 | preload.js 使用 contextBridge 安全暴露 API，未暴露 Node.js 原生 API。但暴露了 `process.platform` — 这是一个轻微的信息泄露（renderer 可以获取平台信息） |
| 静态文件服务器路径保护 | 85 | main.js 中 `startLocalFileServer()` 有路径遍历保护（检查 `fullPath.startsWith(path.resolve(FRONTEND_OUT_DIR))`） |
| CORS 配置 | 80 | 依赖 Python 后端配置 CORS 头，ServerManager 层未做请求白名单校验 |
| 子进程命令注入防护 | 80 | server-manager.js 使用固定命令 `python3 -m yuleosh.ui.server`，不拼接用户输入 ✅ |

#### 跨平台兼容性（Cross-platform Compatibility）— 65/100

| 维度 | 评分 | 评语 |
|:----:|:----:|:------|
| macOS arm64 | 90 | 已验证 ✅ |
| macOS x64 | 50 | electron-builder.yml 配置了 `arch: [x64, arm64]`，但自测清单 5.1.5 列显未实际运行 |
| Linux AppImage | 60 | 构建配置完整，但 5.2.5 Wayland 兼容性列显未验证；自测全部在 macOS 上执行 |
| Linux deb | 50 | `electron-builder.yml` 只配置了 deb x64 target，但 Linux desktop 自测均未实际运行 |
| Windows | 30 | electron-builder.yml 有 NSIS 配置，但是 `MAY-5.1.3`，spec 和验收矩阵均未定义验收条件 |
| Python 版本检测 | 70 | server-manager.js 有 `_checkPythonVersion()` ≥3.10 检测 ✅，但仅检测 `python3` 命令，未检测 `python`（某些 Linux 发行版默认）

#### 代码质量（Code Quality）— 78/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| ES6+ 用法 | 85 | async/await, class, arrow functions 使用恰当 |
| 错误处理 | 70 | server-manager.js 错误处理完善；main.js 后端健康检查失败时 `loadFrontend()` 被调用了两次（第 735 行和 743 行），存在竞态风险 |
| 模块化 | 80 | 4 个模块职责分离清晰 |
| 测试覆盖 | 60 | 无单元测试文件（spec.md 中 AC 引用了 UT，但 `desktop/` 目录下无测试代码） |
| 注释质量 | 75 | JSDoc 注释完整，但 main.js `waitForBackend` timeout 15s vs 10s 的注释未同步更新 |

#### Desktop 综合评分：75/100

### Part B — Phase 2 MISRA C:2023 规则库审查

#### 规则完整性（Rule Completeness）— 90/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| YAML 规则全量覆盖 | 95 | 180 条 MISRA C:2023 规则（166 编号规则 + 14 Directives）全部定义 |
| 向后兼容映射 | 95 | 143 条 C:2012→C:2023 映射，8 种输入格式可解析，测试 30 条全部通过 |
| 规则变更分类 | 90 | unchanged(129)/modified(13)/removed(1)/new(37) 分类准确 |
| 已删除规则处理 | 85 | Rule 5.6 标记为 removed 但仍可识别和分类 |

#### 分类正确性（Classification Correctness）— 88/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| severity 标签准确性 | 90 | Required/Advisory/Directive 分类从 YAML 读取 |
| Directive 识别逻辑 | 85 | `_is_directive()` 方法使用字符串匹配，对部分边缘格式（如 `Dir-4.1` vs `dir4.1`）可能误判 |
| `project_specific` 回退策略 | 90 | 未知规则返回 project_specific 而非 crash，优雅降级 |
| P0-CRITICAL 规则分类 | 85 | 报告中提到 8 条 P0-CRITICAL 规则，但 misra.py 中未显式标识这 8 条规则（归类依赖 YAML severity 字段） |

#### 向后兼容性（Backward Compatibility）— 92/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| C:2012 ID 解析 | 95 | 8 种输入格式均可解析，覆盖完整 |
| 系统测试退化 | 95 | 120 个原有测试全部通过 |
| cppcheck 输出解析 | 90 | 真实日志格式可解析为 misra-c2023-X.Y ID |
| 数据流完整性 | 90 | cppcheck → parser → classify_rule 链路完整 |

#### Phase 2 MISRA 综合评分：90/100

---

## Round 2: Phase 3 yuleASR + Phase 1 Coverage + Tech Debt

### Part A — Phase 3 yuleASR 集成审查

#### 模板完整性（Template Completeness）— 72/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| MCAL 配置 stub 覆盖 | 70 | 只有 5/21 个 MCAL 模块有实际配置 stub（Mcu/Dio/Port/Gpt/Can），其余 16 个模块只有 spec 需求无配置实现 |
| ECUAL 配置 stub 覆盖 | 40 | 29 个 ECUAL 模块全部无配置 stub，仅有 spec 定义 |
| Services 配置 stub 覆盖 | 35 | 44 个 Services 模块全部无配置 stub，仅有 spec 定义 |
| 模板 spec SHALL 数 | 85 | yuleasr 模板 spec 有 105 条 SHALL 条款，覆盖维度完整 |
| template.yaml 模块清单 | 95 | 21+29+44 = 94 模块清单完整 ✅ |

#### 集成正确性（Integration Correctness）— 68/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| CLI init-autosar 可用性 | 65 | `yuleosh_cli.py` 实现了 cmd_init_autosar，但入口点通过 `_entry.py` 桥接。`resolve_template("yuleasr")` 依赖包内导入路径。在 pip install 后，_entry.py 的路径计算可能失效 |
| 模板搜索优先级 | 75 | 三层优先级（项目本地/用户本地/内置）在设计层面定义清晰 |
| BSW 初始化序列顺序 | 80 | main.c 的 7 步初始化序列正确遵循 AUTOSAR 规范顺序 |
| Makefile 构建依赖 | 70 | 依赖 `YULEASR_HOME` 环境变量，未在 init 时自动设置 |
| 链接脚本适配性 | 70 | 仅适配 S32K312（NXP），文档中标注为 "v0.1.0-MVP 仅支持 S32K312" |

#### Phase 3 yuleASR 综合评分：70/100

### Part B — Phase 1 Coverage 评估

#### 覆盖质量（Coverage Quality）— 65/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| 目标模块覆盖率 | 85 | 12 个目标模块全部达到 ≥ 80%（部分 100%）✅ |
| 全局覆盖率 | 50 | 全局 11.38%（包含所有 ~21K 语句），远低于 fail_under=50 目标 |
| 测试质量 | 70 | 183 个新测试覆盖了边缘路径和异常路径，但 review/run.py 和 ci/review_helpers.py 的测试依赖 mock，未覆盖真正的 Agent 交互路径 |
| fail_under 不一致 | 55 | **P1: 门禁分歧** — pyproject.toml 设置 `fail_under = 50`，pytest.ini 设置 `fail_under=45`。当前全局 11.38% 两个标准均不达标，但门禁值不同说明 CI 网关配置不统一 |
| 未覆盖关键模块 | 40 | pipeline/step_handlers/ (~5K 行, 0%), hardware/ (~2K 行, 0%), llm/ (~1.5K 行, <10%), autosar/parser.py (~600 行, 75%) 未达到封关标准 |

#### Phase 1 Coverage 综合评分：65/100

### Part C — 技术债方案评审

#### 方案合理性（Plan Rationality）— 78/100

| 维度 | 评分 | 评语 |
|:------|:----:|:------|
| 技术债全景完整性 | 85 | 9 类技术债识别完整，覆盖测试覆盖缺口/工具 bug/CI 门禁/文档 |
| 优先级排序合理性 | 80 | T1→T2→T3 的优先级合理（低成本高回报优先） |
| 工作量估算可信度 | 75 | T1 3.5 天评估合理，T2 6 天的 "step_handlers 测试" 涉及 LLM 依赖的 5K 行代码，3 天 per 大文件的估算偏乐观 |
| 覆盖提升预期 | 70 | T1 50%→52%, T2→58%, T3→62% 的线性提升假设未考虑测试质量维度的非线性特征 |
| 评审建议充分性 | 80 | 四条建议合理，接受 50% 基线是务实的 |

#### 技术债方案关键风险

| 风险 | 等级 | 说明 |
|:-----|:----:|:------|
| step_handlers 测试预算过紧 | P1 | 7 个大文件 + LLM 依赖 + Agent 交互，3 天极大概率不够 |
| 覆盖率工具 bug 未验证修复 | P1 | "升级 coverage 版本或改用纯 Python tracer" 方案未确认根因 |
| hardware+ 模块测试依赖硬件 HIL | P2 | T3 标注为 "视硬件资源决定"，无具体时间承诺 |

#### 技术债方案综合评分：78/100

---

## Scoring Summary

### Weighted Scoring (per expert-review-check.md)

| 维度 | 分数 | 满分 | 权重 | 加权得分 |
|:-----|:----:|:----:|:----:|:---------:|
| Desktop 架构合理性 | 72 | 100 | — (in R2 area) | — |
| Desktop 安全性 | 85 | 100 | — | — |
| Desktop 跨平台兼容性 | 65 | 100 | — | — |
| Desktop 代码质量 | 78 | 100 | — | — |
| **Desktop 综合** | **75** | **100** | — | — |
| Phase 2 MISRA 规则完整性 | 90 | 100 | — | — |
| Phase 2 MISRA 分类正确性 | 88 | 100 | — | — |
| Phase 2 MISRA 向后兼容性 | 92 | 100 | — | — |
| **Phase 2 MISRA 综合** | **90** | **100** | — | — |
| Phase 3 yuleASR 模板完整性 | 72 | 100 | — | — |
| Phase 3 yuleASR 集成正确性 | 68 | 100 | — | — |
| **Phase 3 yuleASR 综合** | **70** | **100** | — | — |
| Phase 1 覆盖质量 | 65 | 100 | — | — |
| 技术债方案合理性 | 78 | 100 | — | — |

### Expert Review Check Framework Scoring

Following the `expert-review-check.md` 四维框架:

| 轮次 | 维度 | 分数 | 满分 | 权重 | 加权得分 |
|:----:|:-----|:----:|:----:|:----:|:---------:|
| R1 (可追溯性) | — | **72** | 70 | 15% | 10.8/15 |
| R2 (可用性) | — | **68** | 100 | 25% | 17.0/25 |
| R3 (合规深度) | — | *Pending R3 review* | — | 35% | — |
| R4 (系统韧性) | — | *Pending R4 review* | — | 25% | — |
| **R1+R2 加权** | | | | **40%** | **27.8/40** |

### Round 1+2 各维度详细评分

| # | 维度 | 评分 | 满分 | 判定 |
|:-:|:-----|:----:|:----:|:----:|
| **R1.1** | 需求覆盖完整性 | 7 | 10 | ⚠️ 可接受 |
| **R1.2** | 规则库完整性 | 9 | 10 | ✅ 优秀 |
| **R1.3** | 模块清单完备性 | 7 | 10 | ⚠️ 可接受 |
| **R1.4** | 接口契约完整度 | 6 | 10 | 🔴 需补 |
| **R1.5** | 测试-需求双向追溯 | 6 | 10 | 🔴 需补 |
| **R1.6** | CI gate 对齐度 | 5 | 10 | 🔴 需补 |
| **R1.7** | 文档覆盖度 | 8 | 10 | ⚠️ 可接受 |
| **R1 合计** | | **48** | **70** | |
| | | | | |
| **R2.1** | CLI 命令可达性 | 6 | 10 | 🔴 需补 |
| **R2.2** | 模板生成完整性 | 7 | 10 | ⚠️ 可接受 |
| **R2.3** | 向后兼容性 | 9 | 10 | ✅ 优秀 |
| **R2.4** | Desktop 启动时序 | 7 | 10 | ⚠️ 可接受 |
| **R2.5** | Desktop 错误处理 | 8 | 10 | ⚠️ 可接受 |
| **R2.6** | CI pipeline 端到端 | 5 | 10 | 🔴 需补 |
| **R2.7** | 跨平台 Desktop 构建 | 5 | 10 | 🔴 需补 |
| **R2.8** | 规则 ID 多格式解析 | 9 | 10 | ✅ 优秀 |
| **R2.9** | init-autosar 与 template 系统 | 6 | 10 | 🔴 需补 |
| **R2.10** | Desktop 单实例保护 | 6 | 10 | 🔴 需补 |
| **R2 合计** | | **68** | **100** | |

---

## P0/P1 问题清单

### P0 问题（必须修复才能进入下一轮）

| # | 问题 | 模块 | 影响 | 证据 |
|:-:|:-----|:-----|:-----|:------|
| P0-1 | **CLI entry point 冲突** — pyproject.toml 使用 `yuleosh._entry:main`，setup.py 使用 `yuleosh=yuleosh_cli:main`。_entry.py 通过路径查找 `yuleosh_cli.py`，pip install 后路径断裂 | CLI 入口 | 影响到 `yuleosh init-autosar`、`yuleosh template list`、`yuleosh ci run` 等所有 CLI 命令在 pip 安装环境下的可达性。**触发黄牌条件 #3** | pyproject.toml:10, setup.py:30-32, src/yuleosh/_entry.py:20-27 |
| P0-2 | **健康检查超时不一致** — spec.md SHALL-2.1.3 规定 15 秒超时，main.js `waitForBackend()` 使用 10 秒；server-manager.js 使用 15 秒。违反 SHALL-2.1.3 | Desktop | 窗口管理后端就绪前就超时加载 UI，启动时可能显示空白的 backend-loading 页面。**涉及黄牌条件 #4** | desktop/spec.md:44, desktop/main.js:627/737, desktop/server-manager.js:18 |
| P0-3 | **`_DEFAULT_RULES_PATH` 打包后路径级断裂** — `misra.py` 从 `__file__` 上溯 5 级找 `misra-rules.yaml`。pip install 后 `misra-rules.yaml` 不在 site-packages 中 | MISRA rules | 所有 MISRA 规则加载失败，ci run L2 和 L3 功能失效。**触发黄牌条件 #1** | src/yuleosh/ci/rulesets/misra.py:31-32 |

### P1 问题（必须提供修复计划或 workaround 才能通过审查）

| # | 问题 | 模块 | 影响 | 证据 |
|:-:|:-----|:-----|:-----|:------|
| P1-1 | **Desktop 无单元测试** — spec 中 26 条 SHALL 定义了大量 UT（14 条 UT 策略），但 `desktop/` 下无任何测试文件 | Desktop | Spec→实现→测试 的可追溯链断裂。无法自动化验证窗口参数、IPC 事件、菜单构造 | desktop/acceptance-matrix.md （14 UT 测试条目 vs 0 个测试文件） |
| P1-2 | **yuleASR 模板 ECUAL/Services 无实际配置** — 29 个 ECUAL + 44 个 Services 模块只有 spec 定义无配置 stub。只有 5/21 MCAL 有配置 | yuleASR | 生成的 AUTOSAR 项目不能直接编译（仅有 MCAL 配置 stub），ECUAL 和 Services 完全无配置 | phase3-yuleasr-report.md: 第四章 |
| P1-3 | **覆盖率 fail_under 门禁分歧** — pyproject.toml=50, pytest.ini=45 | CI 门禁 | CI pipeline 覆盖门禁不一致，影响 CI gate 对齐度 | pyproject.toml:69, pytest.ini:5 |
| P1-4 | **Desktop 跨平台未实际验证** — 自测仅在 macOS arm64 执行，Linux/Windows/Wayland 列显未验证 | Desktop | 违反了 AC-5.1.2（Linux .AppImage 构建成功）的验收意图 | desktop/self-check.md: 5.x 全部未在 Linux 上实际运行 |
| P1-5 | **yuleosh init-autosar CLI 路径依赖** — `cmd_init_autosar` 内部的 `from yuleosh.templates import resolve_template` 在非开发环境下（pip install 后）可能因 sys.path 问题而失败 | CLI | AUTOSAR 项目初始化功能在标准部署场景下不可用 | yuleosh_cli.py:270 |
| P1-6 | **Desktop 后端路径硬编码** — server-manager.js `_resolveBackendDir()` 假设 `desktop/` 和 `src/` 在同一父目录下，打包后失效 | Desktop | 生产模式下 Python 后端无法启动（除非用户自行安装 pip 包） | desktop/server-manager.js:51-58 |
| P1-7 | **ECUAL/Services spec SHALL 无 mock 测试框架** — yuleasr 模板 tests/ 目录为空，仅有 `create_test_main` 生成的简陋框架 | yuleASR | 无法对 BSW 配置进行自动化验证 | phase3-yuleasr-report.md 第 7 章 |
| P1-8 | **Expert review check 已知风险表中标记的 P0 级未修复** — `yuleosh init-autosar` 在 pip install 后 CLI 不可达，`src/yuleosh/cli/` 中找不到 init-autosar 命令 | CLI | 已知风险表中已标注为 P0 但尚未修复 | expert-review-check.md R2 已知风险表 |
| P1-9 | **Desktop 无集成测试 / CI workflow** — `desktop/self-check.md` 列了 30+ 手动测试项，但没有 CI 自动化测试 | Desktop | 无自动化回归保护，发布前需全手动回归 | desktop/self-check.md |
| P1-10 | **Phase 1 新增测试发现 2 个代码 bug** — `_extract_assertion_lines()` 函数体检测 bug（使用 `line.strip()` 后检查缩进）和 `\btest_unit_\b` 正则边界问题，未修复 | ci/review_helpers.py | 已知代码缺陷未修复，影响 review 助手功能可靠性 | phase-coverage-final.md 第 4 章 |

---

## 黄牌条件检查

| # | 黄牌条件 | 状态 | 说明 |
|:-:|:---------|:----:|:------|
| 1 | P0 级风险未接受且未提供 mitigation plan | ⚠️ **触发** | P0-1（CLI entry point 冲突）和 P0-3（`_DEFAULT_RULES_PATH` 路径断裂）无 mitigation plan |
| 2 | 测试退化 > 5 条 | ✅ 未触发 | 120 + 30 个测试全部通过，无退化 |
| 3 | 关键 CLI 命令不可用 | ⚠️ **触发** | `yuleosh init-autosar` 在 pip install 后 CLI 不可达（因 P0-1） |
| 4 | Desktop 在任意支持平台上无法启动 | ⚠️ **部分触发** | 生产模式下 backend path 硬编码（P1-6）导致 macOS/Linux 打包后 Python 后端不可启动 |
| 5 | MISRA P0-CRITICAL 规则未实现且无替代方案 | ✅ 未触发 | 8 条 P0-CRITICAL 规则已分类，在 YAML 中有定义 |
| 6 | contextIsolation/nodeIntegration 安全配置缺失 | ✅ 未触发 | main.js 已正确设置 contextIsolation=true, nodeIntegration=false |

> **黄牌状态: ⚠️ 触发 2 条（#1 和 #3），部分触发 1 条（#4）**

---

## 综合判定

### R1+R2 加权总分

| 轮次 | 原始分 | 权重 | 加权得分 |
|:----:|:------:|:----:|:---------:|
| R1 可追溯性 | 48/70 | 15% | 10.8/15 |
| R2 可用性 | 68/100 | 25% | 17.0/25 |
| **R1+R2 合计** | | **40%** | **27.8/40** |

### 综合评分（含黄牌判定）

| 项目 | 值 |
|:-----|:----|
| R1+R2 加权分 | 27.8/40 (69.5%) |
| 通过标准 | ≥ 85/100 整体, 且无 P0 未接受风险 |
| 黄牌触发数 | 2 条完全触发 + 1 条部分触发 |
| **最终判定** | **❌ 不通过 — 黄牌触发** |

### 不通过理由

老陈 👨‍🏫 的话：

> 「代码结构我看清楚了。Desktop 的三层隔离做得对，MISRA 规则映射也做得扎实。但三个 P0 问题必须解决：CLI 入口点冲突让 `pip install` 后的用户等于没装，规则文件路径打包后找不到等于 CI 白跑，健康检查超时不一致连 spec 承诺都做不到。
>
> 黄牌条件 1（P0 无 mitigation plan）、条件 3（关键 CLI 不可用）、条件 4（Desktop 打包后启动不了）三条都挂红。这过了我的底线。
>
> 先去修三个 P0，然后把 Desktop 的跨平台验证跑一遍 Linux arm64，覆盖率 fail_under 统一成一个数。再叫我来看。技术债方案的方向是对的，T1 可以并行先做，不影响审查。」—— 老陈

### 具体恢复审查条件

1. **P0-1 修复**: 统一 CLI entry point（建议回归 setup.py 的 `yuleosh=yuleosh_cli:main` 方案，或重构 _entry.py 为 real entry point）
2. **P0-2 修复**: main.js `waitForBackend` 超时统一为 15 秒（对齐 spec.md SHALL-2.1.3）
3. **P0-3 修复**: `misra-rules.yaml` 纳入 pip 包数据文件（通过 `package_data` or `data_files`），或在 `_entry.py` 中设置环境变量指向外部路径
4. **P1-3 修复**: 统一覆盖率 fail_under 值（建议 pyproject.toml 从 50 改为 45 对齐 pytest.ini，或 pytest.ini 改为 50）
5. **Desktop 跨平台验证**: 至少完成 Linux x64 + arm64 的实际启动/构建测试

---

## 附录：详细证据引用

### R1 维度证据

**R1.1 (需求覆盖完整性 — 7/10)**
- Desktop: 26 SHALL 条款全部在 spec.md 中定义 ✅
- 但 SHALL-2.1.3 的实际实现（10s）与 spec（15s）不一致 ⚠️
- yuleasr 模板: 105 SHALL 条款覆盖 94 个模块 ✅
- 但 73/94 模块只有 spec 无配置实现 ⚠️

**R1.2 (规则库完整性 — 9/10)**
- 180 条 MISRA C:2023 规则全量覆盖 ✅
- 143 条 C:2012→C:2023 映射完成 ✅
- `_DEFAULT_RULES_PATH` 路径问题影响部署后规则可用性 ⚠️

**R1.3 (模块清单完备性 — 7/10)**
- yuleasr: 21+29+44 = 94 模块清单完整 ✅
- Desktop: 4 个模块（main/preload/tray/server-manager）职责清晰 ✅
- 但 server-manager 未处理 `python` vs `python3` 平台差异 ⚠️

**R1.4 (接口契约完整度 — 6/10)**
- CLI 子命令在 `yuleosh_cli.py` 定义 ✅
- 但 `_entry.py` 桥接脆弱，pip install 后入口路径计算断裂 🔴
- `_entry.py` 中同时添加 `project_root` 和 `project_root_alt` 两个候选路径，说明入口设计者意识到了路经不确定性

**R1.5 (测试-需求双向追溯 — 6/10)**
- Desktop acceptance-matrix.md 定义了 UT 14 项/IT 5 项/MT 18 项 ✅
- 但实际 desktop/ 下 **0 个测试文件** ❌
- MISRA 测试 30 条全部通过，可追溯到 180 条规则 ✅

**R1.6 (CI gate 对齐度 — 5/10)**
- coverage fail_under: pyproject.toml=50, pytest.ini=45 ❌
- Desktop 无 CI workflow ❌
- MISRA phase2 有 30 个测试但无 CI gate 配置验证 ❌

**R1.7 (文档覆盖度 — 8/10)**
- Desktop: spec.md + architecture.md + self-check.md + acceptance-matrix.md 完整 ✅
- 但 acceptance-matrix.md 表 header 有 typo（"SHAL-1.3.2"）⚠️

### R2 维度证据

**R2.1 (CLI 命令可达性 — 6/10)**
- pyproject.toml 使用 `yuleosh._entry:main` → 桥接到 yuleosh_cli.py
- setup.py 使用 `yuleosh=yuleosh_cli:main`
- pip install -e . 使用 setup.py（PEP 517 fallback 非预期）
- pip install 标准模式使用 pyproject.toml
- `_entry.py` 假设 `src/yuleosh/` → `../..` 为项目根目录 → pip 安装后此路径不成立

**R2.2 (模板生成完整性 — 7/10)**
- `cmd_init_autosar` 完整实现 ✅
- 生成项目结构完整（src/docs/pipeline/config）✅
- 但 73/94 模块无配置 stub，项目不能直接编译 ⚠️

**R2.8 (规则 ID 多格式解析 — 9/10)**
- 8 种输入格式均可解析 ✅
- backward_compat 映射 143 条 C:2012→C:2023 ✅
- 如裸数字 "10.1" → "misra-c2023-10.1", "Dir 4.1" → "misra-c2023-dir-4.1" ✅

**R2.10 (Desktop 单实例保护 — 6/10)**
- Desktop 代码中无单实例锁定机制（无 `app.requestSingleInstanceLock()` 调用）
- 自测清单 7.3 项 "快速双击启动两次 → 只启动一个实例" 标记为 pass，但代码中没有实现
- Electron 默认行为：第二次双击会启动第二个实例
