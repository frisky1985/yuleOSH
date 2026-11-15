---
name: "feature-delivery-flow"
description: "End-to-end delivery loop for yuleOSH desktop features: implement, add backend+frontend tests, verify locally, commit, push feature branch, then cherry-pick to main. Invoke when the user asks to build a desktop feature and ship it, or says '实现并推送 / 提交并合到 main'."
---

# yuleOSH 功能交付闭环

把「实现 → 测试 → 验证 → 提交 → 推送 → 合入 main」固化成一条可重复的流程。
合并环节复用 `.trae/skills/cherry-pick-to-main/`，本 Skill 负责它之前与之后的步骤。

## 适用场景

- 用户提出一个桌面端功能需求，并期望最终落地到远程仓库与 `main`
- 用户说「继续开发其他功能」「提交吧」「推送到远程仓库」「cherry-pick 到 main」
- 已实现的功能需要补测试、补验证后再交付

## 项目上下文

| 项 | 位置 / 约定 |
|---|---|
| 前端 | `frontend/src`，Next.js 16 + React 19 + Tailwind v4，静态导出到 `frontend/out` |
| 后端 | `src/yuleosh`，FastAPI；桌面接口在 `src/yuleosh/api/desktop.py` |
| 桌面壳 | `desktop/`（Electron） |
| 后端测试 | `tests/test_desktop_api.py`、`tests/test_desktop_workspace.py` |
| 前端测试 | `frontend/src/__tests__/*.test.tsx`（jest + RTL） |
| UI 约定 | 深色主题、中文文案、复用 `components/account` 下现有弹窗组件 |
| 分支 | 功能分支 `trae/agent-Gm1m13`，主分支 `main` |

## 执行步骤

### 1. 实现（最小改动）

```bash
# 先定位既有实现与可复用组件，避免重复造轮子
grep -rn "<相关中文文案>" frontend/src src/yuleosh
```

- 优先复用现有弹窗 / 接口 / 工具函数；新依赖需有明确理由。
- 前端数据源优先本地占位或已有接口，不为小功能大改后端。
- 状态持久化写桌面工作区 `settings.json` 时注意权限 0600、敏感值掩码返回。

### 2. 补单元测试

- 后端：在 `tests/test_desktop_api.py` 加测试类，用 `TestClient`，覆盖成功路径 + 校验失败 + 持久化/重启恢复。
- 前端：在 `frontend/src/__tests__/` 加组件测试，覆盖加载回填、提交载荷、失败提示、禁用态、关闭行为；mock `fetch`。

```bash
python3 -m pytest tests/test_desktop_api.py -q -o addopts="" -k "<关键字>" -p no:cacheprovider
cd frontend && npx jest src/__tests__/<file>.test.tsx --silent
```

### 3. 本地验证（全绿才进入提交）

```bash
python3 -m pytest tests/test_desktop_api.py tests/test_desktop_workspace.py -q -o addopts=""
cd frontend
npx tsc --noEmit
npx jest --silent
npm run build          # 静态导出，应输出 28 页
npx eslint src/...     # 只查本次改动文件，存量问题不顺手改
```

UI 改动需实际渲染确认（起本地服务 + 截图），滚动条等细节注意 Playwright 默认
`--hide-scrollbars` 会掩盖问题，需 `ignoreDefaultArgs: ["--hide-scrollbars"]`。

沙箱干扰处置：
- `next build` 报 `[safe-delete]` → 加 `CODEBUDDY_SAFE_DELETE_ENABLED=0`
- pytest basetemp 权限 → 加 `--basetemp=/tmp/xxx --no-cov -p no:cacheprovider`

### 4. 提交（仅用户要求时）

```bash
git add <源码> <测试>              # 不要 add -A，避免带入 .uploads / 截图
git commit -m "feat: <中文摘要>"
```

- 提交信息用 Conventional Commits + 中文摘要。
- 临时产物（验证截图、日志、构建目录）不进入功能提交；已提交的可后续 cherry-pick 时剔除。
- 未经用户要求不 `push`。

### 5. 推送功能分支

```bash
git push origin HEAD
git ls-remote origin refs/heads/trae/agent-Gm1m13
git rev-parse HEAD        # 两者应一致
```

注意：本地 `origin/<feature-branch>` 跟踪 ref 可能过期，以 `ls-remote` 为准；
`git push` 显示 `Everything up-to-date` 不代表没推，需核对真实远程 HEAD。

### 6. 合入 main

按 `.trae/skills/cherry-pick-to-main/` 执行：基线确认 → 圈定提交（剔截图）
→ cherry-pick → main 上复跑校验 → 推送 `origin/main` → 切回功能分支。

### 7. 汇报

固定输出：功能点、改动文件（带行号链接）、测试数量与结果、commit hash、
`origin/main` 区间、当前所在分支、未完成的限制说明。不夸大验证结论。

## 已知坑点

| 现象 | 原因 | 处置 |
|---|---|---|
| 提交时 `nothing to commit` | 环境已自动提交 | 用 `git log -1` 确认内容，不要造空提交 |
| `npx jest` 找不到模块 | 缺 `frontend/node_modules` | 先 `npm install`，再跑测试 |
| 模型/接口测试误触真实网络 | 测试未 mock | 后端测试按 provider 注入假响应，前端 mock `fetch` |
| main 上构建失败 | 只跑单测没跑 build | 必须补 `npm run build` |
| 截图被带进 main | 提交里混入 PNG | cherry-pick 时 `git restore --staged <png>` 并删除 |

## 完成判定

- 功能分支与 `origin/<feature-branch>` 指向同一提交
- `origin/main` 已包含该功能提交，且 main 上 pytest / tsc / jest / build 全绿
- 工作区切回功能分支且干净
- 已向用户给出可核对的 hash 与验证数字
