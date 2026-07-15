# Expert Review Fix Report

> 修复日期: 2026-07-11
> 修复范围: P0-1, P0-2, P0-3, P1-3
> 修复人: 小克 (Claude Agent)

---

## P0-1: CLI Entry Point 冲突 ✅

### 问题
pyproject.toml 指向 `yuleosh=yuleosh._entry:main`，但 setup.py 指向 `yuleosh=yuleosh_cli:main`。  
`_entry.py` 通过向上 2 级目录查找 `yuleosh_cli.py`，pip install 后该路径在 site-packages 中不存在，导致 CLI 不可用。

### 根因
`yuleosh_cli.py` 位于项目根目录，不在 `src/` 下，因此不被 setuptools `packages.find(where=["src"])` 打包。  
`_entry.py` 的路径推导逻辑只适用于 dev 环境。

### 修复
1. **将 `yuleosh_cli.py` 移入包内**：  
   `yuleosh_cli.py` → `src/yuleosh/cli/main.py`，使其成为 `yuleosh.cli.main` 模块，随 pip 包一起发布。

2. **重写 `_entry.py`**：  
   不再依赖路径查找，直接 `from yuleosh.cli.main import main`。  
   开发环境和 pip 安装环境均正常工作。

3. **统一 setup.py 入口**：  
   删除 `setup.py` 中的 `py_modules=["yuleosh_cli"]`，将其 `entry_points` 改为 `yuleosh=yuleosh._entry:main`，与 pyproject.toml 一致。

4. **修复 `cli/main.py` 中的 `OSH_HOME` 和 `SRC_DIR` 逻辑**：  
   - `OSH_HOME` 默认值从 `os.path.dirname(__file__)` 改为 `os.getcwd()`，避免 pip 安装后指向 site-packages 目录。  
   - `SRC_DIR` 路径检查改为条件添加（仅 dev 模式下 src/ 存在时才加入 sys.path）。

### 验证
```
$ yuleosh --help
usage: yuleosh [-h] {init,init-autosar,project,template,spec,...} ...
```

所有子命令正常列出。

---

## P0-2: 健康检查超时不一致 ✅

### 问题
spec.md SHALL-2.1.3 规定 15 秒后端健康检查超时，但 `desktop/main.js` 中 `waitForBackend()` 默认 `timeoutMs=10000`（10 秒）。  
调用处也传了 `10000`。

### 修复
`desktop/main.js` 两处修改：
- `waitForBackend(url, timeoutMs = 10000, ...)` → `waitForBackend(url, timeoutMs = 15000, ...)`
- `await waitForBackend(healthCheckUrl, 10000, 500)` → `await waitForBackend(healthCheckUrl, 15000, 500)`

### 验证
```
$ grep -n '15000\|waitForBackend' desktop/main.js
627:function waitForBackend(url, timeoutMs = 15000, intervalMs = 500) {
737:    await waitForBackend(healthCheckUrl, 15000, 500);
```

---

## P0-3: misra-rules.yaml 路径打包后断裂 ✅

### 问题
`_DEFAULT_RULES_PATH` 从 `__file__` 向上 5 级到项目根目录找 `misra-rules.yaml`。  
`pip install` 后 `misra-rules.yaml` 不在 site-packages 中（它只在项目根目录），导致所有 MISRA 规则加载失败。

### 修复
1. **将 `misra-rules.yaml` 放入包内**：  
   `misra-rules.yaml` → `src/yuleosh/ci/rulesets/misra-rules.yaml`。

2. **更新 `misra.py` 路径解析逻辑**：  
   ```python
   _THIS_DIR = Path(__file__).resolve().parent
   _SITE_PACKAGES_PATH = _THIS_DIR / "misra-rules.yaml"
   _PROJECT_ROOT_PATH = _THIS_DIR.parent.parent.parent.parent.parent / "misra-rules.yaml"
   _DEFAULT_RULES_PATH = _SITE_PACKAGES_PATH if _SITE_PACKAGES_PATH.exists() else _PROJECT_ROOT_PATH
   ```
   - 先查同目录（site-packages 模式）
   - 回落旧路径（开发模式）

3. **添加 `package-data` 配置**：  
   `pyproject.toml` 中新增：
   ```toml
   [tool.setuptools.package-data]
   yuleosh = ["ci/rulesets/misra-rules.yaml"]
   
   [tool.setuptools]
   include-package-data = true
   ```

### 验证
```python
from yuleosh.ci.rulesets.misra import MisraC2023RuleSet
rs = MisraC2023RuleSet()
defs = rs.rule_definitions()
# 194 rule definitions loaded (rules + directives + meta)
```

---

## P1-3: 覆盖率 fail_under 统一 ✅

### 问题
pyproject.toml 设 `fail_under = 50`，但 pytest.ini 设 `--cov-fail-under=45`，两处不一致。

### 修复
pytest.ini `--cov-fail-under=45` → `--cov-fail-under=50`，对齐 pyproject.toml 的 `fail_under=50`。

### 验证
```
$ grep 'cov-fail-under' pytest.ini
addopts = --cov=src/yuleosh --cov-report=term-missing --cov-report=html --cov-fail-under=50
```

---

## 综合验证

### CLI 入口验证
```
$ yuleosh --help
→ 全部子命令正常列出（init, init-autosar, ci, misra, template, spec, pipeline, ...）
```

### MISRA 规则加载验证
```
MisraC2023RuleSet 加载 194 条规则定义（含 meta 元数据）
_DEFAULT_RULES_PATH 指向包内 misra-rules.yaml
```

### 配置文件一致性验证
| 配置项 | pyproject.toml | pytest.ini | setup.py | 一致性 |
|--------|:-:|:-:|:-:|:-:|
| CLI 入口 | `yuleosh._entry:main` | N/A | `yuleosh._entry:main` | ✅ |
| fail_under | 50 | 50 | N/A | ✅ |
| package-data | `ci/rulesets/misra-rules.yaml` | N/A | N/A | ✅ |
| 健康检查超时 | spec.md: 15s | N/A | main.js: 15s | ✅ |
