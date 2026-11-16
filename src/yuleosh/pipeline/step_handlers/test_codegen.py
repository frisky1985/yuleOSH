#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Step: test-codegen — 生成可执行的 C 单元测试（SWE.4 覆盖证据）。

问题背景（2026-11-16, CL2 真跑暴露）: 流水线此前只**执行**已有测试
(``step_claude_test`` / ``step_c_unit_test`` 都是 runner)，从不生成测试。
从零项目跑必然出现 "0/16 SHALL covered" + 覆盖率 0% —— SWE.4 与
G6/G7 门禁永远红，yuleOSH 无法自动跑到 CL2。

本步骤补上生成环节: 按 spec 需求 → LLM 生成 tests/*.c（每文件首行
``// @req <ID>``）→ 确定性生成 ``tests/CMakeLists.txt`` → cmake 构建 +
ctest 实跑；失败则把编译器/ctest 输出回灌 LLM 修复（有限轮次）。

设计约束（与 AUD-ASPICE-001 一致）:
- 测试上下文只从 spec + 公开头文件派生（不注入实现函数体做断言推导）;
- 测试必须带需求注解，否则视为无追溯性 → 直接判失败;
- 构建/运行失败不得"降级为 passed"——宁可让门禁红。
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.step_handlers.test_codegen")

__all__ = ["step_test_codegen"]

TESTS_DIR = "tests"
BUILD_DIR = "build-tests"
MAX_REPAIR_ROUNDS = 2
_MAX_SOURCE_CHARS = 40000
_MAX_REQUIREMENTS = 40
_WIRING_MARKER = "# --- yuleOSH test wiring"
_REQ_ANNOTATION_RE = re.compile(r"@req\s+([A-Za-z][\w.-]*(?:\s*,\s*[\w.-]+)*)")


# ── 项目探测 ──────────────────────────────────────────────────────────────

def _project_dir(session: PipelineSession) -> Path:
    return Path(getattr(session, "project_dir", None)
                or __import__("os").environ.get("OSH_HOME", ".")).resolve()


def _spec_text(session: PipelineSession) -> str:
    spec = Path(getattr(session, "spec_path", "") or "")
    if spec.is_dir():
        return "\n".join(
            f.read_text(encoding="utf-8", errors="replace")
            for f in sorted(spec.rglob("*.md")))
    if spec.is_file():
        return spec.read_text(encoding="utf-8", errors="replace")
    return ""


def _requirements(session: PipelineSession) -> list[tuple[str, str]]:
    """spec 需求 ``[(ID, 语句)]``（确定性解析，最多 40 条）。"""
    try:
        from yuleosh.spec.ssot import extract_requirements

        reqs = extract_requirements(_spec_text(session))
    except Exception as exc:  # noqa: BLE001 — 解析失败按空集降级
        log.warning("test-codegen: spec parse failed: %s", exc)
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for req in reqs:
        rid = (req.id or "").strip().upper()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append((rid, (req.statement or "").strip()))
        if len(out) >= _MAX_REQUIREMENTS:
            break
    return out


def _app_sources(project_dir: Path) -> list[Path]:
    """被测源码: ``src/**/*.c``，排除测试目录与含 ``int main(`` 的文件。

    含 main 的文件（demo 入口）不能链进测试可执行文件，否则 duplicate
    main；被测单元通常是纯模块。
    """
    out: list[Path] = []
    src = project_dir / "src"
    if not src.is_dir():
        return out
    for path in sorted(src.rglob("*.c")):
        parts = path.relative_to(project_dir).parts
        if TESTS_DIR in parts or "build" in " ".join(parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"\bint\s+main\s*\(", text):
            continue
        out.append(path)
    return out


def _existing_tests(project_dir: Path) -> list[Path]:
    tests = project_dir / TESTS_DIR
    if not tests.is_dir():
        return []
    return sorted(tests.rglob("*.c"))


def _system_tests(project_dir: Path) -> list[Path]:
    """SWE.6 系统级/验收测试（test-qualification 的发现范围）。"""
    found: list[Path] = []
    for pattern in ("**/test_qualification*.c", "**/e2e_test*.c",
                    "**/acceptance_test*.c", "**/scenario_test*.c",
                    "**/tests/system/*.c", "**/tests/e2e/*.c"):
        found.extend(p for p in project_dir.glob(pattern) if p.is_file())
    return sorted(set(found))


_SCENARIO_RE = re.compile(
    r"^###\s+Scenario:\s*(?P<name>.+?)\n(?P<body>(?:(?!^###).*\n?)*)",
    re.MULTILINE)


def _scenarios(session: PipelineSession) -> list[tuple[str, str]]:
    """spec 中的 GIVEN/WHEN/THEN 场景 ``[(名称, 原文)]``（确定性解析）。"""
    out: list[tuple[str, str]] = []
    for m in _SCENARIO_RE.finditer(_spec_text(session)):
        name = m.group("name").strip()
        body = (m.group("body") or "").strip()
        if "GIVEN" in body.upper():
            out.append((name, f"### Scenario: {name}\n{body}"))
        if len(out) >= 10:
            break
    return out


def _header_texts(project_dir: Path) -> list[tuple[str, str]]:
    """公开头文件（接口契约）——测试只能依赖这些。"""
    out: list[tuple[str, str]] = []
    inc = project_dir / "src" / "include"
    if not inc.is_dir():
        return out
    for path in sorted(inc.glob("*.h")):
        try:
            out.append((str(path.relative_to(project_dir)),
                        path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return out


def _harness_texts(project_dir: Path) -> list[tuple[str, str]]:
    """主机仿真桩（``src/hal/*.c``）——测试脚手架的语义来源。

    2026-11-16 真跑复盘: 生成测试断言 ``hal_host_toggle_time_at(0) == 500``，
    但主机桩的时间戳只由 ``hal_host_set_time()`` 推进，测试从未调用 →
    3/5 用例假失败。桩是**测试脚手架**（不是被测实现），必须把它的语义
    给模型，否则测试只能靠猜。
    """
    out: list[tuple[str, str]] = []
    hal = project_dir / "src" / "hal"
    if not hal.is_dir():
        return out
    for path in sorted(hal.glob("*.c")):
        try:
            out.append((str(path.relative_to(project_dir)),
                        path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return out


# ── CMake 接线（确定性）──────────────────────────────────────────────────

def _ensure_coverage_option(text: str) -> str:
    """在 ``project()`` 之后插入 ENABLE_COVERAGE 选项（幂等）。

    必须在 target 定义前插入：``add_compile_options`` 只影响其后创建的
    target，追加到文件末尾会漏掉被测库 → gcovr 覆盖率为 0。
    """
    if "ENABLE_COVERAGE" in text:
        return text
    block = (
        "\n# --- yuleOSH coverage option (auto-generated, idempotent) ---\n"
        "option(ENABLE_COVERAGE \"Enable gcov coverage instrumentation\" OFF)\n"
        "if(ENABLE_COVERAGE)\n"
        "  add_compile_options(--coverage -O0 -g)\n"
        "  add_link_options(--coverage)\n"
        "endif()\n"
    )
    m = re.search(r"^\s*project\s*\([^)]*\)\s*$", text, re.MULTILINE)
    if m:
        return text[:m.end()] + "\n" + block + text[m.end():]
    return text + "\n" + block


def _ensure_test_wiring(text: str) -> str:
    """文件末尾追加 enable_testing + add_subdirectory(tests)（幂等）。"""
    if _WIRING_MARKER in text:
        return text
    return text + (
        f"\n{_WIRING_MARKER} (auto-generated, idempotent) ---\n"
        "enable_testing()\n"
        "if(EXISTS \"${CMAKE_CURRENT_SOURCE_DIR}/tests/CMakeLists.txt\")\n"
        "  add_subdirectory(tests)\n"
        "endif()\n"
    )


def _write_tests_cmake(project_dir: Path, tests: list[Path],
                       app_sources: list[Path]) -> Path:
    """生成 ``tests/CMakeLists.txt``：被测源码打成静态库，每个测试一个可执行。"""
    # 2026-11-17: 收集所有含 .h 的目录作为 include 路径 (src/app, src/hal,
    # include/ 等), 不再硬编码 src/include — codegen 产物结构多变。
    inc_dirs: list[Path] = []
    seen: set[str] = set()
    for cand in (project_dir / "src", project_dir / "include"):
        if not cand.is_dir():
            continue
        for h in cand.rglob("*.h"):
            d = h.parent
            key = str(d.resolve())
            if key not in seen:
                seen.add(key)
                inc_dirs.append(d)
    inc_args = " ".join(f'"{d.as_posix()}"' for d in inc_dirs) or '""'
    lines = [
        "# Auto-generated by yuleOSH test-codegen — do not edit by hand.",
        "set(OSH_APP_SRCS",
    ]
    for src in app_sources:
        lines.append(f'  "{src.as_posix()}"')
    lines += [
        ")",
        "add_library(osh_app_under_test STATIC ${OSH_APP_SRCS})",
        f"target_include_directories(osh_app_under_test PUBLIC {inc_args})",
        "",
    ]
    for test in tests:
        # 2026-11-17: 加 osh_unit_ 前缀避免与 codegen 根 CMakeLists.txt
        # 已定义的同名 test target 冲突 (CMP0002 duplicate target)。
        name = "osh_unit_" + test.stem
        lines += [
            f'add_executable({name} "{test.as_posix()}")',
            f"target_link_libraries({name} PRIVATE osh_app_under_test)",
            f"target_include_directories({name} PRIVATE {inc_args} "
            f"\"{test.parent.as_posix()}\")",
            f"add_test(NAME {name} COMMAND {name})",
            "",
        ]
    out = project_dir / TESTS_DIR / "CMakeLists.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return -1, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, f"timeout after {timeout}s: {' '.join(cmd)}"


def _build_and_run(project_dir: Path) -> tuple[bool, str]:
    build_dir = project_dir / BUILD_DIR
    rc, out = _run(["cmake", "-S", str(project_dir), "-B", str(build_dir),
                    "-DCMAKE_BUILD_TYPE=Debug"], project_dir, timeout=180)
    if rc != 0:
        return False, "=== cmake configure ===\n" + out[-4000:]
    rc, bout = _run(["cmake", "--build", str(build_dir), "-j4"],
                    project_dir, timeout=300)
    if rc != 0:
        return False, "=== build ===\n" + bout[-4000:]
    rc, tout = _run(["ctest", "--output-on-failure", "-j4"],
                    build_dir, timeout=300)
    return rc == 0, "=== ctest ===\n" + tout[-4000:]


# ── Prompt ───────────────────────────────────────────────────────────────

def _build_prompt(session: PipelineSession, requirements: list[tuple[str, str]],
                  scenarios: list[tuple[str, str]],
                  headers: list[tuple[str, str]],
                  harness: list[tuple[str, str]],
                  sources: list[Path], repair_note: str = "",
                  scenario_only: bool = False) -> tuple[str, str]:
    system_prompt = (
        "You are a senior embedded test engineer. Write executable C99 unit "
        "tests that prove the specification is met.\n"
        "Output format (strict): for every file emit\n"
        "### FILE: tests/<name>.c\n"
        "followed by a ```c fenced block with the full file.\n"
        "Rules:\n"
        "1. The FIRST line of every test file MUST be a requirement "
        "annotation: `// @req <ID>` (comma-separated IDs allowed). Use only "
        "IDs from the requirement list below.\n"
        "2. No third-party frameworks. Use <stdio.h>, <stdint.h> and the "
        "project headers only. Provide `int main(void)` returning 0 on "
        "success and non-zero on failure; print `FAIL <WHAT>` before returning "
        "non-zero.\n"
        "3. Include the module header(s) via `#include \"<header>.h\"`, never "
        "re-declare functions, never touch GPIO registers; use the HAL.\n"
        "4. Tests must be deterministic: control time by passing explicit "
        "timestamps; never sleep.\n"
        "5. Read the test-harness source below carefully. Any state the "
        "harness records (timestamps, counters) only changes when you call "
        "its own API — e.g. a host stub that records `s_now_ms` observes "
        "nothing unless you call `hal_host_set_time(t)` first. Keep the "
        "harness clock and the module's injected timestamp consistent.\n"
        "6. Cover every requirement ID with at least one assertion. Prefer "
        "several small focused test files over one giant file.\n"
        "7. Also exercise guard/boundary branches reachable through the "
        "public API (out-of-range pin, first/last toggle index, exactly-at-"
        "period vs one-millisecond-early). The pipeline enforces ASIL branch "
        "coverage thresholds, so happy-path-only tests will be rejected.\n"
        "8. Do not emit CMake files, build scripts or prose.\n"
        "9. SWE.6 acceptance: when GIVEN/WHEN/THEN scenarios are listed, "
        "emit ONE system-level test per scenario at "
        "`tests/system/test_scenario_<slug>.c`. Each such file MUST embed the "
        "full scenario text (GIVEN/WHEN/THEN lines) in a leading block "
        "comment, so qualification coverage can match it. Scenario tests also "
        "start with `// @req` and are otherwise plain C `main()` programs.\n"
    )
    scenario_block = "\n\n".join(text for _, text in scenarios)
    req_lines = "\n".join(f"- {rid}: {text}" for rid, text in requirements)
    header_block = "\n\n".join(
        f"### HEADER {path}\n```c\n{body[:_MAX_SOURCE_CHARS]}\n```"
        for path, body in headers)
    harness_block = "\n\n".join(
        f"### TEST HARNESS {path}\n```c\n{body[:_MAX_SOURCE_CHARS]}\n```"
        for path, body in harness)
    src_list = "\n".join(f"- {p.relative_to(Path(session.project_dir))}"
                         for p in sources)
    user_prompt = (
        "## Requirements to cover\n" + (req_lines or "(none parsed)") +
        "\n\n## GIVEN/WHEN/THEN scenarios (SWE.6 acceptance)\n" +
        (scenario_block or "(none)") +
        "\n\n## Public headers (API contract)\n" + (header_block or "(none)") +
        "\n\n## Host test harness (how the stubs behave)\n" +
        (harness_block or "(none)") +
        "\n\n## Source files under test\n" + (src_list or "(none)") +
        "\n\n## Task\n"
    )
    if scenario_only:
        user_prompt += (
            "Unit tests already exist and pass. Emit ONLY the SWE.6 system "
            "tests: one `tests/system/test_scenario_<slug>.c` per scenario "
            "listed above, each embedding the full GIVEN/WHEN/THEN text in a "
            "leading comment. Every file still starts with `// @req`.\n")
    else:
        user_prompt += (
            "Write `tests/*.c` files that verify the requirements above "
            "through the public API, plus one `tests/system/test_scenario_"
            "<slug>.c` per scenario when scenarios are listed. Every file "
            "starts with `// @req`.\n")
    if repair_note:
        user_prompt += "\n## Previous attempt failed — fix these errors\n" \
                       f"```\n{repair_note[-4000:]}\n```\n"
    return system_prompt, user_prompt


def _write_test_files(project_dir: Path, content: str) -> list[Path]:
    """解析 LLM 输出并写入 tests/（只接受 tests/ 下的 .c 文件）。"""
    from yuleosh.codegen.engine import parse_generated_files

    written: list[Path] = []
    for gf in parse_generated_files(content):
        rel = str(gf.path).replace("\\", "/").lstrip("./")
        if not rel.endswith(".c"):
            continue
        if not rel.startswith(TESTS_DIR + "/"):
            rel = f"{TESTS_DIR}/{Path(rel).name}"
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(gf.content, encoding="utf-8")
        written.append(target)
    return written


def _annotation_coverage(tests: list[Path]) -> tuple[set[str], list[str]]:
    ids: set[str] = set()
    unannotated: list[str] = []
    for path in tests:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unannotated.append(str(path))
            continue
        found = False
        for m in _REQ_ANNOTATION_RE.finditer(text):
            for rid in m.group(1).split(","):
                rid = rid.strip().upper()
                if rid:
                    ids.add(rid)
                    found = True
        if not found:
            unannotated.append(str(path))
    return ids, unannotated


# ── Step ─────────────────────────────────────────────────────────────────

def _report_path(session: PipelineSession) -> Path:
    return Path(session.session_dir) / "test-codegen.json"


def _prior_report_passed(session: PipelineSession) -> bool:
    """上一次本步骤报告是否为 passed（跨会话按项目目录回溯）。"""
    candidates = [Path(session.session_dir) / "test-codegen.json"]
    sessions_root = Path(getattr(session, "session_dir", "")).parent
    try:
        candidates += sorted(sessions_root.glob("*/test-codegen.json"),
                             key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    except OSError:
        pass
    for path in candidates:
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if body.get("status") == "passed":
            return True
    return False


def _failed_test_findings(output: str) -> list[dict]:
    """把 ctest 失败行转成 findings（供返工路由读取）。"""
    findings: list[dict] = []
    for line in (output or "").splitlines():
        if "***Failed" in line or line.startswith("FAIL "):
            findings.append({
                "rule": "TEST-FAIL",
                "severity": "critical",
                "message": line.strip()[:300],
                "file": TESTS_DIR,
            })
        if len(findings) >= 10:
            break
    return findings


def _write_report(session: PipelineSession, **body) -> Path:
    out = _report_path(session)
    body.setdefault("step", "test-codegen")
    body.setdefault("agent", "小克")
    body.setdefault("session", session.name)
    body.setdefault("timestamp", datetime.now().isoformat())
    out.write_text(json.dumps(body, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    session.artifacts["test-codegen"] = str(out)
    return out


def step_test_codegen(session: PipelineSession) -> str:
    """Step: 生成 + 构建 + 运行 C 单元测试（SWE.4）。

    Raises
    ------
    PipelineStepError
        生成的测试无需求注解、构建/运行失败且修复轮次用尽，或 LLM 未产出
        任何测试文件 —— 这些情况都意味着 SWE.4 证据缺失，必须让门禁红。
    """
    project_dir = _project_dir(session)
    requirements = _requirements(session)
    scenarios = _scenarios(session)
    sources = _app_sources(project_dir)
    has_cmake = (project_dir / "CMakeLists.txt").is_file()

    skip_reason = ""
    if getattr(session, "mock_mode", None) is True:
        skip_reason = "mock mode — no real code to test"
    elif not has_cmake:
        skip_reason = "no root CMakeLists.txt — C build not applicable"
    elif not sources:
        skip_reason = "no C sources under src/ — nothing to test"
    elif not requirements:
        skip_reason = "no requirement IDs parsed from spec — tests cannot be traced"
    elif (_existing_tests(project_dir) and _prior_report_passed(session)
          and (not scenarios or _system_tests(project_dir))):
        skip_reason = ("tests/*.c already present and passing — keeping "
                       "existing suite (idempotent, no regeneration)")

    if skip_reason:
        path = _write_report(session, status="skipped", reason=skip_reason,
                             requirements=len(requirements),
                             sources=len(sources))
        print(f"  ⏭️  [test-codegen] 跳过: {skip_reason}")
        log.info("test-codegen skipped: %s", skip_reason)
        return str(path)

    # 已有测试（上一轮生成/返工后）：先原地重跑。返工修好实现后应在这里
    # 变绿，而不是重新生成一套"迁就实现"的测试。SPEC 含场景时还要求
    # SWE.6 系统级测试已存在，否则 test-qualification 会判 incomplete。
    existing = _existing_tests(project_dir)
    if existing and (not scenarios or _system_tests(project_dir)):
        print(f"  🔁 [test-codegen] 发现已有 {len(existing)} 个测试文件，先重跑...")
        ok, output = _build_and_run(project_dir)
        if ok:
            ids, unannotated = _annotation_coverage(existing)
            covered = {rid for rid, _ in requirements} & ids
            path = _write_report(
                session, status="passed", attempts=0,
                reason="re-ran existing suite",
                tests=[str(t.relative_to(project_dir)) for t in existing],
                requirements=[rid for rid, _ in requirements],
                covered_requirements=sorted(covered),
                unannotated=sorted(unannotated),
                build_output_tail=output[-2000:],
            )
            print(f"  ✅ [test-codegen] 既有测试全部通过 "
                  f"（覆盖 {len(covered)}/{len(requirements)} 条需求）")
            return str(path)

    print(f"  🧪 [test-codegen] 生成单元测试 "
          f"({len(requirements)} 条需求 / {len(sources)} 个源文件)...")

    from yuleosh.pipeline.stages import _call_llm

    headers = _header_texts(project_dir)
    harness = _harness_texts(project_dir)
    repair_note = ""
    # 保留已存在的单元测试：本次只补 SWE.6 系统级场景测试。
    tests: list[Path] = list(existing)
    last_output = ""

    for attempt in range(MAX_REPAIR_ROUNDS + 1):
        system_prompt, user_prompt = _build_prompt(
            session, requirements, scenarios, headers, harness, sources,
            repair_note, scenario_only=bool(existing))
        result = _call_llm(session, system_prompt, user_prompt, max_tokens=12000)
        content = (result or {}).get("content", "") if isinstance(result, dict) \
            else str(result or "")
        written = _write_test_files(project_dir, content)
        if written:
            tests = sorted(set(tests) | set(written))
        if not tests:
            repair_note = ("No parseable `### FILE: tests/<name>.c` blocks in "
                           "your output. Emit complete files with that marker.")
            continue

        _write_tests_cmake(project_dir, tests, sources)
        root = project_dir / "CMakeLists.txt"
        text = root.read_text(encoding="utf-8", errors="replace")
        new_text = _ensure_test_wiring(_ensure_coverage_option(text))
        if new_text != text:
            root.write_text(new_text, encoding="utf-8")

        ok, last_output = _build_and_run(project_dir)
        ids, unannotated = _annotation_coverage(tests)
        if not ids:
            raise PipelineStepError(
                "test-codegen: generated tests carry no '@req' annotation — "
                "SWE.4 traceability missing (refusing untraceable tests)")
        if ok:
            covered = {rid for rid, _ in requirements} & ids
            path = _write_report(
                session, status="passed", attempts=attempt + 1,
                tests=[str(t.relative_to(project_dir)) for t in tests],
                requirements=[rid for rid, _ in requirements],
                covered_requirements=sorted(covered),
                unannotated=sorted(unannotated),
                build_output_tail=last_output[-2000:],
            )
            print(f"  ✅ [test-codegen] {len(tests)} 个测试文件构建并通过 "
                  f"ctest（覆盖 {len(covered)}/{len(requirements)} 条需求）")
            return str(path)

        repair_note = last_output
        log.warning("test-codegen attempt %d failed: %s", attempt + 1,
                    last_output[-800:])

    path = _write_report(
        session, status="failed", attempts=MAX_REPAIR_ROUNDS + 1,
        tests=[str(t.relative_to(project_dir)) for t in tests],
        requirements=[rid for rid, _ in requirements],
        findings=_failed_test_findings(last_output),
        build_output_tail=last_output[-3000:],
    )
    print("  ❌ [test-codegen] 生成的测试仍无法构建/通过 — SWE.4 证据缺失")
    raise PipelineStepError(
        "test-codegen: generated tests do not build or pass after "
        f"{MAX_REPAIR_ROUNDS + 1} attempts; see {path}")
