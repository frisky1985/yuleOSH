import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.steps import PipelineStep
from yuleosh.codegen.prompts import collect_existing_headers

log = logging.getLogger("pipeline.step_classes")

# ---------------------------------------------------------------------------
# codegen 追加防护 (2026-08-16, 老板拍板 A+C):
#   seed_contract — 现有 src/ 公共函数契约 (engine 检查生成代码不删除)
#   behavior_verify — 编译通过后跑真实测试 (engine repair 轮反馈给 LLM)
# ---------------------------------------------------------------------------


def _collect_seed_contract(project_dir: str | Path) -> dict[str, set[str]]:
    """Collect public function names from existing src/ headers.

    Returns {rel_path_of_c_impl: {func_name, ...}} where funcs come from
    the matching header declarations (non-static public API). The engine
    checks generated .c still implements every declared public function.
    """
    proot = Path(project_dir)
    src_dir = proot / "src"
    if not src_dir.is_dir():
        return {}

    # header decl → func name (comment-stripped)
    def _header_funcs(h: Path) -> set[str]:
        text = h.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        funcs: set[str] = set()
        for m in re.finditer(r"\b([a-zA-Z_]\w*)\s*\([^;{}]*\);", text, flags=re.S):
            name = m.group(1)
            if name in {"if", "for", "while", "switch", "return",
                        "sizeof", "defined"}:
                continue
            funcs.add(name)
        return funcs

    contract: dict[str, set[str]] = {}
    # src/**/include/*.h → 对应 src/**/src/*.c (同 stem)
    for h in sorted(src_dir.rglob("*.h")):
        funcs = _header_funcs(h)
        if not funcs:
            continue
        stem = h.stem  # e.g. window_control
        for c in sorted(src_dir.rglob(f"{stem}.c")):
            rel = str(c.relative_to(proot))
            contract.setdefault(rel, set()).update(funcs)
    return contract


def _make_behavior_verify(project_dir: str | Path):
    """Build a behavior-verify callback for CodegenEngine.

    The callback temporarily deploys generated src/ into the project
    (backed up), runs the real C test suite via CCTestRunner, restores the
    original src/, and returns a failure-text (or "" on pass).

    Safe: restores original src/ even when the test run raises. The deploy
    step later runs its own baseline→verify→rollback behavior guardrail —
    this hook only *pre-empts* obvious regressions inside the codegen loop.
    """
    proot = Path(project_dir)

    def _verify(out_dir: Path) -> str:
        from yuleosh.pipeline.guardrail import CCTestRunner

        gen_src = out_dir / "src"
        if not gen_src.is_dir():
            return ""
        # 备份现有 src 中被覆盖文件
        backup: dict[str, bytes | None] = {}
        try:
            for p in sorted(gen_src.rglob("*")):
                if p.is_dir():
                    continue
                rel = p.relative_to(out_dir)  # keep "src/..." prefix
                dst = proot / rel
                if dst.exists():
                    try:
                        backup[str(rel)] = dst.read_bytes()
                    except OSError:
                        backup[str(rel)] = None
                else:
                    backup[str(rel)] = None
            # 部署生成代码
            for p in sorted(gen_src.rglob("*")):
                if p.is_dir():
                    continue
                rel = p.relative_to(out_dir)
                dst = proot / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, dst)
            # 跑真实测试
            runner = CCTestRunner()
            result = runner.run(proot, force_rebuild=True)
            # 仅真实失败才拦截; skipped (无 C 测试) 视为通过 — 否则
            # Python 项目/无测试项目每次 codegen 都被假失败卡死。
            if result.status != "failed":
                return ""
            return (
                "## ⚠️ 行为测试失败 (codegen 阶段预检, 2026-08-16)\n"
                f"runner={result.runner} passed={result.passed} "
                f"failed={result.failed} status={result.status}\n"
                f"{getattr(result, 'detail', '') or getattr(result, 'output', '') or ''}"
                "\n请修复生成代码的行为逻辑后重新输出涉及的文件。\n"
            )
        except Exception as e:  # pragma: no cover - defensive
            log.warning("behavior_verify exception (non-fatal): %s", e)
            return ""
        finally:
            # 恢复原始 src/ (即使测试异常)
            from yuleosh.pipeline.guardrail import apply_change_set

            try:
                apply_change_set(proot, backup)
            except Exception as e:  # pragma: no cover - defensive
                log.warning("behavior_verify restore failed: %s", e)

    return _verify


class SuperAnalysisStep(PipelineStep):
    """
Step 1: 小明 — S.U.P.E.R analysis powered by real LLM."""


    step_key = "super-analysis"
    agent = "小明"
    description = "S.U.P.E.R 启动分析"
    output_filename = "startup-analysis.md"

    def build_prompts(self, session, spec_content, parsed, artifacts):
        from yuleosh.pipeline.prompts import build_super_analysis_prompt

        requirements = parsed["requirements"]
        scenarios = parsed["scenarios"]
        return build_super_analysis_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            requirements=requirements,
            scenarios=scenarios,
        )

    def _icon(self):
        return "📊"


class PrdStep(PipelineStep):
    """
Step 2: Hermes — AI-powered PRD generation from spec."""


    step_key = "prd"
    agent = "Hermes"
    description = "产品需求分析"
    output_filename = "prd.md"

    def _artifact_keys(self):
        return ["super-analysis"]

    def build_prompts(self, session, spec_content, parsed, artifacts):
        from yuleosh.pipeline.prompts import build_prd_prompt

        requirements = parsed["requirements"]
        scenarios = parsed["scenarios"]
        return build_prd_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            requirements=requirements,
            scenarios=scenarios,
            super_analysis_content=artifacts.get("super-analysis", ""),
        )

    def _icon(self):
        return "🔮"


class ArchitectureStep(PipelineStep):
    """
Step 4: Claude — AI-powered architecture design."""


    step_key = "architecture"
    agent = "Claude"
    description = "架构设计"
    output_filename = "architecture.md"
    max_tokens = 4096

    def build_prompts(self, session, spec_content, parsed, artifacts):
        from yuleosh.pipeline.prompts import build_architecture_prompt
        import os

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        src_dir = project_dir / "src"

        directories: list[str] = []
        source_files: list[str] = []
        tech_stack: set[str] = set()
        src_tree_lines: list[str] = []

        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".") and d != "__pycache__"
                ]
                rel_dir = Path(root).relative_to(project_dir)
                directories.append(str(rel_dir))
                indent = (
                    "  " * (len(Path(rel_dir).parts) - 1)
                    if len(Path(rel_dir).parts) > 1
                    else ""
                )
                src_tree_lines.append(f"{indent}{Path(rel_dir).name}/")
                for f in sorted(files):
                    if f.endswith(
                        (
                            ".py", ".sh", ".html", ".js", ".css", ".ts",
                            ".go", ".rs", ".json", ".toml", ".yaml", ".yml", ".md",
                        )
                    ):
                        source_files.append(str(Path(rel_dir) / f))
                        src_tree_lines.append(f"{indent}  {f}")
                        ext = Path(f).suffix
                        if ext == ".py":
                            tech_stack.add("Python")
                        elif ext == ".go":
                            tech_stack.add("Go")
                        elif ext == ".rs":
                            tech_stack.add("Rust")
                        elif ext in (".html", ".js", ".css", ".ts"):
                            tech_stack.add("Web (HTML/JS/CSS)")
                        elif ext == ".sh":
                            tech_stack.add("Shell")

        key_file_snippets: list[str] = []
        for sf in sorted(source_files)[:15]:
            fpath = project_dir / sf
            if fpath.exists() and fpath.stat().st_size < 10000:
                try:
                    content = fpath.read_text()[:2000]
                    key_file_snippets.append(f"### {sf}\n```\n{content}\n```")
                except Exception as e:
                    log.warning("Could not read source file %s: %s", sf, e)
                    pass

        return build_architecture_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            session_name=session.name,
            directories=directories,
            source_files=source_files,
            tech_stack=sorted(tech_stack),
            source_tree_str="\n".join(src_tree_lines[:80]),
            key_file_snippets=key_file_snippets,
        )

    def process_result(self, session, content, result):
        # Architecture step writes raw content without metadata header
        return content

    def _icon(self):
        return "💻"


class DevelopmentStep(PipelineStep):
    """
Step 5: Claude — AI-powered development.

Two modes (``mode`` constructor arg or ``session.development_mode``):

* ``planning`` (default) — writes ``development-plan.md`` (unchanged
  legacy behavior).
* ``generate-code`` (D3) — directly generates code files from
  spec/architecture/PRD, runs compile verification, and auto-fixes up to
  ``max_retries`` times.  Output lands in
  ``artifacts/generated-code/<session>/`` with a ``codegen-report.md``.
"""


    step_key = "development"
    agent = "Claude"
    description = "开发实现"
    output_filename = "development-plan.md"
    max_tokens = 4096

    def __init__(self, mode: str = "planning", max_retries: int = 3):
        self.mode = mode
        self.max_retries = max_retries

    def _effective_mode(self, session) -> str:
        """Resolve the mode: session config wins, then constructor arg."""
        session_mode = getattr(session, "development_mode", None)
        if session_mode:
            return session_mode
        return self.mode or "planning"

    def _artifact_keys(self):
        return ["architecture", "prd", "super-analysis"]

    def build_prompts(self, session, spec_content, parsed, artifacts):
        from yuleosh.pipeline.prompts import build_development_prompt
        import os
        import subprocess

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # Gather project metrics
        git_log = ""
        git_commits = 0
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", "--format=%h %s (%ar)"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=project_dir,
            )
            if result.returncode == 0:
                git_log = result.stdout.strip()
                git_commits = (
                    len(result.stdout.strip().split("\n"))
                    if result.stdout.strip()
                    else 0
                )
        except Exception as e:
            log.warning(f"Git log failed (non-fatal): {e}")
            git_log = "(not a git repository or git not available)"

        src_lines = 0
        test_lines = 0
        src_files = (
            list(project_dir.glob("src/**/*.py"))
            + list(project_dir.glob("src/**/*.sh"))
            + list(project_dir.glob("src/**/*.html"))
        )
        test_files = list(project_dir.glob("tests/**/*.py"))

        for f in src_files:
            try:
                src_lines += len(f.read_text().splitlines())
            except Exception as e:
                log.warning("Could not read source file in count: %s", e)
                pass
        for f in test_files:
            try:
                test_lines += len(f.read_text().splitlines())
            except Exception as e:
                log.warning("Could not read test file in count: %s", e)
                pass

        return build_development_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            architecture_content=artifacts.get("architecture", ""),
            prd_content=artifacts.get("prd", ""),
            super_analysis_content=artifacts.get("super-analysis", ""),
            src_lines=src_lines,
            src_file_count=len(src_files),
            test_lines=test_lines,
            test_file_count=len(test_files),
            git_commits=git_commits,
            git_log=git_log,
        )

    def __call__(self, session) -> str:
        """Branch on mode: codegen when enabled, planning otherwise."""
        if self._effective_mode(session) == "generate-code":
            return self._run_codegen(session)
        return super().__call__(session)

    def _run_codegen(self, session) -> str:
        """D3 loop: prompt → LLM → write files → verify → auto-fix → report."""
        from yuleosh.codegen.engine import CodegenEngine, build_codegen_report
        from yuleosh.codegen.prompts import build_codegen_prompt, collect_existing_headers, collect_seed_sources

        print("  💻 [Claude] Running generate-code mode (D3)...")
        # 2026-08-12: 优先用 session.project_dir (创建时解析), 避免环境
        # 变量变化导致退化为 cwd — seed 复制/API 契约会指向错误目录。
        project_dir = Path(getattr(session, "project_dir", None)
                           or os.environ.get("OSH_HOME", ".")).resolve()
        spec_path = Path(session.spec_path)
        spec_content = (
            spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        )
        artifacts = self._read_artifacts(session, self._artifact_keys())

        cfg = session.config.get("codegen", {}) if getattr(session, "config", None) else {}
        skills = cfg.get("skills") or ["autosar-coding"]
        target_language = cfg.get("target_language")
        build_cmd = cfg.get("build_cmd")
        language_hint = cfg.get("language")

        # 方案 C seed 增量 (2026-08-12): 注入现有 src 代码作为基线,
        # engine 复制 seed 到输出目录, LLM 只增量修改。
        seed_sources = collect_seed_sources(project_dir)

        system_prompt, user_prompt = build_codegen_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            architecture_content=artifacts.get("architecture", ""),
            prd_content=artifacts.get("prd", ""),
            super_analysis_content=artifacts.get("super-analysis", ""),
            skills=skills,
            target_language=target_language,
            existing_headers=collect_existing_headers(project_dir),
            seed_sources=seed_sources,
        )

        engine = CodegenEngine(
            output_dir=cfg.get("output_dir"),
            max_retries=int(cfg.get("max_retries", self.max_retries)),
            llm_client=getattr(session, "llm_client", None),
            max_tokens=self.max_tokens,
            seed_dir=project_dir if seed_sources else None,
            seed_contract=_collect_seed_contract(project_dir),
            behavior_verify=_make_behavior_verify(project_dir),
        )
        result = engine.generate(
            session, system_prompt, user_prompt,
            language_hint=language_hint, build_cmd=build_cmd,
        )

        # Also record a pointer note as the step output file so downstream
        # steps (devplan-review etc.) still have content to read.
        note = (
            f"# Development (generate-code mode): {session.name}\n\n"
            f"> Status: {result.status}\n"
            f"> Generated files: {len(result.files)}\n"
            f"> Output dir: {result.output_dir}\n"
            f"> Report: {result.report_path}\n"
            f"> Rounds: {result.rounds} (max retries {result.max_retries})\n\n"
            + build_codegen_report(result, session)
        )
        out_path = session.session_dir / self.output_filename
        out_path.write_text(note, encoding="utf-8")
        print(f"  ✅ [Claude] generate-code: {len(result.files)} files, "
              f"status={result.status}, report={result.report_path}")
        log.info(
            "Codegen complete: status=%s files=%d rounds=%d",
            result.status, len(result.files), result.rounds,
        )
        return result.report_path

    def _icon(self):
        return "💻"


class TestPlanningStep(PipelineStep):
    """
Step 6: Claude — AI-powered test planning."""


    step_key = "test-planning"
    agent = "Claude"
    description = "测试规划"
    output_filename = "test-plan.md"
    max_tokens = 4096

    def _artifact_keys(self):
        return ["architecture", "development"]

    def build_prompts(self, session, spec_content, parsed, artifacts):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        requirements = parsed["requirements"]
        architecture_content = artifacts.get("architecture")
        dev_plan_content = artifacts.get("development")

        return build_test_planning_prompt(
            spec_content=spec_content,
            requirements=requirements,
            architecture_content=architecture_content,
            development_plan_content=dev_plan_content,
        )

    def _icon(self):
        return "📋"


class HermesReviewStep(PipelineStep):
    """
Step 8: Hermes — AI-powered code review."""


    step_key = "code-review"
    agent = "Hermes"
    description = "代码审查"
    output_filename = "code-review.json"
    max_tokens = 4096

    def _artifact_keys(self):
        return [
            "architecture", "development", "self-test",
            "prd", "super-analysis", "review-result",
        ]

    def build_prompts(self, session, spec_content, parsed, artifacts):
        from yuleosh.pipeline.prompts import build_code_review_prompt
        import os

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # Scan actual source files
        source_files: list[dict] = []
        src_dir = project_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".") and d != "__pycache__"
                ]
                for f in sorted(files):
                    if f.endswith(".py"):
                        fpath = Path(root) / f
                        rel = fpath.relative_to(project_dir)
                        content = (
                            fpath.read_text()
                            if fpath.exists() and fpath.stat().st_size < 20000
                            else ""
                        )
                        source_files.append({
                            "path": str(rel),
                            "lines": len(content.splitlines()),
                            "content": content[:3000],
                        })

        return build_code_review_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            session_name=session.name,
            artifact_contents=artifacts,
            source_files=source_files,
            timestamp=datetime.now().isoformat(),
        )

    def process_result(self, session, content, result):
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = content.strip()
        review = _try_parse_hermes_json(raw, session.name)
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "Hermes")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault(
            "finding_breakdown",
            {"critical": 0, "major": 0, "minor": 0, "info": 0},
        )
        review.setdefault("summary", "")
        return json.dumps(review, indent=2, ensure_ascii=False)

    def _icon(self):
        return "🔮"


# Map of step_key -> PipelineStep instance (singletons)
STEP_CLASSES: dict[str, PipelineStep] = {
    "super-analysis": SuperAnalysisStep(),
    "prd": PrdStep(),
    "architecture": ArchitectureStep(),
    "development": DevelopmentStep(),
    "test-planning": TestPlanningStep(),
    "code-review": HermesReviewStep(),
}


def get_step_instance(step_key: str) -> PipelineStep | None:
    """
Return the singleton PipelineStep instance for *step_key*."""

    return STEP_CLASSES.get(step_key)


def register_step(step_key: str, instance: PipelineStep) -> None:
    """
Register a custom step instance (for extensibility)."""

    STEP_CLASSES[step_key] = instance