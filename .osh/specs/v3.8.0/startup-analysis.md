# Startup Analysis — yuleOSH v3.8.0（Track2 架构收敛）

> 版本: v3.8.0 · 基线: v3.7.0 (2e0eef5) · 日期: 2026-08-03
> 方法: Superpowers S.U.P.E.R.（Situation / Understanding / Problem / Evaluation / Resolution）
> 决策: 老板 2026-08-02 已确认方案 A（v3.7.0=Track1+Track4 ✅ 已发布 → v3.8.0=Track2 架构收敛 → v3.9.0=Track3 前端安全）

---

## S — Situation（现状）

- yuleOSH v3.7.0 (2e0eef5) 已发布：**9873 passed / 0 failed**，覆盖率 **84.10%**；Track1 7 项 + Track4 5 项落地；小马复验 9.0/10；tag 已推送。
- 遗留复验注意项（TASK_STATUS）：M4 契约语义待复验判定、W6 匿名缓存为 IP 维度、subscription/wizard 随机 secret 跨调用验签必失败、do_POST/do_DELETE 审计 200 假记录、W2 限流进程内限制。
- 核心架构债（ultra-full 三审一致）：**认证三套并存（A-C-02）**、**审计三套并存（A-W-01）**、**路由双轨（ARC-W1）**、**Store 双实现裸 SQL（ARC-W3）**、**cli/main.py 2793→2873 行单体 + sys.path.insert（A-P2-01/05）**、**dashboard/page.tsx 1972 行单体（ARC-W5）**。
- 认证相关现状（grep 证据）：
  - secret 读取 4 处：`api/auth.py:38`（fail-fast）、`ui/auth_extended.py:40`（fail-fast）、`api/subscription.py:60`（**每次随机兜底**）、`api/wizard.py:21`（**同款**）。
  - bcrypt 2 套、token 签发 2 套（`user_id/org_id` vs `sub/org`）、token 解码 3 套、限流 2 套（普通 dict vs _ThreadSafeDict）、登录 handler 2 套（/api/v1/auth/login vs /api/auth/signin）。
  - middleware 已做双格式兼容（P0-A）——收敛前提具备。

## U — Understanding（理解）

**v3.8.0 的本质**：不是功能版，而是**架构收敛版**——把 v3.6/v3.7 多次评审点名、但一直被"排期未做"的六项架构债一次性清掉。目标是把系统从"三套并存、巧合正确"推向"单一来源、显式正确"。

**为什么现在做（时机成熟）**：
1. **A1 认证合一**：v3.7.0 已完成 W2（限流加固）、M3（AUTH_ENABLED 单一来源）、M5（SEC-W3 secret 治理锁定）、P0-A（middleware 双格式兼容）——四块拼图全部就位，A1 是最后一块。且 F1（subscription/wizard 随机 secret）是**真 bug**：v3.7.0 下这两个端点跨调用验签必失败，属于"修不修都该修"。
2. **A2 审计统一**：ring 是写-only 死代码、JSONL 路由被遮蔽、event_bus 持久化是 AttributeError 被吞的静默死代码——三处"看起来在审计、实际没在审计"，审计合规性存疑（SAAS-4 对外演示必查）。
3. **A3 路由去双轨**：`_dispatch_legacy` 的 audit 分支"巧合正确"的死代码（synthesis 原文）——路由表与 legacy 委托并存，改一处漏一处的风险持续累积。
4. **A4/A5/A6**：结构债，成本低、收益明确（可测试性、可维护性），且 A5 的 sys.path.insert 清理是测试基建卫生。

**与 v3.9 的关系**：Track3 前端安全（token cookie 迁移）依赖"认证收敛后单一 token 语义"，A1 是 T1 的前置。**A1 不做，v3.9.0 的 cookie 迁移无从谈起**——这是本版优先级的硬理由。

## P — Problem（问题定义）

**一句话**：如何在 **4-5 天**内完成六项架构收敛 + 四项遗留收尾，**不破坏 9873/0 基线、覆盖率 ≥84.10% 不降、公开 API 契约零变化**，且让"认证三套/审计三套/路由双轨"从代码层面可验证地消失？

**关键矛盾**：
- **收敛（合并）vs 兼容（契约零变化）**：A1 限流合并、A2 审计数据面扩展、A3 响应契约保持——每一处都是"内部大变、外部不变"的精细活。
- **删除（死代码）vs 回归（测试依赖）**：A2 删 JSONL 路由、A3 删 _dispatch_legacy、A5 删 sys.path.insert——删除前必须确认无隐式依赖（如测试直接 import 内部函数）。
- **基座（auth_extended）vs 既有事实（api/auth.py 被 router 引用）**：依赖方向（api→ui.auth_extended 已存在）与循环导入风险。

**非目标**：Track3 前端安全、yuleASR-Configurator、限流多 worker 共享存储（S-P2-02）、COR-W4 zip 二次校验。

## E — Evaluation（方案评估）

**优先级论证（A1 第一的硬理由）**：
1. **A1 是安全收敛前提**：三套认证 = 三个攻击面/三份实现漂移风险；F1 随机 secret 是活跃 bug（v1 端点验签必失败 + 若被误用为"验签宽松"则形同虚设）；且 A1 是 v3.9.0 T1（cookie 迁移）的硬前置。
2. **F1 依附 A1**：subscription/wizard 的 secret 修复必须随 A1 的 secret 单一来源一起做（Step 0）。
3. **F2 依附 A1**：preview 匿名 user_key 换 user_id 只有认证收敛后才语义完整。
4. **A2/A3 独立但互为前提的一部分**：A2 删 audit_routes（JSONL 死代码）与 A3 删 _dispatch_legacy 的 audit 分支是同一处收敛的两个侧面，可并行但验收需联动。
5. **A4/A5/A6 纯结构**：低风险高确定性，放后段做（A5 测试面大，需全量回归兜底）。

**开发批次设计**（依赖驱动）：

| 批次 | 内容 | 依赖 | 局部回归重点 |
|------|------|------|-------------|
| P0 | A1 Step 0-1（secret 单一来源 + F1） | 无 | auth/subscription/wizard 测试 |
| P1 | A1 Step 2（middleware verify 统一）| P0 | test_security + 全部 require_auth 面 |
| P2 | A1 Step 3-5（handler 委托 + 删重复 + 全量）| P1 | test_api_auth_* + 前端登录链 E2E |
| P3 | A2（审计统一）+ A3（路由去双轨）| 独立于 P2，可与 P2 并行 | test_api_audit_ext + test_security + test_v344_p0ab |
| P4 | A4（Store 补方法）| 可与 A2 合并实施 | test_store_pg_deep + project/stats 测试 |
| P5 | A5（CLI 拆分）+ F3/F4 | 无 | test_cli_*（130 用例）+ test_ui_server_deep |
| P6 | A6（dashboard 拆组件）+ F2 | A1 完成后 | npm run build + tsc --noEmit + 手工四 tab |

**每批后局部回归**：`python3 -m pytest tests/test_backlog_p1_v350.py tests/test_ui_server_deep.py tests/test_cli_main_adv_unit.py tests/test_api_auth_deep.py tests/test_api_audit_ext.py tests/test_security.py -q`；P2/P5 后各跑一次全量。

## R — Resolution（决议）

### 为什么做（Why）
| 类别 | 项 | 价值 |
|------|-----|------|
| 安全 | A1, F1, F2 | 消灭三套认证攻击面、修复随机 secret 验签 bug、缓存键收敛到 user_id |
| 合规/信任 | A2 | 审计从"三套假审计"到"单一持久审计"，SAAS-4 可对外演示 |
| 可维护性 | A3, A4, A5, A6 | 路由单一表、Store 单一接口、CLI 模块化、前端组件化 |
| 工程卫生 | F3, F4 | 审计状态码真实化、页面缓存头补全 |

### 优先级（P0 顺序）
1. **A1 + F1**（安全收敛前提，改动面最大，先做，独立 PR 分步提交）
2. **F2**（依附 A1，A1 收尾后立即做）
3. **A2 + A3**（审计/路由双轨收敛，可并行，验收联动）
4. **A4**（Store 补方法，可与 A2 合并）
5. **A5 + F3 + F4**（结构拆分 + 小修，全量回归兜底）
6. **A6**（前端拆分，最后收尾）

### 成功标准（Done 定义）
1. 六项 + 四项附项全部有正例 + 负例测试，`acceptance-matrix.md` 全部 ✅；
2. 全量回归 ≥ 9873 passed / 0 failed（v3.7.0 基线）只增不减；覆盖率 ≥84.10% 不降；
3. 架构债消失的代码级证据：grep 无 `_dispatch_legacy`、无 `api/auth.py` 重复实现、无 `audit_routes` HTTP 引用、无 `secrets.token_urlsafe(32)` 兜底、tests/ 无 sys.path.insert；
4. A1 前端登录链 E2E 全绿（双链互认 + 负例 401）；
5. 附录 B 七个裁决项全部经小明确认并记录；
6. 每步独立 commit 可回滚（A1 尤其）。

### 风险与缓解
| 风险 | 等级 | 缓解 |
|------|------|------|
| A1 middleware 统一 verify 改变 15 个 handler 鉴权行为 | 高 | Step 2 独立 commit + test_security 负例全绿 + 前端登录链手工验证 + 可单独 revert |
| A1 限流合并（两套→一套）行为收紧 | 中 | 验收矩阵注明共享计数语义（T-A1-08-neg）；文案与 429 语义不变 |
| A2 审计数据面扩展（legacy 入表） | 中 | 裁决 B3（推荐仅 /api/ 前缀入表）；表加索引 |
| A3 legacy→新式 body 读取/鉴权语义差异 | 高 | 逐端点响应对照测试；read_body 统一；require_auth 等价性用例 |
| A4 PostgresStore 漏实现新方法 | 中 | 三实现一致性测试 + test_store_pg_deep 全绿 |
| A5 CLI 测试 import 内部函数导致大面积改测试 | 中 | 先 grep 测试 import 面评估；main.py 保留兼容 re-export（如 `from .commands.misra import *` 再导出 cmd_*） |
| A5 删 sys.path.insert 后本地/CI 导入差异 | 中 | 确认 pytest.ini pythonpath 双环境生效；删除后全量跑 |
| A6 props 边界漂移 | 低 | tsc --noEmit + 四 tab 手工验证；产物不重建（B6） |
| F1 改动后 subscription/wizard 从"必失败"变"可用" | 中 | 新增跨调用验签用例锁定；行为变化在 delta 明示 |

### 验收负责人
- **开发**: 小克（按 spec.md SHALL 条款 + acceptance-matrix.md 测试清单；A1 分步 commit）
- **复验**: 小马（独立跑测试 + grep 架构债消失证据 + 前端登录链手工 + 附录 B 核验）
- **终审**: 小明（附录 B 七个裁决、A1 公共模块归属、审计数据面口径）

### 时间盒
- 预估 **4-5 天**（A1 2d + A2 1.5d + A3 1d + A4 1d + A5 2d + A6 1d，可并行压缩）。
- 上下文安全：本 session 产出四份契约文档后结束；开发阶段小克按批次推进，每批后小马复验。
