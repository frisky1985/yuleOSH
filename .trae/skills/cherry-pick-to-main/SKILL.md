---
name: "cherry-pick-to-main"
description: "Cherry-picks feature commits onto main, re-verifies on main, pushes origin/main, then restores the feature branch. Invoke when the user asks to merge/apply/pick feature work into main or to publish to origin/main."
---

# Cherry-pick 功能提交到 main

把功能分支上已验证的提交按依赖顺序摘到 `main`，在 main 上复跑校验后推送，
最后切回原分支。遵循项目规则 `.ai-rules.md` 7.10（优先 cherry-pick，不用
merge/rebase 把整条分支历史带入 main）。

## 适用场景

- 用户说「cherry-pick 到主分支 / 合到 main / 推到 origin/main」
- 功能分支与 main 历史分叉（常见：`main` 是无共同祖先的快照提交
  `chore: pre-termination backup`），不能直接 merge 整条分支

## 执行步骤

### 1. 确认基线

```bash
git status --short                 # 必须干净，否则先处理
git branch --show-current          # 记下功能分支名，最后要切回
git fetch origin --quiet
git rev-parse main origin/main     # 两者应一致；不一致先 ff-only 对齐
git ls-remote origin refs/heads/main   # 远程真实 HEAD（跟踪 ref 可能过期）
```

若 `main` 落后 `origin/main`：`git checkout main && git merge --ff-only origin/main`。

### 2. 圈定要摘的提交

```bash
git log --oneline -8 <feature-branch>
git show --stat <commit>           # 确认改动面，排除截图/日志/构建产物
```

- 按**时间正序**排列，依赖先摘（如：UI 入口依赖的组件 → 功能 → 测试）。
- 临时产物提交（`*.png` 截图等）不进入 main。
- 功能提交可能依赖更早的提交（如左下角用户区），main 缺失时必须一并摘，
  否则会出现「引用了不存在的 state / import」的编译错误。

### 3. 执行 cherry-pick

```bash
git checkout main
git merge --ff-only origin/main    # 确保基于最新远程
git cherry-pick <c1> <c2> <c3>
```

冲突处理：
- 用 `git diff` 看冲突块；若 HEAD 侧为空，通常是 main 缺少整段能力，取功能侧（theirs）。
- 解决后检查新增 JSX / 函数引用的 state、import、组件在 main 上是否都存在。
- 禁止直接 `git cherry-pick --abort` 放弃，或 `push --force` 覆盖远程。

### 4. 在 main 上复跑校验（必须全绿）

```bash
# 后端（按改动面挑相关测试，必要时全量）
python3 -m pytest tests/test_desktop_api.py -q -o addopts="" -k "<相关关键字>"

# 前端
cd frontend
npx tsc --noEmit
npx jest <相关测试文件> --silent
npm run build
```

注意沙箱环境干扰（见 `.ai-rules.md` 7.4）：`next build` 若报 `[safe-delete]`
需加 `CODEBUDDY_SAFE_DELETE_ENABLED=0`；pytest 的 basetemp 权限问题加
`--basetemp=/tmp/xxx --no-cov -p no:cacheprovider`。

### 5. 推送并恢复现场

```bash
git push origin main
git checkout <feature-branch>      # 切回原分支，避免用户后续改动落在 main
git ls-remote origin refs/heads/main   # 确认远程 HEAD = 本地 cherry-pick 结果
```

## 已知坑点

| 现象 | 原因 | 处置 |
|---|---|---|
| `git merge-base` 失败 | main 是无共同祖先的快照分支 | 不要 merge 全分支，按提交 cherry-pick |
| `git push` 提示 `Everything up-to-date` 但 `origin/<branch>` 显示旧值 | 远程 fetch refspec 只跟踪 `main`，功能分支的跟踪 ref 不会更新 | 用 `git ls-remote origin refs/heads/<branch>` 查真实值；必要时 `git push origin HEAD:refs/heads/<branch>` |
| cherry-pick 冲突中 HEAD 侧为空 | main 缺少整段功能 | 接受功能侧，并核对依赖的 state/import 是否齐全 |
| 摘了功能但漏了依赖提交 | 提交链有前置能力 | 回看 `git log` 与 `git show --stat`，按顺序补摘 |
| main 上测试通过但构建失败 | 只跑了单测没跑 build | 必须补 `npm run build`（静态导出 28 页） |

## 完成判定

- `origin/main` 指向包含目标功能的提交
- main 上 pytest / tsc / jest / build 全绿
- 工作区切回功能分支，`git status` 干净
- 向用户报告：commit hash、改动文件数、验证数字、远程 main 区间（如 `b71c2dc3..f5f2b4f9`）
