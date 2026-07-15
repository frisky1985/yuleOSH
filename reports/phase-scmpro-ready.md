# scm-pro 座椅模块验证准备就绪报告

> 生成日期: 2026-07-02 01:51 CST  
> 项目: yuleOSH — 嵌入式 AI 开发 SaaS 平台  
> 任务: scm-pro 座椅模块全流程验证准备

---

## 1. 模板系统支持验证

### 1.1 AUTOSAR Classic 模板

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 模板存在 | ✅ | `src/yuleosh/templates/autosar-classic/` |
| template.yaml 清单 | ✅ | 版本 v1.0.0，含 ARM/STM32/Renesas 平台标签 |
| pipeline/config.yaml | ✅ | 11-step 默认配置 + L1/L2/L3 CI + 审查门控 |
| specs/spec.md | ✅ | 含 System Requirements + Software Requirements + ARXML + RTE + BSW + Test Plan |
| ARXML 支持 | ✅ | spec 中包含 ARXML 章节和导入导出说明 |

### 1.2 generic-embedded-c 模板

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 模板存在 | ✅ | `src/yuleosh/templates/generic-embedded-c/` |
| pipeline/config.yaml | ✅ | 10-step 配置 + L1/L2/L3 CI + 审查门控 |
| specs/spec.md | ✅ | 通用嵌入式 C 项目规格 |

### 1.3 其他可用模板

共 **10 个内置模板**:
- arm-cmsis, autosar-classic, baremetal-safety, esp32-idf, freertos-misra
- generic-embedded-c, generic-python, stm32-hal, unit-test-harness, zephyr-rtos

---

## 2. Spec-Contract 需求导入验证

| 检查项 | 状态 | 详情 |
|--------|------|------|
| OpenSpec 解析器 | ✅ | `yuleosh.spec.validate.parse_spec()` 可用 |
| AUTOSAR spec 解析 | ✅ | 4 requirements, 1 scenarios 解析成功 |
| SHALL/SHOULD/MAY 支持 | ✅ | 标准 OpenSpec 格式 (SHALL/SHOULD/MAY/GIVEN/WHEN/THEN) |
| 需求追溯 | ✅ | `ci/review_helpers.auto_map_shall_coverage()` 支持 SHALL ID 自动映射 |
| UT 测试源发现 | ✅ | `find_test_source_files()` 支持 `.py` 和 `.c` |

---

## 3. 28-Step Pipeline 全流程验证

### 3.1 Pipeline 定义

```python
从 yuleosh.pipeline.run import PIPELINE_STEPS
# 共 28 个步骤就绪
```

### 3.2 步骤一览

| # | 步骤 ID | 步骤名称 | Agent | 类型 |
|---|---------|---------|-------|------|
| 1 | spec-check | OpenSpec 合规检查 | 小明 | 验证 |
| 2 | super-analysis | S.U.P.E.R 启动分析 | 小明 | 分析 |
| 3 | prd | 产品需求分析 | Hermes | 生成 |
| 4 | prd-review | PRD 质量审查 | 小马 | 审查 |
| 5 | architecture | 架构设计 | Claude | 生成 |
| 6 | arch-review | 架构审查 | 小克 | 审查 |
| 7 | development | 开发计划与代码实现 | Claude | 生成 |
| 8 | devplan-review | 开发计划审查 | 小克 | 审查 |
| 9 | internal-code-review | 代码实现预审 | 小克 | 审查 |
| 10 | test-planning | 测试规划 | Claude | 生成 |
| 11 | self-test | 自测验证 | Claude | 生成 |
| 12 | self-test-review | 自测结果审查 | 小克 | 审查 |
| 13 | c-unit-test | C 单元测试 (Unity) | 小克 | 测试 |
| 14 | integration-test | 接口集成测试 | 小克 | 测试 |
| 15 | code-review | 集成代码审查 | Hermes | 审查 |
| 16 | misra-review | MISRA 合规审查 | 小马 | 审查 |
| 17 | coverage-review | 测试覆盖审查 | 小马 | 审查 |
| 18 | review-linker | 链接脚本审查 | 小克 | 审查 |
| 19 | review-startup | 启动代码审查 | 小克 | 审查 |
| 20 | review-rtos | RTOS 配置审查 | 小克 | 审查 |
| 21 | review-memory | 内存安全审查 | 小克 | 审查 |
| 22 | review-bsp | BSP 板级支持包验证 | 小克 | 审查 |
| 23 | review-build | 编译输出验证 | 小克 | 审查 |
| 24 | review-power | 低功耗审查 | 小克 | 审查 |
| 25 | review-stack | 堆栈使用分析 | 小克 | 审查 |
| 26 | review-mmio | MMIO 配置审查 | 小克 | 审查 |
| 27 | test-qualification | 合格性测试 | 小明 | 测试 |
| 28 | final-report | 最终报告 | 小明 | 报告 |

### 3.3 Pipeline 运行入口

```python
# mock 模式（跳过 LLM key 检查）
from yuleosh.pipeline.run import run_pipeline
run_pipeline("path/to/spec.md", mock=True)

# 正常模式
from yuleosh.pipeline.run import run_pipeline
run_pipeline("path/to/spec.md")
```

### 3.4 Profile 过滤支持

```python
from yuleosh.ci.profile import validate_active_profile, filter_steps_for_profile
# 支持按 profile 过滤步骤
```

---

## 4. 产出完整性验证

### 4.1 测试报告

| 组件 | 状态 | 路径 |
|------|------|------|
| pytest 测试运行 | ✅ | `yuleosh.pipeline.run.run_pipeline()` 含各步骤 handler |
| JUnit XML 解析 | ✅ | `ci/review_helpers.parse_junit_xml()` |
| 测试类型推断 | ✅ | `_infer_test_type()` unit/integration/system |
| 测试结果结构化 | ✅ | failure type/message/stacktrace |

### 4.2 覆盖率

| 组件 | 状态 | 路径 |
|------|------|------|
| Python 覆盖率 | ✅ | 通过 pytest-cov + `ci/coverage_pipeline.py` |
| C 覆盖率 (gcov) | ✅ | `ci/gcov_coverage.py` |
| 覆盖率趋势追踪 | ✅ | `ci/coverage_trend.py`, `ci/kpi/trend.py` |
| 覆盖率预测 | ✅ | `preview/coverage_predictor.py` |
| 覆盖率审查 | ✅ | `review/run.review_coverage()` |

### 4.3 证据包

| 组件 | 状态 | 路径 |
|------|------|------|
| 证据收集 | ✅ | `evidence/collection.py` - `DataCollectionMixin` |
| 证据打包 | ✅ | `evidence/pack.py` - `EvidenceCollector` |
| 证据完整性检查 | ✅ | `evidence/evidence_check.py` - `check_evidence_integrity` |
| 证据包 (zip) | ✅ | `evidence/evidence_check.py` - `pack_evidence_bundle` |
| 合规证据 | ✅ | `evidence/compliance.py` - `generate_evidence`, `pack_compliance_zip` |
| 证据子目录 | ✅ | `EVIDENCE_SUBDIRS` 配置，强制组件列表 |
| 证据 Excel 报告 | ✅ | `evidence/excel_writer.py` - `ExcelReportWriter` |

### 4.4 追溯矩阵

| 组件 | 状态 | 路径 |
|------|------|------|
| SHALL 自动映射 | ✅ | `ci/review_helpers.auto_map_shall_coverage()` |
| 断言行提取 | ✅ | `_extract_assertion_lines()` |
| 函数名推断覆盖 | ✅ | `evidence/analysis.infer_covers_from_function_names()` |
| 注释 @cover 解析 | ✅ | `evidence/analysis.parse_comment_covers()` |
| 生成追溯报告 | ✅ | `tools/generate-rtm-report.py` |
| ASPICE 合规检查 | ✅ | `evidence/aspice_check.py` |

---

## 5. scm-pro 座椅模块验证步骤

推荐验证命令序列：

```bash
# 1. 选择 AUTOSAR Classic 模板
cd /path/to/scm-pro/seating-module

# 2. 初始化项目
yuleosh init --template autosar-classic

# 3. 导入座椅模块 spec-contract 需求
cp /path/to/scm-seat-spec.md specs/spec.md

# 4. 运行完整 28-step pipeline（mock 模式）
PYTHONPATH=src python3 -m yuleosh.pipeline.run mock spec.md

# 或使用 orchestrator:
PYTHONPATH=src python3 -c "
from yuleosh.pipeline.run import run_pipeline
run_pipeline('specs/spec.md', mock=True, name='scm-pro-valid')
"

# 5. 检查产出
ls -la sessions/scm-pro-valid/
ls -la sessions/scm-pro-valid/evidence/
ls -la sessions/scm-pro-valid/report/
```

---

## 6. 已知限制

| 限制 | 说明 | 建议 |
|------|------|------|
| LLM 依赖 | pipeline 需要 LLM API key 或 mock 模式 | scm-pro 验证使用 `mock=True` |
| 外部工具 | gcov, ceedling, go test 需要安装 | C 单元测试需要 Ceedling 环境 |
| 覆盖率全局目标 | 当前 11.32%，目标 60% | 建议增加 api/、store/、ci/run.py 覆盖 |

---

## 7. 总结

| 验证维度 | 状态 |
|---------|------|
| 模板系统支持 AUTOSAR Classic | ✅ |
| 模板系统支持 generic-embedded-c | ✅ |
| Spec-contract 需求导入 | ✅ |
| 28-step pipeline 就绪 | ✅ |
| 测试报告 | ✅ |
| 覆盖率报告 | ✅ |
| 证据包生成 | ✅ |
| 追溯矩阵生成 | ✅ |
| Pipeline mock 模式（无 LLM） | ✅ |

**结论: scm-pro 座椅模块验证环境已就绪，可立即启动全流程验证。** 🚀
