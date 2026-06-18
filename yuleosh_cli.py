#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — Embedded AI Development Platform CLI

Usage:
    yuleosh init [dir]                       — Initialize project
    yuleosh project init [--template <name>] — Initialize project from template
    yuleosh template list                    — List available templates
    yuleosh template init <project-name>     — Create new project from starter template
    yuleosh spec validate <file>             — Validate OpenSpec spec
    yuleosh spec diff <old> <new>            — Diff two specs
    yuleosh pipeline run [--mock] <spec>     — Run full Agent pipeline
    yuleosh pipeline status [name]           — Show pipeline status
    yuleosh review auto                      — Auto-review changes
    yuleosh review task <name> [kind]        — Review specific task
    yuleosh ci run <layer>                   — Run CI layer (1/2/3)
    yuleosh evidence pack                    — Generate ASPICE compliance pack
    yuleosh audit evidence [-o <dir>]        — Generate CL2 audit evidence bundle
    yuleosh stats [--json]                   — Show project statistics
    yuleosh ui                              — Start dashboard server (:8080)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

OSH_HOME = os.environ.get(
    "OSH_HOME",
    os.path.dirname(os.path.abspath(__file__)),
)

# Ensure src/ is importable
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ANSI color constants for CLI output
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


def ensure_osh_home():
    os.environ.setdefault("OSH_HOME", OSH_HOME)


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


def cmd_pipeline_run(spec_path: str, mock: bool = False):
    from yuleosh.pipeline.run import run_pipeline

    session = run_pipeline(spec_path, mock=mock)
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

    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=OSH_HOME,
    )
    changed = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    run_review(task, kind, OSH_HOME, changed)


def cmd_demo_uart(target_dir: str = None, do_build: bool = False, skip_cmake: bool = False):
    """Create and run the STM32+ESP32 UART demo project."""
    from src.cli.commands.demo_uart import cmd_demo_uart
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

    project_dir = Path(OSH_HOME).resolve()

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


def cmd_stats(json_output: bool = False):
    from yuleosh.cli.stats import cmd_stats
    cmd_stats(to_json=json_output)


# ── Traceability Commands ───────────────────────────────────────────────


def cmd_traceability_report(args):
    """Generate full traceability report (Requirement ↔ Code ↔ Test ↔ Review)."""
    from yuleosh.alm.traceability import generate_traceability_report

    project_dir = getattr(args, "project_dir", OSH_HOME)
    spec_path = getattr(args, "spec", None)

    report = generate_traceability_report(
        project_dir=project_dir,
        spec_path=spec_path,
        output_dir=os.path.join(project_dir, ".yuleosh", "reports"),
    )

    summary = report.get("coverage_summary", {})
    print(f"\n  📊 追溯完整性报告")
    print(f"  {'─' * 50}")
    print(f"  需求总数:        {summary.get('requirements_total', 'N/A')}")
    print(f"  测试覆盖率:      {summary.get('test_coverage_pct', 0):.1f}%")
    print(f"  代码覆盖率:      {summary.get('code_coverage', 'N/A')}")
    print(f"  评审覆盖率:      {summary.get('review_coverage', 'N/A')}")
    print(f"  覆盖缺口数:      {summary.get('total_gaps', 0)}")
    print(f"  孤立测试文件:    {summary.get('orphaned_tests', 0)}")

    recs = report.get("recommendations", [])
    if recs:
        print()
        for r in recs:
            print(f"  {r}")

    report_path = os.path.join(project_dir, ".yuleosh", "reports", "traceability-report.json")
    print(f"\n  完整报告: {report_path}\n")


def cmd_traceability_matrix(args):
    """Generate LRM / LRT matrix as JSON and print formatted overview."""
    from yuleosh.alm.traceability import generate_lrm, generate_lrt

    project_dir = getattr(args, "project_dir", OSH_HOME)
    spec_path = getattr(args, "spec", None)

    lrt = generate_lrt(project_dir, spec_path)
    lrm = lrt.get("lrm", {})
    requirements = lrm.get("requirements", [])
    summary = lrm.get("summary", {})
    gaps = lrt.get("gap_analysis", {})

    # Print formatted overview
    print(f"\n  {'=' * 70}")
    print(f"  📋 需求追溯矩阵 (LRM / LRT)")
    print(f"  {'=' * 70}")
    print(f"  生成时间: {lrm.get('generated_at', '')[:19]}")
    print(f"  {'─' * 70}")

    # Table header
    header = f"  {'req_id':<20} {'SHALL':<8} {'Code':<6} {'Test':<6} {'Review':<6} {'StepHdlr':<8} Section"
    print(header)
    print(f"  {'─' * 70}")

    for req in requirements:
        req_id = req.get("req_id") or "—"
        shall_id = req.get("id", "—")
        code_icon = "✅" if req.get("has_code") else "❌"
        test_icon = "✅" if req.get("has_test") else "❌"
        review_icon = "✅" if req.get("has_review") else "❌"
        steps = req.get("step_handlers", [])
        step_str = f"{len(steps)}" if steps else "—"
        section = (req.get("section", "") or "")[:30]
        print(f"  {req_id:<20} {shall_id:<8} {code_icon:<6} {test_icon:<6} {review_icon:<6} {step_str:<8} {section}")

    print(f"  {'─' * 70}")
    total = summary.get("total", 0)
    cov = summary.get("coverage_pct", 0.0)
    print(f"  需求总数: {total}  |  测试覆盖率: {cov}%")
    print(f"  Code: {summary.get('with_code', 0)}/{total}  Test: {summary.get('with_test', 0)}/{total}  Review: {summary.get('with_review', 0)}/{total}")

    gap_list = gaps.get("gaps", [])
    if gap_list:
        print(f"\n  ⚠️  覆盖缺口: {len(gap_list)}")
        for g in gap_list[:10]:
            rid = g.get("req_id", "?")
            stmt = g.get("statement", "")[:50]
            print(f"    • [{g['type']}] {rid}: {stmt}...")
        if len(gap_list) > 10:
            print(f"    ... 还有 {len(gap_list) - 10} 个缺口")

    print()

    # Also output full JSON to stdout for pipe/redirect
    print(">>> Full JSON:", file=sys.stderr)
    print(json.dumps(lrt, indent=2, ensure_ascii=False, default=str))


# ── MISRA Deviate Commands ─────────────────────────────────────────────


def cmd_misra_deviate(args):
    """Handle ``yuleosh misra deviate`` subcommands.

    Reads/Writes deviations from/to ``.yuleosh/ci-config.yaml``.
    """
    from yuleosh.ci.config import (
        load_ci_config, update_deviation_status, _deviations_to_yaml_dicts,
    )

    project_dir = OSH_HOME
    cfg = load_ci_config(project_dir)
    deviations = cfg.misra.deviations if cfg else []

    sub = args.deviate_sub

    if sub == "list":
        if not deviations:
            print("No deviation records found.")
            return
        print(f"\n{'#':<3} {'Rule ID':<28} {'File Pattern':<30} {'Status':<12} {'Approved By':<16} {'Expires':<14}")
        print("-" * 105)
        for idx, d in enumerate(deviations, 1):
            print(f"{idx:<3} {d.rule_id:<28} {d.file_pattern:<30} {d.status:<12} {d.approved_by:<16} {d.expires:<14}")
        print()

    elif sub == "approve":
        dev_id = args.dev_id
        rule, file_pat = _parse_dev_id(dev_id)
        if not rule and not file_pat:
            print(f"Error: invalid dev_id format '{dev_id}' — expected 'rule_id:file_pattern'", file=sys.stderr)
            sys.exit(1)
        # Find the deviation by rule_id only (file_pattern may have glob chars)
        matched = [d for d in deviations if d.rule_id == rule]
        if not matched:
            print(f"Error: deviation for rule '{rule}' not found", file=sys.stderr)
            sys.exit(1)
        # Update via YAML write
        target_file = file_pat or matched[0].file_pattern
        ok = update_deviation_status(project_dir, rule, target_file, "approved")
        if ok:
            print(f"✅ Deviation {rule}:{target_file} → APPROVED")
        else:
            print(f"Error: failed to update deviation '{dev_id}'", file=sys.stderr)
            sys.exit(1)

    elif sub == "reject":
        dev_id = args.dev_id
        rule, file_pat = _parse_dev_id(dev_id)
        if not rule and not file_pat:
            print(f"Error: invalid dev_id format '{dev_id}' — expected 'rule_id:file_pattern'", file=sys.stderr)
            sys.exit(1)
        matched = [d for d in deviations if d.rule_id == rule]
        if not matched:
            print(f"Error: deviation for rule '{rule}' not found", file=sys.stderr)
            sys.exit(1)
        target_file = file_pat or matched[0].file_pattern
        ok = update_deviation_status(project_dir, rule, target_file, "rejected")
        if ok:
            print(f"✅ Deviation {rule}:{target_file} → REJECTED")
        else:
            print(f"Error: failed to update deviation '{dev_id}'", file=sys.stderr)
            sys.exit(1)

    elif sub == "add":
        _interactive_add_deviation(project_dir)

    else:
        print(f"Unknown deviate subcommand: {sub}", file=sys.stderr)
        sys.exit(1)


def _parse_dev_id(dev_id: str) -> tuple[str, str]:
    """Parse a dev_id string 'rule_id:file_pattern' into its components."""
    if ":" in dev_id:
        parts = dev_id.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    # Try matching by rule_id alone
    return dev_id.strip(), ""


def _interactive_add_deviation(project_dir: str) -> None:
    """Interactive prompt to add a new deviation to ci-config.yaml."""
    import yaml
    from pathlib import Path

    config_path = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    print("\n📝 Add a new MISRA deviation:")
    try:
        rule = input("  Rule ID (e.g. misra-c2023-17.7): ").strip()
        file_pat = input("  File pattern (e.g. src/legacy/*.c): ").strip()
        reason = input("  Reason for deviation: ").strip()
        approved_by = input("  Approved by: ").strip()
        expires = input("  Expires (ISO date, e.g. 2026-09-30): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)

    if not rule or not file_pat:
        print("Error: rule_id and file_pattern are required.", file=sys.stderr)
        sys.exit(1)

    new_entry = {
        "rule": rule,
        "file": file_pat,
        "reason": reason or "(not specified)",
        "approved_by": approved_by or "(not specified)",
        "expires": expires or "2099-12-31",
        "status": "pending",
    }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Error: failed to parse config: {e}", file=sys.stderr)
        sys.exit(1)

    # Ensure deviations list exists
    misra_block = raw.setdefault("misra", {})
    deviations = misra_block.setdefault("deviations", [])
    deviations.append(new_entry)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"✅ Deviation added: {rule}:{file_pat} (status: pending)")
    except OSError as e:
        print(f"Error: failed to write config: {e}", file=sys.stderr)
        sys.exit(1)


# ── MISRA Trend Command ────────────────────────────────────────────────


def cmd_misra_trend(args):
    """Handle ``yuleosh misra trend`` — display or export trend data."""
    from yuleosh.ci.misra_trend import show_trend

    project_dir = OSH_HOME
    result = show_trend(
        project_dir,
        lines=args.lines,
        days=args.days,
        as_json=args.json,
    )
    print(result)


# ── MISRA Profile Commands (G-17) ────────────────────────────────────────


def cmd_misra_profile_list():
    """List available MISRA profiles — both from ci-config.yaml and misra-rules.yaml."""
    from yuleosh.ci.config import load_ci_config
    import yaml

    cfg = load_ci_config(OSH_HOME)
    profiles = cfg.misra.profiles
    active = cfg.misra.active_profile

    # Count rules per profile from misra-rules.yaml
    misra_rules_path = os.path.join(OSH_HOME, "misra-rules.yaml")
    profile_counts: dict[str, int] = {"safety": 0, "performance": 0, "testing": 0}
    if os.path.exists(misra_rules_path):
        try:
            with open(misra_rules_path, encoding="utf-8") as f:
                rules_data = yaml.safe_load(f) or {}
            for rule_id, rule in rules_data.items():
                if rule_id == "meta":
                    continue
                p = rule.get("profile", "safety")
                if p in profile_counts:
                    profile_counts[p] += 1
                else:
                    profile_counts[p] = 1
        except (yaml.YAMLError, OSError):
            pass

    print(f"\n  📋 MISRA Profiles")
    print(f"  {'=' * 60}")
    
    # Show profile counts from misra-rules.yaml
    print(f"  Rules by profile (from misra-rules.yaml):")
    for prof_name in ["safety", "performance", "testing"]:
        count = profile_counts.get(prof_name, 0)
        marker = " 👉 ACTIVE" if prof_name == active else ""
        print(f"    {prof_name:15s}  {count:4d} rules{marker}")

    # Show ci-config.yaml profile overrides if any
    if profiles:
        print()
        print(f"  Profile overrides (from .yuleosh/ci-config.yaml):")
        for prof_name, prof in sorted(profiles.items()):
            marker = "👉" if prof_name == active else "  "
            ovr_count = len(prof.rule_overrides)
            dev_count = len(prof.deviations)
            print(f"  {marker} {prof_name:15s}  {prof.name}")
            if ovr_count > 0:
                print(f"        Rule overrides: {ovr_count}")
            if dev_count > 0:
                print(f"        Deviations:     {dev_count}")
    print()


def cmd_misra_profile_set(name: str):
    """Switch active MISRA profile."""
    from yuleosh.ci.config import load_ci_config

    cfg = load_ci_config(OSH_HOME)
    profiles = cfg.misra.profiles

    if not profiles:
        print("No MISRA profiles configured.")
        return

    if name not in profiles:
        print(f"Profile '{name}' not found. Available: {', '.join(profiles.keys())}")
        return

    # Update ci-config.yaml
    import yaml

    config_path = Path(OSH_HOME) / ".yuleosh" / "ci-config.yaml"
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        print("Failed to parse config YAML.")
        return

    misra_raw = raw.setdefault("misra", {})
    misra_raw["active_profile"] = name

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"✅ Switched to profile: {name} ({profiles[name].name})")


# ── MISRA Report Command ───────────────────────────────────────────────


def cmd_misra_report(args):
    """Handle ``yuleosh misra report`` — read latest report and output."""
    report_dir = Path(OSH_HOME) / ".yuleosh" / "reports"

    # Determine format
    output_format = getattr(args, "format", "summary")

    json_path = report_dir / "misra-report.json"
    md_path = report_dir / "misra-report.md"

    if not json_path.exists():
        print(f"No MISRA report found. Run CI first: yuleosh ci run 1", file=sys.stderr)
        sys.exit(1)

    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading report: {e}", file=sys.stderr)
        sys.exit(1)

    if output_format == "html":
        _render_misra_report_html(report)
    elif output_format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    elif output_format == "markdown":
        if md_path.exists():
            print(md_path.read_text(encoding="utf-8"))
        else:
            print("Markdown report not available.", file=sys.stderr)
            sys.exit(1)
    else:
        # summary (default)
        _print_misra_report_summary(report)


def _print_misra_report_summary(report: dict) -> None:
    """Print a human-readable summary of the MISRA report."""
    summary = report.get("summary", {})
    generated = report.get("generated_at", "")[:19]

    print(f"\n  📊 MISRA C:2023 Compliance Report")
    print(f"  {'─' * 50}")
    print(f"  Generated: {generated}")
    print(f"  Tool:      {report.get('tool', 'cppcheck')}")
    print()
    print(f"  Total violations:   {summary.get('total_violations', 0)}")
    print(f"  Rules violated:    {summary.get('total_rules_violated', 0)}")
    print(f"  Files affected:    {len(summary.get('unique_files', []))}")
    print()

    sev_counts = summary.get("severity_counts", {})
    if sev_counts:
        print(f"  Severity breakdown:")
        for sev in ["error", "warning", "style", "performance", "portability", "information"]:
            count = sev_counts.get(sev, 0)
            if count:
                icon = {"error": "❌", "warning": "⚠️", "style": "🎨", "performance": "⚡",
                        "portability": "🔗", "information": "ℹ️"}.get(sev, "•")
                print(f"    {icon} {sev}: {count}")

    print()
    per_file = summary.get("per_file_counts", {})
    if per_file:
        print(f"  Files with violations:")
        for fname, count in sorted(per_file.items(), key=lambda x: -x[1])[:10]:
            print(f"    • {fname}: {count}")
        if len(per_file) > 10:
            print(f"    ... and {len(per_file) - 10} more file(s)")
    print()

    # Groups (top rules)
    groups = report.get("groups", {})
    if groups:
        print(f"  Top violated rules:")
        sorted_groups = sorted(groups.items(), key=lambda x: -x[1].get("count", 0))[:5]
        for rule_id, g in sorted_groups:
            title = g.get("title", "")
            sev = g.get("severity_category", "unknown")
            sev_icon = {"required": "🔴", "advisory": "🟡", "unknown": "⚪"}.get(sev, "⚪")
            print(f"    {sev_icon} {rule_id}: {g.get('count', 0)} — {title}")
    print()

    summary_path = Path(OSH_HOME) / ".yuleosh" / "reports" / "misra-report.json"
    print(f"  Full report: {summary_path}")
    print()


def _render_misra_report_html(report: dict) -> None:
    """Render MISRA report as a simple HTML page to stdout."""
    summary = report.get("summary", {})
    generated = report.get("generated_at", "")[:19]
    total_v = summary.get("total_violations", 0)
    rules_v = summary.get("total_rules_violated", 0)
    files_n = len(summary.get("unique_files", []))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MISRA C:2023 — Compliance Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #333; }}
  h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 0.5rem; }}
  h2 {{ color: #16213e; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  .summary-card {{ background: #f8f9fa; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; display: flex; gap: 2rem; }}
  .stat {{ text-align: center; }}
  .stat-value {{ font-size: 2rem; font-weight: 700; color: #e94560; }}
  .stat-label {{ font-size: 0.85rem; color: #666; }}
  .severity-required {{ color: #d32f2f; }}
  .severity-advisory {{ color: #f57c00; }}
  footer {{ margin-top: 3rem; font-size: 0.85rem; color: #999; border-top: 1px solid #eee; padding-top: 1rem; }}
</style>
</head>
<body>
<h1>🔍 MISRA C:2023 Compliance Report</h1>
<p>Generated: {generated} | Tool: {report.get('tool', 'cppcheck')}</p>
<div class="summary-card">
  <div class="stat"><div class="stat-value">{total_v}</div><div class="stat-label">Total Violations</div></div>
  <div class="stat"><div class="stat-value">{rules_v}</div><div class="stat-label">Rules Violated</div></div>
  <div class="stat"><div class="stat-value">{files_n}</div><div class="stat-label">Files Affected</div></div>
</div>
"""

    # Severity breakdown
    sev_counts = summary.get("severity_counts", {})
    if sev_counts:
        html += "<h2>Severity Breakdown</h2>\n<table>\n<tr><th>Severity</th><th>Count</th></tr>\n"
        for sev in ["error", "warning", "style", "performance", "portability", "information"]:
            count = sev_counts.get(sev, 0)
            if count:
                html += f"<tr><td>{sev}</td><td>{count}</td></tr>\n"
        html += "</table>\n"

    # Per-file
    per_file = summary.get("per_file_counts", {})
    if per_file:
        html += "<h2>Files with Violations</h2>\n<table>\n<tr><th>File</th><th>Violations</th></tr>\n"
        for fname, count in sorted(per_file.items(), key=lambda x: -x[1])[:20]:
            html += f"<tr><td>{fname}</td><td>{count}</td></tr>\n"
        html += "</table>\n"

    # Groups
    groups = report.get("groups", {})
    if groups:
        html += "<h2>Violations by Rule</h2>\n"
        sorted_groups = sorted(groups.items(), key=lambda x: -x[1].get("count", 0))
        for rule_id, g in sorted_groups:
            title = g.get("title", "")
            sev = g.get("severity_category", "unknown")
            count = g.get("count", 0)
            sev_class = f"severity-{sev}" if sev in ("required", "advisory") else ""
            html += f"<h3 class=\"{sev_class}\">{rule_id}: {title}</h3>\n"
            html += f"<p>Count: {count} | Severity: {sev}</p>\n"
            html += "<table>\n<tr><th>File</th><th>Line</th><th>Column</th><th>Message</th></tr>\n"
            for v in g.get("violations", [])[:20]:
                msg = v.get("message", "")[:80]
                html += f"<tr><td>{v.get('file', '')}</td><td>{v.get('line', '')}</td><td>{v.get('col', '')}</td><td>{msg}</td></tr>\n"
            html += "</table>\n"

    html += """
<footer>
  Report generated by yuleOSH MISRA Report Formatter
</footer>
</body>
</html>
"""

    html_path = Path(OSH_HOME) / ".yuleosh" / "reports" / "misra-report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML report saved to: {html_path}")


# ── Parser ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the yuleOSH CLI."""
    parser = argparse.ArgumentParser(
        prog="yuleosh",
        description="yuleOSH — Embedded AI Development Platform CLI",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Initialize a yuleOSH project directory")
    p_init.add_argument("dir", nargs="?", default=".", help="Project directory")

    # project
    p_project = sub.add_parser("project", help="Project management")
    pjsub = p_project.add_subparsers(dest="project_sub")
    p_proj_init = pjsub.add_parser("init", help="Initialize project from template")
    p_proj_init.add_argument("--template", "-t", default=None, help="Template name")
    p_proj_init.add_argument("project_dir", nargs="?", default=None, help="Target project directory")

    # template
    p_template = sub.add_parser("template", help="Project template management")
    tsub = p_template.add_subparsers(dest="template_sub")
    tsub.add_parser("list", help="List all available templates")
    p_template_init = tsub.add_parser("init", help="Create project from template")
    p_template_init.add_argument("--from", dest="from_template", default=None, help="Template name or path")
    p_template_init.add_argument("project_name", help="Project name")

    # spec
    p_spec = sub.add_parser("spec", help="OpenSpec management")
    ssub = p_spec.add_subparsers(dest="spec_sub")
    p_spec_val = ssub.add_parser("validate", help="Validate an OpenSpec file")
    p_spec_val.add_argument("file", help="Spec file path")
    p_spec_diff = ssub.add_parser("diff", help="Diff two OpenSpec files")
    p_spec_diff.add_argument("old", help="Old spec file")
    p_spec_diff.add_argument("new", help="New spec file")

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="Agent pipeline management")
    psub = p_pipe.add_subparsers(dest="pipeline_sub")
    p_pipe_run = psub.add_parser("run", help="Run the full Agent pipeline")
    p_pipe_run.add_argument("--mock", action="store_true", help="Run in mock mode (no real LLM)")
    p_pipe_run.add_argument("spec", help="Specification file path")
    p_pipe_status = psub.add_parser("status", help="Show pipeline status")
    p_pipe_status.add_argument("name", nargs="?", help="Pipeline session name")

    # review
    p_review = sub.add_parser("review", help="Code review management")
    rsub = p_review.add_subparsers(dest="review_sub")
    rsub.add_parser("auto", help="Auto-review recent changes")
    p_review_task = rsub.add_parser("task", help="Review a specific task")
    p_review_task.add_argument("name", help="Task name")
    p_review_task.add_argument("kind", nargs="?", default="feature", help="Task kind")

    # ci
    p_ci = sub.add_parser("ci", help="CI pipeline management")
    csub = p_ci.add_subparsers(dest="ci_sub")
    p_ci_run = csub.add_parser("run", help="Run a CI layer")
    p_ci_run.add_argument("layer", help="CI layer (1/2/3)")

    # evidence
    sub.add_parser("evidence", help="Generate ASPICE compliance evidence")

    # stats
    p_stats = sub.add_parser("stats", help="Show project statistics")
    p_stats.add_argument("--json", action="store_true", help="Output as JSON")

    # demo
    p_demo = sub.add_parser("demo", help="Create and run demo projects")
    dsub = p_demo.add_subparsers(dest="demo_sub")
    p_demo_quick = dsub.add_parser("quick", help="Quick pipeline from one-line requirement")
    p_demo_quick.add_argument("requirement", help="One-line user requirement (e.g. '写一个刹车灯控制')")
    p_demo_quick.add_argument("--dir", default=".", help="Working directory for the demo")
    p_demo_uart = dsub.add_parser("uart", help="STM32F4 ↔ ESP32 UART communication demo")
    p_demo_uart.add_argument("--dir", default=None, help="Target directory for the demo project")
    p_demo_uart.add_argument("--build", action="store_true", help="Build and run the demo after creating it")
    p_demo_uart.add_argument("--skip-cmake", action="store_true", help="Skip CMake environment check")

    # traceability
    p_trace = sub.add_parser("traceability", help="Traceability matrix management")
    tsub = p_trace.add_subparsers(dest="traceability_sub")
    p_trace_report = tsub.add_parser("report", help="Generate full traceability report")
    p_trace_report.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_trace_report.add_argument("--spec", default=None, help="Path to spec file")
    p_trace_matrix = tsub.add_parser("matrix", help="Generate LRM/LRT matrix (JSON output)")
    p_trace_matrix.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_trace_matrix.add_argument("--spec", default=None, help="Path to spec file")

    # misra
    # coverage
    p_coverage = sub.add_parser("coverage", help="Code coverage management")
    csub = p_coverage.add_subparsers(dest="coverage_sub")
    p_coverage_c = csub.add_parser("c", help="Generate C/C++ code coverage report via gcov/lcov")
    p_coverage_c.add_argument("--build-dir", default=".",
                               help="Build directory containing .gcda/.gcno files")
    p_coverage_c.add_argument("--src-dir", default="src",
                               help="Source directory for filtering")

    # audit
    p_audit = sub.add_parser("audit", help="CL2 audit evidence management")
    asub = p_audit.add_subparsers(dest="audit_sub")
    p_audit_evidence = asub.add_parser("evidence", help="Generate CL2 audit evidence bundle (with ZIP export)")
    p_audit_evidence.add_argument("--output-dir", "-o", default=None,
                                   help="Output directory for audit bundle (default: .yuleosh/audit/)")
    p_audit_evidence.add_argument("--zip", action="store_true", default=True,
                                   help="Package evidence into a .zip archive (default: true)")
    p_audit_evidence.add_argument("--no-zip", action="store_false", dest="zip",
                                   help="Skip .zip packaging")
    p_audit_sync = asub.add_parser("sync-check", help="Doc sync gate — verify docs updated with code")
    p_audit_sync.add_argument("--project-dir", default=OSH_HOME,
                               help="Project root directory")
    p_audit_sync.add_argument("--base-ref", default="HEAD",
                               help="Git base reference for diff (default: HEAD)")
    p_audit_sync.add_argument("--save", action="store_true", default=True,
                               help="Save evidence to .yuleosh/reports/docsync-evidence.json")

    # misra
    p_misra = sub.add_parser("misra", help="MISRA C:2023 compliance management")
    msub = p_misra.add_subparsers(dest="misra_sub")

    # misra trend
    p_misra_trend = msub.add_parser("trend", help="Show MISRA violation trend")
    p_misra_trend.add_argument("--json", action="store_true", help="Output as JSON")
    p_misra_trend.add_argument("--days", type=int, default=0, help="Filter entries within N days")
    p_misra_trend.add_argument("--lines", "-n", type=int, default=30, help="Number of entries to show")

    # misra report
    p_misra_report = msub.add_parser("report", help="Show MISRA compliance report")
    p_misra_report.add_argument(
        "--format", "-f",
        choices=["summary", "json", "markdown", "html"],
        default="summary",
        help="Output format (default: summary)",
    )

    # misra profile (G-17)
    p_misra_profile = msub.add_parser("profile", help="Manage MISRA profiles")
    mprof = p_misra_profile.add_subparsers(dest="profile_sub")
    mprof.add_parser("list", help="List available profiles")
    p_misra_prof_set = mprof.add_parser("set", help="Switch active profile")
    p_misra_prof_set.add_argument("name", help="Profile name (safety|performance|testing)")

    # misra deviate
    p_misra_deviate = msub.add_parser("deviate", help="Manage deviation records")
    mdev = p_misra_deviate.add_subparsers(dest="deviate_sub")
    # deviate list
    mdev.add_parser("list", help="List all deviation records")
    # deviate approve <id>
    p_misra_dev_approve = mdev.add_parser("approve", help="Approve a deviation")
    p_misra_dev_approve.add_argument("dev_id", help="Deviation ID (rule_id:file_pattern)")
    # deviate reject <id>
    p_misra_dev_reject = mdev.add_parser("reject", help="Reject a deviation")
    p_misra_dev_reject.add_argument("dev_id", help="Deviation ID (rule_id:file_pattern)")
    # deviate add
    mdev.add_parser("add", help="Interactive add a deviation")

    # ui
    sub.add_parser("ui", help="Start the web dashboard")

    return parser


# ── Dispatch ────────────────────────────────────────────────────────────

def main():
    ensure_osh_home()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    if args.command == "init":
        cmd_init(args.dir)

    elif args.command == "project":
        if args.project_sub == "init":
            # Determine project directory name
            template_name = args.template
            project_dir = args.project_dir or (template_name + "-project" if template_name else "my-project")
            cmd_template_init(project_dir, parent_dir=".", template_name=template_name)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "template":
        if args.template_sub == "list":
            cmd_template_list()
        elif args.template_sub == "init":
            template_name = getattr(args, "from_template", None)
            cmd_template_init(args.project_name, parent_dir=".", template_name=template_name)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "spec":
        if args.spec_sub == "validate":
            cmd_spec_validate(args.file)
        elif args.spec_sub == "diff":
            cmd_spec_diff(args.old, args.new)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "pipeline":
        if args.pipeline_sub == "run":
            cmd_pipeline_run(args.spec, mock=args.mock)
        elif args.pipeline_sub == "status":
            cmd_pipeline_status(args.name)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "review":
        if args.review_sub == "auto":
            cmd_review_auto()
        elif args.review_sub == "task":
            cmd_review_task(args.name, args.kind)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "coverage":
        if args.coverage_sub == "c":
            _cmd_coverage_c(args.build_dir, args.src_dir)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "demo":
        if args.demo_sub == "quick":
            from yuleosh.api.demo_quick import main as demo_quick_main
            demo_quick_main(args.requirement, args.dir)
        elif args.demo_sub == "uart":
            cmd_demo_uart(args.dir, args.build, args.skip_cmake)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "ci":
        if args.ci_sub == "run":
            cmd_ci_run(args.layer)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "evidence":
        cmd_evidence_pack()

    elif args.command == "audit":
        if args.audit_sub == "evidence":
            cmd_audit_evidence(output_dir=args.output_dir, create_zip=getattr(args, "zip", True))
        elif args.audit_sub == "sync-check":
            cmd_audit_sync_check(
                project_dir=getattr(args, "project_dir", OSH_HOME),
                base_ref=getattr(args, "base_ref", "HEAD"),
                save=getattr(args, "save", True),
            )
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "traceability":
        if args.traceability_sub == "report":
            cmd_traceability_report(args)
        elif args.traceability_sub == "matrix":
            cmd_traceability_matrix(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "stats":
        cmd_stats(json_output=args.json)

    elif args.command == "misra":
        if args.misra_sub == "trend":
            cmd_misra_trend(args)
        elif args.misra_sub == "report":
            cmd_misra_report(args)
        elif args.misra_sub == "deviate":
            cmd_misra_deviate(args)
        elif args.misra_sub == "profile":
            if args.profile_sub == "list":
                cmd_misra_profile_list()
            elif args.profile_sub == "set":
                cmd_misra_profile_set(args.name)
            else:
                parser.print_help()
                sys.exit(1)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "ui":
        from yuleosh.ui.server import main as ui_main
        ui_main()


if __name__ == "__main__":
    main()
