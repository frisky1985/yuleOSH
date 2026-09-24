# 本地 14B 模型跑 Pipeline 验证报告

> 生成时间：2026-09-18 · 项目：yuleOSH v4.0.0 · 验证对象：座椅控制器 `projects/21`
> 服务：本机 `yuleosh ui`（端口 8080，加载新代码 `5af40fa9`）· 本地模型 `qwen2.5-coder:14b`

## 1. 结论速览

| 问题 | 答案 |
|---|---|
| 能用本地 14B 模型跑吗？ | **能 ✅**（完整跑完 24 步） |
| 14B 降级链路是否生效 | 生效（无外部 key → Ollama `qwen2.5-coder:14b`） |
| 24 步结果 | **23 passed / 1 failed** |
| 末道 G10 合格性是否通过 | **未通过（failed）**，但与模型大小无关（4B 同样 fail） |
| 全程「No LLM API key」错误 | **0** |

## 2. 部署方式

本地 Ollama 已拉取 `qwen2.5-coder:14b`（9.0 GB）。重新部署时指定本地降级模型：

```bash
# 先解除旧 launchd 守护占用（KeepAlive 会让旧进程杀而不死）
launchctl unload ~/Library/LaunchAgents/com.yuleosh.ui.plist 2>/dev/null

# 手动后台拉起（launchd 注册已损坏，绕过之）
cd /Users/ingeek/workspace/yuleOSH
source .venv/bin/activate
YULEOSH_AUTH_DISABLED=1 \
YULEOSH_JWT_SECRET=local-dev-insecure-secret-do-not-use-in-prod \
OSH_HOME=/Users/ingeek/workspace/yuleOSH \
YULEOSH_HOST=127.0.0.1 YULEOSH_PORT=8080 \
YULEOSH_LLM_LOCAL_MODEL=qwen2.5-coder:14b \
nohup python -m yuleosh ui > /tmp/yuleosh-ui.14b.out 2>&1 &
```

## 3. 降级路径验证（轻量）

无外部 key 时直接调用 `chat_completion`：

```
外部 LLM 不可用 → 降级到本地 Ollama (http://127.0.0.1:11434), timeout=1800s
降级成功 | model=qwen2.5-coder:14b | 耗时=24.6s | 返回='可行'
```

（24.6s 含首次 14B 模型加载到内存，后续调用更快）

## 4. 座椅控制器项目 14B 运行结果（run_id `e836aa082928`）

整体状态：**completed** · 步骤定论：24/24

| # | 步骤 | 状态 | # | 步骤 | 状态 |
|---|---|---|---|---|---|
| 1 | spec-check | ✅ passed | 13 | verify-loop | ✅ passed |
| 2 | super-analysis | ✅ passed | 14 | c-unit-test | ✅ passed |
| 3 | prd | ✅ passed | 15 | code-review | ✅ passed |
| 4 | prd-review | ✅ passed | 16 | misra-review | ✅ passed |
| 5 | architecture | ✅ passed | 17 | integration-test | ✅ passed |
| 6 | arch-review | ✅ passed | 18 | qemu-verify | ✅ passed |
| 7 | development | ✅ passed | 19 | coverage-review | ✅ passed |
| 8 | development-review | ✅ passed | 20 | review-critical-safety | ✅ passed |
| 9 | codegen-deploy | ✅ passed | 21 | fault-injection | ✅ passed |
| 10 | internal-code-review | ✅ passed | 22 | merge-gate | ✅ passed |
| 11 | claude-review | ✅ passed | 23 | **test-qualification** | ❌ **failed** |
| 12 | test-planning | ✅ passed | 24 | final-report | ✅ passed |

10 道门禁：G1/G2/G5 passed，G3/G4/G6/G7/G8/G9 skipped，**G10 合格性 failed**。

## 5. G10 合格性失败根因（关键）

`test-qualification` 步 `status=failed`、`error=None`、`output_path=None` —— 它是**质量门禁**，不是异常崩溃。
深入 `gate-summary.json` 与产物目录，根因是：

- 座椅控制器项目的 `spec.md` 仅 397 字节（极简 demo），LLM 生成的产物是**文档/审查类 JSON**，**整个项目没有任何 C/C++ 源文件**（`find -name '*.c'/'*.cpp'/'*.h'` 为空）。
- 覆盖率门禁 `c-coverage-gate` 因此被 skipped：
  `"reason": "No C/C++ sources — C coverage gate not applicable"`，`gate_passed=false`。
- 合格性门禁（SWE.6）要求有可编译、可测试、有覆盖率证据的固件；因无 C 源码 → 合格性证据不足 → **G10 failed**。

**这与模型大小无关**：此前 4B（`qwen:latest`）跑同样项目，G10 也是 failed，中间 LLM 步骤同样全部 passed。换 14B 并未改变 G10 结论。

## 6. 14B vs 4B 对比

| 维度 | 4B (`qwen:latest`) | 14B (`qwen2.5-coder:14b`) |
|---|---|---|
| 架构/prd/development 等 LLM 重步 | 全部 passed | 全部 passed |
| 中间各 review（misra/coverage/critical-safety） | passed | passed |
| 末道 G10 合格性 | failed | failed |
| 单步耗时（首步含模型加载） | 更快（模型小） | 较慢（~1–2 min/步，全 24 步约 30+ 分钟） |

结论：**14B 在「中间 LLM 生成/审查质量」上未出现 4B 的失败，但 G10 这类「合格性证据」门禁的通过与否取决于项目是否生成了真实可测的固件代码，而非模型参数规模。**

## 7. 建议

- 若要让 G10 通过，需让项目产出**真实 C 固件源码 + 可执行的单元测试/覆盖率**，而非仅文档产物。这取决于项目 spec 的复杂度与 LLM 生成行为，可换更完整的示例项目（如 `gpio-led-chaser`）验证。
- 日常快速验证用 4B（`qwen:latest`）更快；需要更高质量代码生成时切 14B。
- 当前 8080 服务已加载 14B 模型驻留内存，可直接在 Dashboard 打开 `projects/21` 实时查看，或换其他项目试跑。

---

*注：本报告为验证记录，未做提交。pipeline 运行产物位于 `projects/21/.osh/sessions/e836aa082928/`。*
