# 方法论宿主平台化（L3）— 接入指南

> yuleOSH v3.12.0 · L3 方法论宿主平台化
> 前置: L1 行为约束层（v3.10.1）+ L2 可执行门禁（v3.11.0）

## 1. 是什么

yuleOSH 的方法论资产（L1 行为约束四件套 + L2 六维门禁 + CONTEXT 统一语言）从仓库内部
抽成了**可复用宿主包**。任何项目——不限于 yuleOSH 自己的仓库——都可以一键挂载这套
方法论，并在自己的 CI 中独立运行方法论门禁。

```
方法论宿主包 (src/yuleosh/templates/methodology/)
├── .yuleosh/agents/
│   ├── AGENTS.md       # 角色定义（小明/小克/小马 三人小队）
│   ├── METHODOLOGY.md  # L1 六契约（grilling/domain-model/two-axis/tight-loop/slices/handoff）
│   ├── RULES.md        # 零容忍规则（P0/P1 不跨阶段 / Loop Chain / 上下文阈值）
│   └── HOOKS.md        # 触发钩子（Task-Init / CI Failure / Review Required）
├── CONTEXT.md          # 统一语言模板（{{PROJECT_NAME}} 占位符）
├── ci-config.methodology.yaml  # L2 门禁最小配置片段
└── template.yaml       # 模板清单（可被 yuleosh template list 发现）
```

## 2. 快速接入（2 分钟）

### 2.1 挂载

```bash
# 在目标项目根目录（yuleDKCS / yuleASR / 任意新项目）
cd /path/to/your-project
yuleosh methodology init .
```

生成:
- `.yuleosh/agents/` 四件套（AGENTS / METHODOLOGY / RULES / HOOKS）
- `CONTEXT.md`（统一语言模板，含 `{{PROJECT_NAME}}` 已替换为项目名）
- `.yuleosh/ci-config.yaml`（门禁最小配置，若已存在则跳过，需手动合并 methodology 段）

**幂等安全**: 二次运行不覆盖已有文件（除非 `--force`）。用户编辑过的 CONTEXT.md 不会被冲掉。

### 2.2 验证门禁

```bash
yuleosh methodology check .
# ✅ 六维检查跑完，hard 违反 → exit 1（阻断），soft 违反 → warning（不阻断）
```

- 非方法论项目（无 spec/CONTEXT/.yuleosh 标记）→ 自动跳过，exit 0，不误伤。
- CI 管道友好: `--json` 输出 stdout 只含 JSON（人类日志走 stderr）：

```bash
yuleosh methodology check . --json | jq '.passed'
```

### 2.3 接入 CI

在目标项目的 CI workflow 中加一步（GitHub Actions 示例）:

```yaml
- name: Methodology Gate (L2)
  run: pip install yuleosh && yuleosh methodology check .
  continue-on-error: false   # hard 违反阻断合并
```

或在 yuleOSH 自己的 Layer 1 中（layer_executor 已内置 `methodology-gate` stage）。

## 3. 挂载后要做什么

1. **填 CONTEXT.md**: 把模板里的示例术语替换成项目真实领域术语（统一语言）。
2. **写 spec 带决策记录**: 门禁 §1 要求 spec 含 `决策记录`/`Grilling` 痕迹。
   ```markdown
   ## 9. 决策记录（Grilling/对齐沉淀）
   - **决策（X-1）**: 采用 A 方案。
   ```
3. **评审走双轴**: 正式评审报告分 `## Standards` 与 `## Spec` 两节。
4. **修复先建回路**: RCA/调试报告含 `复现步骤`/`red-capable` 证据。

## 4. 命令参考

| 命令 | 作用 | 退出码 |
|:-----|:-----|:------:|
| `yuleosh methodology init [dir]` | 挂载宿主包（幂等） | 0 |
| `yuleosh methodology init [dir] --force` | 强制覆盖已有文件 | 0 |
| `yuleosh methodology check [dir]` | 运行六维门禁 | 0=过/跳, 1=hard 违反 |
| `yuleosh methodology check [dir] --json` | JSON 输出（stdout 纯 JSON） | 同上 |

## 5. 实现架构

- 模板: `src/yuleosh/templates/methodology/`（与 unit-test-harness / stm32-hal 并列，`template list` 可发现）
- CLI: `src/yuleosh/cli/commands/methodology.py`（A5 拆分风格，不 import cli.main 避免循环）
- 门禁复用: `yuleosh methodology check` 直接调 `src/yuleosh/ci/stages/methodology_gate.py::run_methodology_gate`
  （L2 引擎与 L3 CLI 同源，单一实现不重复）
- 注册: `cli/main.py` `_build_parser()` 内 `_build_methodology(sub)` + dispatch 分支

## 6. 验收清单

- [ ] `yuleosh methodology init` 生成 6 个文件（4 agents + CONTEXT + ci-config）
- [ ] 二次 init 幂等（不覆盖用户编辑）
- [ ] check 在挂载项目: 全绿 exit 0 / 缺 spec exit 1 / 非方法论项目 skip exit 0
- [ ] `--json` stdout 可被 `json.loads` 消费
- [ ] 模板可被 `yuleosh template list` 发现
- [ ] 全量回归无新增失败
