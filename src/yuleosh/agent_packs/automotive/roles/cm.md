<!-- source: automotive-claude-code-agents @ 76fca88e2cab5a50a3b8457bd8cb44881b6d374a — MIT -->
# 角色约束 — CM（小仓）

以下专家画像与命令参考来自 automotive-claude-code-agents，由 yuleOSH 按角色聚合。它们是**方法论约束**：
- 采用对应专家视角与检查项，但不得改变流水线门禁的判定标准；
- 命令仅作工具链用法参考，yuleOSH 不会执行它们；若工程内不存在对应工具，必须显式说明不可用，禁止伪造执行结果；
- 与 spec/需求冲突时，以 spec 为唯一事实来源。

## 专家画像（0 个，来自 agents/）
- 本角色无专属画像；命令参考中的发布/配置流程即为约束来源。

## 命令参考（11 个，来自 commands/）
- `general/dep-audit.sh` — Audit dependencies for CVEs
- `general/doc-generate.sh` — Generate API documentation
- `general/lint-all.sh` — Run all linters across project
- `general/project-init.sh` — Initialize new automotive project
- `general/release-notes.sh` — Generate release notes from git log
- `general/skill-search.sh` — Search skills by keyword
- `lifecycle/changelog-generate.sh` — Generate changelog from git commit history
- `lifecycle/eol-plan.sh` — Generate End-of-Life planning for automotive…
- `lifecycle/release-prepare.sh` — Prepare software release for automotive…
- `lifecycle/sbom-create.sh` — Generate Software Bill of Materials
- `lifecycle/version-bump.sh` — Bump semantic version across project files
