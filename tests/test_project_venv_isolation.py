"""EI-M1B.5 隔离验收 — 两项目不同依赖并行互不污染。"""

# @tests src/yuleosh/project_detection.py

import subprocess

from yuleosh.engine.project_venv import ensure_venv, install_dependencies


def test_two_projects_conflicting_deps_isolated(tmp_path):
    """GIVEN 项目 A 依赖 rich==13.x、项目 B 依赖 rich==12.x（Python 3.12 兼容）
    WHEN 各自 venv 安装 THEN 各自 import 版本正确、互不污染。"""
    # 项目 A: rich 13.x
    proj_a = tmp_path / "proj-a"
    proj_a.mkdir()
    (proj_a / "requirements.txt").write_text("rich==13.9.4\n")

    # 项目 B: rich 12.x
    proj_b = tmp_path / "proj-b"
    proj_b.mkdir()
    (proj_b / "requirements.txt").write_text("rich==12.6.0\n")

    venv_a = ensure_venv(proj_a)
    venv_b = ensure_venv(proj_b)
    install_dependencies(proj_a, venv_a)
    install_dependencies(proj_b, venv_b)

    def _rich_version(venv) -> str:
        out = subprocess.run(
            [str(venv / "bin" / "python"), "-c",
             "import importlib.metadata as m; print(m.version('rich'))"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()

    ver_a = _rich_version(venv_a)
    ver_b = _rich_version(venv_b)
    # A 是 13.x，B 是 12.x，互不污染
    assert ver_a.startswith("13.")
    assert ver_b.startswith("12.")
