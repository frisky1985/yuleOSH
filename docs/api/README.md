# yuleOSH API 接口参考索引

> 生成日期：2026-10-07
> 范围：`src/yuleosh/` 38 个子系统（与 `docs/reports/engineering-doc-coverage.md` 的 38 子系统一一对应）
> 形态：统一 API 接口参考（概述 / HTTP 端点 / Python 公共 API 符号表带 `文件:行` / 配置 / 调用示例 / 偏差）
> 生成方式：`ast` 实读源码 + Grep 验证生产调用方；不臆造。

## 查阅说明
- 每个子系统一份 `<name>_api.md`，与本索引同目录 `docs/api/`。
- 符号 / 端点均带 `文件:行`，可直接跳转源码核实。
- **HTTP 端点契约**：各端点的方法 / 路径 / 参数 / 响应以对应 handler 为准；`api` 层完整端点清单（约 60+）见 `docs/modules/api.md` §2 路由模型。
- **偏差节（§6）** 标注 ORPHAN（无生产调用方）、死代码、与直觉相悖处 —— 团队接入前请先读。

## 按职能域分组

### 流水线编排核心
- [pipeline](pipeline_api.md) · [engine](engine_api.md) · [loop_engine](loop_engine_api.md) · [plan](plan_api.md)

### LLM / Agent
- [llm](llm_api.md) · [skills](skills_api.md)

### 合规 / 追溯 / 审计
- [compliance](compliance_api.md) · [alm](alm_api.md) · [evidence](evidence_api.md) · [audit](audit_api.md)

### 知识
- [kb](kb_api.md) · [knowledge](knowledge_api.md) · [knowledge_graph](knowledge_graph_api.md) · [knowledge_management](knowledge_management_api.md)

### 设备 / 硬件 / 仿真
- [device](device_api.md) · [hardware](hardware_api.md) · [cross](cross_api.md) · [autosar](autosar_api.md) · [sil](sil_api.md) · [adapter](adapter_api.md)

### 多租户 / 计费 / 权限
- [tenant](tenant_api.md) · [rbac](rbac_api.md) · [billing](billing_api.md) · [usage](usage_api.md)

### CI / 测试 / 审查
- [ci](ci_api.md) · [testgen](testgen_api.md) · [review](review_api.md)

### 接口 / 集成
- [api](api_api.md) · [cli](cli_api.md) · [plugins](plugins_api.md) · [hooks](hooks_api.md) · [preview](preview_api.md)

### 代码生成 / 规格 / 模板
- [codegen](codegen_api.md) · [spec](spec_api.md) · [templates](templates_api.md)

### 前端 / 报表
- [ui](ui_api.md) · [report](report_api.md)

### 平台服务
- [memory](memory_api.md)

## 已知 ORPHAN / 薄壳（读前注意）
以下子系统经 Grep 验证生产调用方极少或为薄壳，真实逻辑可能在 `ui/routes/` 或暂未接入，详情见各文档 §6：
- **薄壳**（核心逻辑在 `ui/routes/<name>_routes.py`）：`tenant`、`rbac`、`billing`、`usage`、`plugins`
- **疑似 ORPHAN（已确认）**：`hardware`、`cross`、`sil`、`adapter`（详见各自文档 §6）
- `testgen` 生产引用极少，可能未完全接入
- 其余子系统均有活跃生产引用。

---
_本索引由脚本批量生成，与 `docs/modules/` 设计文档互补：设计文档讲「为什么 / 怎么组织」，API 参考讲「有什么接口 / 怎么调用」。_
