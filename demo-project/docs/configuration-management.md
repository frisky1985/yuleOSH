# 配置管理计划（SUP.8）

- 生成时间：2026-11-10T15:31:23+00:00
- 配置项数量：61
- 清单摘要（manifest_sha256）：`72ae29bfd041faa0af6055204cd16acfc8cd8c23df0798f75925341fb9a6a483`

## 配置项识别

- `.gitignore`
- `.yuleosh/knowledge_graph.db`
- `.yuleosh/reports/codegen-deploy.json`
- `.yuleosh/store.db`
- `README.md`
- `ci-config.yaml`
- `data/audit/2026-11-10.jsonl`
- `docs/change-request-register.yaml`
- `docs/change-requests.md`
- `docs/configuration-items.yaml`
- `docs/configuration-management.md`
- `docs/hw-design.md`
- `docs/hw-implementation-report.md`
- `docs/hw-item-register.yaml`
- `docs/hw-requirements.md`
- `docs/hw-verification-report.md`
- `docs/issue-register.yaml`
- `docs/known-issues.md`
- `docs/measurement-plan.md`
- `docs/measurement-report.md`
- ……共 61 个配置项（完整清单见 `baselines/pipeline-baseline.json`）

## 基线

- 基线清单：`baselines/pipeline-baseline.json`（逐项 SHA256 + 清单摘要）。
- 基线一经批准不得原地修改；变更须走 `docs/change-requests.md`（SUP.10）。

## 变更控制

- 配置项变更须经变更请求评审与批准后实施。
- 待人工确认：基线批准人、批准日期与版本标识。

## 数据来源

- `walk:project`（排除 .osh, .git, .venv, node_modules, __pycache__, .pytest_cache, dist, build-venv, baselines）
