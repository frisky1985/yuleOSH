# Sprint Contract: yuleOSH CI 优化 — 方案 A（路径分流）+ 吸收 B/C 优势

## Scope
- What: 优化 yuleOSH GitHub Actions CI 流水线
  - **A（主）**: 路径分流 — 按改动路径只跑相关 job，减少无关 CI 消耗
  - **B（吸收）**: 分层门禁 — 明确 PR 快速层 / main 全量层，软门禁状态显式声明
  - **C（吸收）**: 发布流水线 — 新增 tag 触发 release.yml，复用 desktop-build 产物
- In Scope: `.github/workflows/` 下 ci.yml / codeql.yml / desktop-build.yml 改造 + 新增 release.yml；workflow 语法验证；推送后 CI 真跑观察
- Out of Scope: 不改产品代码；不升覆盖率阈值；不动 nightly-compose / honesty-gate（已按需触发）

## 现状约束（必须先确认）
- test job `needs: frontend-build` 且依赖 frontend/out/ 静态产物（不入库）→ **任何跑 test 的路径都需先构建 frontend**
- 软门禁现状：actionlint/ruff/bandit/mypy 均 continue-on-error；npm audit 软
- desktop-build.yml 已有 paths 过滤（desktop/**, frontend/**）
- codeql.yml push + PR + weekly 全量跑（成本高）

## Architecture Decision
- architect-lead: 小明 (Hermes)
- 路径检测: `dorny/paths-filter@v3`（社区标准，detect job 输出变更集，下游 job 按需执行）
- 分层模型:
  - **PR 层（快速）**: lint / plan-lint / test（忽略 e2e）/ 路径相关构建
  - **main 层（全量）**: PR 层 + 覆盖率门禁 + evidence/RTM + 软门禁严格模式
  - **Nightly 层（已有）**: honesty-gate / nightly-compose（不动）
- 发布: 新增 release.yml（tag `v*` 触发），复用 frontend-build + 三平台 electron-builder，softprops/action-gh-release 上传产物

## Testable Behaviors
### Workflow 结构
- [ ] B1: ci.yml 增加 detect job（paths-filter），输出 `src/frontend/desktop/docs/workflow` 变更标记
- [ ] B2: test job 在 src 或 frontend 或 workflow 变更时执行；纯 docs/desktop 变更跳过 test
- [ ] B3: code-quality 在 src 变更时执行
- [ ] B4: cve-scan 在 src/desktop/frontend 变更时执行
- [ ] B5: evidence 在 src 变更时执行（main 分支强制）
- [ ] B6: codeql.yml 增加 paths 过滤（src 相关 + weekly 不受影响）
- [ ] B7: release.yml 存在且 tag v* 触发，构建三平台并上传 GitHub Release

### 门禁强度
- [ ] B8: PR 分支：软门禁保持 continue-on-error（不挡 PR）
- [ ] B9: main 分支：软门禁跑严格模式（`ruff check` 无 `|| echo` 兜底），红则挡
- [ ] B10: 所有 workflow YAML 通过 yaml.safe_load 解析 + actionlint 无 error

> ⚠️ **2026-08-11 证据修正（Evaluator 发现）**：软门禁当前全红——ruff 4232 errors、bandit 392 High、mypy 未安装。
> 原 B9"main 严格模式红则挡"**不可行**（main 会立即全红）。B 吸收调整为**渐进式**：
> - 分层结构就位：PR 快速层 / main 全量层 / nightly 深度层（显式矩阵）
> - 软门禁在 main 上**仍保持软**（continue-on-error），但新增独立 job `quality-report`：main 分支跑严格模式并上传报告（不挡 merge）
> - 代码库达标后逐个把软门禁升级为硬门禁（矩阵标注升级路径）

### 行为验证
- [ ] B11: 本地 yaml 解析全部通过
- [ ] B12: 推送后 CI 真跑观察：docs-only 改动不触发 test；src 改动触发全链路
- [ ] B13: 未改动 nightly-compose / honesty-gate 触发条件

## Acceptance Criteria
| ID | Criterion | Pass Condition | Fail Condition | Priority | Owner |
|----|-----------|----------------|----------------|----------|-------|
| AC1 | 路径分流生效 | docs-only push 不跑 test job；src push 全链路 | 所有 push 仍全量跑 | P0 | 小明 |
| AC2 | 分层门禁 | main 分支 ruff/bandit/mypy 严格模式可执行 | 软门禁全部仍 continue-on-error 无分层 | P0 | 小明 |
| AC3 | 发布流水线 | release.yml 存在、语法合法、tag 触发配置正确 | 缺失或语法错误 | P1 | 小明 |
| AC4 | YAML 合法 | 5+1 个 workflow 全部 yaml.safe_load 通过 | 任一解析失败 | P0 | 小明 |
| AC5 | CI 真跑 | 推送后观察 1 轮：无新增红、路径过滤生效 | 新引入红/路径过滤失效 | P0 | 小明 |

## Responsibility Matrix
| Criterion | Responsible | Fallback |
|-----------|-------------|----------|
| 设计 detect 路径集 | 小明 | — |
| ci.yml 改造 | 小明 | — |
| codeql.yml 过滤 | 小明 | — |
| release.yml 新建 | 小明 | — |
| YAML 验证 + 真跑观察 | 小明（Evaluator 角色） | — |

## Negotiation Log
| Round | Party | Action | Notes |
|-------|-------|--------|-------|
| 1 | 老板 | 拍板 | 方案 A 先推进，吸收 B/C 优势（2026-08-11） |
