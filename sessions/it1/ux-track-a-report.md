# yuleOSH UX Track A: 安装体验 — pip install 可用

## 已完成

### A-1: 创建 setup.py
- 位置：`setup.py`
- 使用 `find_namespace_packages(include=["src", "src.*"])` 正确发现 src/ 下各子包（包括无 `__init__.py` 的目录）
- 通过 `py_modules=["yuleosh_cli"]` 将顶层 CLI 模块纳入安装
- `entry_points` 配置 `yuleosh = yuleosh_cli:main`

### A-2: 更新 pyproject.toml
- 添加 `[build-system]` 节（requires setuptools>=64.0, build-backend=setuptools.build_meta）
- 统一 version 到 0.3.0
- 保留原有的 `[project.scripts]` 配置

### A-3: 验证结果

| 测试项 | 结果 |
|--------|------|
| `pip install -e .` | ✅ 成功 |
| `yuleosh --help` （从 /tmp） | ✅ 输出帮助信息 |
| `yuleosh spec validate docs/spec.md` | ✅ 验证通过（13条需求，100%覆盖） |
| `yuleosh spec validate /absolute/path` (从 /tmp) | ✅ 跨目录可用 |
| `yuleosh stats` | ✅ 输出完整项目统计 |
| `import yuleosh_cli` | ✅ 正常 |
| `import src.spec.validate` (等所有子模块) | ✅ 全部正常 |

## 关键决策
1. **`find_namespace_packages`** 而非 `find_packages` — 因为 src/ 自身及各子包（ci, cross, evidence, pipeline, review, spec, ui）无 `__init__.py`，find_packages 会遗漏它们
2. **不修改 src/ 下业务代码** — 无任何 src/ 文件被改动
3. **pyproject.toml + setup.py 双保险** — pyproject.toml 提供现代 build-system 声明，setup.py 提供 find_namespace_packages 支持
