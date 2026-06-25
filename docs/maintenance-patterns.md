# yuleOSH 维护模式记忆库

> 自动记录修复模式，供未来类似问题自动引用。
> 每次修复上线前的问题时更新此文件。

---

## 模式1：测试污染 — os.environ 跨模块残留

**症状**: 单测通过，全量运行时特定测试因 `999999` 等异常值失败。
**根因**: `test_alpha*.py` 在模块级（非函数级）设置 `os.environ["YULEOSH_RATE_LIMIT"]`，从未清理，污染后续所有依赖该 env var 的测试。

**修复**:
- 在 `test_api.py` 的 `reset_store` fixture 中 `os.environ.pop("YULEOSH_RATE_LIMIT")` + `importlib.reload(ratelimit)`
- fixture 运行前后保存/恢复 env var

**自动检测**: `grep -rn 'os.environ\[.*YULEOSH' tests/ --include="*.py"` 检查是否有模块级设置

---

## 模式2：Mock.patch 对模块级常量的不可靠性

**症状**: `mock.patch("module.CONSTANT", value)` 在 `with` 块内不生效。
**根因**: `mock.patch` 在 `with` 入口/出口设置/恢复属性，但模块属性可能在 `importlib.reload()` 后被替换为新的对象引用。

**修复**: 直接赋值代替 `mock.patch`：
```python
module.CONSTANT = True  # 替代 mock.patch("module.CONSTANT", True)
try:
    # test logic
finally:
    module.CONSTANT = original_value
```

**自动检测**: `grep -rn 'mock.patch.*AUTH_ENABLED\|mock.patch.*API_KEY' tests/ --include="*.py"`

---

## 模式3：coverage instrumentation 与 importlib.reload 冲突

**症状**: 启用 `--cov` 时测试失败，不启用时通过。
**根因**: `importlib.reload()` 重新创建模块对象，coverage collector 追踪旧对象；新对象的方法不被 instrumentation 包裹，导致行为不一致。

**修复**: 
1. 优先避免 `importlib.reload()` — 改用 fixture 在测试间重置状态
2. 不得不使用 `reload()` 时，务必在 try/finally 中恢复原状态

**自动检测**: `grep -rn 'importlib.reload' tests/ --include="*.py"`

---

## 模式4：预上线全量测试协议

**上线前必须执行的命令**:
```bash
# 1. 不启用 coverage 的全量测试（检测逻辑错误，速度快）
pytest tests/ -q --no-cov

# 2. 启用 coverage 的全量测试（检测覆盖率门禁）
pytest tests/ -q

# 3. 部署验证脚本
bash scripts/deploy-verify.sh

# 4. 核心 CLI 功能验证
yuleosh --help | grep -q "Available commands"
yuleosh ev check --help | grep -q "Gap"
yuleosh coverage gate --help | grep -q "fail-under"
```

---

## 模式5：C覆盖率报告不占用自动化门禁

**注意**: C 覆盖率依赖 gcc/gcov 工具链和 CMake 构建系统。
- CI 中需确保 gcc+lcov 已安装
- 本地开发环境可能没有 gcc/gcov → 不会阻塞启动
- 上线环境中 coverage gate 检查 Python + C 两套覆盖率

---

## 版本

- 创建: 2026-06-20
- 最新更新: 2026-06-20
- 涉及 commit: 72088274, 8a5b8665
