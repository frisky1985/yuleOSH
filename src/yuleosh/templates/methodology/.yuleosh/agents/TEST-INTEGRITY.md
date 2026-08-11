# TEST-INTEGRITY.md — 测试真实性与降级透明性（第一准则延伸）

> **Version**: 1.0.0
> **Status**: Active
> **Format**: OpenSpec (RFC 2119: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN)
> **Source**: 第一准则 PRIME-DIRECTIVE.md 的详细落地条款。冲突时以第一准则为准。
> **Scope**: 本文件约束所有 agent 编写/审查测试、实现/修改降级路径时的具体行为。

---

## 1. Mock 合规边界 (Mock Boundary Rules)

### 1.1 什么可以 mock（外部边界白名单）

**SHALL**:
- mock SHALL 仅用于替换**外部边界**：subprocess/外部进程、网络调用（HTTP/gRPC/socket）、第三方 SDK 与 CLI 工具（cppcheck、编译器、git、数据库驱动连接）、文件系统 IO、系统时钟/随机源、LLM API 调用（管道 --mock 模式）。
- mock 目标 SHALL 是"被测单元不拥有的外部资源"——被测单元依赖但不由其定义的东西。

**SHALL NOT**:
- 测试 SHALL NOT mock 被测模块自身的核心逻辑（被测函数内部调用的本模块函数、被修复的 bug 所在代码路径）。
- 测试 SHALL NOT mock 掉"修复点本身"来让测试通过（假绿）。

### 1.2 mock 路径必须等于生产路径

**SHALL**:
- `mock.patch(...)` 的目标路径 SHALL 与生产代码的 import 路径完全一致（例如生产代码 `from yuleosh.knowledge_graph.coverage_importer import import_coverage_from_default`，测试 SHALL patch `yuleosh.knowledge_graph.coverage_importer.import_coverage_from_default`，不得 patch 别的等价路径）。
- 这样做的理由：路径不一致时 `mock.patch` 会抛 `ModuleNotFoundError`/`AttributeError`，测试必红——mock 路径即契约，天然守护 import 路径正确性。

### 1.3 断言必须包含真实副作用

**SHALL**:
- 测试断言 SHALL 验证**真实副作用**：函数返回值、落盘文件存在且内容正确、数据库行/状态、API 状态码与响应体。
- `assert_called_once` / `mock.return_value` SHALL 仅作为编排验证的补充，不得作为唯一断言。

**SHALL NOT**:
- 测试 SHALL NOT 以"mock 返回 X → 断言函数也返回 X"的循环论证方式通过。

### 1.4 关键路径必须有全链路用例

**SHOULD**:
- 每个关键子系统 SHOULD 至少有一个**不 mock 内部逻辑**的全链路测试（真实实例化核心类、真实读写存储），与 mock 单测互补。
- 修复 bug 的回归测试 SHOULD 优先选择不 mock 修复点的形式（真实走通修复路径）。

---

## 2. 降级/容错透明性 (Degradation Transparency)

### 2.1 异常类型收窄

**SHALL**:
- 降级/fallback 路径 SHALL 只捕获**真实故障类型**：存储类（`sqlite3.Error`、`OSError`、`IOError`）、网络类（`TimeoutError`、`requests.RequestException`）、外部依赖类（subprocess 非零退出、SDK 异常）。
- 编程错误（`TypeError`、`ValueError`、`AttributeError`、`KeyError`、逻辑断言失败）SHALL 向上抛出，SHALL NOT 被降级吞掉——否则自己的 bug 会被降级掩盖，测试环境不触发、生产静默降级。
- 确需宽捕获时（如插件边界），SHALL 在 except 内重新抛出非预期类型：`except Exception as e: if isinstance(e, (ExpectedTypes...)): degrade(); raise`。

**SHALL NOT**:
- 代码 SHALL NOT 使用裸 `except Exception:` 降级而不区分异常类型。
- 代码 SHALL NOT 用 `except:  # noqa` 静默吞掉一切。

### 2.2 降级必须可观测

**SHALL**:
- 每次降级 SHALL 至少记录一条 `log.warning`（或更高级别），说明：降级原因（异常类型+消息）、降级后行为（如"多 worker 共享限流预算未生效，退回进程内存限流"）。
- 模块 SHALL 有 logger（`logging.getLogger(__name__)`）；禁止在无 logger 的模块里静默降级。
- 关键降级点 SHOULD 暴露健康指标（计数器/状态字段），便于生产监控发现"系统长期处于降级状态"。

**SHALL NOT**:
- 降级 SHALL NOT 静默发生（无日志、无指标、无任何痕迹）。

### 2.3 降级测试必须真实

**SHALL**:
- 降级路径的测试 SHALL 用**真实故障类型**触发（如让 SQLite 目录不可写 → `sqlite3.OperationalError`；让子进程返回非零 → 对应异常）。
- 测试 SHALL 断言：降级行为生效（返回 fallback 结果）+ 降级被记录（日志含 warning）+ **编程错误不被降级**（构造会抛编程错误的输入，断言异常向上抛、测试红）。
- 测试 SHALL NOT 用 `RuntimeError` 万能模拟一切故障——那等于测试"什么都降级"的过宽行为。

---

## 3. 回归测试纪律 (Regression Test Discipline)

### 3.1 RED → GREEN

**SHALL**:
- 任何 bug 修复 SHALL 先写回归测试，运行确认其在修复前失败（RED，且失败原因是被测 bug 而非测试自身错误）。
- 然后实施修复，运行确认测试转绿（GREEN）。
- 修复完成后 SHALL 运行该测试所在模块的完整测试集，确认无回归。

**SHALL NOT**:
- 不允许"只改代码、不写测试"的修复。
- 不允许"测试先行但从未运行 RED"的流程（跳过 RED 无法证明测试真的守护了 bug）。

### 3.2 修复证据

**SHALL**:
- 修复提交的 message 或关联报告 SHALL 注明回归测试的位置（如 `tests/test_http_security_degradation.py::test_programming_error_not_degraded`）。
- 修复后 SHALL 运行相关测试并记录结果（通过数/失败数）。

---

## 4. GIVEN/WHEN/THEN 验收矩阵

##### GIVEN 被测模块含降级路径（如 check_rate_limit）
##### WHEN agent 编写该路径的测试
##### THEN 测试 SHALL 用真实故障类型（sqlite3.Error/OSError）触发降级
##### AND 断言降级返回 fallback 结果 + 日志含 warning
##### AND 另有用例验证编程错误（TypeError 等）向上抛、不降级

##### GIVEN 测试 mock 了某个依赖
##### WHEN 小马审查该测试
##### THEN mock 目标 SHALL 属于外部边界白名单（§1.1）
##### AND mock 路径 SHALL 与生产 import 路径一致（§1.2）
##### AND 断言 SHALL 包含真实副作用验证（§1.3）

##### GIVEN 一个 bug 修复
##### WHEN agent 提交修复
##### THEN 提交 SHALL 包含先在修复前失败的回归测试（RED→GREEN 证据）
##### AND 相关测试集 SHALL 全部通过

---

**版本记录**:
- 1.0.0 (2026-08-07): 第一准则延伸规则落盘。背景：v3.13.2 审查修复 http_security 静默降级（无日志 + except Exception 吞编程错误）；测试曾用 mock 绕过限流真实语义。与 PRIME-DIRECTIVE.md 同时生效。
