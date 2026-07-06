# yuleOSH v2.2.0 — Push 9 质量加固发布

> **发布日期**: 2026-07-07
> **版本**: v2.2.0
> **上一个版本**: v2.1.0

---

## 概览

Push 9 是一次全面的**质量加固**发布，在 Push 8 专家评审（8.0/10）的基础上，关闭了所有 P0/P1/P2 遗留问题。

---

## 🚀 新功能

### Dashboard 数据真实化
- **swe_status 写入 evidence pack** — `pack_evidence_bundle()` 现在自动聚合 SWE.1~SWE.6 状态并写入 manifest，Dashboard 的 SWE 状态端点不再回落 mock 数据
- **coverage-trend 自动采集** — CI 覆盖率管道每次运行自动追加趋势记录到 `coverage-trend.jsonl`
- **KB MISRA 去重** — `KbStore.deduplicate_misra_articles()` 按 rule_id+file+line 去重，Dashboard 违规列表质量大幅提升
- **_estimate_swe_completed() 真实数据化** — 优先从 evidence pack manifest 读取，回落 heuristic

### MISRA 规则映射修复
- **映射率 0.3% → ~99%** 🎯 — 修复了 `_normalize_rule_id()` 的键格式不匹配和 `enrich_with_definitions()` 的嵌套结构读取错误

### Benchmark 难度扩展
- **27 个测试用例** (12 easy + 10 medium + 5 hard) — 新增嵌入式场景：环形缓冲区指针运算、CAN 协议回调、类型泛型宏、packed struct 位域等
- Runner 支持多级子目录 + 难度自动检测

### 工具自身 ASPICE 验证
- **18 BP 评估**: 12 pass, 3 partial, 3 fail — 覆盖 SWE.1~SWE.6 全过程域
- self-assessment 报告作为基线，指引后续改进方向

### MISRA C:2023 升级规划
- 9 周分 3 阶段路线图：YAML 更新 → 规则映射库重构 → 知识管理+试点
- 识别 C:2012→C:2023 的 180 条规则变更，含 modified/new/deleted 分类

---

## 🔒 安全修复

- **P0 🔴 SQL 注入修复** — `kb/store.py` 中 3 处高风险（update_article/lesson/fmea）新增白名单字段验证；`store.py/store_pg.py` 中 2 处低风险修复
- **Redirect 安全审查** — 确认所有 redirect 使用纯硬编码路径，无 tabs vs spaces 解析差异风险

---

## 🛠️ 兼容性

- **向后兼容**: 所有现有 API 响应格式保持不变
- **CLI 接口**: 全部 22 个子命令签名不变
- **证据包格式**: manifest schema 新增 `swe_status` 字段（可选，现版本兼容旧格式）

---

## ✅ 验证

| 验证项 | 结果 |
|:-------|:----:|
| 回归测试 | 144 passed, 0 failed |
| MISRA 规则映射 | ~99% 已知（原 0.3%） |
| Dashboard 端点 | 7/7 真实数据（零假数据） |
| SQL 注入 | 0 高风险残留 |
| ASPICE 自检 | 18 BP baseline 建立 |
| Benchmark | 27 用例，100% success rate |

---

## 📦 安装

```bash
pip install yuleosh==2.2.0
```

或通过 Docker:

```bash
docker pull yuleosh/yuleosh:2.2.0
```
