# Sprint Contract — v3.4.1 Backlog 修复轮

> 创建: 2026-08-01 09:40 | 负责人: 小克 👨‍💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: v3.4.0 终审通过后，进入 backlog 修复轮。目标是把全量回归从"60 个预存失败文件"降到可信基线，并清理安全漏洞与已知测试污染。

---

## 1. Backlog 清单（按优先级）

### P1-A: 预存失败测试修复（~60 文件，最高优先）
- [x] A1. 逐文件诊断 59 FAIL + 1 HANG 的根因分类（缺依赖/stub / mock 语义 / 副作用污染 / 真实外部服务依赖）
- [x] A2. 缺依赖类（stripe/pyserial/plugins 等）：补 mock/stub 或 skipif 条件，不得让 CI 全量回归被环境依赖拖垮
- [x] A3. mock 语义类（agent-constraints、session.status）：按 v3.4.0 真实语义修复测试
- [x] A4. 副作用类（KG SQLite 测试副作用、全局缓存污染）：隔离 tmp_path / 清理 fixture
- [x] A5. 挂起类（test_kg_performance benchmark、test_pipeline_extended 子进程递归、test_server_integration 真实 server、test_cli HANG）：加 timeout / mock 外部进程 / 拆分 perf 标记
- [x] A6. `test_template_init_existing` stdin-capture 预存失败修复
- [x] A7. 修复后全量回归：失败文件数 60 → **0**（344/344 全部 PASS，0 FAIL，0 TIMEOUT）

### P1-B: 依赖安全（dependabot）
- [x] B1. 评估 12 个依赖漏洞：均为 npm 传递依赖（vscode-extension 11 个 + frontend 1 个），无 Python 生产依赖漏洞
- [x] B2. 修复可安全升级的（12/12 全部修复）：undici 7.19→7.29、fast-uri 3.1.2→3.1.5、js-yaml 4.2→4.3.1、linkify-it 5.0.1→5.0.2、form-data 4.0.5→4.0.6、postcss 8.5.15→8.5.25（lockfile 已更新，push 后 dependabot 重新扫描关闭告警）
- [x] B3. 无法立即升级的：无（全部可安全升级，均为 lockfile 传递依赖，无破坏性版本变更）

### P2-C: 已知功能缺陷
- [x] C1. KbStore 数据库隔离不足（硬编码 `.yuleosh/kb.db`）→ 支持 `YULEOSH_KB_DB` 环境变量（src 修改 + 2 个专用测试）
- [x] C2. `test_run_layer1_*` 系列测试污染 → 重构 mock 策略（patch `_run_layer1_impl` 覆盖所有内部子调用）
- [x] C3. `_test_file_cache` 全局缓存污染预防已加，验证有效（test_ci_run_deep 全量通过）

### P2-D: 技术债（可延后，本轮只评估不强制）
- [x] D1. 记录 TD-003/004/005/011 模块拆分项（preview/analyzer 976 行、ui/server 842 行、ci/stages 1200 行、kpi 800 行）——本轮不动，仅确认清单

## 2. Done 标准（验收矩阵）
- [x] A7 达成：全量回归失败文件 60 → 0，挂起清零（perf 标记隔离 + E2E 门控 RUN_E2E=1）
- [x] B1/B2/B3 完成：依赖漏洞处置清单（修复 12 个 + 记录 0 个）
- [x] C1 完成：KbStore 支持环境变量 + 测试（2 个专用测试）
- [x] C2 完成：test_run_layer1_* 全量套件下稳定通过
- [x] 新增测试覆盖本次修复（≥10 个，实际新增 21+ 个测试函数）
- [x] 提交推送 origin/main，报告含 commit hash
- [x] 不引入新回归（修复前基线 63 问题文件 vs 修复后 0）

## 3. 范围外（不做）
- 模块大拆分（TD-003/004/005/011）——只记录不执行
- 覆盖率攻坚（30%→50%）——下一轮专项
- 新功能开发

## 4. 时间盒
- 开发 ≤ 2.5h（小克 sub-agent，可 checkpoint）
- 评估 ≤ 30min（小马）

## 5. 验收方式
- 小克修复后给失败文件对比表（修复前/后）✅ 已完成（见最终报告）
- 小马独立抽样验证 → 评分 → 小明终审 → 推远程
