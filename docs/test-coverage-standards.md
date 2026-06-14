# 测试覆盖规范 & 准入标准

> 版本: v1.0 | 更新: 2026-06-14  
> 规范维护人: 小马 🐴（质量架构师）

---

## 1. 总体目标

| 指标 | 当前 | 目标 | 状态 |
|------|------|------|------|
| 全量测试通过 | 671 passed | — | ✅ |
| 整体覆盖率 | ~49.70% → **52%+** | 55% | 🟡 |
| CI Gate | 49% | 55% | 🟡 |
| store_pg.py | 0% → **100%** | 40%+ | ✅ |
| ci/run.py | 56% → **83%** | 70%+ | ✅ |

---

## 2. store_pg.py 测试规范

**文件**: `src/yuleosh/store_pg.py` (300 行)  
**测试文件**: `tests/test_store_pg_deep.py` (87 个测试)  
**当前覆盖**: 100% line, 100% branch

### 2.1 测试原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **不连真实数据库** | 所有测试通过 mock psycopg2 实现，不依赖 PostgreSQL 实例 |
| 2 | **mock 游标作为上下文管理器** | `mock_cursor.__enter__.return_value = mock_cursor` 确保 `with conn.cursor() as cur:` 正确传递游标 |
| 3 | **每次测试重置单例** | `PostgresStore.reset()` 在 `mock_db` fixture 中调用，确保隔离 |
| 4 | **验证 SQL 调用** | 每个 CRUD 方法至少验证 `cursor.execute` 被调用且 `conn.commit()` 被调用 |
| 5 | **覆盖返回 None 路径** | fetchone 返回 None 时 get* 方法应返回 None |

### 2.2 必测方法清单

每个方法至少覆盖以下场景：

```
create_organization         → 成功插入 + RETURNING id
get_organization            → 找到 | 未找到
get_organization_by_id      → 找到 | 未找到
list_organizations          → 返回列表

create_user                 → 默认 role=member | 指定 role 和 password_hash
get_user                    → 找到 | 未找到
get_user_by_id              → 找到 | 未找到
list_users                  → 返回列表

create_org_project          → 默认 description="" | 自定义 desc
get_org_project             → 找到 | 未找到
get_org_project_by_id       → 找到 | 未找到
list_org_projects           → 返回列表

create_session              → 默认 ttl=24h
get_session                 → 有效 | 过期 | 未找到
delete_session              → DELETE 执行
cleanup_expired_sessions    → DELETE 执行

cache_spec_parse            → UPSERT 执行
get_cached_spec_parse       → 找到(JSON 解析) | 未找到

create_api_key              → RETURNING id, revoked=0
get_api_key_by_hash         → 找到 | 未找到
list_api_keys               → 返回列表
revoke_api_key              → 成功(rowcount=1) | 已吊销(rowcount=0)
update_api_key_last_used    → UPDATE 执行

save_pipeline               → UPSERT 执行
get_pipeline                → 找到 | 未找到
list_pipelines              → 返回列表

save_ci                     → 正常 | None coverage
list_ci                     → 按 limit 返回

save_review                 → UPSERT 执行
list_reviews                → 返回列表

log_evidence                → INSERT 执行
list_evidence               → 返回列表

init_project                → INSERT ON CONFLICT
get_project                 → 找到 | 未找到

record_usage                → INSERT 执行
get_monthly_usage           → 聚合 | 空数据
get_subscription            → 找到 | 未找到
upsert_subscription         → 插入(不存在) | 更新(已存在)
update_org_tier             → UPDATE 执行
get_org_by_stripe_sub       → 找到 | 未找到

record_activity             → UPDATE 执行
get_total_users             → COUNT 返回
get_total_projects          → projects + org_projects 求和
get_usage_stats             → 全表聚合

get_migration_version       → 找到(int) | 未找到(0)
is_wizard_completed         → 是 | 否 | 无记录
complete_wizard             → UPSERT 执行

_row_to_dict                → 基本映射 | 空 description
```

### 2.3 fixture 设计

```python
# 唯一推荐的 fixture 模式
@pytest.fixture
def mock_db():
    store_pg.PostgresStore.reset()
    mock_cursor = mock.MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor  # ← 关键
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.rowcount = 0
    mock_conn = mock.MagicMock()
    mock_conn.closed = False
    mock_conn.cursor.return_value = mock_cursor
    mock_psycopg2 = mock.MagicMock()
    mock_psycopg2.connect.return_value = mock_conn
    with mock.patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
        yield mock_conn, mock_cursor, mock_psycopg2

@pytest.fixture
def store(mock_db):
    return PostgresStore(dsn="pg://test:test@localhost:5432/test")

@pytest.fixture
def store_with_conn(store, mock_db):
    return store, mock_db[1], mock_db[0]  # store, cursor, conn
```

### 2.4 row_to_dict 的 cursor.description 构造

```python
def mock_description(names):
    """cursor.description 是 [(col_name,), ...] 格式"""
    return [[n] for n in names]

# 使用:
cursor.description = mock_description(["id", "name", "email"])
```

---

## 3. ci/run.py 测试规范

**文件**: `src/yuleosh/ci/run.py` (895 行)  
**测试文件**: `tests/test_ci_run_deep.py` (132 个测试) + `tests/test_ci_run_extended.py`  
**当前覆盖**: **83%** line, 分支覆盖主要路径

### 3.1 测试原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **mock subprocess** | 所有 `subprocess.run()` 通过 mock 控制返回值，不执行真实命令 |
| 2 | **mock 跨包导入** | 在测试模块顶层注入 `sys.modules["cross.*"]` 和 `sys.modules["evidence.*"]` 假模块 |
| 3 | **不写真实文件** | 使用 `TemporaryDirectory` 作为项目目录 |
| 4 | **每次测试独立目录** | `tmp_proj` fixture 提供隔离的临时目录 |
| 5 | **mock git_commit_hash** | 调用 `git_commit_hash()` 的测试需 mock 其返回值避免依赖 git |

### 3.2 mock 模块注入

```python
# 在测试文件顶部（导入 yuleosh 之前）：
import types as _t
# cross.* 假模块
c = _t.ModuleType("cross")
c.__path__ = []
sys.modules["cross"] = c
for name in ["sil_runner", "target_config", "flash", "hil_runner"]:
    m = _t.ModuleType(f"cross.{name}")
    m.sil_test = lambda **kw: ...  # 默认没有副作用
    m.TargetConfig = lambda **kw: None
    sys.modules[f"cross.{name}"] = m

# evidence.* 假模块
sys.modules["evidence"] = _t.ModuleType("evidence")
sys.modules["evidence.pack"] = _t.ModuleType("evidence.pack")
```

### 3.3 测试分层

```
CIResult         → init, add_stage, complete, to_dict (7 个测试)
Git helpers      → git_commit_hash, get_changed_files (4 个测试)
File discovery   → find_test_files (Python/Go/Java/C), cache key (7 个测试)
Layer deps       → 各层依赖验证, JSON 解析, config fallback (8 个测试)
Env checks       → is_strict, is_misra_fail_fast (4 个测试)
Coverage helpers → skip reason, load_coverage_json, run_coverage (7 个测试)
Save/Error       → _save_layer_result, _handle_stage_error (4 个测试)
_run_subprocess  → 4 种返回路径 (5 个测试)
timed_stage      → 装饰器验证 (4 个测试)
run_plan_lint    → 无任务文件, 有效/无效任务, plan 目录 (4 个测试)
run_clang_tidy   → 无 C 文件, 通过/失败, not found, timeout (5 个测试)
run_unit_tests   → 无测试发现, fallback 成功/失败, Python 文件, 异常 (7 个测试)
run_coverage     → 跳过, 高于/低于阈值, run_fails, JSON 解码, config fallback (7 个测试)
run_sil_tests    → 无 ELF, 通过/失败, import error, 异常 (5 个测试)
run_layer1       → 全部通过, lint 失败, stage 异常 (3 个测试)
Layer2 helpers   → _find_c_sources, cross-compile 各路径, static analysis, 集成测试 (15 个测试)
run_layer2       → 全部通过, SIL 失败 (2 个测试)
HIL helpers      → detect_mock, import_error, mock_tests, record, report (8 个测试)
run_layer_25     → mock mode, strict mode (2 个测试)
run_layer3       → 各种 E2E/version/evidence 路径 (7 个测试)
run_all          → pass, block, unknown layer, layer fail, dep check (4 个测试)
main()           → 所有层 CLI, unknown, no args, exit on fail (9 个测试)
Cross-compile    → make, docker, timeout, not found (7 个测试)
```

### 3.4 通用 subprocess mock 模式

```python
# 在需要 mock 子进程的测试中：
with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
    mrun.return_value.returncode = 0
    mrun.return_value.stdout = "output text"
    mrun.return_value.stderr = ""
    # 使用被测试函数 ...
```

### 3.5 ci config mock

```python
@pytest.fixture
def mock_ci_config():
    from yuleosh.ci.config import CiConfig, CoverageConfig, HardwareTestConfig
    cfg = CiConfig()
    cfg.layers = [1, 2, 25, 3]
    cfg.layer_dependencies = {1: [], 2: [1], 25: [1, 2], 3: [1, 2, 25]}
    cfg.coverage = CoverageConfig(threshold_line=85.0, threshold_condition=80.0)
    cfg.hardware_test = HardwareTestConfig(mock=True, ...)
    with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
        yield
```

---

## 4. CI 准入标准

### 4.1 提 MR 前检查清单

- [ ] `store_pg.py` 覆盖率 ≥ 80% (当前: 100%)
- [ ] `ci/run.py` 覆盖率 ≥ 70% (当前: 83%)
- [ ] 新增代码行覆盖率 ≥ 60%
- [ ] 无新增测试失败 (全量 671 passed)
- [ ] CI Gate 不低于当前值 (49%)

### 4.2 覆盖率红线

| 文件 | 最低要求 | 优先级 | 备注 |
|------|----------|--------|------|
| store_pg.py | 80% | P0 | 持久层核心 |
| ci/run.py | 70% | P0 | CI/CD 引擎 |
| store.py | 60% | P1 | SQLite 存储 |
| api/*.py | 50% | P1 | REST API 层 |
| cross/*.py | 40% | P2 | 硬件交互层 |

### 4.3 测试设计规范

```
1. 每个测试方法用 GIVEN/WHEN/THEN 思路编写
   例: "GIVEN 无效 token WHEN get_session THEN 返回 None"

2. 测试方法名格式: test_<场景>_<期望结果>
   例: test_revoke_api_key_success, test_get_organization_not_found

3. mock 范围精确: 
   - store_pg: 仅 mock psycopg2 模块
   - ci/run: 仅 mock subprocess.run + git_commit_hash

4. 每次测试独立:
   - store_pg: 每次调用 PostgresStore.reset()
   - ci/run: 每次使用新 tmp_proj
```

### 4.4 新增文件时

添加新模块的测试时，按照以下步骤：

1. 确定模块依赖 (外部库/系统命令)
2. 在测试文件中导入目标模块前注入 mock 依赖
3. 编写 fixture 隔离模块级状态
4. 对每个公共方法编写 2-3 个测试 (happy path + error path)
5. 验证覆盖率: `pytest --cov=path.to.module --cov-report=term-missing`

---

## 5. 当前覆盖率报告

```text
src/yuleosh/store_pg.py    300   0 stmts missing    100% line, 100% branch
src/yuleosh/ci/run.py      895   142 stmts missing   83%  line (目标: 70%)
```

> 最后更新: 2026-06-14 12:49 CST  
> 全量测试: 671 passed, 0 failed
