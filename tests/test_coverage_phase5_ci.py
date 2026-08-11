"""Phase 5 coverage boost — CI 工具模块（verify_c_coverage_gate / profile / dashboard_writer）。

Target modules (2026-08-09 baseline):
  - src/yuleosh/ci/verify_c_coverage_gate.py  43.9% → 补齐编译/运行/gcov 解析辅助函数
  - src/yuleosh/ci/profile.py                 56.3% → 校验/过滤/审计日志分支
  - src/yuleosh/ci/dashboard_writer.py        56.6% → KG 状态/趋势/KPI 写入分支

风格：直测函数/分支，外部命令 mock，全部落在 tmp_path。
"""

import json
import subprocess
from pathlib import Path
from unittest import mock

# =====================================================================
# verify_c_coverage_gate — 辅助函数
# =====================================================================

class TestBuildCDemoDetailed:
    def test_no_c_sources(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        assert _build_c_demo(demo) is None

    def test_cmake_build_success_finds_exe(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        build_dir = demo / "_build_verify"
        exe = build_dir / "uart_demo_host"

        # _build_c_demo 开头会 rmtree(build_dir) 再重建，预建文件会被删掉；
        # 必须由 mock 的 subprocess.run 在 cmake --build 成功后创建 exe。
        def fake_run(cmd, **kwargs):
            if cmd and cmd[0].endswith("cmake") and cmd[1] == "--build":
                # cmake --build 成功后创建 exe（configure 命令 cmd[1] 是源码目录）
                exe.parent.mkdir(parents=True, exist_ok=True)
                exe.write_text("#!/bin/sh\nexit 0\n")
                exe.chmod(0o755)
                return mock.MagicMock(returncode=0, stdout="", stderr="")
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/cmake"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=fake_run):
            result = _build_c_demo(demo)
        assert result == exe

    def test_cmake_configure_fail_falls_back_to_gcc(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        build_dir = demo / "_build_verify"
        out_exe = build_dir / "demo_verify"
        out_exe.parent.mkdir(parents=True)
        out_exe.write_text("#!/bin/sh\nexit 0\n")
        out_exe.chmod(0o755)

        def fake_run(cmd, **kwargs):
            if cmd[0].endswith("cmake"):
                return mock.MagicMock(returncode=1, stdout="", stderr="cfg failed")
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        side_effect=lambda n: "/usr/bin/gcc" if n in ("gcc", "cc", "cmake") else None), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=fake_run):
            result = _build_c_demo(demo)
        assert result == out_exe

    def test_cmake_build_fail_then_gcc_ok(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        build_dir = demo / "_build_verify"
        out_exe = build_dir / "demo_verify"
        out_exe.parent.mkdir(parents=True)
        out_exe.write_text("#!/bin/sh\nexit 0\n")
        out_exe.chmod(0o755)

        def fake_run(cmd, **kwargs):
            if cmd[0].endswith("cmake") and "--build" in cmd:
                return mock.MagicMock(returncode=1, stdout="", stderr="build failed")
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        side_effect=lambda n: "/usr/bin/gcc" if n in ("gcc", "cc", "cmake") else None), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=fake_run):
            result = _build_c_demo(demo)
        assert result == out_exe

    def test_cmake_build_finds_any_executable(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        build_dir = demo / "_build_verify"
        other = build_dir / "other_bin"

        # 同上：build_dir 会被 rmtree 重建，mock 在 cmake --build 成功后创建任意可执行文件
        def fake_run(cmd, **kwargs):
            if cmd and cmd[0].endswith("cmake") and cmd[1] == "--build":
                other.parent.mkdir(parents=True, exist_ok=True)
                other.write_text("#!/bin/sh\nexit 0\n")
                other.chmod(0o755)
                return mock.MagicMock(returncode=0, stdout="", stderr="")
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/cmake"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=fake_run):
            result = _build_c_demo(demo)
        assert result == other

    def test_manual_gcc_no_compiler(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value=None):
            assert _build_c_demo(demo) is None

    def test_manual_gcc_compile_fail(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        side_effect=lambda n: "/usr/bin/gcc" if n in ("gcc", "cc") else None), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=1, stdout="", stderr="err")):
            assert _build_c_demo(demo) is None

    def test_manual_gcc_timeout(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        side_effect=lambda n: "/usr/bin/gcc" if n in ("gcc", "cc") else None), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("gcc", 120)):
            assert _build_c_demo(demo) is None

    def test_manual_gcc_cleanup_build_dir(self, tmp_path):
        """已存在的 _build_verify 应先被 rmtree 再重建。"""
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "main.c").write_text("int main(void){return 0;}\n")
        (demo / "_build_verify").mkdir(parents=True)
        (demo / "_build_verify" / "stale.txt").write_text("x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        side_effect=lambda n: "/usr/bin/gcc" if n in ("gcc", "cc") else None), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout="", stderr="")):
            result = _build_c_demo(demo)
        assert result is not None
        assert not (demo / "_build_verify" / "stale.txt").exists()


class TestRunDemoExecutable:
    def test_success(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _run_demo_executable
        exe = tmp_path / "demo"
        exe.write_text("x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout="ok", stderr="")):
            assert _run_demo_executable(exe) is True

    def test_nonzero(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _run_demo_executable
        exe = tmp_path / "demo"
        exe.write_text("x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=3, stdout="", stderr="boom")):
            assert _run_demo_executable(exe) is False

    def test_timeout(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _run_demo_executable
        exe = tmp_path / "demo"
        exe.write_text("x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("demo", 30)):
            assert _run_demo_executable(exe) is False

    def test_exception(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _run_demo_executable
        exe = tmp_path / "demo"
        exe.write_text("x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=OSError("noexec")):
            assert _run_demo_executable(exe) is False


class TestFindGcdaFiles:
    def test_finds_nested(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _find_gcda_files
        (tmp_path / "obj" / "sub").mkdir(parents=True)
        (tmp_path / "obj" / "a.gcda").write_bytes(b"x")
        (tmp_path / "obj" / "sub" / "b.gcda").write_bytes(b"x")
        (tmp_path / "obj" / "c.txt").write_text("x")
        found = _find_gcda_files(tmp_path / "obj")
        assert len(found) == 2
        assert {p.name for p in found} == {"a.gcda", "b.gcda"}

    def test_none(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _find_gcda_files
        assert _find_gcda_files(tmp_path) == []


class TestParseGcovrCoverage:
    def test_gcovr_missing_uses_gcov_text(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcovr_coverage
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value=None), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcov_text",
                        return_value={"line_rate": 0.5}):
            assert _parse_gcovr_coverage(tmp_path) == {"line_rate": 0.5}

    def test_gcovr_success(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcovr_coverage
        data = {"files": [{"file": "a.c"}], "line_rate": 0.8}
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcovr"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout="", stderr="")) as mrun:
            # 先写一个假的 json 输出文件：_parse_gcovr_coverage 会读它
            def _side_effect(cmd, **kw):
                out = Path(cmd[cmd.index("-o") + 1])
                out.write_text(json.dumps(data))
                return mock.MagicMock(returncode=0, stdout="", stderr="")
            mrun.side_effect = _side_effect
            result = _parse_gcovr_coverage(tmp_path)
        assert result["line_rate"] == 0.8

    def test_gcovr_nonzero_but_json_exists(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcovr_coverage
        data = {"files": [], "line_rate": 0.1}
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcovr"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run") as mrun:
            def _side_effect(cmd, **kw):
                out = Path(cmd[cmd.index("-o") + 1])
                out.write_text(json.dumps(data))
                return mock.MagicMock(returncode=1, stdout="", stderr="err")
            mrun.side_effect = _side_effect
            result = _parse_gcovr_coverage(tmp_path)
        assert result["line_rate"] == 0.1

    def test_gcovr_timeout_falls_back(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcovr_coverage
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcovr"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("gcovr", 60)), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcov_text",
                        return_value=None):
            assert _parse_gcovr_coverage(tmp_path) is None

    def test_gcovr_json_missing_falls_back(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcovr_coverage
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcovr"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout="", stderr="")), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcov_text",
                        return_value={"line_rate": 0.25}):
            assert _parse_gcovr_coverage(tmp_path) == {"line_rate": 0.25}


class TestParseGcovText:
    def test_no_gcov_tool(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value=None):
            assert _parse_gcov_text(tmp_path) is None

    def test_no_gcda_files(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"):
            assert _parse_gcov_text(tmp_path) is None

    def test_gcov_json_output(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        (tmp_path / "a.gcda").write_bytes(b"x")
        gcov_json = json.dumps({
            "files": [{"file": "a.c", "lines": {"count": [1, 0, 1]}}],
        })
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout=gcov_json, stderr="")):
            result = _parse_gcov_text(tmp_path)
        assert result["totals"]["lines"] == {"found": 3, "hit": 2}

    def test_gcov_json_multiple_files(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        (tmp_path / "a.gcda").write_bytes(b"x")
        gcov_json = json.dumps({
            "files": [
                {"file": "a.c", "lines": {"count": [5, 0]}},
                {"file": "b.c", "lines": {"count": [1]}},
            ],
        })
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout=gcov_json, stderr="")):
            result = _parse_gcov_text(tmp_path)
        assert result["totals"]["lines"] == {"found": 3, "hit": 2}
        assert len(result["files"]) == 2

    def test_gcov_plain_text_fallback(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        (tmp_path / "a.gcda").write_bytes(b"x")
        plain = "        -:    0:Source:a.c\n       12:    1:int main()\n        #####:    2:  dead()\n"
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout=plain, stderr="")):
            result = _parse_gcov_text(tmp_path)
        # "12:" → count 12 命中; "#####" 非数字跳过; "-:" 跳过
        assert result["totals"]["lines"]["found"] == 1
        assert result["totals"]["lines"]["hit"] == 1

    def test_gcov_plain_text_run_marker(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        (tmp_path / "a.gcda").write_bytes(b"x")
        # gcov 文本输出真实计数行是右对齐数字（"      1:" 7 个前导空格 + 数字），
        # 旧实现 startswith("        ") 8 空格永远不命中；新实现按 \s*(\d+): 提取。
        plain = "        1:    2:int main()\n"
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout=plain, stderr="")):
            result = _parse_gcov_text(tmp_path)
        assert result["totals"]["lines"]["found"] == 1
        assert result["totals"]["lines"]["hit"] == 1

    def test_gcov_all_zero_total_returns_none(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        (tmp_path / "a.gcda").write_bytes(b"x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        return_value=mock.MagicMock(returncode=0, stdout="no data", stderr="")):
            assert _parse_gcov_text(tmp_path) is None

    def test_gcov_exception_skipped(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _parse_gcov_text
        (tmp_path / "a.gcda").write_bytes(b"x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which",
                        return_value="/usr/bin/gcov"), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("gcov", 30)):
            assert _parse_gcov_text(tmp_path) is None


class TestLoadCFailUnder:
    def test_default_when_no_config(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _load_c_fail_under
        assert _load_c_fail_under(tmp_path) == 70

    def test_custom_value(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _load_c_fail_under
        with mock.patch("yuleosh.ci.config._get_ci_config") as mcfg:
            mcfg.return_value = mock.MagicMock(coverage=mock.MagicMock(c_fail_under=60))
            assert _load_c_fail_under(tmp_path) == 60

    def test_exception_returns_default(self, tmp_path):
        from yuleosh.ci.verify_c_coverage_gate import _load_c_fail_under
        with mock.patch("yuleosh.ci.config._get_ci_config",
                        side_effect=RuntimeError("bad config")):
            assert _load_c_fail_under(tmp_path) == 70


class TestVerifyCoverageDataPaths:
    def test_coverage_data_none(self, tmp_path):
        """_parse_gcovr_coverage 返回 None → warnings + success。"""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        exe = tmp_path / "_build_verify" / "demo"
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project",
                        return_value=demo), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo",
                        return_value=exe), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable",
                        return_value=True), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files",
                        return_value=[exe]), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage",
                        return_value=None):
            result = verify_c_coverage_gate(str(tmp_path))
        assert result["success"] is True
        assert any("Failed to parse coverage" in w for w in result["warnings"])

    def test_branch_rate_percent_float(self, tmp_path):
        """branch_rate 为 0~1 浮点 → 转百分比。"""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        exe = tmp_path / "_build_verify" / "demo"
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
        data = {"files": [{"file": "a.c", "line_rate": 0.9}],
                "line_rate": 0.9, "branch_rate": 0.42}
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project",
                        return_value=demo), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo",
                        return_value=exe), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable",
                        return_value=True), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files",
                        return_value=[exe]), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage",
                        return_value=data):
            result = verify_c_coverage_gate(str(tmp_path))
        assert result["line_rate"] == 90.0
        assert result["branch_rate"] == 42.0
        assert result["per_file"][0]["line_rate"] == 0.9

    def test_line_rate_already_percent(self, tmp_path):
        """line_rate 为 88.0（已是百分比）→ 原样保留。"""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        demo = tmp_path / "demos" / "uart"
        demo.mkdir(parents=True)
        (demo / "CMakeLists.txt").write_text("project(demo)\n")
        exe = tmp_path / "_build_verify" / "demo"
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
        data = {"files": [], "line_rate": 88.0, "branch_rate": 99.0}
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project",
                        return_value=demo), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo",
                        return_value=exe), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable",
                        return_value=True), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files",
                        return_value=[exe]), \
             mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage",
                        return_value=data):
            result = verify_c_coverage_gate(str(tmp_path))
        assert result["line_rate"] == 88.0
        assert result["branch_rate"] == 99.0


# =====================================================================
# ci/profile.py
# =====================================================================

class TestProfileBasics:
    def test_get_available_profiles(self):
        from yuleosh.ci.profile import get_available_profiles
        profiles = get_available_profiles()
        assert {"safety", "ci", "performance", "testing"} <= set(profiles)

    def test_get_profile_config_found(self):
        from yuleosh.ci.profile import get_profile_config
        assert get_profile_config("ci")["exclude_steps"]
        assert get_profile_config("safety")["exclude_steps"] == []

    def test_get_profile_config_missing(self):
        from yuleosh.ci.profile import get_profile_config
        assert get_profile_config("nope") is None


class _FakeMisra:
    def __init__(self, active_profile="safety", profiles=None):
        self.active_profile = active_profile
        self.profiles = profiles or {}


class TestValidateActiveProfile:
    def _cfg(self, active="safety", profiles=None):
        return mock.MagicMock(misra=_FakeMisra(active, profiles))

    def test_valid(self, tmp_path):
        from yuleosh.ci.profile import validate_active_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        return_value=self._cfg("safety")):
            ok, msg = validate_active_profile(str(tmp_path))
        assert ok is True
        assert "safety" in msg

    def test_cannot_load_config(self, tmp_path):
        from yuleosh.ci.profile import validate_active_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        side_effect=RuntimeError("no config")):
            ok, msg = validate_active_profile(str(tmp_path))
        assert ok is False
        assert "Cannot load" in msg

    def test_unknown_profile(self, tmp_path):
        from yuleosh.ci.profile import validate_active_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        return_value=self._cfg("bogus")):
            ok, msg = validate_active_profile(str(tmp_path))
        assert ok is False
        assert "not found" in msg

    def test_profile_not_in_custom(self, tmp_path):
        from yuleosh.ci.profile import validate_active_profile
        # active 在内置里但不在自定义 profiles 中 → 仍然有效（OR 条件）
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        return_value=self._cfg("safety", {"custom": object()})):
            ok, _ = validate_active_profile(str(tmp_path))
        assert ok is True

    def test_only_one_profile_total(self, tmp_path):
        # 内置 4 个 profile，无法构造 <2 的场景 —— 直接 patch BUILTIN_PROFILES
        # （clear=True 必须：patch.dict 默认合并，不替换原 4 个 profile）
        import yuleosh.ci.profile as prof
        from yuleosh.ci.profile import validate_active_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        return_value=self._cfg("safety")), \
             mock.patch.dict(prof.BUILTIN_PROFILES, {"safety": {}}, clear=True):
            ok, msg = validate_active_profile(str(tmp_path))
        assert ok is False
        assert "At least 2 profiles" in msg


class TestFilterSteps:
    STEPS: tuple = (
        ("super-analysis", "a", "Super", None),
        ("code-review", "b", "Review", None),
        ("unit-tests", "c", "Unit", None),
    )

    def test_ci_excludes(self):
        from yuleosh.ci.profile import filter_steps_for_profile
        filtered = filter_steps_for_profile(self.STEPS, "ci")
        assert [s[0] for s in filtered] == ["unit-tests"]

    def test_include_whitelist(self):
        from yuleosh.ci.profile import filter_steps_for_profile
        # 注意：filter_steps_for_profile 的默认参数会求值 BUILTIN_PROFILES["safety"]，
        # patch 的 dict 必须包含 safety 键否则 KeyError。
        with mock.patch("yuleosh.ci.profile.BUILTIN_PROFILES", {
            "mini": {"description": "", "include_steps": ["code-review"],
                     "exclude_steps": []},
            "safety": {"description": "", "exclude_steps": []},
        }):
            filtered = filter_steps_for_profile(self.STEPS, "mini")
        assert [s[0] for s in filtered] == ["code-review"]

    def test_unknown_profile_falls_back_to_safety(self):
        from yuleosh.ci.profile import filter_steps_for_profile
        filtered = filter_steps_for_profile(self.STEPS, "does-not-exist")
        assert len(filtered) == 3

    def test_custom_override(self, tmp_path):
        """方向1: 自定义 exclude_steps 追加到 base（不变量3 差集等价）。

        旧语义「覆盖」会丢掉 ci 档默认排除（super-analysis/code-review），
        违反不变量3。新语义: 在 ci 档默认排除上追加 unit-tests → 全部排除。
        """
        from yuleosh.ci.profile import filter_steps_for_profile
        custom = mock.MagicMock(exclude_steps=["unit-tests"])
        cfg = mock.MagicMock(misra=_FakeMisra("ci", {"ci": custom}))
        with mock.patch("yuleosh.ci.profile._get_ci_config", return_value=cfg):
            filtered = filter_steps_for_profile(self.STEPS, "ci", str(tmp_path))
        # ci 档默认排除 super-analysis/code-review + 自定义追加 unit-tests
        assert [s[0] for s in filtered] == []

    def test_config_load_error_falls_back(self, tmp_path):
        from yuleosh.ci.profile import filter_steps_for_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        side_effect=RuntimeError("no cfg")):
            filtered = filter_steps_for_profile(self.STEPS, "ci", str(tmp_path))
        assert [s[0] for s in filtered] == ["unit-tests"]


class TestGetCurrentProfile:
    def test_configured(self, tmp_path):
        from yuleosh.ci.profile import get_current_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        return_value=mock.MagicMock(misra=_FakeMisra("testing"))):
            assert get_current_profile(str(tmp_path)) == "testing"

    def test_fallback(self, tmp_path):
        from yuleosh.ci.profile import get_current_profile
        with mock.patch("yuleosh.ci.profile._get_ci_config",
                        side_effect=Exception("boom")):
            assert get_current_profile(str(tmp_path)) == "safety"


class TestProfileAudit:
    def test_get_git_commit(self, tmp_path):
        from yuleosh.ci.profile import _get_git_commit
        proc = mock.MagicMock(returncode=0, stdout="abc1234\n")
        with mock.patch("yuleosh.ci.profile._subprocess.run", return_value=proc):
            assert _get_git_commit(str(tmp_path)) == "abc1234"

    def test_get_git_commit_unknown(self, tmp_path):
        from yuleosh.ci.profile import _get_git_commit
        proc = mock.MagicMock(returncode=1, stdout="")
        with mock.patch("yuleosh.ci.profile._subprocess.run", return_value=proc):
            assert _get_git_commit(str(tmp_path)) == "unknown"

    def test_get_git_commit_exception(self, tmp_path):
        from yuleosh.ci.profile import _get_git_commit
        with mock.patch("yuleosh.ci.profile._subprocess.run",
                        side_effect=OSError("no git")):
            assert _get_git_commit(str(tmp_path)) == "unknown"

    def test_get_git_user(self, tmp_path):
        from yuleosh.ci.profile import _get_git_user
        proc = mock.MagicMock(returncode=0, stdout="dev\n")
        with mock.patch("yuleosh.ci.profile._subprocess.run", return_value=proc):
            assert _get_git_user(str(tmp_path)) == "dev"

    def test_get_git_user_unknown(self, tmp_path):
        from yuleosh.ci.profile import _get_git_user
        with mock.patch("yuleosh.ci.profile._subprocess.run",
                        side_effect=Exception("x")):
            assert _get_git_user(str(tmp_path)) == "unknown"

    def test_record_profile_change_with_user(self, tmp_path):
        from yuleosh.ci.profile import record_profile_change
        entry = record_profile_change(str(tmp_path), "safety", "ci",
                                      user="alice", reason="speed")
        assert entry["user"] == "alice"
        assert entry["old_profile"] == "safety"
        assert entry["new_profile"] == "ci"
        assert entry["reason"] == "speed"
        log_path = tmp_path / ".yuleosh" / "reports" / "profile-audit.jsonl"
        assert log_path.exists()
        line = json.loads(log_path.read_text().strip())
        assert line["user"] == "alice"

    def test_record_profile_change_auto_user(self, tmp_path):
        from yuleosh.ci.profile import record_profile_change
        with mock.patch("yuleosh.ci.profile._get_git_user",
                        return_value="auto-user"), \
             mock.patch("yuleosh.ci.profile._get_git_commit",
                        return_value="c0ffee"):
            entry = record_profile_change(str(tmp_path), "ci", "safety")
        assert entry["user"] == "auto-user"
        assert entry["commit"] == "c0ffee"

    def test_get_audit_log_missing_file(self, tmp_path):
        from yuleosh.ci.profile import get_profile_audit_log
        assert "No profile change audit" in get_profile_audit_log(str(tmp_path))
        assert get_profile_audit_log(str(tmp_path), as_json=True) == json.dumps(
            {"error": "*No profile change audit records found.*"})

    def test_get_audit_log_as_json(self, tmp_path):
        from yuleosh.ci.profile import get_profile_audit_log, record_profile_change
        record_profile_change(str(tmp_path), "a", "b", user="u")
        record_profile_change(str(tmp_path), "b", "c", user="v")
        out = json.loads(get_profile_audit_log(str(tmp_path), as_json=True))
        assert out["total_entries"] == 2
        # 最近在前
        assert out["entries"][0]["old_profile"] == "b"

    def test_get_audit_log_text(self, tmp_path):
        from yuleosh.ci.profile import get_profile_audit_log, record_profile_change
        record_profile_change(str(tmp_path), "safety", "ci", user="u")
        text = get_profile_audit_log(str(tmp_path))
        assert "safety" in text
        assert "ci" in text
        assert "| 1 |" in text

    def test_get_audit_log_skips_bad_lines(self, tmp_path):
        from yuleosh.ci.profile import get_profile_audit_log
        log_path = tmp_path / ".yuleosh" / "reports" / "profile-audit.jsonl"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("{bad json}\n" + json.dumps({"old_profile": "x"}) + "\n")
        out = json.loads(get_profile_audit_log(str(tmp_path), as_json=True))
        assert out["total_entries"] == 1

    def test_get_audit_log_empty_after_filter(self, tmp_path):
        from yuleosh.ci.profile import get_profile_audit_log
        log_path = tmp_path / ".yuleosh" / "reports" / "profile-audit.jsonl"
        log_path.parent.mkdir(parents=True)
        log_path.write_text(json.dumps({"old_profile": "x"}) + "\n")
        text = get_profile_audit_log(str(tmp_path), limit=0)
        assert "*无记录*" in text


# =====================================================================
# ci/dashboard_writer.py
# =====================================================================

class TestCheckKgAvailable:
    def test_available(self):
        from yuleosh.ci import dashboard_writer as dw
        with mock.patch("yuleosh.ci.dashboard_writer._HAS_KG", None), \
             mock.patch.dict("sys.modules", {"yuleosh.knowledge_graph": mock.MagicMock()}):
            assert dw._check_kg_available() is True

    def test_unavailable(self):
        from yuleosh.ci import dashboard_writer as dw
        # from yuleosh import knowledge_graph 走包属性，patch sys.modules 无效；
        # 直接拦截 __import__ 抛 ImportError 测 import 失败分支。
        with mock.patch("yuleosh.ci.dashboard_writer._HAS_KG", None), \
             mock.patch("builtins.__import__",
                        side_effect=ImportError("no kg")):
            assert dw._check_kg_available() is False


class TestSweStatusFromKg:
    def test_kg_unavailable(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=False):
            assert _swe_status_from_kg(tmp_path) == {}

    def test_no_db_file(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=True):
            assert _swe_status_from_kg(tmp_path) == {}

    def test_store_open_exception(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "knowledge_graph.db").write_bytes(b"x")
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=True), \
             mock.patch("yuleosh.knowledge_graph.get_store",
                        side_effect=RuntimeError("corrupt db")):
            assert _swe_status_from_kg(tmp_path) == {}

    def test_zero_nodes(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "knowledge_graph.db").write_bytes(b"x")
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=True), \
             mock.patch("yuleosh.knowledge_graph.get_store",
                        return_value=mock.MagicMock()), \
             mock.patch("yuleosh.knowledge_graph.get_graph_stats",
                        return_value={"total_nodes": 0}):
            assert _swe_status_from_kg(tmp_path) == {}

    def test_full_status(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "knowledge_graph.db").write_bytes(b"x")
        stats = {"total_nodes": 10,
                 "nodes_by_type": {"requirement": 5},
                 "edges_by_type": {"covers": 5}}
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=True), \
             mock.patch("yuleosh.knowledge_graph.get_store",
                        return_value=mock.MagicMock()), \
             mock.patch("yuleosh.knowledge_graph.get_graph_stats",
                        return_value=stats), \
             mock.patch("yuleosh.knowledge_graph.get_confirmation_trace",
                        return_value=[{"id": 1}]), \
             mock.patch("yuleosh.knowledge_graph.list_snapshots",
                        return_value=[1, 2, 3]), \
             mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage",
                        return_value={"unit": {"total_covers": 2}}):
            status = _swe_status_from_kg(tmp_path)
        assert status["SWE.4"] == "completed"
        assert status["SWE.5"] == "completed"
        assert status["SWE.8"] == "validated"  # 3 snapshots
        assert status["SWE.10"] == "validated"  # covers >= reqs

    def test_snapshots_partial(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "knowledge_graph.db").write_bytes(b"x")
        stats = {"total_nodes": 1, "nodes_by_type": {}, "edges_by_type": {}}
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=True), \
             mock.patch("yuleosh.knowledge_graph.get_store",
                        return_value=mock.MagicMock()), \
             mock.patch("yuleosh.knowledge_graph.get_graph_stats",
                        return_value=stats), \
             mock.patch("yuleosh.knowledge_graph.get_confirmation_trace",
                        return_value=[]), \
             mock.patch("yuleosh.knowledge_graph.list_snapshots",
                        return_value=[1]), \
             mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage",
                        return_value={"unit": {"total_covers": 0}}):
            status = _swe_status_from_kg(tmp_path)
        assert status["SWE.8"] == "completed"

    def test_query_exception_falls_back(self, tmp_path):
        from yuleosh.ci.dashboard_writer import _swe_status_from_kg
        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "knowledge_graph.db").write_bytes(b"x")
        with mock.patch("yuleosh.ci.dashboard_writer._check_kg_available",
                        return_value=True), \
             mock.patch("yuleosh.knowledge_graph.get_store",
                        return_value=mock.MagicMock()), \
             mock.patch("yuleosh.knowledge_graph.get_graph_stats",
                        side_effect=RuntimeError("query failed")):
            assert _swe_status_from_kg(tmp_path) == {}


class TestWriteSweStatus:
    def test_full_evidence_classification(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        # SWE.1: spec
        (tmp_path / "docs").mkdir(parents=True)
        (tmp_path / "docs" / "spec.md").write_text("# spec")
        (tmp_path / ".osh" / "sessions" / "s1").mkdir(parents=True)
        (tmp_path / ".osh" / "sessions" / "s1" / "spec-check.json").write_text("{}")
        # SWE.2: arch
        (tmp_path / "docs" / "architecture.md").write_text("# arch")
        # SWE.3: design
        (tmp_path / "docs" / "design.md").write_text("# design")
        # SWE.4: misra report
        (tmp_path / ".yuleosh" / "reports").mkdir(parents=True)
        (tmp_path / ".yuleosh" / "reports" / "misra-report.json").write_text(
            json.dumps({"summary": {"total_violations": 3}}))
        # SWE.5: integration tests
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_integration_x.py").write_text("x")
        # SWE.6: swe6 spec + tests
        (tmp_path / "docs" / "swe6-confirmation-spec.md").write_text("x")
        (tmp_path / "tests" / "test_swe6").mkdir()
        (tmp_path / "tests" / "test_swe6" / "t.py").write_text("x")
        # SWE.7: review report + code-review.json
        (tmp_path / ".yuleosh" / "reports" / "gscr-report.json").write_text("{}")
        (tmp_path / "sessions" / "x").mkdir(parents=True)
        (tmp_path / "sessions" / "x" / "code-review.json").write_text("{}")
        # SWE.8: ci reports
        (tmp_path / ".yuleosh" / "reports" / "ci-final-report.json").write_text("{}")
        (tmp_path / ".yuleosh" / "reports" / "layer1-report.json").write_text("{}")
        # SWE.9: defect log
        (tmp_path / ".yuleosh" / "reports" / "defect-escape.jsonl").write_text("x\n")
        # SWE.10: traceability
        (tmp_path / ".yuleosh" / "reports" / "traceability-report.json").write_text("{}")

        with mock.patch("yuleosh.ci.dashboard_writer._swe_status_from_kg",
                        return_value={}):
            record = write_swe_status(tmp_path, force=True)
        status = record["status"]
        # spec defined + spec validated:1 → 2 条 → completed
        assert status["SWE.1"] in ("completed", "validated")
        assert status["SWE.6"] == "completed"
        # 文件已写入
        db = tmp_path / ".yuleosh" / "reports" / "swe-status.jsonl"
        assert db.exists()

    def test_misra_unreadable(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        (tmp_path / ".yuleosh" / "reports").mkdir(parents=True)
        (tmp_path / ".yuleosh" / "reports" / "misra-report.json").write_text("{bad")
        with mock.patch("yuleosh.ci.dashboard_writer._swe_status_from_kg",
                        return_value={}):
            record = write_swe_status(tmp_path, force=True)
        assert any("unreadable" in e for ev in record["evidence_summary"].values()
                   for e in ev)

    def test_skip_unchanged(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        db = tmp_path / ".yuleosh" / "reports" / "swe-status.jsonl"
        db.parent.mkdir(parents=True)
        first = write_swe_status(tmp_path, force=True)
        # 再次写入（状态未变，force=False）→ 不追加
        second = write_swe_status(tmp_path, force=False)
        lines = db.read_text().strip().split("\n")
        assert len(lines) == 1
        assert second["status"] == first["status"]

    def test_force_appends(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        db = tmp_path / ".yuleosh" / "reports" / "swe-status.jsonl"
        db.parent.mkdir(parents=True)
        write_swe_status(tmp_path, force=True)
        write_swe_status(tmp_path, force=True)
        assert len(db.read_text().strip().split("\n")) == 2

    def test_spec_path_provided(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        spec = tmp_path / "custom-spec.md"
        spec.write_text("# s")
        with mock.patch("yuleosh.ci.dashboard_writer._swe_status_from_kg",
                        return_value={}):
            record = write_swe_status(tmp_path, spec_path=str(spec), force=True)
        assert record["status"]["SWE.1"] != "not_started"

    def test_spec_path_missing_falls_back(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        with mock.patch("yuleosh.ci.dashboard_writer._swe_status_from_kg",
                        return_value={}):
            record = write_swe_status(tmp_path, spec_path=str(tmp_path / "nope.md"),
                                      force=True)
        assert record["status"]["SWE.1"] == "not_started"

    def test_kg_merge_overrides(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_swe_status
        with mock.patch("yuleosh.ci.dashboard_writer._swe_status_from_kg",
                        return_value={"SWE.4": "validated", "SWE.10": "completed"}):
            record = write_swe_status(tmp_path, force=True)
        assert record["status"]["SWE.4"] == "validated"
        assert record["status"]["SWE.10"] == "completed"


class TestWriteCoverageTrend:
    def test_writes_and_reads(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_coverage_trend
        trend_file = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend_file.parent.mkdir(parents=True)
        entry = {"c": {"line_rate": 87.5, "branch_rate": 80.0}}
        with mock.patch("yuleosh.ci.coverage_trend.record_coverage") as mrec:
            def _record(project_dir):
                trend_file.write_text(json.dumps(entry) + "\n")
            mrec.side_effect = _record
            latest = write_coverage_trend(tmp_path)
        assert latest["c"]["line_rate"] == 87.5
        mrec.assert_called_once_with(str(tmp_path))

    def test_no_trend_file(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_coverage_trend
        with mock.patch("yuleosh.ci.coverage_trend.record_coverage"):
            assert write_coverage_trend(tmp_path) == {}


class TestWriteKpiTrend:
    def _seed(self, tmp_path):
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "misra-report.json").write_text(
            json.dumps({"summary": {"total_violations": 7}}))
        (reports / "coverage-trend.jsonl").write_text(
            json.dumps({"c": {"line_rate": 90.0, "branch_rate": 85.0}}) + "\n")
        (reports / "ci-final-report.json").write_text(
            json.dumps({"status": "passed", "layers": [1, 2]}))

    def test_full_kpi(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_kpi_trend
        self._seed(tmp_path)
        cfg = mock.MagicMock(misra=mock.MagicMock(deviations=[1, 2]))
        with mock.patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            kpi = write_kpi_trend(tmp_path, force=True)
        assert kpi["misra_violations"] == 7
        assert kpi["c_line_coverage"] == 90.0
        assert kpi["c_branch_coverage"] == 85.0
        assert kpi["ci_status"] == "passed"
        assert kpi["deviations_count"] == 2

    def test_skip_unchanged(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_kpi_trend
        self._seed(tmp_path)
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=mock.MagicMock(misra=None)):
            write_kpi_trend(tmp_path, force=True)
            kpi2 = write_kpi_trend(tmp_path, force=False)
        db = tmp_path / ".yuleosh" / "reports" / "process-kpi.jsonl"
        assert len(db.read_text().strip().split("\n")) == 1
        assert kpi2["misra_violations"] == 7

    def test_bad_reports_ignored(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_kpi_trend
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "misra-report.json").write_text("{bad")
        (reports / "coverage-trend.jsonl").write_text("{bad\n")
        (reports / "ci-final-report.json").write_text("{bad")
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=mock.MagicMock(misra=None)):
            kpi = write_kpi_trend(tmp_path, force=True)
        assert "misra_violations" not in kpi
        assert "ci_status" not in kpi

    def test_no_misra_config(self, tmp_path):
        from yuleosh.ci.dashboard_writer import write_kpi_trend
        with mock.patch("yuleosh.ci.config.load_ci_config", return_value=None):
            kpi = write_kpi_trend(tmp_path, force=True)
        assert "deviations_count" not in kpi


class TestRunDashboardUpdate:
    def test_orchestrator_and_bundle(self, tmp_path):
        from yuleosh.ci.dashboard_writer import run_dashboard_update
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "coverage-trend.jsonl").write_text("x\n")
        (reports / "process-kpi.jsonl").write_text("y\n")
        (reports / "swe-status.jsonl").write_text("z\n")
        (reports / "misra-trend.jsonl").write_text("m\n")
        with mock.patch("yuleosh.ci.dashboard_writer.write_swe_status",
                        return_value={"status": {"SWE.1": "completed"}}), \
             mock.patch("yuleosh.ci.dashboard_writer.write_coverage_trend",
                        return_value={"c": {"line_rate": 88.0}}), \
             mock.patch("yuleosh.ci.dashboard_writer.write_kpi_trend",
                        return_value={"misra_violations": 1}):
            result = run_dashboard_update(tmp_path, force=True)
        assert result["status"] == "completed"
        assert result["swe_status"]["status"]["SWE.1"] == "completed"
        # evidence-bundle 镜像
        bundle = tmp_path / ".yuleosh" / "evidence-bundle" / "trend-data"
        assert (bundle / "coverage-trend.jsonl").exists()
        assert (bundle / "misra-trend.jsonl").exists()
        assert not (bundle / "nonexistent.jsonl").exists()
