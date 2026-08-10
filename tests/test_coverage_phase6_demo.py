"""Phase 6 coverage boost — api/demo 域低覆盖文件（demo_uart CLI、kb API、demo_quick）。

Target modules (Phase 6 baseline, 2026-08-10):
  - src/yuleosh/cli/commands/demo_uart.py   0.0%  → 模板复制/构建/工具检查/主命令全分支
  - src/yuleosh/api/kb.py                  0.0%  → articles/lessons/fmea CRUD 路由全分支
  - src/yuleosh/api/demo_quick.py          0.0%  → spec 生成/mock LLM/管线步骤/证据打包/main

风格：直测函数/分支，子进程与外部命令全部 mock，文件操作全部落在 tmp_path。
KB 使用真实 SQLite（tmp 库），demo_quick 的 10 个 step handler 全部 mock
（不真跑管线、不碰网络、不执行子进程）。
"""

import contextlib
import os
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.api import demo_quick
from yuleosh.api import kb as kb_mod
from yuleosh.cli.commands import demo_uart
from yuleosh.kb.store import KbStore

# =====================================================================
# cli/commands/demo_uart.py — 工具检查
# =====================================================================


class TestDemoUartCheckTool:
    def test_tool_found(self, capsys):
        """shutil.which 命中 → 返回 True 并打印 ✅。"""
        with mock.patch.object(demo_uart.shutil, "which", return_value="/usr/bin/gcc"):
            assert demo_uart._check_tool("gcc") is True
        out = capsys.readouterr().out
        assert "gcc" in out
        assert "✅" in out

    def test_tool_missing(self, capsys):
        """shutil.which 未命中 → 返回 False 并打印 ⚠️。"""
        with mock.patch.object(demo_uart.shutil, "which", return_value=None):
            assert demo_uart._check_tool("gcc") is False
        out = capsys.readouterr().out
        assert "gcc" in out
        assert "⚠️" in out


# =====================================================================
# cli/commands/demo_uart.py — 模板复制
# =====================================================================


class TestDemoUartCopyTemplate:
    @staticmethod
    def _make_template_tree(root: Path, missing: set[str] | None = None) -> Path:
        """在 tmp 下构造一份 TEMPLATE_FILES 模板树（可指定缺失文件）。"""
        src = root / "templates"
        missing = missing or set()
        for rel in demo_uart.TEMPLATE_FILES:
            if rel in missing:
                continue
            f = src / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"content of {rel}\n", encoding="utf-8")
        return src

    def test_copies_all_template_files(self, tmp_path):
        """全量模板 → 逐文件 copy2 到目标目录，并补 .gitkeep。"""
        src = self._make_template_tree(tmp_path)
        target = tmp_path / "out"
        with mock.patch.object(demo_uart, "TEMPLATE_DIR", src):
            result = demo_uart._copy_template(target)
        assert result == target
        for rel in demo_uart.TEMPLATE_FILES:
            copied = target / rel
            assert copied.exists(), f"missing copied file: {rel}"
            assert "content of" in copied.read_text(encoding="utf-8")
        for sub in ("stm32", "esp32", "cmake"):
            assert (target / sub / ".gitkeep").exists()

    def test_missing_template_prints_warning(self, tmp_path, capsys):
        """模板源缺失个别文件 → 跳过 copy2 并打印警告。"""
        src = self._make_template_tree(tmp_path, missing={"README.md"})
        target = tmp_path / "out"
        with mock.patch.object(demo_uart, "TEMPLATE_DIR", src):
            demo_uart._copy_template(target)
        out = capsys.readouterr().out
        assert "Template file missing" in out
        assert not (target / "README.md").exists()
        assert (target / "CMakeLists.txt").exists()


# =====================================================================
# cli/commands/demo_uart.py — host 模式构建
# =====================================================================


class TestDemoUartBuildHost:
    @staticmethod
    def _ok(returncode: int = 0, stderr: str = "") -> mock.Mock:
        return mock.Mock(returncode=returncode, stderr=stderr, stdout="")

    def _make_project(self, tmp_path, with_exe: bool = True):
        """构造目标目录 + build_host + 可选 demo 可执行文件。"""
        target = tmp_path / "proj"
        build_dir = target / "build_host"
        build_dir.mkdir(parents=True)
        if with_exe:
            (build_dir / "uart_demo_host").write_text("#!/bin/sh\n", encoding="utf-8")
        return target

    def test_build_success_runs_demo(self, tmp_path, capsys):
        """cmake/make/demo 全部成功 → 返回 True。"""
        target = self._make_project(tmp_path)
        runs = [self._ok(), self._ok(), self._ok(returncode=0)]
        with mock.patch.object(demo_uart.subprocess, "run", side_effect=runs) as m:
            assert demo_uart._build_host(target) is True
        assert m.call_count == 3
        assert m.call_args_list[0].args[0] == ["cmake", "-DTARGET=host", ".."]
        assert m.call_args_list[1].args[0] == ["make", "-j", str(os.cpu_count() or 4)]
        out = capsys.readouterr().out
        assert "CMake configured" in out
        assert "Build succeeded" in out
        assert "Demo exited with code 0" in out

    def test_build_demo_rc_nonzero_returns_false(self, tmp_path):
        """demo 可执行文件返回非 0 → 返回 False。"""
        target = self._make_project(tmp_path)
        runs = [self._ok(), self._ok(), self._ok(returncode=3)]
        with mock.patch.object(demo_uart.subprocess, "run", side_effect=runs):
            assert demo_uart._build_host(target) is False

    def test_cmake_timeout_returns_false(self, tmp_path, capsys):
        """cmake 超时（TimeoutExpired）→ 打印超时并返回 False。"""
        target = self._make_project(tmp_path)
        with mock.patch.object(
            demo_uart.subprocess, "run",
            side_effect=demo_uart.subprocess.TimeoutExpired("cmake", 120),
        ):
            assert demo_uart._build_host(target) is False
        assert "CMake 超时" in capsys.readouterr().out

    def test_cmake_failure_returns_false(self, tmp_path, capsys):
        """cmake 返回非 0 → 打印 stderr 并返回 False。"""
        target = self._make_project(tmp_path)
        with mock.patch.object(
            demo_uart.subprocess, "run",
            side_effect=[self._ok(returncode=1, stderr="cmake boom")],
        ):
            assert demo_uart._build_host(target) is False
        out = capsys.readouterr().out
        assert "CMake failed" in out
        assert "cmake boom" in out

    def test_make_timeout_returns_false(self, tmp_path):
        """make 超时 → 返回 False。"""
        target = self._make_project(tmp_path)
        runs = [self._ok(), demo_uart.subprocess.TimeoutExpired("make", 300)]
        with mock.patch.object(demo_uart.subprocess, "run", side_effect=runs):
            assert demo_uart._build_host(target) is False

    def test_make_failure_returns_false(self, tmp_path, capsys):
        """make 返回非 0 → 打印 stderr 并返回 False。"""
        target = self._make_project(tmp_path)
        runs = [self._ok(), self._ok(returncode=2, stderr="make boom")]
        with mock.patch.object(demo_uart.subprocess, "run", side_effect=runs):
            assert demo_uart._build_host(target) is False
        out = capsys.readouterr().out
        assert "Build failed" in out
        assert "make boom" in out

    def test_demo_binary_missing_returns_false(self, tmp_path, capsys):
        """demo 可执行文件不存在 → 警告并返回 False（不跑 demo）。"""
        target = self._make_project(tmp_path, with_exe=False)
        runs = [self._ok(), self._ok()]
        with mock.patch.object(demo_uart.subprocess, "run", side_effect=runs) as m:
            assert demo_uart._build_host(target) is False
        assert m.call_count == 2
        assert "Demo binary not found" in capsys.readouterr().out

    def test_demo_run_timeout_returns_false(self, tmp_path):
        """demo 运行超时 → 返回 False。"""
        target = self._make_project(tmp_path)
        runs = [self._ok(), self._ok(), demo_uart.subprocess.TimeoutExpired("uart_demo_host", 120)]
        with mock.patch.object(demo_uart.subprocess, "run", side_effect=runs):
            assert demo_uart._build_host(target) is False


# =====================================================================
# cli/commands/demo_uart.py — 主命令 cmd_demo_uart
# =====================================================================


class TestCmdDemoUart:
    @staticmethod
    def _patch_tools(gcc: bool = True, cmake: bool = True, arm: bool = True):
        """按工具名分别控制 _check_tool 返回值。"""
        table = {"gcc": gcc, "cmake": cmake, "arm-none-eabi-gcc": arm}

        def _check(name: str) -> bool:
            return table[name]

        return mock.patch.object(demo_uart, "_check_tool", side_effect=_check)

    def test_default_dir_no_build(self, tmp_path, monkeypatch):
        """无参数 → 目标为 cwd/demos/uart，do_build=False 不触发构建。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(), mock.patch.object(
            demo_uart, "_copy_template", return_value=tmp_path / "demos" / "uart"
        ) as copy, mock.patch.object(demo_uart, "_build_host") as build:
            rc = demo_uart.cmd_demo_uart()
        assert rc == 0
        copy.assert_called_once_with(tmp_path / "demos" / "uart")
        build.assert_not_called()

    def test_explicit_target_dir(self, tmp_path, monkeypatch):
        """显式 --dir → target 按 resolve() 展开。"""
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "custom"
        with self._patch_tools(), mock.patch.object(
            demo_uart, "_copy_template", return_value=target
        ) as copy:
            rc = demo_uart.cmd_demo_uart(target_dir=str(target))
        assert rc == 0
        copy.assert_called_once_with(target.resolve())

    def test_skip_cmake_forces_no_build(self, tmp_path, monkeypatch):
        """--skip-cmake → 即使 cmake 存在也跳过构建。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(gcc=True, cmake=True), mock.patch.object(
            demo_uart, "_copy_template"
        ), mock.patch.object(demo_uart, "_build_host") as build:
            rc = demo_uart.cmd_demo_uart(do_build=True, skip_cmake=True)
        assert rc == 0
        build.assert_not_called()

    def test_build_requires_gcc(self, tmp_path, monkeypatch, capsys):
        """--build 但无 gcc → 返回 1 并提示 gcc required。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(gcc=False, cmake=True), mock.patch.object(
            demo_uart, "_copy_template"
        ):
            rc = demo_uart.cmd_demo_uart(do_build=True)
        assert rc == 1
        assert "gcc is required for --build" in capsys.readouterr().out

    def test_build_without_cmake_skips_build(self, tmp_path, monkeypatch):
        """有 gcc 但无 cmake → 不调用 _build_host。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(gcc=True, cmake=False), mock.patch.object(
            demo_uart, "_copy_template"
        ), mock.patch.object(demo_uart, "_build_host") as build:
            rc = demo_uart.cmd_demo_uart(do_build=True)
        assert rc == 0
        build.assert_not_called()

    def test_build_success_path(self, tmp_path, monkeypatch):
        """有 gcc + cmake + do_build → 调用 _build_host 一次。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(), mock.patch.object(
            demo_uart, "_copy_template"
        ), mock.patch.object(demo_uart, "_build_host", return_value=True) as build:
            rc = demo_uart.cmd_demo_uart(do_build=True)
        assert rc == 0
        build.assert_called_once()

    def test_build_issues_warning(self, tmp_path, monkeypatch, capsys):
        """_build_host 返回 False → 打印 Build had issues，rc 仍为 0。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(), mock.patch.object(
            demo_uart, "_copy_template"
        ), mock.patch.object(demo_uart, "_build_host", return_value=False):
            rc = demo_uart.cmd_demo_uart(do_build=True)
        assert rc == 0
        assert "Build had issues" in capsys.readouterr().out

    def test_summary_with_arm_gcc(self, tmp_path, monkeypatch, capsys):
        """安装 arm-none-eabi-gcc → 打印 STM32 交叉编译提示。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(arm=True), mock.patch.object(demo_uart, "_copy_template"):
            assert demo_uart.cmd_demo_uart() == 0
        assert "cmake -DTARGET=stm32f4" in capsys.readouterr().out

    def test_summary_without_arm_gcc(self, tmp_path, monkeypatch, capsys):
        """未安装 arm-none-eabi-gcc → 打印安装建议。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(arm=False), mock.patch.object(demo_uart, "_copy_template"):
            assert demo_uart.cmd_demo_uart() == 0
        assert "Install arm-none-eabi-gcc" in capsys.readouterr().out

    def test_banner_and_footer(self, tmp_path, monkeypatch, capsys):
        """Banner / Step 标题 / 完成提示均输出。"""
        monkeypatch.chdir(tmp_path)
        with self._patch_tools(), mock.patch.object(demo_uart, "_copy_template"):
            demo_uart.cmd_demo_uart()
        out = capsys.readouterr().out
        assert "y u l e O S H   D E M O   U A R T" in out
        assert "Step 1/4" in out
        assert "Step 2/4" in out
        assert "Step 4/4" in out
        assert "Demo complete!" in out


# =====================================================================
# api/kb.py — 路由分发与鉴权短路
# =====================================================================


@pytest.fixture
def kb_store(tmp_path):
    """真实 SQLite KbStore，落在 tmp_path，不污染仓库 .yuleosh/kb.db。"""
    store = KbStore(str(tmp_path / "kb.db"))
    yield store
    store.close()


@pytest.fixture
def kb_api(kb_store):
    """把 kb._get_kb_store 替换为共享的临时 store 实例。"""
    with mock.patch.object(kb_mod, "_get_kb_store", return_value=kb_store):
        yield kb_store


def _kb_call(method: str, tail: str, body: dict | None = None, query: dict | None = None):
    """经 require_auth 包装调用 handle_kb，注入 current_user 绕过 JWT。"""
    return kb_mod.handle_kb(
        method, tail, body or {}, query or {},
        current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"},
    )


class TestKbRouting:
    def test_empty_tail_404(self):
        """空 path_tail → KB resource required 404。"""
        result, status = _kb_call("GET", "")
        assert result["ok"] is False
        assert status == 404
        assert "KB resource required" in result["error"]

    def test_unknown_resource_404(self):
        """未知资源名 → 404。"""
        result, status = _kb_call("GET", "widgets")
        assert status == 404
        assert "Unknown KB resource: widgets" in result["error"]

    def test_requires_auth_without_current_user(self):
        """未注入 current_user/handler → 401 短路（require_auth 兜底）。"""
        result, status = kb_mod.handle_kb("GET", "articles", {}, {})
        assert status == 401
        assert result["ok"] is False

    def test_resource_routing_dispatches(self, kb_api):
        """articles/lessons/fmea 分别路由到各自 handler。"""
        for resource in ("articles", "lessons", "fmea"):
            result, status = _kb_call("GET", resource)
            assert status == 200
            assert result["ok"] is True


class TestKbHelpers:
    def test_get_kb_store_creates_store(self, tmp_path):
        """_get_kb_store 未打补丁时按 YULEOSH_KB_DB 创建真实 store。"""
        db = tmp_path / "kb-direct.db"
        with mock.patch.dict(os.environ, {"YULEOSH_KB_DB": str(db)}):
            store = kb_mod._get_kb_store()
        assert isinstance(store, KbStore)
        assert db.exists()
        store.close()

    def test_parse_id_variants(self):
        """_parse_id 覆盖空/纯数字/带子路径/非法 id。"""
        assert kb_mod._parse_id("") == (None, "")
        assert kb_mod._parse_id("7") == (7, "")
        assert kb_mod._parse_id("7/children") == (7, "children")
        assert kb_mod._parse_id("abc") == (None, "abc")

    def test_get_query_param(self):
        """_get_query_param 覆盖命中/缺失/默认值。"""
        query = {"search": ["uart"], "limit": ["5"]}
        assert kb_mod._get_query_param(query, "search") == "uart"
        assert kb_mod._get_query_param(query, "offset") == ""
        assert kb_mod._get_query_param(query, "offset", "0") == "0"
        assert kb_mod._get_query_param({}, "x", "d") == "d"


# =====================================================================
# api/kb.py — articles CRUD
# =====================================================================


class TestKbArticles:
    def test_get_by_id_found(self, kb_api):
        """GET /articles/<id> 命中 → 200 + to_dict。"""
        created, _ = _kb_call("POST", "articles", {"title": "MISRA", "content": "rule", "tags": "misra"})
        aid = created["data"]["id"]
        result, status = _kb_call("GET", f"articles/{aid}")
        assert status == 200
        assert result["data"]["title"] == "MISRA"

    def test_get_by_id_not_found(self, kb_api):
        """GET /articles/<id> 未命中 → 404。"""
        result, status = _kb_call("GET", "articles/9999")
        assert status == 404
        assert "Article not found" in result["error"]

    def test_list_defaults(self, kb_api):
        """GET /articles 无参数 → items/total/limit/offset 默认值。"""
        _kb_call("POST", "articles", {"title": "A1"})
        result, status = _kb_call("GET", "articles")
        assert status == 200
        assert len(result["data"]["items"]) == 1
        assert result["data"]["total"] == 1
        assert result["data"]["limit"] == 100
        assert result["data"]["offset"] == 0

    def test_list_with_search_limit_offset(self, kb_api):
        """GET /articles 带 search/limit/offset → 过滤 + 分页。"""
        for title in ("uart driver", "i2c driver", "spi driver"):
            _kb_call("POST", "articles", {"title": title})
        query = {"search": ["driver"], "limit": ["2"], "offset": ["1"]}
        result, _ = _kb_call("GET", "articles", query=query)
        assert result["data"]["total"] == 3
        assert len(result["data"]["items"]) == 2
        assert result["data"]["limit"] == 2
        assert result["data"]["offset"] == 1

    def test_post_ok(self, kb_api):
        """POST /articles 合法 body → 200 + 新文章。"""
        result, status = _kb_call("POST", "articles", {"title": "New", "content": "body"})
        assert status == 200
        assert result["data"]["title"] == "New"
        assert result["data"]["id"] >= 1

    def test_post_missing_title(self, kb_api):
        """POST /articles 缺 title → 400。"""
        result, status = _kb_call("POST", "articles", {"content": "no title"})
        assert status == 400
        assert "title is required" in result["error"]

    def test_put_ok(self, kb_api):
        """PUT /articles/<id> → 200 + 更新后的文章。"""
        created, _ = _kb_call("POST", "articles", {"title": "Old"})
        aid = created["data"]["id"]
        result, status = _kb_call("PUT", f"articles/{aid}", {"title": "New"})
        assert status == 200
        assert result["data"]["title"] == "New"

    def test_put_invalid_id_requires_id(self, kb_api):
        """PUT /articles/abc（id 非数字）→ 400 Article ID required。"""
        result, status = _kb_call("PUT", "articles/abc", {"title": "X"})
        assert status == 400
        assert "Article ID required" in result["error"]

    def test_put_no_valid_fields(self, kb_api):
        """PUT 只有非法字段 → 400 No valid fields。"""
        result, status = _kb_call("PUT", "articles/1", {"bogus": "x"})
        assert status == 400
        assert "No valid fields to update" in result["error"]

    def test_put_not_found(self, kb_api):
        """PUT 不存在的 id → 404。"""
        result, status = _kb_call("PUT", "articles/9999", {"title": "X"})
        assert status == 404
        assert "Article not found" in result["error"]

    def test_delete_ok(self, kb_api):
        """DELETE /articles/<id> → 200 + deleted: true。"""
        created, _ = _kb_call("POST", "articles", {"title": "Temp"})
        aid = created["data"]["id"]
        result, status = _kb_call("DELETE", f"articles/{aid}")
        assert status == 200
        assert result["data"] == {"deleted": True}

    def test_delete_invalid_id(self, kb_api):
        """DELETE /articles/abc → 400 Article ID required。"""
        result, status = _kb_call("DELETE", "articles/abc")
        assert status == 400
        assert "Article ID required" in result["error"]

    def test_delete_not_found(self, kb_api):
        """DELETE 不存在的 id → 404。"""
        result, status = _kb_call("DELETE", "articles/9999")
        assert status == 404
        assert "Article not found" in result["error"]

    def test_method_not_allowed(self, kb_api):
        """PATCH → 405。"""
        result, status = _kb_call("PATCH", "articles")
        assert status == 405
        assert "Method not allowed" in result["error"]


# =====================================================================
# api/kb.py — lessons CRUD
# =====================================================================


class TestKbLessons:
    def test_get_by_id_found(self, kb_api):
        """GET /lessons/<id> 命中 → 200。"""
        created, _ = _kb_call("POST", "lessons", {"title": "Lesson", "problem": "p", "solution": "s"})
        result, status = _kb_call("GET", f"lessons/{created['data']['id']}")
        assert status == 200
        assert result["data"]["title"] == "Lesson"

    def test_get_by_id_not_found(self, kb_api):
        """GET /lessons/<id> 未命中 → 404。"""
        result, status = _kb_call("GET", "lessons/9999")
        assert status == 404
        assert "Lesson not found" in result["error"]

    def test_list_with_filters(self, kb_api):
        """GET /lessons 带 project_id/severity 过滤。"""
        _kb_call("POST", "lessons", {"title": "L1", "project_id": "P1", "severity": "high"})
        _kb_call("POST", "lessons", {"title": "L2", "project_id": "P2", "severity": "low"})
        query = {"project_id": ["P1"], "severity": ["high"], "limit": ["10"], "offset": ["0"]}
        result, _ = _kb_call("GET", "lessons", query=query)
        assert result["data"]["total"] == 1
        assert result["data"]["items"][0]["title"] == "L1"

    def test_list_invalid_severity(self, kb_api):
        """GET /lessons 非法 severity → 400。"""
        result, status = _kb_call("GET", "lessons", query={"severity": ["extreme"]})
        assert status == 400
        assert "Invalid severity: extreme" in result["error"]

    def test_post_ok(self, kb_api):
        """POST /lessons 合法 → 200。"""
        result, status = _kb_call("POST", "lessons", {"title": "New", "problem": "p"})
        assert status == 200
        assert result["data"]["title"] == "New"

    def test_post_missing_title(self, kb_api):
        """POST /lessons 缺 title → 400。"""
        result, status = _kb_call("POST", "lessons", {"problem": "p"})
        assert status == 400
        assert "title is required" in result["error"]

    def test_put_ok(self, kb_api):
        """PUT /lessons/<id> → 200。"""
        created, _ = _kb_call("POST", "lessons", {"title": "Old"})
        result, status = _kb_call("PUT", f"lessons/{created['data']['id']}", {"title": "New"})
        assert status == 200
        assert result["data"]["title"] == "New"

    def test_put_invalid_id(self, kb_api):
        """PUT /lessons/abc → 400 Lesson ID required。"""
        result, status = _kb_call("PUT", "lessons/abc", {"title": "X"})
        assert status == 400
        assert "Lesson ID required" in result["error"]

    def test_put_no_valid_fields(self, kb_api):
        """PUT 只有非法字段 → 400。"""
        result, status = _kb_call("PUT", "lessons/1", {"bogus": 1})
        assert status == 400
        assert "No valid fields to update" in result["error"]

    def test_put_not_found(self, kb_api):
        """PUT 不存在的 id → 404。"""
        result, status = _kb_call("PUT", "lessons/9999", {"title": "X"})
        assert status == 404
        assert "Lesson not found" in result["error"]

    def test_delete_ok(self, kb_api):
        """DELETE /lessons/<id> → 200。"""
        created, _ = _kb_call("POST", "lessons", {"title": "Temp"})
        result, status = _kb_call("DELETE", f"lessons/{created['data']['id']}")
        assert status == 200
        assert result["data"] == {"deleted": True}

    def test_delete_invalid_id(self, kb_api):
        """DELETE /lessons/abc → 400。"""
        result, status = _kb_call("DELETE", "lessons/abc")
        assert status == 400
        assert "Lesson ID required" in result["error"]

    def test_delete_not_found(self, kb_api):
        """DELETE 不存在的 id → 404。"""
        result, status = _kb_call("DELETE", "lessons/9999")
        assert status == 404
        assert "Lesson not found" in result["error"]

    def test_method_not_allowed(self, kb_api):
        """PATCH → 405。"""
        _, status = _kb_call("PATCH", "lessons")
        assert status == 405


# =====================================================================
# api/kb.py — fmea CRUD
# =====================================================================


class TestKbFmea:
    def _create(self, kb_api, **overrides):
        body = {"item": "brake", "failure_mode": "no response", "severity": 9,
                "occurence": 5, "detection": 2}
        body.update(overrides)
        created, status = _kb_call("POST", "fmea", body)
        assert status == 200
        return created["data"]

    def test_get_by_id_found(self, kb_api):
        """GET /fmea/<id> 命中 → 200。"""
        data = self._create(kb_api)
        result, status = _kb_call("GET", f"fmea/{data['id']}")
        assert status == 200
        assert result["data"]["item"] == "brake"

    def test_get_by_id_not_found(self, kb_api):
        """GET /fmea/<id> 未命中 → 404。"""
        result, status = _kb_call("GET", "fmea/9999")
        assert status == 404
        assert "FMEA entry not found" in result["error"]

    def test_list_with_sorting(self, kb_api):
        """GET /fmea 带 sort_by/sort_desc=false → 200。"""
        self._create(kb_api)
        query = {"sort_by": ["severity"], "sort_desc": ["false"], "limit": ["5"], "offset": ["0"]}
        result, status = _kb_call("GET", "fmea", query=query)
        assert status == 200
        assert result["data"]["total"] == 1
        assert result["data"]["items"][0]["item"] == "brake"

    def test_list_default_sort_desc(self, kb_api):
        """GET /fmea 无 sort_desc → 默认降序（true）。"""
        self._create(kb_api)
        result, _ = _kb_call("GET", "fmea")
        assert result["data"]["items"][0]["item"] == "brake"

    def test_post_ok(self, kb_api):
        """POST /fmea 合法 → 200。"""
        result, status = _kb_call("POST", "fmea", {"item": "ecu", "failure_mode": "freeze"})
        assert status == 200
        assert result["data"]["item"] == "ecu"
        assert result["data"]["failure_mode"] == "freeze"

    def test_post_missing_item(self, kb_api):
        """POST /fmea 缺 item → 400。"""
        result, status = _kb_call("POST", "fmea", {"failure_mode": "freeze"})
        assert status == 400
        assert "item is required" in result["error"]

    def test_post_missing_failure_mode(self, kb_api):
        """POST /fmea 缺 failure_mode → 400。"""
        result, status = _kb_call("POST", "fmea", {"item": "ecu"})
        assert status == 400
        assert "failure_mode is required" in result["error"]

    def test_put_ok(self, kb_api):
        """PUT /fmea/<id> → 200。"""
        data = self._create(kb_api)
        result, status = _kb_call("PUT", f"fmea/{data['id']}", {"recommendation": "add watchdog"})
        assert status == 200
        assert result["data"]["recommendation"] == "add watchdog"

    def test_put_invalid_id(self, kb_api):
        """PUT /fmea/abc → 400 FMEA entry ID required。"""
        result, status = _kb_call("PUT", "fmea/abc", {"item": "x"})
        assert status == 400
        assert "FMEA entry ID required" in result["error"]

    def test_put_not_found(self, kb_api):
        """PUT 不存在的 id → 404。"""
        result, status = _kb_call("PUT", "fmea/9999", {"item": "x"})
        assert status == 404
        assert "FMEA entry not found" in result["error"]

    def test_delete_ok(self, kb_api):
        """DELETE /fmea/<id> → 200。"""
        data = self._create(kb_api)
        result, status = _kb_call("DELETE", f"fmea/{data['id']}")
        assert status == 200
        assert result["data"] == {"deleted": True}

    def test_delete_invalid_id(self, kb_api):
        """DELETE /fmea/abc → 400。"""
        result, status = _kb_call("DELETE", "fmea/abc")
        assert status == 400
        assert "FMEA entry ID required" in result["error"]

    def test_delete_not_found(self, kb_api):
        """DELETE 不存在的 id → 404。"""
        result, status = _kb_call("DELETE", "fmea/9999")
        assert status == 404
        assert "FMEA entry not found" in result["error"]

    def test_method_not_allowed(self, kb_api):
        """PATCH → 405。"""
        _, status = _kb_call("PATCH", "fmea")
        assert status == 405


# =====================================================================
# api/demo_quick.py — spec 生成与 mock LLM
# =====================================================================


class TestGenerateDemoSpec:
    def test_content_placeholders(self):
        """模板渲染：标题/需求/场景/描述均替换。"""
        spec = demo_quick.generate_demo_spec("  blink led  ")
        assert "Demo: blink led" in spec
        assert "REQ-001: blink led" in spec
        assert "- The system SHALL implement blink led" in spec
        assert "Auto-generated spec from user requirement" in spec
        assert "WHEN blink led is triggered" in spec

    def test_timestamp_from_now(self):
        """时间戳来自 datetime.now()。"""
        with mock.patch("yuleosh.api.demo_quick.datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-08-10 12:00:00"
            spec = demo_quick.generate_demo_spec("flash")
        assert "Generated: 2026-08-10 12:00:00" in spec


class TestDemoMockLlm:
    def test_returns_expected_shape(self):
        """_demo_mock_llm 返回固定结构的 mock 响应。"""
        out = demo_quick._demo_mock_llm("sys", "user", temperature=0.2)
        assert "Demo Analysis" in out["content"]
        assert "DemoController" in out["content"]
        assert out["model"] == "demo-mock"
        assert out["usage"] == {"prompt_tokens": 150, "completion_tokens": 120, "total_tokens": 270}
        assert out["finish_reason"] == "stop"


# =====================================================================
# api/demo_quick.py — 管线步骤执行（10 个 handler 全部 mock）
# =====================================================================

_HANDLER_PATCH_TARGETS = [
    "yuleosh.pipeline.step_handlers.spec.step_spec_check",
    "yuleosh.pipeline.step_handlers.analysis.step_super_analysis",
    "yuleosh.pipeline.step_handlers.analysis.step_hermes_prd",
    "yuleosh.pipeline.step_handlers.analysis.step_internal_review",
    "yuleosh.pipeline.step_handlers.execution.step_claude_arch",
    "yuleosh.pipeline.step_handlers.execution.step_claude_dev",
    "yuleosh.pipeline.step_handlers.execution.step_test_planning",
    "yuleosh.pipeline.step_handlers.execution.step_claude_test",
    "yuleosh.pipeline.step_handlers.review.step_hermes_review",
    "yuleosh.pipeline.step_handlers.review.step_final_report",
]


@contextlib.contextmanager
def _patch_handlers(fail_at: int | None = None):
    """把 10 个 step handler 换成返回 'ok' 的 mock；fail_at 指定第几步抛异常。"""
    patches = []
    for i, target in enumerate(_HANDLER_PATCH_TARGETS):
        if fail_at is not None and i == fail_at:
            patches.append(mock.patch(target, side_effect=RuntimeError("step boom")))
        else:
            patches.append(mock.patch(target, return_value="ok"))
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


class TestRunDemoPipelineSteps:
    @staticmethod
    def _spec_file(tmp_path):
        spec = tmp_path / "docs" / "spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# spec\n", encoding="utf-8")
        return spec

    def test_all_steps_complete(self, tmp_path, capsys):
        """10 步全部成功 → complete_step×10、_save 一次、无 fail_step。"""
        spec = self._spec_file(tmp_path)
        fake = mock.MagicMock()
        fake.status = "created"
        with mock.patch("yuleosh.pipeline.session.PipelineSession", return_value=fake), \
                _patch_handlers():
            session = demo_quick.run_demo_pipeline_steps(str(spec), tmp_path)
        assert session is fake
        assert fake.add_step.call_count == 10
        assert fake.complete_step.call_count == 10
        assert fake.set_artifact.call_count == 10
        fake._save.assert_called_once()
        fake.fail_step.assert_not_called()
        out = capsys.readouterr().out
        assert out.count("✅") == 10

    def test_step_failure_breaks_loop(self, tmp_path, capsys):
        """第 1 步抛异常 → fail_step 一次、循环中断、后续步骤不再执行。"""
        spec = self._spec_file(tmp_path)
        fake = mock.MagicMock()
        fake.status = "created"
        with mock.patch("yuleosh.pipeline.session.PipelineSession", return_value=fake), \
                _patch_handlers(fail_at=0):
            session = demo_quick.run_demo_pipeline_steps(str(spec), tmp_path)
        assert session is fake
        fake.fail_step.assert_called_once()
        assert fake.add_step.call_count == 1
        fake.complete_step.assert_not_called()
        assert "❌ spec-check" in capsys.readouterr().out

    def test_final_report_sets_completed_and_saves(self, tmp_path):
        """final-report 步骤：status=completed 且调用 _save。"""
        spec = self._spec_file(tmp_path)
        fake = mock.MagicMock()
        fake.status = "created"
        with mock.patch("yuleosh.pipeline.session.PipelineSession", return_value=fake), \
                _patch_handlers():
            demo_quick.run_demo_pipeline_steps(str(spec), tmp_path)
        assert fake.status == "completed"
        assert fake._save.call_count == 1


# =====================================================================
# api/demo_quick.py — 完整 demo 管线（证据收集真跑，落 tmp_path）
# =====================================================================


class TestRunDemoPipeline:
    @staticmethod
    def _fake_session(status="completed", errors=None, tokens=270):
        return mock.Mock(
            status=status,
            errors=errors or [],
            session_dir="/tmp/demo-session",
            token_usage_total=tokens,
        )

    def test_success_flow(self, tmp_path, capsys):
        """成功路径：项目结构/spec/测试文件/证据 zip 全部产出，env 还原。"""
        fake = self._fake_session()
        with mock.patch.object(demo_quick, "run_demo_pipeline_steps", return_value=fake):
            result = demo_quick.run_demo_pipeline("blink led", str(tmp_path))
        assert result["status"] == "completed"
        assert result["token_usage"] == 270
        project = tmp_path / "demo-project"
        for sub in (".osh", "docs", "src", "tests", "specs"):
            assert (project / sub).is_dir(), f"missing subdir: {sub}"
        assert (project / "docs" / "spec.md").exists()
        assert (project / "tests" / "test_demo.py").exists()
        assert (project / "docs" / "spec.md").read_text(encoding="utf-8").startswith("# Demo: blink led")
        assert len(result["artifacts"]) == 6
        assert result["evidence_zip"]
        assert os.path.exists(result["evidence_zip"])
        assert os.environ.get("LLM_API_KEY") != "demo-mock-key"
        assert os.environ.get("OSH_HOME") != str(project)
        assert "Generated demo spec" in capsys.readouterr().out

    def test_failed_status(self, tmp_path):
        """session.status=failed → 返回失败结果与 errors，不再生成证据。"""
        fake = self._fake_session(status="failed", errors=["spec invalid"])
        with mock.patch.object(demo_quick, "run_demo_pipeline_steps", return_value=fake):
            result = demo_quick.run_demo_pipeline("x", str(tmp_path))
        assert result["status"] == "failed"
        assert result["errors"] == ["spec invalid"]
        assert "evidence_zip" not in result

    def test_existing_project_dir_removed(self, tmp_path):
        """已存在的 demo-project → 先 rmtree 再重建。"""
        project = tmp_path / "demo-project"
        project.mkdir()
        (project / "old.txt").write_text("old", encoding="utf-8")
        fake = self._fake_session()
        with mock.patch.object(demo_quick, "run_demo_pipeline_steps", return_value=fake):
            demo_quick.run_demo_pipeline("x", str(tmp_path))
        assert not (project / "old.txt").exists()
        assert (project / "docs" / "spec.md").exists()

    def test_env_restored_when_preexisting(self, tmp_path):
        """调用前已有 LLM_API_KEY/OSH_HOME → 调用后原样还原。"""
        fake = self._fake_session()
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "real-key", "OSH_HOME": "/real/home"}):
            with mock.patch.object(demo_quick, "run_demo_pipeline_steps", return_value=fake):
                demo_quick.run_demo_pipeline("x", str(tmp_path))
            assert os.environ["LLM_API_KEY"] == "real-key"
            assert os.environ["OSH_HOME"] == "/real/home"

    def test_env_cleaned_when_absent(self, tmp_path):
        """调用前无 LLM_API_KEY/OSH_HOME → 调用后键被移除。"""
        fake = self._fake_session()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_API_KEY", None)
            os.environ.pop("OSH_HOME", None)
            with mock.patch.object(demo_quick, "run_demo_pipeline_steps", return_value=fake):
                demo_quick.run_demo_pipeline("x", str(tmp_path))
            assert "LLM_API_KEY" not in os.environ
            assert "OSH_HOME" not in os.environ


# =====================================================================
# api/demo_quick.py — main CLI 入口
# =====================================================================


class TestDemoQuickMain:
    def test_main_completed(self, tmp_path, capsys):
        """completed → 打印 Spec/Evidence/ZIP/Tokens/Artifacts。"""
        zip_path = tmp_path / "evidence.zip"
        zip_path.write_bytes(b"PK\x03\x04")
        result = {
            "status": "completed",
            "spec_path": str(tmp_path / "spec.md"),
            "evidence_dir": str(tmp_path / "ev"),
            "evidence_zip": str(zip_path),
            "artifacts": ["a", "b", "c"],
            "token_usage": 270,
        }
        with mock.patch.object(demo_quick, "run_demo_pipeline", return_value=result) as m:
            out = demo_quick.main("blink", str(tmp_path))
        assert out is result
        m.assert_called_once_with("blink", str(tmp_path))
        text = capsys.readouterr().out
        assert "Demo pipeline completed successfully" in text
        assert "Spec:" in text
        assert "ZIP:" in text and "bytes" in text
        assert "Tokens: 270" in text
        assert "Artifacts: 3" in text

    def test_main_completed_without_zip_or_tokens(self, tmp_path, capsys):
        """completed 但无 zip/token → 跳过对应打印。"""
        result = {
            "status": "completed",
            "spec_path": str(tmp_path / "spec.md"),
            "evidence_dir": str(tmp_path / "ev"),
            "evidence_zip": "",
            "artifacts": [],
        }
        with mock.patch.object(demo_quick, "run_demo_pipeline", return_value=result):
            demo_quick.main("x", str(tmp_path))
        text = capsys.readouterr().out
        assert "ZIP:" not in text
        assert "Tokens:" not in text
        assert "Artifacts: 0" in text

    def test_main_failed(self, capsys):
        """failed → 打印错误列表。"""
        result = {"status": "failed", "errors": ["spec invalid", "no evidence"]}
        with mock.patch.object(demo_quick, "run_demo_pipeline", return_value=result):
            demo_quick.main("x", ".")
        text = capsys.readouterr().out
        assert "Demo pipeline failed" in text
        assert "spec invalid" in text
        assert "no evidence" in text
