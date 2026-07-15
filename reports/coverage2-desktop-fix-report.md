# yuleOSH 覆盖提升第二轮 + Desktop 路径修复报告

**生成时间**: 2026-07-11 23:45 CST  
**范围**: Desktop 后端路径硬编码修复 + LLM/UI 测试覆盖率提升

---

## 一、Desktop 后端路径硬编码修复

### 问题描述
`desktop/server-manager.js` 中 `_resolveBackendDir()` 方法将后端路径硬编码为开发路径：
```
desktop/ → ../src/
```
当 Electron 打包后（app.asar），`__dirname` 指向 asar 内部路径，`../src/` 不存在，导致后端无法启动。

### 修改的文件
**`desktop/server-manager.js`** — 改动摘要：

| 修改点 | 说明 |
|---|---|
| `require('fs')` 新增 | 导入 `fs` 模块用于文件存在性检查 |
| `_resolveBackendDir()` 重写 | 分环境解析：dev→相对路径，prod→userData 或 resourcesPath |
| `_resolveOshHome()` 新增 | 生产模式下 OSH_HOME 指向 Electron userData 目录 |
| `_getUserDataPath()` 新增 | Electron app.getPath('userData') 封装，带安全 fallback |
| `start()` 中的 OSH_HOME | 从 `this.backendDir` → `this._resolveOshHome()` |
| `_restart()` 中的 OSH_HOME | 同上，保持一致 |

### 修复逻辑

```javascript
_resolveBackendDir() {
  if (ELECTRON_DEV=true) {
    // 开发模式：desktop/ → ../src/
    return 相对路径解析;
  }
  // 生产模式：
  // 1. 检查 extraResources 中是否打包了后端源码（预留扩展）
  // 2. 未打包→发出清晰警告提示 pip install yuleosh
  // 3. fallback 到 userData 目录
}
```

### 验证
- ✅ Node.js 语法通过（`node -c desktop/server-manager.js` 无错误）
- ✅ 模块加载通过（`require('./desktop/server-manager.js')` 正常）
- ✅ 开发模式向后兼容（ELECTRON_DEV 不影响现有行为）

---

## 二、覆盖率提升

### 目标模块覆盖提升

| 模块 | 提升前 | 提升后 | 新增测试文件 |
|---|---|---|---|
| `llm/cost.py` | 0% | **95%** | `test_llm_cost_ext.py` (126行) |
| `llm/token_budget.py` | 0% | **100%** | `test_llm_token_budget_ext.py` (150行) |
| `llm/providers/base.py` | 0% | **93%** | `test_llm_providers_ext.py` (190行) |
| `llm/providers/mock.py` | 0% | **97%** | `test_llm_providers_ext.py` (同上) |
| `ui/routes/api_routes.py` | 18% | **99%** | `test_ui_routes_api_ext.py` (277行) |

### 新增测试文件

#### 1. `tests/test_llm_cost_ext.py` — L126
覆盖 CostLogger 全部核心能力：
- LLMCallLog 数据类构造
- `CostLogger.log()` JSONL 写入 + 追加 + 目录创建
- `CostLogger.log_dict()` 便捷方法
- `CostLogger.init()` 初始化
- `get_daily_summary()` 单日聚合、失败计数、损坏行跳过、任务类型分解
- `get_task_cost()` 任务成本求和、无匹配返 0、损坏行跳过

#### 2. `tests/test_llm_token_budget_ext.py` — L150
覆盖 TokenBudgetChecker 全部场景：
- `estimate_tokens()` 空字符串、英文、CJK、混合文本
- `check()` 未知模型失败、正常通过、system_prompt 计数
- 上下文窗口超限检查
- Cost 预算超限检查
- Task budget 优先级
- 未知 task_type fallback
- 返回结果字段完整性

#### 3. `tests/test_llm_providers_ext.py` — L190
覆盖 Provider 基础组件 + MockProvider：
- LLMConfig 数据类默认值与自定义
- LLMResponse 数据类构造
- PRICING_TABLE 和 TASK_BUDGETS 常量验证
- AbstractProvider ABC 抽象验证
- MockProvider：默认响应、注册响应、错误触发、空消息
- 多 Key 匹配优先级
- Token usage 估计

#### 4. `tests/test_ui_routes_api_ext.py` — L277
覆盖所有 API 路由处理器：
- `handle_status()` 返回结构 + OSH_HOME 环境
- `handle_health()` 返回值、AUTH_ENABLED 真假、OSH_HOME
- `list_evidence()` 无目录、有文件、compliance-pack 标记、元数据
- `list_reviews()` 无目录、读 session、跳过空目录
- `list_ci_results()` 无目录、读 layer 文件
- `handle_pipeline_status()` 成功、404、500
- `handle_usage()` 无 token 401、无效会话 401、成功、500

---

## 三、总览

### 所有测试通过
```
tests/test_llm_cost_ext.py ...........                          [ 16%]
tests/test_llm_token_budget_ext.py ........................... [ 50%]
tests/test_llm_providers_ext.py .............................. [ 72%]
tests/test_ui_routes_api_ext.py ............................. [100%]
80 passed
```

### 覆盖率数据
```
llm/cost.py                         101     3    22    3   95%
llm/token_budget.py                  46     0    10    0  100%
llm/providers/base.py                41     3     0    0   93%
llm/providers/mock.py                25     0     6    1   97%
ui/routes/api_routes.py              78     0    28    1   99%
```

### 后续建议
1. **`llm/rag/engine.py`** — 当前 24%，RAG 引擎较大，建议独立一轮覆盖
2. **`ui/auth.py`** — 当前 26%，已有测试但未覆盖 edge cases
3. **`kb/cli.py`** — 0%，KB CLI 模块需独立测试
4. **`compliance/compliance_checker.py`** — 0%，合规检查器需独立测试
