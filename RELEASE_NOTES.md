# yuleOSH v3.12.1 — 工具链打通 + CI 门禁复活发布

> **发布日期**: 2026-08-05
> **版本**: v3.12.1
> **上一个发布 tag**: v3.9.1 (2026-08-04)
> **版本跨度**: v3.10.0 → v3.10.1 → v3.11.0 → v3.12.0 → v3.12.1

---

## 🎯 本版核心

从 v3.9.1 到 v3.12.1 共 **43 个 commit**，主线：**CI 门禁复活 + 方法论平台化 + yuleDKCS 混合语言工具链打通**。

---

## 🚀 v3.12.1 — yuleDKCS 混合语言支持 + MISRA 工具链打通

### CI 混合语言支持（yuleOSH-check 5c4721a / d9355d3f）
- **config/yaml_validator/layer_config/layer_executor**: Go/Python 项目也能跑嵌入式 C MISRA；`project_language: mixed` 配置覆盖自动检测；Go monorepo 多模块 build/vet/test
- **review.py 关键 3 修**: cppcheck 相对路径 `-I`（绝对路径 .h 违规不匹配 baseline 根因）；exclude normpath（`./` 前缀致 exclude 失效）；scan_dirs 驱动文件发现
- **misra_report parser**: 跳过 information 级（checkersReport/unmatchedSuppression 等非违规误报）
- **layer_executor e2e**: pytest exit 5（no tests collected）→ skip 而非 fail（Go-only e2e 目录）
- **yuleDKCS 实测**: MISRA C:2023 **690 → 0 违规**（57 文件），三层 CI 全绿

### 集成测试环境探测（yuleDKCS）
- scenarios 12 测试 + security 3 测试加环境探测 skip：carsim/gateway 不可达时 SKIP 不 block CI

### 产物治理（yuleDKCS）
- gitignore carsim 二进制 / `.osh/` 运行产物 / `*.dump`（cppcheck 中间产物）

---

## ✨ v3.12.0 — 方法论平台化 + Pipeline 修复

### L3 方法论宿主平台化
- **L3-B 独立门禁引擎**: standalone 零依赖 + 一致性测试
- 一键挂载（yuleASR 试点成功）+ 独立门禁 CLI
- 模板 `.yuleosh/agents` 被根 .gitignore 忽略未入库修复

### Pipeline 修复
- **qemu-run** `timed_step self` 丢失 + c-coverage-gate project_dir 层级错误
- **spec THEN 误捕修复**: 场景内 SHALL 行不再被当独立需求
- **mock 全链 33 步 completed errors=0**: gate 阻断语义 + 11 review 步骤 mock 跳过；6 个 code-quality gate 一致跳过

---

## 🛡️ v3.11.0 — 方法论契约门禁

- **L2 Methodology Gate 可执行化**: 非方法论项目自动跳过 + 测试去 sys.path.insert
- Semgrep SARIF upload 无文件时报错修复（hashFiles 条件跳过）

---

## 🧠 v3.10.x — 方法论约束层 + 真实 LLM 集成

### v3.10.1
- **L1 方法论约束层**: 融合 mattpocock 工程方法论进 agent 行为

### v3.10.0 Track0/Track1
- **真实 LLM 集成修复**: pipeline 端到端验证第一批（此前 CI 门禁死亡 ≥11 天被修复）
- **CI 门禁复活**: ci.yml YAML 缩进错误修复（fd76c96e 引入）、Python 3.10/3.11 f-string 兼容（PEP 701）、tomllib→tomli fallback、code-quality 移除冗余 coverage 全量测试（CI 卡死根因）、恢复 cve-scan pip-audit 安装、lint kind + cppcheck 补装
- **测试跨版本修复**: B 类 10 个失败拆解 3 根因组（api_preview/review_selftest、status_pipeline mock 精准化、cross/evidence 注入挂包对象属性）
- **依赖声明补全**: openpyxl>=3.1.0、pytest-asyncio>=0.23
- **技能库**: 导入 mattpocock 41 技能 + 项目管理 SOP

---

## ✅ 质量状态

| 指标 | 值 |
|:-----|:---|
| 全量测试 (v3.9.0 基线) | 10017 passed / 0 failed，cov 84.17% |
| v3.12.1 针对性回归 | 797 passed / 0 failed (CI/MISRA/层/pipeline 全组) |
| yuleDKCS 三层 CI | L1 MISRA 0 违规 + go 7 模块 / L2 cppcheck / L3 evidence 全绿 |
| 认证 | 复验 9.5/10 (v3.9.1)，v3.10+ 持续 |

---

## 📦 安装

```bash
pip install -e .        # 开发安装（editable）
# 或从源码:
pip install .
```

**注意**: 版本号已从 3.4.4 同步至 3.12.1（pyproject.toml + `__version__`）。
