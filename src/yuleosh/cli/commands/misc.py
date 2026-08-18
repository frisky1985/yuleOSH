# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CLI — remaining command groups (A5 monolith split).

Extracted from cli/main.py in v3.8.0 (A5): template / init-autosar /
spec / pipeline / review / demo / ci / evidence / coverage / audit /
kpi / stats command groups.  Behavior is identical to the v3.7.0 inline
implementation; cli/main.py re-exports every symbol for backward
compatibility.

SHALL-A5.5: this module never imports cli.main at module level — _osh_home()
resolves lazily through cli.main so tests that monkeypatch it keep working.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = Path(_SCRIPT_DIR).resolve().parent.parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _osh_home() -> str:
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


# ANSI color constants (moved with the command groups, A5)
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


def ensure_osh_home():
    from yuleosh.cli.main import ensure_osh_home as _e
    return _e()


# ── Template commands (TG-REQ-003, TG-REQ-004) ──────────────────────────

def cmd_template_list():
    """List all available templates in a formatted table (TG-REQ-004)."""
    from yuleosh.templates import list_templates

    templates = list_templates()
    if not templates:
        print("No templates found.")
        return

    print(f"\n{'Name':<22} {'Version':<10} {'Description'}")
    print(f"{'-'*22} {'-'*10} {'-'*50}")
    for t in templates:
        desc = t.get("description", "")
        if len(desc) > 50:
            desc = desc[:47] + "..."
        platforms = ", ".join(t.get("platforms", []))
        version = t.get("version", "")

        print(f"{t['name']:<22} {version:<10} {desc}")
    print(f"\n{len(templates)} template(s) available.\n")


def cmd_ecu_template_list():
    """List all available ECU templates in a formatted table."""
    from yuleosh.templates.ecus import list_ecu_templates

    templates = list_ecu_templates()
    if not templates:
        print("No ECU templates found.")
        return

    print(f"\n{'Name':<8} {'MCU':<10} {'ASIL':<10} {'Description':<50}")
    print(f"{'---':<8} {'---':<10} {'---':<10} {'---':<50}")
    for t in templates:
        desc = t.get("description", "")
        if len(desc) > 50:
            desc = desc[:47] + "..."
        print(f"{t['name']:<8} {t.get('mcu', '-'):<10} {t.get('asil', '-'):<10} {desc:<50}")
    print(f"\n{len(templates)} ECU template(s) available.")
    print("Use: yuleosh init --template <name> --name <project>\n")


def cmd_template_init(project_name: str, parent_dir: str = ".", template_name: str | None = None):
    """Create a new project from a built-in or user template (TG-REQ-003)."""
    from yuleosh.templates import resolve_template, get_template_dir

    if template_name:
        # Resolve template via search priority
        tpl = resolve_template(template_name, project_root=parent_dir)
        if tpl is None:
            print(f"Error: template '{template_name}' not found.", file=sys.stderr)
            sys.exit(1)

        tpl_dir = get_template_dir(tpl)
        if tpl_dir is None:
            print(f"Error: template '{template_name}' directory not found.", file=sys.stderr)
            sys.exit(1)

        project_dir = Path(parent_dir) / project_name

        if project_dir.exists():
            print(f"Error: Directory already exists: {project_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"📦 Creating project '{project_name}' from template '{template_name}'...")

        # Copy template files (spec, pipeline, src)
        specs_src = tpl_dir / "specs"
        pipeline_src = tpl_dir / "pipeline"
        src_src = tpl_dir / "src"
        gitignore_src = tpl_dir / ".gitignore"
        template_yaml = tpl_dir / "template.yaml"

        # Create directories
        project_dir.mkdir(parents=True, exist_ok=True)

        # Copy specs/spec.md -> docs/spec.md
        if specs_src.exists():
            (project_dir / "docs").mkdir(exist_ok=True)
            shutil.copy2(str(specs_src / "spec.md"), str(project_dir / "docs" / "spec.md"))

        # Copy pipeline/config.yaml -> pipeline/config.yaml
        if pipeline_src.exists():
            (project_dir / "pipeline").mkdir(exist_ok=True)
            shutil.copy2(str(pipeline_src / "config.yaml"), str(project_dir / "pipeline" / "config.yaml"))

        # Copy src/ skeleton
        if src_src.exists():
            shutil.copytree(str(src_src), str(project_dir / "src"), dirs_exist_ok=True)

        # Copy .gitignore
        if gitignore_src.exists():
            shutil.copy2(str(gitignore_src), str(project_dir / ".gitignore"))

        # Generate yuleosh.yaml project config with template metadata
        yuleosh_config = {
            "project": project_name,
            "template": template_name,
            "template_version": tpl.get("version", "1.0.0"),
            "created_with": "yuleosh",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
        }
        (project_dir / "yuleosh.yaml").write_text(
            json.dumps(yuleosh_config, indent=2, ensure_ascii=False)
        )

        # Create tests/ placeholder
        (project_dir / "tests").mkdir(exist_ok=True)
        (project_dir / "tests" / ".gitkeep").write_text("")

        print(f"\n✅ Project '{project_name}' initialized from template '{template_name}'")
        print(f"   Location: {project_dir}")
        print(f"   ├── docs/spec.md")
        print(f"   ├── pipeline/config.yaml")
        print(f"   ├── src/")
        print(f"   ├── tests/")
        print(f"   ├── .gitignore")
        print(f"   └── yuleosh.yaml")
        print()
        # Tool chain status
        _ensure_tool_deps()

        available_stages = []
        if shutil.which("cppcheck"):
            available_stages.append("L1: misra-check")
        if shutil.which("python3") or shutil.which("python"):
            available_stages.append("L1: unit-tests")
        available_stages.append("L1: plan-lint")

        print(f"   {_GREEN}Available tool chain:{_RESET}")
        for stage_name in available_stages:
            print(f"     • {stage_name}")
        print()
        print(f"   Next steps:")
        print(f"   1. Edit docs/spec.md with your requirements")
        print(f"   2. Run: yuleosh spec validate docs/spec.md")
        print(f"   3. Run: yuleosh ci run 1    # Verify L1 CI")
        print()

    else:
        # Interactive mode — show list and prompt
        _interactive_template_init(project_name, parent_dir)


def _interactive_template_init(project_name: str, parent_dir: str = "."):
    """Interactive template selection (TG-REQ-003C)."""
    from yuleosh.templates import list_templates

    templates = list_templates(project_root=parent_dir)
    if not templates:
        print("No templates available.", file=sys.stderr)
        sys.exit(1)

    print("\nAvailable templates:")
    for i, t in enumerate(templates, 1):
        desc = t.get("description", "")
        print(f"  {i}. {t['name']} — {desc}")

    print()
    try:
        choice = input("Select a template (1-{}): ".format(len(templates))).strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(templates):
            raise ValueError
    except (ValueError, EOFError):
        print("Invalid selection.", file=sys.stderr)
        sys.exit(1)

    selected = templates[idx]
    cmd_template_init(project_name, parent_dir, selected["name"])


# ── Existing commands ──────────────────────────────────────────────────


def _ensure_tool_deps():
    """Check tool dependencies (cppcheck) and suggest install commands.

    Prints green ✅ for available tools and yellow ⚠️ with install
    commands for missing tools.  Does NOT block init on missing tools.
    """
    print("  🔧 Tool dependency check...")

    # Check cppcheck
    cppcheck_version = None
    cppcheck_path = shutil.which("cppcheck")
    if cppcheck_path:
        try:
            result = subprocess.run(
                ["cppcheck", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                cppcheck_version = result.stdout.strip() or result.stderr.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if cppcheck_version:
        print(f"    {_GREEN}✅{_RESET} cppcheck — {cppcheck_version}")
    else:
        install_cmds = []
        if shutil.which("brew"):
            install_cmds.append("brew install cppcheck")
        if shutil.which("apt-get"):
            install_cmds.append("sudo apt-get install -y cppcheck")
        if shutil.which("pip3"):
            install_cmds.append("pip3 install cppcheck")

        if install_cmds:
            print(f"    {_YELLOW}⚠️  cppcheck not found{_RESET}")
            for cmd in install_cmds:
                print(f"       Try: {cmd}")
        else:
            print(f"    {_YELLOW}⚠️  cppcheck not found — install manually from https://cppcheck.sourceforge.io/{_RESET}")


def cmd_init_autosar(project_name: str, parent_dir: str = ".", yuleasr_home: str | None = None):
    """Initialize a yuleASR AUTOSAR BSW project from the yuleasr template.

    Creates a complete AUTOSAR project structure with:
      - MCAL (21 modules): Mcu, Dio, Port, Gpt, Can, Lin, Spi, Adc, Pwm, Icu, ...
      - ECUAL (29 modules): CanIf, CanTp, LinIf, MemIf, Fee, WdgIf, ...
      - Services (44 modules): Com, Dcm, Dem, EcuM, BswM, SchM, NvM, ...
      - Application SW-Cs with RTE-compatible interfaces
      - Build system (Makefile + CMakeLists.txt) referencing yuleASR
      - Linker script for S32K312

    Args:
        project_name: Name of the new AUTOSAR project.
        parent_dir: Parent directory to create the project in.
        yuleasr_home: Override path to yuleASR checkout. If not provided,
                      the YULEASR_HOME environment variable is used.
    """
    # Resolve template via the built-in template system
    from yuleosh.templates import resolve_template, get_template_dir

    tpl = resolve_template("yuleasr", project_root=".")
    if tpl is None:
        print(f"Error: built-in template 'yuleasr' not found.", file=sys.stderr)
        sys.exit(1)

    tpl_dir = get_template_dir(tpl)
    if tpl_dir is None or not tpl_dir.exists():
        print(f"Error: yuleasr template directory not found.", file=sys.stderr)
        sys.exit(1)

    project_dir = Path(parent_dir) / project_name
    if project_dir.exists():
        print(f"Error: Directory already exists: {project_dir}", file=sys.stderr)
        sys.exit(1)

    # Resolve yuleASR home
    asr_home = yuleasr_home or os.environ.get("YULEASR_HOME", "")
    asr_path_info = ""
    if asr_home:
        asr_path = Path(asr_home)
        if asr_path.exists() and asr_path.is_dir():
            asr_path_info = f"yuleASR found at: {asr_path.resolve()}"
        else:
            asr_path_info = f"⚠️  YULEASR_HOME set but not found: {asr_home}"
    else:
        asr_path_info = "⚠️  YULEASR_HOME not set. Set it before building."

    print(f"🔧 Initializing {_GREEN}yuleASR AUTOSAR BSW{_RESET} project '{project_name}'...")
    print(f"   Template: {tpl_dir}")
    print(f"   {asr_path_info}")

    # Copy template files
    specs_src = tpl_dir / "specs"
    pipeline_src = tpl_dir / "pipeline"
    src_src = tpl_dir / "src"
    gitignore_src = tpl_dir / ".gitignore"

    project_dir.mkdir(parents=True, exist_ok=True)

    # Docs: spec.md
    if specs_src.exists():
        (project_dir / "docs").mkdir(exist_ok=True)
        spec_content = (specs_src / "spec.md").read_text(encoding="utf-8")
        spec_content = spec_content.replace("{name}", project_name)
        (project_dir / "docs" / "spec.md").write_text(spec_content, encoding="utf-8")

    # Pipeline config
    if pipeline_src.exists():
        (project_dir / "pipeline").mkdir(exist_ok=True)
        shutil.copy2(str(pipeline_src / "config.yaml"), str(project_dir / "pipeline" / "config.yaml"))

    # Source code
    if src_src.exists():
        shutil.copytree(str(src_src), str(project_dir / "src"), dirs_exist_ok=True)

    # .gitignore
    if gitignore_src.exists():
        shutil.copy2(str(gitignore_src), str(project_dir / ".gitignore"))

    # Create config/ and linker/ directories with stubs
    (project_dir / "config").mkdir(exist_ok=True)
    (project_dir / "linker").mkdir(exist_ok=True)
    (project_dir / "arxml").mkdir(exist_ok=True)

    # Create config stubs
    from datetime import datetime
    config_stubs = {
        "Mcu_Cfg.h": f"""/**
 * @file Mcu_Cfg.h
 * @brief MCU Configuration — generated by yuleOSH init-autosar
 * Target: S32K312
 */
#ifndef MCU_CFG_H
#define MCU_CFG_H

#define MCU_CORE_CLOCK_HZ   120000000UL   /* 120 MHz */
#define MCU_BUS_CLOCK_HZ    60000000UL    /* 60 MHz  */

#endif /* MCU_CFG_H */
""",
        "Dio_Cfg.h": f"""/**
 * @file Dio_Cfg.h
 * @brief DIO Configuration — generated by yuleOSH init-autosar
 */
#ifndef DIO_CFG_H
#define DIO_CFG_H

#define DIO_NUM_CHANNELS    4U

#endif /* DIO_CFG_H */
""",
        "Port_Cfg.h": f"""/**
 * @file Port_Cfg.h
 * @brief Port Configuration — generated by yuleOSH init-autosar
 */
#ifndef PORT_CFG_H
#define PORT_CFG_H

#define PORT_NUM_PINS       10U

#endif /* PORT_CFG_H */
""",
        "Can_Cfg.h": f"""/**
 * @file Can_Cfg.h
 * @brief CAN Configuration — generated by yuleOSH init-autosar
 */
#ifndef CAN_CFG_H
#define CAN_CFG_H

#define CAN_NUM_CONTROLLERS 1U
#define CAN_0_BAUDRATE      500000UL

#endif /* CAN_CFG_H */
""",
    }

    for fname, content in config_stubs.items():
        (project_dir / "config" / fname).write_text(content)

    # Create tests/ placeholder
    (project_dir / "tests").mkdir(exist_ok=True)
    (project_dir / "tests" / ".gitkeep").write_text("")

    # Generate project metadata
    metadata = {
        "project": project_name,
        "template": "yuleasr",
        "template_version": tpl.get("version", "1.0.0"),
        "target_mcu": "S32K312",
        "bsw_modules": {
            "mcal": tpl.get("yuleasr", {}).get("modules_mcal", []),
            "ecual": tpl.get("yuleasr", {}).get("modules_ecual", []),
            "services": tpl.get("yuleasr", {}).get("modules_services", []),
        },
        "yuleasr_home": asr_home,
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }
    (project_dir / "yuleosh.yaml").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    mcal_count = len(metadata["bsw_modules"]["mcal"])
    ecual_count = len(metadata["bsw_modules"]["ecual"])
    svc_count = len(metadata["bsw_modules"]["services"])

    print(f"\n✅ AUTOSAR BSW project '{project_name}' initialized")
    print(f"   Location: {project_dir}")
    print(f"   ├── docs/spec.md          — OpenSpec with yuleASR AUTOSAR requirements")
    print(f"   ├── pipeline/config.yaml  — Pipeline configuration")
    print(f"   ├── src/                   — Application source (main.c, SW-Cs)")
    print(f"   ├── config/               — BSW configuration headers")
    print(f"   ├── linker/               — Linker script (S32K312)")
    print(f"   ├── arxml/                — ARXML descriptors")
    print(f"   ├── tests/                — Unit tests")
    print(f"   ├── .gitignore")
    print(f"   └── yuleosh.yaml")
    print()
    print(f"   {_GREEN}yuleASR BSW Stack:{_RESET}")
    print(f"     • MCAL     {mcal_count:2d} modules — hardware abstraction")
    print(f"     • ECUAL    {ecual_count:2d} modules — communication & memory abstraction")
    print(f"     • Services {svc_count:2d} modules — diagnostics, COM, NVM, mode mgmt")
    print()
    if asr_home:
        print(f"   yuleASR path: {asr_home}")
    else:
        print(f"   Set YULEASR_HOME before building:")
        print(f"     export YULEASR_HOME=/path/to/yuleASR")
    print()
    print(f"   Next steps:")
    print(f"   1. Review docs/spec.md and add your project-specific requirements")
    print(f"   2. Edit config/*.h with your target-specific BSW configuration")
    print(f"   3. Set YULEASR_HOME and build:")
    print(f"      export YULEASR_HOME=/path/to/yuleASR")
    print(f"      cd {project_dir}")
    print(f"      make")
    print(f"   4. Run: yuleosh spec validate docs/spec.md")
    print(f"   5. Run: yuleosh ci run 1")
    print()


def cmd_init(dir_path: str = "."):
    """Initialize a new yuleOSH project directory."""
    # Tool dependency check
    _ensure_tool_deps()

    target = Path(dir_path)
    dirs = [
        target / "specs",
        target / "tasks",
        target / "src",
        target / "docs",
        target / "evidence",
        target / ".osh",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Available CI stages
    available_stages = []
    if shutil.which("cppcheck"):
        available_stages.append("L1: misra-check")
    if shutil.which("python3") or shutil.which("python"):
        available_stages.append("L1: unit-tests")
    available_stages.append("L1: plan-lint")

    print(f"✅ Initialized yuleOSH project at {target}")
    print()
    print(f"   {_GREEN}Available tool chain:{_RESET}")
    for stage_name in available_stages:
        print(f"     • {stage_name}")
    print()
    print(f"   Next steps:")
    print(f"   1. Add your source code to src/")
    print(f"   2. Run: yuleosh ci run 1    # Verify L1 CI")
    print()


def cmd_spec_merge(delta_file: str, project_dir: str | None = None, dry_run: bool = False):
    """Merge a spec-delta file into the main spec (QG-003)."""
    from yuleosh.spec.merge import cmd_spec_merge as _merge_cmd
    success = _merge_cmd(delta_file, project_dir=project_dir, dry_run=dry_run)
    if not success:
        sys.exit(1)


def cmd_spec_validate(filepath: str):
    from yuleosh.spec.validate import parse_spec, validate_spec

    try:
        doc = parse_spec(filepath)
        issues = validate_spec(doc)
        error_count = sum(1 for i in issues if i.get("severity") == "ERROR")
        if error_count > 0:
            print(f"❌ Spec validation failed: {error_count} error(s)")
            for i in issues:
                if i.get("severity") == "ERROR":
                    print(f"  - {i.get('message', i)}")
            sys.exit(1)
        print(f"✅ Spec validated successfully")
    except Exception as e:
        print(f"❌ Spec validation failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_spec_diff(old: str, new: str):
    from yuleosh.spec.validate import diff_specs

    try:
        result = diff_specs(old, new)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Spec diff failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_spec_cp(args) -> None:
    """Dispatch `yuleosh spec cp <sub>` — Change Proposal management."""
    from yuleosh.spec.changes import (
        archive_change,
        list_changes,
        load_proposal,
        mark_implemented,
        propose_change,
        set_status,
        validate_proposal,
    )

    project_dir = getattr(args, "project_dir", None) or os.environ.get("OSH_HOME", ".")
    sub = getattr(args, "cp_sub", None)
    try:
        if sub == "propose":
            path = propose_change(
                project_dir,
                args.change_id,
                title=args.title,
                affects=args.affects,
            )
            print(f"✅ Change proposal created: {path}")
            print(f"   status: proposed — run `yuleosh spec cp validate {args.change_id}` to check")
        elif sub == "list":
            cps = list_changes(project_dir)
            if not cps:
                print("(no change proposals)")
                return
            for cp in cps:
                blocking = " ⛔ BLOCKING (approved, not implemented)" if cp.is_blocking else ""
                evidence = f" (evid:{cp.implemented_by})" if cp.implemented_by else ""
                print(f"  {cp.change_id:12s} [{cp.status:12s}] {cp.title}{blocking}{evidence}")
        elif sub == "status":
            cp = load_proposal(project_dir, args.change_id)
            if cp is None:
                print(f"❌ change proposal '{args.change_id}' not found")
                sys.exit(1)
            print(f"id:      {cp.change_id}")
            print(f"status:  {cp.status}")
            print(f"title:   {cp.title}")
            print(f"created: {cp.created}")
            print(f"affects: {', '.join(cp.affects) if cp.affects else '-'}")
            print(f"tasks:   {len(cp.tasks)} unchecked")
            print(f"evidence:{cp.implemented_by or '-'}")
        elif sub == "approve":
            cp = set_status(project_dir, args.change_id, "approved")
            print(f"✅ {cp.change_id} → approved (implementation may proceed)")
        elif sub == "implement":
            pipeline_run = getattr(args, "pipeline_run", "") or ""
            if pipeline_run:
                cp = mark_implemented(project_dir, args.change_id, pipeline_run)
                print(f"✅ {cp.change_id} → implemented (evidence: {pipeline_run}, ready to archive)")
            else:
                cp = set_status(project_dir, args.change_id, "implemented")
                print(f"⚠️  {cp.change_id} → implemented WITHOUT pipeline-run evidence")
                print("   archive will be BLOCKED — run `yuleosh spec cp implement "
                      f"{args.change_id} --pipeline-run <run_id>` or `yuleosh spec cp auto` first")
        elif sub == "archive":
            target = archive_change(project_dir, args.change_id)
            print(f"✅ {args.change_id} archived → {target}")
        elif sub == "validate":
            result = validate_proposal(project_dir, args.change_id)
            if not result["valid"]:
                print(f"❌ Change proposal '{args.change_id}' invalid:")
                for e in result["errors"]:
                    print(f"  - {e}")
                sys.exit(1)
            print(f"✅ Change proposal '{args.change_id}' valid")
            for w in result["warnings"]:
                print(f"  ⚠️ {w}")
        elif sub == "review":
            _cmd_spec_cp_review(project_dir)
        elif sub == "auto":
            _cmd_spec_cp_auto(project_dir, mock=getattr(args, "mock", False))
        else:
            print("usage: yuleosh spec cp <propose|list|status|approve|implement|archive|validate|review|auto>", file=sys.stderr)
            sys.exit(2)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_spec_cp_auto(project_dir: str, mock: bool = False) -> None:
    """Auto-implement approved CPs by running the pipeline (non-intrusive).

    For each approved-but-not-implemented CP: find the spec target
    (.osh/specs/ dir or spec.md), run the pipeline against it, and on
    completion record the pipeline run id as implementation evidence
    (implemented_by frontmatter). Archive afterwards is allowed.
    """
    from yuleosh.spec.changes import get_blocking_cps, mark_implemented

    blocking = get_blocking_cps(project_dir)
    if not blocking:
        print("(no approved-but-unimplemented change proposals — nothing to auto)")
        return
    spec_target = Path(project_dir) / ".osh" / "specs"
    if not spec_target.exists():
        alt = Path(project_dir) / "spec.md"
        if alt.exists():
            spec_target = alt
        else:
            print("❌ No spec found (.osh/specs/ or spec.md) — cannot auto-run pipeline", file=sys.stderr)
            sys.exit(1)

    from yuleosh.pipeline.orchestrator import run_pipeline

    for cp in blocking:
        print(f"▶️  Auto-implementing {cp.change_id} ({cp.title})...")
        try:
            session = run_pipeline(
                str(spec_target),
                name=f"cp-auto-{cp.change_id}",
                mock=mock,
            )
        except SystemExit as e:
            print(f"❌ {cp.change_id}: pipeline exited {e.code}", file=sys.stderr)
            continue
        run_id = getattr(session, "run_id", None) or getattr(session, "name", "unknown")
        if getattr(session, "status", "") == "completed":
            mark_implemented(project_dir, cp.change_id, run_id)
            print(f"✅ {cp.change_id} → implemented (pipeline {run_id})")
        else:
            print(f"⚠️  {cp.change_id}: pipeline finished with status '{getattr(session, 'status', '?')}' — not marked implemented", file=sys.stderr)


def _cmd_spec_cp_review(project_dir: str) -> None:
    """Standalone CP review via LLM (no pipeline session)."""
    import json as _json
    from pathlib import Path as _Path

    from yuleosh.pipeline.session import PipelineSession
    from yuleosh.pipeline.step_handlers.spec_cp_review import step_spec_cp_review
    from yuleosh.spec.changes import list_changes

    pending = [cp for cp in list_changes(project_dir) if cp.status == "proposed"]
    if not pending:
        print("(no pending change proposals to review)")
        return
    # Pick a spec target: .osh/specs/ directory if present, else spec.md
    spec_target = _Path(project_dir) / ".osh" / "specs"
    if not spec_target.exists():
        alt = _Path(project_dir) / "spec.md"
        if alt.exists():
            spec_target = alt
        else:
            print("❌ No spec found (.osh/specs/ or spec.md) — cannot review", file=sys.stderr)
            sys.exit(1)
    import os as _os
    _os.environ.setdefault("OSH_HOME", project_dir)
    session = PipelineSession(name="spec-cp-review-cli", spec_path=str(spec_target))
    try:
        out = step_spec_cp_review(session)
    except Exception as e:
        print(f"❌ CP review failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(_json.dumps(_json.loads(_Path(out).read_text(encoding="utf-8")), indent=2, ensure_ascii=False))


def cmd_pipeline_run(spec_path: str, mock: bool = False, from_step: int = 0):
    from yuleosh.pipeline.run import run_pipeline

    session = run_pipeline(spec_path, mock=mock, from_step=from_step)
    sys.exit(0 if session.status == "completed" else 1)


def cmd_pipeline_status(name: str = None):
    from yuleosh.pipeline.run import status_pipeline

    status_pipeline(name)


def cmd_review_auto():
    from yuleosh.review.run import auto_review

    auto_review()


def cmd_review_task(task: str, kind: str = "feature"):
    import subprocess
    from yuleosh.review.run import run_review

    try:
        # W-7 (SEC-W6 / Fix 10): bound git calls so a hung repo never
        # blocks the CLI indefinitely.
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=_osh_home(), timeout=30,
        )
    except subprocess.TimeoutExpired:
        print("❌ git diff 超时 (30s) — 已终止")
        sys.exit(1)
    changed = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    run_review(task, kind, _osh_home(), changed)


def cmd_demo_uart(target_dir: str = None, do_build: bool = False, skip_cmake: bool = False):
    """Create and run the STM32+ESP32 UART demo project."""
    from yuleosh.cli.commands.demo_uart import cmd_demo_uart
    sys.exit(cmd_demo_uart(target_dir, do_build, skip_cmake))


def cmd_ci_run(layer: str):
    from yuleosh.ci.run import run_layer1, run_layer2, run_layer3

    layers = {"1": run_layer1, "2": run_layer2, "3": run_layer3}
    handler = layers.get(layer)
    if not handler:
        print(f"❌ Unknown CI layer: {layer}", file=sys.stderr)
        sys.exit(1)

    success = handler()
    sys.exit(0 if success else 1)


def cmd_evidence_pack():
    from yuleosh.evidence.pack import generate_evidence
    generate_evidence()


def _cmd_coverage_c(build_dir: str = ".", src_dir: str = "src"):
    """Run C/C++ coverage report via gcov/lcov (``yuleosh coverage c``)."""
    from yuleosh.ci.gcov_coverage import generate_c_coverage_report

    print(f"\n  📊 C/C++ Coverage (gcov/lcov)")
    print(f"  {'=' * 50}")
    print(f"  Build dir: {build_dir}")
    print(f"  Source dir: {src_dir}")
    print()

    json_path = generate_c_coverage_report(build_dir=build_dir)
    if json_path:
        print(f"  ✅ C/C++ coverage report generated")
        print(f"  📍 JSON: {json_path}")

        # Try to load and print summary
        import json as _json
        try:
            with open(json_path) as f:
                report = _json.load(f)
            print(f"  Line rate:   {report.get('line_rate', 'N/A')}%")
            print(f"  Branch rate: {report.get('branch_rate', 'N/A')}%")
            print(f"  Files:       {report.get('total_files', 0)}")
        except Exception:
            pass
    else:
        print(f"  ❌ C/C++ coverage generation failed")
        print(f"  💡 Ensure lcov/genhtml are installed and build/ has .gcda/.gcno files")
        sys.exit(1)


def cmd_audit_code_style(project_dir: str, save: bool = True, block: bool = False, json_out: bool = False):
    """Run SWC 软件编程规范 code-style scan (``yuleosh audit code-style``)."""
    from yuleosh.ci.stages.code_style import scan_project, write_report, _load_rules

    # 项目根有规则文件才扫描
    rules_path = Path(project_dir) / "swc-c-rules.yaml"
    if not rules_path.exists():
        print("⚠️  项目根缺少 swc-c-rules.yaml — 无规则可检查")
        print("💡 复制平台默认规则: cp <yuleosh-repo>/swc-c-rules.yaml ./swc-c-rules.yaml")
        sys.exit(0 if not block else 0)

    rules = _load_rules(rules_path)
    result = scan_project(project_dir, rules)
    write_report(project_dir, result, save=save)

    if json_out:
        import json
        report = write_report(project_dir, result, save=False)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"SWC code-style scan: {result.files_scanned} files, {len(result.violations)} violations")
        for v in result.violations[:30]:
            print(f"  [{v.rule_id}] {v.file}:{v.line} {v.message}")
        if len(result.violations) > 30:
            print(f"  ... and {len(result.violations) - 30} more")
        if save:
            print(f"  📄 Report: .yuleosh/reports/code-style-report.json")

    if block and result.violations:
        sys.exit(1)


def cmd_audit_sync_check(project_dir: str, base_ref: str = "HEAD", save: bool = True):
    """Run doc sync gate check (``yuleosh audit sync-check``)."""
    from yuleosh.ci.sync_check import run_sync_check, save_sync_evidence, print_sync_result

    result = run_sync_check(project_dir, base_ref=base_ref)

    if save:
        path = save_sync_evidence(project_dir, result)
        result["_evidence_path"] = path

    print_sync_result(result)

    if result.get("status") == "failed":
        sys.exit(1)


def _cmd_coverage_gate(args):
    """Run Python coverage gate (``yuleosh coverage gate --fail-under=50``)."""
    fail_under = getattr(args, "fail_under", 50)
    print(f"\n  🧪 Coverage Gate")
    print(f"  {'=' * 50}")
    print(f"  Fail-under threshold: {fail_under}%")
    print()

    import subprocess
    import sys as _sys

    try:
        result = subprocess.run(
            [
                _sys.executable, "-m", "coverage", "run",
                "--source=src/yuleosh",
                "-m", "pytest", "tests/",
                "-q", "--ignore=tests/test_e2e.py",
                "-x", "--tb=short",
            ],
            capture_output=True,
            text=True,
            timeout=300,  # W-7: test run is the long pole — bound it explicitly
        )
    except subprocess.TimeoutExpired:
        print("❌ coverage run 超时 (300s) — 已终止")
        _sys.exit(1)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print(f"  ❌ Tests failed, cannot measure coverage")
        _sys.exit(1)

    try:
        report_result = subprocess.run(
            [_sys.executable, "-m", "coverage", "report", "--fail-under", str(fail_under)],
            capture_output=True,
            text=True,
            timeout=120,  # W-7
        )
    except subprocess.TimeoutExpired:
        print("❌ coverage report 超时 (120s) — 已终止")
        _sys.exit(1)
    print(report_result.stdout)
    if report_result.stderr:
        print(report_result.stderr)

    if report_result.returncode != 0:
        print(f"  ❌ Coverage gate FAILED: {fail_under}% threshold not met")
        _sys.exit(1)

    print(f"  ✅ Coverage gate PASSED ({fail_under}% threshold met)")


def _cmd_coverage_trend(args):
    """Show coverage trend (``yuleosh coverage trend``)."""
    from yuleosh.ci.coverage_trend import show_coverage_trend

    result = show_coverage_trend(
        _osh_home(),
        days=getattr(args, "days", 30),
        lines=getattr(args, "lines", 50),
        as_json=getattr(args, "json", False),
    )
    print(result)


def _collect_audit_log_verification(project_dir: Path, out_path: Path):
    """安全可审计: verify the audit log hash chain and collect the proof.

    Runs AuditLog.verify() over the project's audit logs and writes
    ``audit-log-verification.json`` into the evidence bundle. The manifest
    entry records the verdict — an intact chain is evidence the toolchain's
    own audit trail has not been tampered with.
    """
    import json as _json
    from datetime import datetime as _dt

    try:
        from yuleosh.audit import AuditLog

        log = AuditLog(data_root=str(project_dir / "data"))
        result = log.verify()

        verification = {
            "type": "audit-log-verification",
            "generated_at": _dt.now().isoformat(),
            "tool": "yuleosh audit verify",
            "valid": result["valid"],
            "checked_events": result["checked"],
            "legacy_events": result["legacy"],
            "files_covered": len(result["files"]),
            "broken_at": result["broken_at"],
            "reason": result["reason"],
            "files": result["files"],
        }
        # Write the proof into the bundle (also into reports/ for reuse).
        verify_path = out_path / "audit-log-verification.json"
        verify_path.write_text(_json.dumps(verification, ensure_ascii=False, indent=2))
        reports_dir = project_dir / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "audit-log-verification.json").write_text(
            _json.dumps(verification, ensure_ascii=False, indent=2))

        verdict = "✅ 完整" if result["valid"] else "🔴 检测到篡改"
        print(f"   🛡️ Audit Log Verification: {verdict} "
              f"({result['checked']} events)")
        return {
            "type": "audit-log-verification",
            "source": str(verify_path),
            "valid": result["valid"],
            "checked_events": result["checked"],
            "legacy_events": result["legacy"],
        }
    except Exception as e:  # noqa: BLE001 — evidence collection must not crash
        print(f"   ⚠️  Cannot verify audit log: {e}")
        return None


def cmd_audit_evidence(output_dir: str | None = None, create_zip: bool = True):
    """Generate CL2 audit evidence bundle.

    Collects all CI results, doc sync reports, C coverage reports,
    and MISRA analysis artifacts into a single audit evidence package
    suitable for CL2 functional safety assessment.

    The bundle includes:
    - All CI layer results (.osh/ci/layer*.json)
    - C/C++ coverage report (.yuleosh/reports/c-coverage.json)
    - Doc sync gate evidence
    - MISRA compliance report and trend
    - Traceability report (LRM / LRT)
    - Review reports
    - Latest pipeline run status
    - Overall audit summary (audit-manifest.json)
    - Zipped archive (.yuleosh/audit-evidence-{date}.zip)
    """
    import json
    import shutil
    from datetime import datetime
    from pathlib import Path

    project_dir = Path(_osh_home()).resolve()

    if output_dir:
        out_path = Path(output_dir).resolve()
    else:
        out_path = project_dir / ".yuleosh" / "audit"

    out_path.mkdir(parents=True, exist_ok=True)

    print(f"\n📋 CL2 Audit Evidence Generation")
    print(f"{'='*55}")
    print(f"   Project: {project_dir}")
    print(f"   Output:  {out_path}\n")

    evidence = {
        "generated_at": datetime.now().isoformat(),
        "project": str(project_dir),
        "artifacts": [],
    }

    # 1. Collect CI layer results
    ci_dir = project_dir / ".osh" / "ci"
    if ci_dir.exists():
        layer_files = sorted(ci_dir.glob("layer*.json"))
        for lf in layer_files:
            try:
                data = json.loads(lf.read_text())
                evidence["artifacts"].append({
                    "type": "ci-layer-result",
                    "source": str(lf),
                    "layer": data.get("layer"),
                    "status": data.get("status"),
                    "stages": data.get("stages", []),
                })
                # Copy to audit bundle
                shutil.copy2(str(lf), str(out_path / lf.name))
                print(f"   📄 CI Layer {data.get('layer')}: {data.get('status', 'unknown')}")
            except (json.JSONDecodeError, OSError) as e:
                print(f"   ⚠️  Cannot read {lf.name}: {e}")
    else:
        print("   ⏭️  No CI layer results found")

    # 2. Collect C/C++ coverage report
    c_cov_path = project_dir / ".yuleosh" / "reports" / "c-coverage.json"
    if c_cov_path.exists():
        try:
            data = json.loads(c_cov_path.read_text())
            evidence["artifacts"].append({
                "type": "c-coverage",
                "source": str(c_cov_path),
                "line_rate": data.get("line_rate"),
                "branch_rate": data.get("branch_rate"),
                "total_files": data.get("total_files"),
            })
            shutil.copy2(str(c_cov_path), str(out_path / "c-coverage.json"))
            print(f"   📊 C Coverage: {data.get('line_rate', 'N/A')}% line, {data.get('branch_rate', 'N/A')}% branch")
        except (json.JSONDecodeError, OSError) as e:
            print(f"   ⚠️  Cannot read C coverage: {e}")
    else:
        print("   ⏭️  No C coverage report")

    # 3. Collect doc sync gate evidence
    docsync_path = project_dir / ".yuleosh" / "reports" / "docsync-evidence.json"
    if docsync_path.exists():
        try:
            data = json.loads(docsync_path.read_text())
            evidence["artifacts"].append({
                "type": "docsync-gate",
                "source": str(docsync_path),
                "status": data.get("status", "unknown"),
                "rule_results": data.get("rule_results", []),
            })
            shutil.copy2(str(docsync_path), str(out_path / "docsync-evidence.json"))
            status = data.get("status", "unknown")
            print(f"   📝 Doc Sync Gate: {status}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"   ⚠️  Cannot read doc sync evidence: {e}")
    else:
        print("   ⏭️  No doc sync gate evidence (run 'yuleosh ci run 1' first)")

    # 4. Collect MISRA report
    misra_report_path = project_dir / ".yuleosh" / "reports" / "misra-report.json"
    if misra_report_path.exists():
        try:
            data = json.loads(misra_report_path.read_text())
            evidence["artifacts"].append({
                "type": "misra-report",
                "source": str(misra_report_path),
                "total_violations": data.get("summary", {}).get("total_violations", 0),
                "total_rules_violated": data.get("summary", {}).get("total_rules_violated", 0),
            })
            shutil.copy2(str(misra_report_path), str(out_path / "misra-report.json"))
            viol = data.get("summary", {}).get("total_violations", 0)
            print(f"   🔍 MISRA Report: {viol} violation(s)")
        except (json.JSONDecodeError, OSError) as e:
            print(f"   ⚠️  Cannot read MISRA report: {e}")
    else:
        print("   ⏭️  No MISRA report")

    # 5. Check for MISRA trend data
    misra_trend_path = project_dir / ".yuleosh" / "reports" / "misra-trend.json"
    if misra_trend_path.exists():
        try:
            shutil.copy2(str(misra_trend_path), str(out_path / "misra-trend.json"))
            evidence["artifacts"].append({
                "type": "misra-trend",
                "source": str(misra_trend_path),
            })
            print("   📈 MISRA Trend: collected")
        except OSError:
            pass

    # 6. Check pipeline status
    pipeline_status_path = project_dir / ".osh" / "pipeline-status.json"
    if pipeline_status_path.exists():
        try:
            data = json.loads(pipeline_status_path.read_text())
            evidence["artifacts"].append({
                "type": "pipeline-status",
                "source": str(pipeline_status_path),
                "status": data.get("status"),
            })
            shutil.copy2(str(pipeline_status_path), str(out_path / "pipeline-status.json"))
            print(f"   🔄 Pipeline Status: {data.get('status', 'unknown')}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"   ⚠️  Cannot read pipeline status: {e}")
    else:
        print("   ⏭️  No pipeline status")

    # 7. Collect evidence pack if exists
    evidence_dir = project_dir / ".osh" / "evidence"
    if evidence_dir.exists():
        evidence_zips = list(evidence_dir.glob("*.zip"))
        if evidence_zips:
            latest_zip = max(evidence_zips, key=lambda p: p.stat().st_mtime)
            try:
                shutil.copy2(str(latest_zip), str(out_path / latest_zip.name))
                evidence["artifacts"].append({
                    "type": "evidence-zip",
                    "source": str(latest_zip),
                })
                print(f"   📦 Evidence Pack: {latest_zip.name}")
            except OSError as e:
                print(f"   ⚠️  Cannot copy evidence pack: {e}")

    # 8. Collect CI config for audit trail
    ci_config_path = project_dir / ".yuleosh" / "ci-config.yaml"
    if ci_config_path.exists():
        try:
            shutil.copy2(str(ci_config_path), str(out_path / "ci-config.yaml"))
            evidence["artifacts"].append({
                "type": "ci-config",
                "source": str(ci_config_path),
            })
            print("   ⚙️  CI Config: collected")
        except OSError as e:
            print(f"   ⚠️  Cannot copy CI config: {e}")

    # 9. Collect traceability report (E13 requirement)
    traceability_report = project_dir / ".yuleosh" / "reports" / "traceability-report.json"
    if traceability_report.exists():
        try:
            data = json.loads(traceability_report.read_text())
            evidence["artifacts"].append({
                "type": "traceability-report",
                "source": str(traceability_report),
                "coverage_summary": data.get("coverage_summary", {}),
            })
            shutil.copy2(str(traceability_report), str(out_path / "traceability-report.json"))
            print(f"   📋 Traceability Report: collected")
        except (json.JSONDecodeError, OSError) as e:
            print(f"   ⚠️  Cannot read traceability report: {e}")
    else:
        print("   ⏭️  No traceability report")

    # 10. Collect LRM / LRT matrix
    lrt_path = project_dir / ".yuleosh" / "reports" / "lrt-matrix.json"
    if lrt_path.exists():
        try:
            shutil.copy2(str(lrt_path), str(out_path / "lrt-matrix.json"))
            evidence["artifacts"].append({
                "type": "lrt-matrix",
                "source": str(lrt_path),
            })
            print(f"   📋 LRT Matrix: collected")
        except OSError as e:
            print(f"   ⚠️  Cannot copy LRT matrix: {e}")
    else:
        print("   ⏭️  No LRT matrix")

    # 11. Collect review reports
    review_dir = project_dir / ".yuleosh" / "reports" / "reviews"
    if review_dir.exists():
        review_files = sorted(review_dir.glob("*.json"))
        if review_files:
            rev_out = out_path / "reviews"
            rev_out.mkdir(parents=True, exist_ok=True)
            for rf in review_files:
                try:
                    shutil.copy2(str(rf), str(rev_out / rf.name))
                    evidence["artifacts"].append({
                        "type": "review-report",
                        "source": str(rf),
                    })
                except OSError as e:
                    print(f"   ⚠️  Cannot copy review report {rf.name}: {e}")
            print(f"   📝 Review Reports: {len(review_files)} file(s)")
    else:
        print("   ⏭️  No review reports")

    # 12. Collect everything in evidence_dir (not just zips)
    if evidence_dir.exists():
        for ev_file in sorted(evidence_dir.glob("*.*")):
            try:
                shutil.copy2(str(ev_file), str(out_path / ev_file.name))
                evidence["artifacts"].append({
                    "type": "evidence-artifact",
                    "source": str(ev_file),
                })
            except OSError:
                pass

    # 12.5 安全可审计: verify audit log hash chain (2026-08-07)
    # Proves the toolchain's own audit trail is intact — tampering with any
    # recorded event breaks the chain and fails this evidence gate.
    audit_verification = _collect_audit_log_verification(project_dir, out_path)
    if audit_verification is not None:
        evidence["artifacts"].append(audit_verification)

    # Write audit manifest
    manifest_path = out_path / "audit-manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(evidence, f, indent=2)

    print(f"\n{'='*55}")
    print(f"✅ CL2 Audit Evidence Bundle Complete")
    print(f"   Location: {out_path}/")
    print(f"   Artifacts collected: {len(evidence['artifacts'])}")
    print(f"   Manifest: {manifest_path}")

    # E13: Create zip archive
    if create_zip:
        import zipfile
        date_str = datetime.now().strftime("%Y%m%d")
        zip_path = project_dir / ".yuleosh" / f"audit-evidence-{date_str}.zip"

        print(f"\n   📦 Packaging evidence into: {zip_path}")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in out_path.rglob("*"):
                if item.is_file():
                    arcname = str(item.relative_to(out_path))
                    zf.write(str(item), arcname)

        evidence["zip_path"] = str(zip_path)
        zip_size = zip_path.stat().st_size
        print(f"   ✅ Audit evidence archive created ({zip_size:,} bytes)")

        # Update manifest to include zip info
        evidence["artifacts"].append({
            "type": "audit-evidence-zip",
            "source": str(zip_path),
            "size_bytes": zip_size,
        })
        with open(manifest_path, "w") as f:
            json.dump(evidence, f, indent=2)

    print()

    return evidence


# ── KPI Commands (E08/E09) ────────────────────────────────────────────


def cmd_kpi_status(args):
    """Show current KPI dashboard (violations, coverage, trend)."""
    from yuleosh.ci.kpi import kpi_status
    result = kpi_status(
        project_dir=_osh_home(),
        as_json=getattr(args, "json", False),
    )
    print(result)


def cmd_kpi_baseline_save(args):
    """Save current state as KPI baseline."""
    from yuleosh.ci.kpi import kpi_baseline_save
    saved = kpi_baseline_save(
        project_dir=_osh_home(),
        label=getattr(args, "label", ""),
    )
    if getattr(args, "json", False):
        print(json.dumps(saved, indent=2, ensure_ascii=False, default=str))
    else:
        label = saved.get("label", "")
        bl_id = saved["baseline_id"]
        ts = saved["saved_at"][:19]
        print(f"\n  ✅ KPI 基线已保存")
        print(f"     ID:    {bl_id}")
        if label:
            print(f"     Label: {label}")
        print(f"     时间:  {ts}")
        print(f"     MISRA 违规:  {saved['snapshot']['misra']['total_violations']}")
        print(f"     C Line 覆盖率: {saved['snapshot']['coverage']['c_line_rate']}%")
        print()


def cmd_kpi_baseline_compare(args):
    """Compare current state against baseline."""
    from yuleosh.ci.kpi import kpi_baseline_compare
    result = kpi_baseline_compare(
        project_dir=_osh_home(),
        as_json=getattr(args, "json", False),
    )
    print(result)


def cmd_stats(json_output: bool = False):
    from yuleosh.cli.stats import cmd_stats
    cmd_stats(to_json=json_output)


# ── MP-16: KPI 基线 CI 告警联动 ─────────────────────────────────────


def cmd_kpi_ci_alert(args):
    """Check KPI baseline thresholds and emit CI warnings (MP-16)."""
    from yuleosh.ci.kpi import (
        DEFAULT_THRESHOLDS, _load_latest_misra_entry, _load_latest_coverage_entry
    )
    from yuleosh.ci.misra_trend import TREND_FILE as _misra_trend_file
    from yuleosh.ci.coverage_trend import TREND_FILE as _cov_trend_file

    project_dir = _osh_home()
    warnings = []

    # Check MISRA trend against threshold
    misra_entry = _load_latest_misra_entry(project_dir)
    if misra_entry:
        total_violations = misra_entry.get("total_violations", 0)
        threshold = DEFAULT_THRESHOLDS.get("misra_total_violations", 50)
        if total_violations > threshold:
            warnings.append({
                "type": "misra_trend",
                "message": f"MISRA 违规数 {total_violations} 超过阈值 {threshold}",
                "current": total_violations,
                "threshold": threshold,
                "severity": "WARNING" if total_violations <= threshold * 1.5 else "CRITICAL",
            })

    # Check coverage trend against threshold
    cov_entry = _load_latest_coverage_entry(project_dir)
    if cov_entry:
        line_rate = cov_entry.get("line_rate", 100.0)
        if isinstance(line_rate, str):
            try:
                line_rate = float(line_rate.rstrip("%"))
            except (ValueError, AttributeError):
                line_rate = 100.0
        line_rate = float(line_rate)
        threshold = DEFAULT_THRESHOLDS.get("c_line_coverage_pct", 80.0)
        if line_rate < threshold:
            warnings.append({
                "type": "coverage_trend",
                "message": f"C 覆盖率 {line_rate:.1f}% 低于阈值 {threshold}%",
                "current": line_rate,
                "threshold": threshold,
                "severity": "WARNING" if line_rate >= threshold * 0.85 else "CRITICAL",
            })

    as_json = getattr(args, "json", False)

    if as_json:
        output = {
            "check_time": __import__("datetime").datetime.now().isoformat(),
            "total_warnings": len(warnings),
            "warnings": warnings,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        return

    print(f"\n  {'=' * 60}")
    print(f"   KPI 基线 CI 告警联动检查 (MP-16)")
    print(f"  {'=' * 60}")

    if not warnings:
        print(f"\n   ✅ 所有 KPI 阈值正常，无告警\n")
        return

    for w in warnings:
        severity_icon = "🔴" if w["severity"] == "CRITICAL" else "🟡"
        print(f"  {severity_icon} [{w['severity']}] {w['type']}")
        print(f"     {w['message']}")
        print()

    print(f"  总告警数: {len(warnings)}")

    if any(w["severity"] == "CRITICAL" for w in warnings):
        print(f"  ⚠️ 存在 CRITICAL 告警 — 请检查 KPI 基线")
    print()




def cmd_audit_verify(tenant: str = "", from_date: str = "",
                     to_date: str = "", as_json: bool = False):
    """Verify audit log hash-chain integrity (安全可审计, 2026-08-07).

    Replays every audit event in the covered date range and confirms the
    SHA-256 hash chain is unbroken. Any edit, deletion, or reordering of a
    recorded event is detected. Exit code 0 = chain intact, 1 = tampered.
    """
    from yuleosh.audit import AuditLog

    log = AuditLog()
    result = log.verify(tenant=tenant, from_date=from_date, to_date=to_date)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["valid"] else 1)

    if result["valid"]:
        print("✅ 审计日志哈希链完整（安全可审计）")
        print(f"   校验事件数: {result['checked']}")
        print(f"   旧格式事件(legacy): {result['legacy']}")
        print(f"   覆盖文件: {len(result['files'])} 个")
        for f in result["files"]:
            print(f"     - {f}")
        sys.exit(0)
    else:
        print("🔴 审计日志哈希链校验失败 — 检测到篡改！")
        print(f"   断裂位置: 第 {result['broken_at']} 个事件")
        print(f"   原因: {result['reason']}")
        print(f"   已校验事件数: {result['checked']}")
        sys.exit(1)
