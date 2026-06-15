# 产品线 v1 — Template Gallery · SaaS Try-it Demo · AI Preview Assessment

> **Version**: 1.0.0-draft
> **基于**: Sprint 5 完成；行业分析 (docs/analysis-brainstorm-industry.md)
> **格式**: RFC 2119 (SHALL / SHOULD / MAY) + GIVEN/WHEN/THEN
> **作者**: 小马 🐴 (质量架构师)
> **日期**: 2026-06-15

---

## 目录

- [1. Template Gallery (模板市场)](#1-template-gallery-模板市场)
- [2. SaaS Try-it Demo](#2-saas-try-it-demo)
- [3. AI Preview Assessment (AI 预览评估)](#3-ai-preview-assessment-ai-预览评估)
- [附录A: 验收矩阵](#附录a-验收矩阵)

---

# 1. Template Gallery (模板市场)

## 1.1 概述

Template Gallery 为用户提供预置项目模板。新建项目时选模板 → 自动生成 OpenSpec + pipeline 配置 + 初始代码骨架。模板以 yaml/md 格式存储在 `templates/` 目录下。

### 模板清单（初始 v1 版本）

| 模板名称 | 描述 | 目标场景 |
|:---------|:-----|:---------|
| `zephyr-rtos` | Zephyr RTOS 项目模板 | Zephyr 嵌入式开发，含设备树和 Kconfig |
| `freertos-misra` | FreeRTOS + MISRA 检测模板 | FreeRTOS 项目，开启 MISRA-C 2012 静态分析 |
| `autosar-classic` | AUTOSAR 经典平台模板 | 汽车 ECU 项目，含 ARXML 和 RTE 配置占位 |
| `generic-embedded-c` | 通用 Embedded C 项目模板 | 通用 MCU C 项目，含 hal 抽象层 |
| `generic-python` | 通用 Python 项目模板 | yuleOSH pipeline 的 Python 工具项目 |
| `stm32-hal` | STM32 HAL 库模板 | STM32 项目，含 HAL 驱动和 FreeRTOS 集成 |
| `esp32-idf` | ESP32-IDF 项目模板 | ESP32 项目，含 Wi-Fi/BLE 框架占位 |
| `arm-cmsis` | ARM CMSIS 项目模板 | ARM Cortex-M 裸机项目，含 CMSIS-Core |
| `baremetal-safety` | 安全关键裸机模板 | ISO 26262 ASIL-B 级项目，含看门狗和 ECC 框架 |
| `unit-test-harness` | C 单元测试框架模板 | 仅测试骨架项目，含 Unity/CMock 测试配置 |

---

## 1.2 需求定义

### TG-REQ-001: 模板存储结构

- The system **SHALL** store built-in templates under `yuleosh/templates/` directory.
- Each template **SHALL** contain at minimum:
  - `template.yaml` — 模板清单文件（元数据 + 配置声明）
  - `specs/spec.md` — 初始 OpenSpec 规范文件
  - `pipeline/config.yaml` — pipeline 配置（steps, ci_layers, review_gates）
  - `src/` — 初始代码骨架目录
- The template.yaml manifest **SHALL** include the following fields:
  - `name` — 模板唯一标识符（kebab-case）
  - `version` — 语义化版本号
  - `description` — 简短描述（≤200 字符）
  - `platforms` — 支持平台列表（stm32, esp32, arm, generic）
  - `tags` — 分类标签列表
  - `spec_sections` — 初始 spec 中预置的节头列表
  - `pipeline_config` — 预置 pipeline config 引用

**GIVEN** the package is installed  
**WHEN** the system reads the built-in templates directory  
**THEN** the system SHALL find at least 5 template directories  
**AND** each template directory SHALL contain a valid `template.yaml`, `specs/spec.md`, `pipeline/config.yaml`, and `src/` directory

---

### TG-REQ-002: 模板搜索优先级

- The system **SHALL** search for templates in the following order, first match wins:
  1. **Project-local**: `<project_root>/.yuleosh/templates/<name>/`
  2. **User-local**: `~/.yuleosh/templates/<name>/`
  3. **Built-in**: `<package_install_path>/yuleosh/templates/<name>/`
- The system **SHALL** merge the effective template by overlaying entries: user-defined entries supplement built-in entries rather than replacing the entire directory.

**GIVEN** a template name exists in both built-in and user-local directories  
**WHEN** the system resolves the template  
**THEN** the user-local version SHALL be used  
**AND** files only present in the built-in version SHALL be inherited

---

### TG-REQ-003: `yuleosh project init --template <name>` CLI 命令

- The system **SHALL** support the CLI command `yuleosh project init --template <name> [project_dir]`.
- When `--template` is omitted, the system **SHALL** enter interactive mode listing all available templates.
- The command **SHALL**:
  1. Resolve the template via search priority (TG-REQ-002).
  2. Create the target project directory (default: `./<name>-project`).
  3. Copy the spec skeleton to `<project_dir>/docs/spec.md`.
  4. Copy the pipeline config to `<project_dir>/pipeline/config.yaml`.
  5. Copy the code skeleton to `<project_dir>/src/`.
  6. Generate a `<project_dir>/yuleosh.yaml` project config file with template metadata.
  7. Print a success message with next steps.

**GIVEN** the user runs `yuleosh project init --template zephyr-rtos my-zephyr-app`  
**WHEN** the template `zephyr-rtos` is resolved  
**THEN** the system SHALL create directory `my-zephyr-app/`  
**AND** the system SHALL create `my-zephyr-app/docs/spec.md` with pre-populated Zephyr RTOS spec content  
**AND** the system SHALL create `my-zephyr-app/pipeline/config.yaml` with pre-configured Zephyr pipeline steps  
**AND** the system SHALL create `my-zephyr-app/src/` with initial C source files  
**AND** the system SHALL create `my-zephyr-app/yuleosh.yaml` with template provenance metadata

**GIVEN** the user runs `yuleosh project init --template nonexistent-template`  
**WHEN** the template is not found in any search location  
**THEN** the system SHALL exit with a non-zero status  
**AND** the system SHALL print an error message: `Error: template 'nonexistent-template' not found.`

**GIVEN** the user runs `yuleosh project init` without `--template`  
**WHEN** no `--template` flag is provided  
**THEN** the system SHALL display an interactive numbered list of all available templates  
**AND** the system SHALL prompt: `Select a template (1-N):`

---

### TG-REQ-004: `yuleosh template list` 命令

- The system **SHALL** support the CLI command `yuleosh template list` to enumerate all discoverable templates.
- The output **SHALL** be a formatted table with columns: `Name`, `Version`, `Description`, `Platforms`.
- The list **SHALL** show all templates from all search paths (TG-REQ-002), deduplicated by name (user-local overrides built-in).

**GIVEN** the user runs `yuleosh template list`  
**WHEN** 10 templates exist across built-in and user-local directories  
**THEN** the output SHALL display a table containing all 10 templates  
**AND** each row SHALL show the template name, version, description, and platforms

---

### TG-REQ-005: 模板生成内容完整性

- The generated spec skeleton (`docs/spec.md`) **SHALL** contain at minimum:
  - A title matching the template
  - Pre-populated SHALL/SHALL NOT requirements with placeholder IDs
  - At least one GIVEN/WHEN/THEN scenario skeleton
  - Placeholder sections for System Requirements, Software Requirements, Test Plan
- The generated pipeline config (`pipeline/config.yaml`) **SHALL** contain at minimum:
  - Default step sequence matching the template's target framework
  - CI layer configuration (at minimum L1 unit test enabled)
  - Review gate configuration
- The generated code skeleton (`src/`) **SHALL** contain at minimum:
  - `main.c` or equivalent entry point with framework boilerplate
  - A build system file (`CMakeLists.txt` or `Makefile`)
  - A placeholder hardware abstraction header for MCU templates
  - Empty test directory `tests/` with a dummy unit test file

**GIVEN** the user runs `yuleosh project init --template autosar-classic`  
**WHEN** the project directory is created  
**THEN** `docs/spec.md` SHALL contain AUTOSAR-specific requirement sections  
**AND** `pipeline/config.yaml` SHALL include AUTOSAR-specific static analysis rules  
**AND** `src/` SHALL contain an ARXML-compatible code structure sketch  
**AND** `src/CMakeLists.txt` SHALL reference AUTOSAR RTE headers

---

### TG-REQ-006: 模板初始化产物覆盖

- The `yuleosh project init` command **SHALL NOT** overwrite existing files in the target directory unless `--force` is specified.
- When `--force` is provided, the system **SHALL** overwrite colliding files after printing a warning with the list of files to be overwritten and requiring user confirmation via `[y/N]` prompt.

**GIVEN** the target directory `my-app/` exists and contains `docs/spec.md`  
**WHEN** the user runs `yuleosh project init --template generic-embedded-c my-app`  
**THEN** the system SHALL print: `Warning: my-app/docs/spec.md already exists. Skipping.`  
**AND** the system SHALL NOT modify the existing `docs/spec.md`

**GIVEN** the target directory `my-app/` exists and contains `docs/spec.md`  
**WHEN** the user runs `yuleosh project init --template generic-embedded-c my-app --force`  
**THEN** the system SHALL list all files that will be overwritten  
**AND** the system SHALL prompt `Overwrite these files? [y/N]`  
**AND** if user answers `y`, the system SHALL overwrite all colliding files

---

### TG-REQ-007: 模板热加载

- The system **MAY** support hot-reloading templates without reinstalling the package, by watching `~/.yuleosh/templates/` on each `template list` or `project init` invocation (no daemon needed).

---

---

# 2. SaaS Try-it Demo

## 2.1 概述

在 Landing page 上添加"Try Demo"按钮。用户点击后触发一个预置的 mock pipeline 运行（不依赖真实 LLM 调用），展示 pipeline progress、各 step 结果、最终报告、evidence pack。不需要注册，体验完引导注册。后端提供 `GET /api/demo/pipeline` 端点。

---

## 2.2 需求定义

### DEMO-REQ-001: Landing Page "Try Demo" 入口

- The landing page **SHALL** display a prominent "Try Demo" button on the hero section.
- The button **SHALL** be visually distinct (primary call-to-action styling, minimum 48px height).
- Clicking the button **SHALL** navigate the user to `/demo` (or trigger an inline demo experience).
- The landing page **SHALL** also display a secondary "Try Demo" button in the navigation bar for screens ≥768px.

**GIVEN** a user visits the yuleOSH landing page on a desktop browser  
**WHEN** the page finishes loading  
**THEN** a "Try Demo" button SHALL be visible in the hero section  
**AND** the button SHALL have a ≥48px height  
**AND** a second "Try Demo" button SHALL be visible in the navigation bar

**GIVEN** a user clicks the "Try Demo" button  
**WHEN** the click event fires  
**THEN** the browser SHALL navigate to `/demo`

---

### DEMO-REQ-002: Demo Pipeline 后端 API

- The server **SHALL** expose a `GET /api/demo/pipeline` endpoint.
- This endpoint **SHALL NOT** require authentication or API key.
- This endpoint **SHALL** return a JSON response simulating a full pipeline run.
- The response **SHALL NOT** depend on any external LLM service — all data **SHALL** be pre-seeded mock data.
- The endpoint **SHALL** accept an optional query parameter `?step=<step_id>` to simulate progress after a specific step, returning partial results.

#### 响应 Schema

```json
{
  "status": "running" | "completed" | "failed",
  "pipeline_id": "demo-<uuid>",
  "total_steps": 10,
  "current_step": <int>,
  "steps": [
    {
      "id": "spec-parse",
      "name": "Spec Parsing",
      "status": "completed" | "running" | "pending" | "failed",
      "output_summary": "<string>",
      "duration_ms": <int>,
      "artifacts": {
        "requirements_count": <int>,
        "scenarios_count": <int>
      }
    },
    ...
  ],
  "final_report": {
    "summary": "<markdown string>",
    "coverage_prediction": "72%",
    "review_score": "8.4/10",
    "compliance_gates": {
      "aspice": "passed",
      "misra": "3 warnings",
      "unit_test": "18/20 passed"
    }
  },
  "evidence_pack_url": "/api/demo/evidence/demo-<uuid>.zip"
}
```

- The response **SHALL** include at least the following mock step results:
  1. Spec Parsing
  2. Requirements Analysis
  3. System Design Document (SDD)
  4. Code Generation
  5. Internal Review
  6. Test Plan Generation
  7. Code Review (4-Agent Matrix)
  8. CI Layer 1 — Unit Test
  9. CI Layer 2 — Cross-Compile + Static Analysis
  10. CI Layer 3 — System Verification + Evidence Pack

**GIVEN** a client sends `GET /api/demo/pipeline`  
**WHEN** the request is received  
**THEN** the server SHALL return HTTP 200  
**AND** the response body SHALL match the JSON schema above  
**AND** `pipeline_id` SHALL be unique per request  
**AND** `status` SHALL be `"completed"` when no `?step=` parameter is provided  
**AND** the response SHALL NOT make any LLM API calls

**GIVEN** a client sends `GET /api/demo/pipeline?step=3`  
**WHEN** the request is received  
**THEN** `current_step` SHALL be `3`  
**AND** `status` SHALL be `"running"`  
**AND** steps 0-2 SHALL have `status: "completed"`  
**AND** step 3 SHALL have `status: "running"`  
**AND** steps 4-9 SHALL have `status: "pending"`

---

### DEMO-REQ-003: Demo Pipeline 前置检查

- The server **SHALL** validate that the demo pipeline is ready before responding.
- If the demo pipeline enabler is configured (e.g., `YULEOSH_DEMO_ENABLED=true`), the endpoint **SHALL** function normally.
- If the demo pipeline is explicitly disabled, the endpoint **SHALL** return HTTP 503 with a descriptive message.
- By default (no env var), the endpoint **SHALL** be enabled.

**GIVEN** `YULEOSH_DEMO_ENABLED=false` is set  
**WHEN** a client sends `GET /api/demo/pipeline`  
**THEN** the server SHALL return HTTP 503  
**AND** the response body SHALL contain: `{"error": "demo_pipeline_disabled", "message": "Demo pipeline is disabled by administrator."}`

**GIVEN** `YULEOSH_DEMO_ENABLED=true` or no env var is set  
**WHEN** a client sends `GET /api/demo/pipeline`  
**THEN** the server SHALL return HTTP 200  
**AND** the demo pipeline SHALL execute normally

---

### DEMO-REQ-004: Demo 前端体验

- The `/demo` page **SHALL** display a pipeline progress UI.
- The progress UI **SHALL** show all 10 steps in order.
- For each step, the UI **SHALL** display:
  - Step name and icon
  - Status indicator (pending → running → completed/failed) with smooth animation
  - Duration display (for completed steps)
  - Expandable detail panel showing step-level output summary and artifacts
- The `/demo` page **SHALL** animate through steps sequentially with a configurable delay (default: 800ms per step).
- The `/demo` page **SHOULD** provide a "Skip to end" button to jump to the final report immediately.
- After all steps complete, the UI **SHALL** display:
  - Final report section with coverage prediction, review score, and compliance gates
  - A "Download Evidence Pack" button linking to `/api/demo/evidence/<pipeline_id>.zip`
  - A call-to-action banner: "Want to run this on your own code? → [Sign Up Free]"

**GIVEN** a user navigates to `/demo`  
**WHEN** the page loads  
**THEN** the page SHALL call `GET /api/demo/pipeline?step=0` or use SSE to start streaming  
**AND** step 0 `"Spec Parsing"` SHALL show "running" status with a spinner  
**AND** steps 1-9 SHALL show "pending" status with a dashed outline

**GIVEN** the demo pipeline completes in the frontend  
**WHEN** all 10 steps show "completed" status  
**THEN** the final report section SHALL be visible  
**AND** a "Download Evidence Pack" button SHALL be rendered  
**AND** a "Sign Up Free" CTA banner SHALL be visible below the report

---

### DEMO-REQ-005: Demo 速率限制

- The `GET /api/demo/pipeline` endpoint **SHALL** be rate-limited per client IP address.
- The default limit **SHALL** be 10 requests per minute per IP.
- When rate-limited, the server **SHALL** return HTTP 429 with a `Retry-After` header.

**GIVEN** a client IP has made 10 demo requests in the last 60 seconds  
**WHEN** the client sends the 11th `GET /api/demo/pipeline` request  
**THEN** the server SHALL return HTTP 429  
**AND** the response SHALL include `Retry-After: <seconds>` header

---

### DEMO-REQ-006: Demo Evidence Pack

- The server **SHALL** expose `GET /api/demo/evidence/<pipeline_id>.zip` to download a pre-seeded evidence pack ZIP.
- The ZIP **SHALL** contain mock versions of:
  - `traceability-matrix.csv` — 追溯矩阵
  - `acceptance-matrix.md` — 验收矩阵
  - `review-report.md` — 审查报告
  - `coverage-report.xml` — 覆盖率报告 (Cobertura 格式)
  - `compliance-checklist.md` — 合规检查清单
- The evidence pack **SHALL** be statically generated (no real pipeline traces needed).

**GIVEN** a client sends `GET /api/demo/evidence/demo-xxx.zip`  
**WHEN** the pipeline_id is valid (starts with `demo-`)  
**THEN** the server SHALL return a downloadable ZIP file  
**AND** the ZIP SHALL contain at least 5 files as specified above  
**AND** the ZIP SHALL NOT contain any real project data

---

### DEMO-REQ-007: 无注册体验

- The demo experience **SHALL** be fully functional without user registration or authentication.
- The `/demo` page **SHALL NOT** display login/register prompts until after the demo pipeline completes.
- The call-to-action after demo completion **SHOULD** link to a registration page.

**GIVEN** an unauthenticated user navigates to `/demo`  
**WHEN** the page loads  
**THEN** the demo pipeline SHALL run without asking the user to log in or register  
**AND** no authentication wall SHALL appear before the demo results are shown

---

### DEMO-REQ-008: Demo 日志

- The server **SHOULD** log anonymous demo usage statistics: timestamp, IP (masked last octet), user-agent, whether the demo completed or abandoned.
- These logs **SHALL NOT** contain personally identifiable information beyond masked IP.
- The system **MAY** use these logs for internal analytics only.

---

---

# 3. AI Preview Assessment (AI 预览评估)

## 3.1 概述

用户上传代码（ZIP 文件或 git repo URL），后端静态分析后返回报告：覆盖率预测、合规风险、推荐的 pipeline 配置。不跑硬件，5 分钟内出报告。API: `POST /api/preview/assess`。

---

## 3.2 需求定义

### PREVIEW-REQ-001: 接受上传方式

- The system **SHALL** accept two input modes via `POST /api/preview/assess`:
  1. **ZIP upload**: `multipart/form-data` with field `file` containing a `.zip` archive
  2. **Git repo URL**: `application/json` with field `repo_url` containing a `https://` git repository URL
- The system **SHALL** validate that exactly one input mode is provided; if both or neither are provided, the system **SHALL** return HTTP 400 with a descriptive error.
- For git repo URLs, the system **SHALL** support public GitHub, GitLab, and Bitbucket repositories.
- The system **SHALL** clone git repos to a temporary directory and clean up after analysis.

**GIVEN** a client sends `POST /api/preview/assess` with `Content-Type: multipart/form-data` containing a valid `.zip` file  
**WHEN** the request is received  
**THEN** the server SHALL return HTTP 202 Accepted  
**AND** the response SHALL include `{"preview_id": "<uuid>", "status": "analyzing", "estimated_seconds": <int>}`

**GIVEN** a client sends `POST /api/preview/assess` with `Content-Type: application/json` and body `{"repo_url": "https://github.com/user/project"}`  
**WHEN** the request is received  
**THEN** the server SHALL clone the repository  
**AND** SHALL return HTTP 202 Accepted  
**AND** the response SHALL include `{"preview_id": "<uuid>", "status": "analyzing", "estimated_seconds": <int>}`

**GIVEN** a client sends `POST /api/preview/assess` with `Content-Type: application/json` and body `{}`  
**WHEN** no `file` and no `repo_url` are provided  
**THEN** the server SHALL return HTTP 400  
**AND** the response SHALL include `{"error": "input_required", "message": "Provide either 'file' (ZIP upload) or 'repo_url' (git URL)."}`

---

### PREVIEW-REQ-002: 输入验证与限制

- ZIP uploads **SHALL** be limited to a maximum file size of 50 MB.
- ZIP uploads **SHALL** be validated as a valid ZIP archive before extraction; invalid archives **SHALL** return HTTP 400.
- For git repo URLs, the system **SHALL** enforce a clone timeout of 120 seconds; exceeding this **SHALL** return HTTP 408.
- For git repo URLs, the system **SHALL** limit the total cloned size to 200 MB; repositories exceeding this **SHALL** be rejected with HTTP 413.
- The extracted source code **SHALL** be scanned for supported file extensions only: `.c`, `.h`, `.py`, `.yaml`, `.yml`, `.md`, `.cfg`, `.cmake`, `.txt`, `.arxml`, `.dts`, `.ld`.
- Non-matching files **SHALL** be silently ignored (not counted as errors).

**GIVEN** a client uploads a 60 MB ZIP file  
**WHEN** the server receives the request  
**THEN** the server SHALL reject with HTTP 413  
**AND** the response SHALL include `{"error": "file_too_large", "max_size_mb": 50}`

**GIVEN** a client uploads a file that is not a valid ZIP archive  
**WHEN** the server attempts to extract it  
**THEN** the server SHALL return HTTP 400  
**AND** the response SHALL include `{"error": "invalid_archive", "message": "Uploaded file is not a valid ZIP archive."}`

**GIVEN** a client provides an unsupported git host URL (e.g., `https://my-private-git.company.com/repo`)  
**WHEN** the server processes the URL  
**THEN** the server SHALL return HTTP 400  
**AND** the response SHALL include `{"error": "unsupported_git_host", "supported_hosts": ["github.com", "gitlab.com", "bitbucket.org"]}`

---

### PREVIEW-REQ-003: 分析结果轮询

- After the initial `POST /api/preview/assess` returns HTTP 202, the system **SHALL** provide a `GET /api/preview/assess/<preview_id>` endpoint for status polling.
- The polling endpoint **SHALL** return:
  - `status: "analyzing"` — analysis in progress (estimated_seconds remaining)
  - `status: "completed"` — analysis finished, report included
  - `status: "failed"` — analysis encountered an error
- The analysis **SHALL** complete within 300 seconds (5 minutes) for inputs up to 50 MB ZIP / 200 MB cloned repo.

**GIVEN** a client has received `preview_id` from a POST request  
**WHEN** the client polls `GET /api/preview/assess/<preview_id>`  
**THEN** if analysis is still running, the response SHALL be `{"status": "analyzing", "estimated_remaining_seconds": <int>}`  
**AND** if analysis is complete, the response SHALL include the full assessment report under `"report"`

**GIVEN** a valid input of 10 MB ZIP with typical embedded C code  
**WHEN** analysis is triggered  
**THEN** the system SHALL complete analysis within 300 seconds  
**AND** the system SHALL NOT execute, compile, or flash any code on hardware

---

### PREVIEW-REQ-004: 分析报告内容

The assessment report **SHALL** contain the following sections:

#### 3.2.4.1 覆盖率预测 (Coverage Prediction)

- The coverage prediction **SHALL** estimate line coverage based on:
  - Detected test framework (Unity, CMock, Google Test, pytest, none)
  - Test file density (ratio of test files to source files)
  - Function call graph analysis (static reachability)
  - Historical model: `coverage_estimate = f(test_density, code_complexity, test_maturity)`
- The prediction **SHALL** be expressed as:
  - `current_coverage_estimate` — estimated current line coverage percentage (0-100)
  - `projected_coverage_after_yuleosh` — projected coverage after running yuleOSH test generation (0-100)
  - `confidence` — low / medium / high
  - `bottleneck_files` — top 5 files with the lowest estimated coverage

**GIVEN** an uploaded project contains 2 test files and 20 source files (test_density 0.10)  
**WHEN** coverage prediction runs  
**THEN** the report SHALL include `current_coverage_estimate`  
**AND** SHALL include `projected_coverage_after_yuleosh`  
**AND** SHALL include a `confidence` rating  
**AND** SHALL list at most 5 `bottleneck_files`

#### 3.2.4.2 合规风险 (Compliance Risk)

- The compliance risk assessment **SHALL** analyze:
  - **MISRA-C violations detected** (via pattern matching on known MISRA violation patterns; not a full MISRA checker)
  - **Coding standard adherence** (detection of naming conventions, comment density, function length violations)
  - **ASPIRE compliance readiness** (evidence maturity: are there any spec files, trace matrices, test reports already?)
  - **Safety-critical risk factors**:
    - Lack of assertions / defensive programming
    - Unbounded loops detected (static limit analysis)
    - Recursion detected (not recommended for safety-critical embedded)
    - Dynamic memory allocation detected (malloc/free in embedded C)
- Each risk factor **SHALL** include:
  - `risk_level`: `critical` / `high` / `medium` / `low` / `none`
  - `description`: human-readable explanation
  - `occurrences`: count of findings (where applicable)
  - `recommendation`: actionable mitigation suggestion

**GIVEN** an uploaded embedded C project contains `malloc()` calls and an unbounded `while(1)` loop  
**WHEN** compliance risk analysis runs  
**THEN** the report SHALL flag dynamic memory allocation with risk level ≥ `medium`  
**AND** SHALL flag unbounded loop detection  
**AND** SHALL include occurrence counts and recommendations for each finding

#### 3.2.4.3 推荐的 Pipeline 配置 (Recommended Pipeline Config)

- The system **SHALL** generate a recommended pipeline configuration YAML snippet based on:
  - Detected framework (FreeRTOS detected → add FreeRTOS analysis steps)
  - Detected platform (STM32 detected → add OpenOCD flash step; ARM → add JLink)
  - Complexity level (high complexity → add additional review gate)
  - Safety relevance (recursion/dynamic memory → force MISRA check + static analysis)
- The recommendation **SHALL** include:
  - `recommended_template` — suggested template name from Template Gallery (if match found)
  - `steps` — ordered list of recommended pipeline steps with rationale
  - `ci_layers` — recommended CI configuration
  - `review_gates` — recommended review gates
  - `yaml_snippet` — a ready-to-use YAML snippet that the user can copy into their pipeline config

**GIVEN** an uploaded project contains FreeRTOS headers (`FreeRTOS.h`, `task.h`) and targets STM32  
**WHEN** pipeline config recommendation runs  
**THEN** the report SHALL recommend template `freertos-misra` or `stm32-hal`  
**AND** SHALL include OpenOCD flash/debug steps in ci_layers  
**AND** SHALL include MISRA static analysis in the review gates  
**AND** SHALL provide a copyable YAML snippet

---

### PREVIEW-REQ-005: 匿名使用与限制

- The preview assessment **SHALL** be available without authentication, but with stricter rate limits.
- Unauthenticated users **SHALL** be limited to 3 preview assessments per 24 hours per IP address.
- Authenticated users (with valid API key or session) **SHALL** have a limit of 20 preview assessments per 24 hours.
- Rate limit exceeded **SHALL** return HTTP 429 with a `Retry-After` header.

**GIVEN** an unauthenticated IP has submitted 3 preview assessments in the last 24 hours  
**WHEN** the 4th request arrives  
**THEN** the server SHALL return HTTP 429  
**AND** the response SHALL include `{"error": "rate_limited", "message": "Preview assessment limit reached. Sign up for more."}`

---

### PREVIEW-REQ-006: 分析结果保留

- Preview assessment results **SHOULD** be retained for 24 hours, after which they **MAY** be deleted.
- The system **SHOULD** provide a `DELETE /api/preview/assess/<preview_id>` endpoint for the client to explicitly discard their result (advisory; the backend **MAY** still retain for operational purposes).

**GIVEN** a preview assessment is completed  
**WHEN** 24 hours have passed  
**THEN** the system MAY delete the analysis results  
**AND** `GET /api/preview/assess/<preview_id>` MAY return HTTP 404

---

### PREVIEW-REQ-007: 结果缓存

- The system **MAY** cache assessment results by git repo URL hash to serve repeated requests faster. If a cached result exists and was generated within the last 24 hours, the system **MAY** return it immediately (status: "completed") instead of re-analyzing.

**GIVEN** a client submits `POST /api/preview/assess` with `repo_url: "https://github.com/user/project"`  
**WHEN** an analysis result for the same repo exists from within the last 24 hours  
**THEN** the system MAY return HTTP 200 immediately with the cached report  
**AND** the response SHALL include `"cached": true`

---

### PREVIEW-REQ-008: Git repo 临时清理

- Temporarily cloned repositories **SHALL** be cleaned up within 30 minutes of analysis completion, regardless of whether the result was polled.
- The system **SHALL** use OS-level temp directories (e.g., `/tmp/yuleosh_preview_*`).

**GIVEN** a preview assessment for a git repo completes at T=0  
**WHEN** the time is T+31 minutes  
**THEN** the cloned repository SHALL be deleted from the filesystem  
**AND** no source code SHALL persist on disk beyond 30 minutes

---

---

# 附录A: 验收矩阵

## A.1 Template Gallery 验收判定

| ID | 需求 | 验收标准 | 优先级 | 自动测试 | 手动验证 |
|:---|:-----|:---------|:------:|:--------:|:--------:|
| TG-REQ-001 | 模板存储结构 | `templates/` 下有 ≥5 个模板，各有 template.yaml/specs/spec.md/pipeline/config.yaml/src/ | P0 | ✅ | — |
| TG-REQ-002 | 模板搜索优先级 | 三种搜索路径按序匹配，user-local 覆写 built-in | P0 | ✅ | — |
| TG-REQ-003A | CLI init 成功路径 | `project init --template` 创建完整项目结构 | P0 | ✅ | — |
| TG-REQ-003B | CLI init 模板不存在 | 不存在的模板返回非零退出码 + 错误信息 | P0 | ✅ | — |
| TG-REQ-003C | CLI init 交互模式 | 无 `--template` 时展示交互式选择列表 | P1 | ✅ | — |
| TG-REQ-004 | template list | `template list` 输出格式化表格 | P1 | ✅ | — |
| TG-REQ-005 | 模板生成内容完整性 | spec/pipeline/src 各有模板相关内容 | P0 | ✅ | ✅ |
| TG-REQ-006A | 不覆盖已有文件 | 非 `--force` 跳过已有文件 | P0 | ✅ | — |
| TG-REQ-006B | --force 覆盖流程 | `--force` 需用户确认后再覆写 | P1 | ✅ | ✅ |

## A.2 SaaS Try-it Demo 验收判定

| ID | 需求 | 验收标准 | 优先级 | 自动测试 | 手动验证 |
|:---|:-----|:---------|:------:|:--------:|:--------:|
| DEMO-REQ-001A | Hero 区按钮 | Landing page 有 ≥48px "Try Demo" 按钮 | P0 | ✅ | ✅ |
| DEMO-REQ-001B | 导航栏按钮 | 768px+ 屏幕有第二个 "Try Demo" 按钮 | P1 | — | ✅ |
| DEMO-REQ-002A | API 返回格式 | `GET /api/demo/pipeline` 返回符合 schema 的 JSON | P0 | ✅ | — |
| DEMO-REQ-002B | 无 LLM 调用 | API 响应过程中不调用任何 LLM | P0 | ✅ | — |
| DEMO-REQ-002C | step 参数 | `?step=N` 返回正确的 partial 状态 | P1 | ✅ | — |
| DEMO-REQ-003 | 前置检查 | `YULEOSH_DEMO_ENABLED=false` 返回 503 | P0 | ✅ | — |
| DEMO-REQ-004A | 前端进度 UI | 10 步有状态动画，可展开详情 | P0 | — | ✅ |
| DEMO-REQ-004B | 最终报告 + CTA | 完成后显示报告、下载证据包、注册引导 | P0 | — | ✅ |
| DEMO-REQ-005 | 速率限制 | 10 req/min/IP，超出返回 429 | P1 | ✅ | — |
| DEMO-REQ-006 | 证据包下载 | ZIP 包含 5 个 mock 文件 | P1 | ✅ | — |
| DEMO-REQ-007 | 无注册体验 | 全程无需登录，完成后引导注册 | P0 | — | ✅ |

## A.3 AI Preview Assessment 验收判定

| ID | 需求 | 验收标准 | 优先级 | 自动测试 | 手动验证 |
|:---|:-----|:---------|:------:|:--------:|:--------:|
| PREVIEW-REQ-001A | ZIP 上传 | `multipart/form-data` ZIP → 202 + preview_id | P0 | ✅ | — |
| PREVIEW-REQ-001B | Git URL 上传 | JSON body repo_url → 202 + preview_id | P0 | ✅ | — |
| PREVIEW-REQ-001C | 输入缺失 | 同时无 file 和 repo_url → 400 | P0 | ✅ | — |
| PREVIEW-REQ-002A | 文件大小限制 | >50MB → 413 | P1 | ✅ | — |
| PREVIEW-REQ-002B | 无效 ZIP | 非 ZIP 文件 → 400 | P1 | ✅ | — |
| PREVIEW-REQ-002C | 不支持的 Git 主机 | 非 github/gitlab/bitbucket → 400 | P1 | ✅ | — |
| PREVIEW-REQ-003A | 状态轮询 | `GET /api/preview/assess/<id>` 返回 analyzing/completed/failed | P0 | ✅ | — |
| PREVIEW-REQ-003B | 5 分钟时限 | 50MB/200MB 以下输入 300s 内完成 | P0 | ✅ | — |
| PREVIEW-REQ-003C | 不跑硬件 | 分析过程中不执行/编译/刷写任何代码 | P0 | — | ✅ |
| PREVIEW-REQ-004A | 覆盖率预测 | 报告含 current_coverage_estimate + projected 等字段 | P0 | ✅ | — |
| PREVIEW-REQ-004B | 合规风险 | 报告含 risk_level/description/occurrences/recommendation | P0 | ✅ | — |
| PREVIEW-REQ-004C | 推荐 Pipeline 配置 | 报告含 recommended_template + steps + YAML snippet | P0 | ✅ | — |
| PREVIEW-REQ-005A | 未认证限流 | 3次/24h/IP，超出返回 429 | P1 | ✅ | — |
| PREVIEW-REQ-005B | 已认证限流 | 20次/24h，超出返回 429 | P2 | ✅ | — |
| PREVIEW-REQ-006 | 结果保留 24h | 24h 后可返回 404 | P2 | ✅ | — |
| PREVIEW-REQ-008 | Git temp 清理 | 30 分钟内清理克隆仓库 | P1 | ✅ | — |

---

> **验收判定矩阵说明**: P0 = 必须通过（阻塞发布）；P1 = 建议通过；P2 = 可以延期。
> 自动化测试优先用 pytest + httpx（对 API 层）和 Playwright（对前端 Demo 页）。
