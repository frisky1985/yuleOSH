# 测试生成 (`testgen`) API 参考

> 代码根:`src/yuleosh/testgen/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`testgen` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/testgen.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_sanitize` | `(s: str)` | Sanitize a description string for use as a test function name. | `testgen/formatter.py:25` |
| `_escape_c_string` | `(s: str)` | Escape a string for embedding in a C string literal. | `testgen/formatter.py:38` |
| `_escape_python_string` | `(s: str)` | Escape a string for embedding in a Python string literal. | `testgen/formatter.py:43` |
| `format_pytest` | `(test_cases: list[TestCase], module_name: str)` | Format test cases as a pytest-compatible Python test file. | `testgen/formatter.py:58` |
| `format_gotest` | `(test_cases: list[TestCase], package: str)` | Format test cases as a Go test file (testing package). | `testgen/formatter.py:114` |
| `format_ceedling` | `(test_cases: list[TestCase])` | Format test cases as a C test file using Ceedling / Unity Test framework. | `testgen/formatter.py:158` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `TestCase` | `()` | A single test case derived from an OpenSpec SHALL/SHOULD/MAY statement. | `testgen/generator.py:35` |
| `TestGenerator` | `()` | AI-powered test case generator from OpenSpec. | `testgen/generator.py:108` |
| `TestResult` | `()` | Result of executing a single test case. | `testgen/runner.py:31` |
| `TestReport` | `()` | Aggregate report from running a batch of test cases. | `testgen/runner.py:40` |
| `CoverageEntry` | `()` | A single SHALL → test-case mapping. | `testgen/runner.py:61` |
| `CoverageReport` | `()` | SHALL-level coverage report showing which requirements have tests. | `testgen/runner.py:70` |
| `TestRunner` | `()` | Execute generated test cases and produce coverage/execution reports. | `testgen/runner.py:91` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `TestCase.to_dict` | `(self)` | — | `testgen/generator.py:57` |
| `TestGenerator.__init__` | `(self, llm_provider: Any)` | Initialize with an LLM provider module. | `testgen/generator.py:117` |
| `TestGenerator.generate_from_spec` | `(self, spec_path: str, temperature: float, max_tokens: int)` | Read an OpenSpec file, invoke the LLM, and return parsed TestCase objects. | `testgen/generator.py:129` |
| `TestGenerator.generate_code_tests` | `(self, test_cases: list[TestCase], lang: str)` | Convert a list of TestCase objects into executable test code. | `testgen/generator.py:174` |
| `TestGenerator.estimate_effectiveness` | `(self, test_cases: list[TestCase], spec_path: Optional[str], doc: Any, temperature: float, max_tokens: int)` | Evaluate test case coverage and effectiveness against the spec. | `testgen/generator.py:201` |
| `TestGenerator.quick_coverage` | `(self, test_cases: list[TestCase], spec_path: Optional[str], doc: Any)` | Compute a simple deterministic coverage estimate (no LLM call). | `testgen/generator.py:255` |
| `TestReport.to_dict` | `(self)` | — | `testgen/runner.py:50` |
| `TestReport.pass_rate` | `(self)` | — | `testgen/runner.py:54` |
| `CoverageReport.to_dict` | `(self)` | — | `testgen/runner.py:78` |
| `TestRunner.__init__` | `(self)` | — | `testgen/runner.py:105` |
| `TestRunner.run_tests` | `(self, test_cases: list[TestCase], project_dir: str, dry_run: bool, spec_path: Optional[str], lang: str)` | Run the given test cases and produce an execution report. | `testgen/runner.py:111` |
| `TestRunner.coverage_report` | `(self)` | Return the last computed coverage report as a dict. | `testgen/runner.py:155` |
| `TestRunner.print_report` | `(self, report: Optional[TestReport])` | Pretty-print a TestReport to stdout. | `testgen/runner.py:166` |

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> ⚠️ 本子系统**无生产调用方**（ORPHAN，已 grep 全仓 `yuleosh.%s` 验证）。以下为基于公共 API 签名的自包含用法骨架，**参数以源码 `文件:行` 为准，请勿臆造**。

```python
from yuleosh.testgen import TestCase  # 主类，定义见 src/yuleosh/testgen/generator.py:35
# obj = TestCase(...)  # 必填参数见 src/yuleosh/testgen/generator.py:35
```

> 整治建议：若计划保留本子系统，应将其接入对应 Pipeline Step 或路由；否则归档/删除（删除前需先移除其测试引用，避免破坏 CI）。

## 6. 偏差 / 备注

- 生产调用方:❌ 疑似 ORPHAN(无生产调用方)(Grep `yuleosh.testgen` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/testgen/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_
