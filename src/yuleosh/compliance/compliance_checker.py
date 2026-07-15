"""
yuleOSH ASPICE Compliance Checker — Engine.

Traverses a project directory, compares project artifacts against ASPICE
v3.1 SWE.1~SWE.6 checkpoint templates, and produces a compliance report
marking each base practice as ✅ (present), ⚠️ (partial), or ❌ (gap).
"""

import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

# Path to the ASPICE v3.1 definition YAML
_DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "aspice_v3.1.yaml"


class ComplianceChecker:
    """Check a project directory for ASPICE v3.1 compliance."""

    def __init__(self, project_dir: str, template_path: Optional[Path] = None):
        self.project_dir = Path(project_dir)
        self.template_path = template_path or _DEFAULT_TEMPLATE
        self.template = self._load_template()
        self.results: list[dict] = []
        self.generated_at = datetime.now().isoformat()

    def _load_template(self) -> dict:
        """Load the ASPICE checkpoint definition YAML."""
        with open(self.template_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ------------------------------------------------------------------
    # Check helpers
    # ------------------------------------------------------------------

    def _file_exists(self, *parts: str) -> bool:
        """Check if a relative file path exists under the project dir."""
        return (self.project_dir.joinpath(*parts)).exists()

    def _dir_has_files(self, *parts: str) -> bool:
        """Check if a relative directory has files under the project dir."""
        d = self.project_dir.joinpath(*parts)
        return d.is_dir() and any(d.iterdir())

    def _has_content_matching(self, pattern: str, *parts: str) -> bool:
        """Check if a file contains a regex-like substring pattern."""
        target = self.project_dir.joinpath(*parts)
        if not target.exists() or not target.is_file():
            return False
        try:
            content = target.read_text(errors="replace")
            return pattern.lower() in content.lower()
        except Exception:
            return False

    def _has_traced_requirements(self) -> bool:
        """Check for requirement traceability evidence."""
        trace_files = [
            self.project_dir / ".osh" / "evidence" / "traceability-matrix.md",
            self.project_dir / ".osh" / "evidence" / "traceability-matrix.json",
            self.project_dir / ".osh" / "evidence" / "acceptance-matrix.md",
        ]
        return any(tf.exists() for tf in trace_files)

    def _count_unit_tests(self) -> int:
        """Count unit test files in tests/ directory."""
        tests_dir = self.project_dir / "tests"
        if not tests_dir.is_dir():
            return 0
        return sum(1 for f in tests_dir.glob("test_*.py") if f.is_file())

    def _ci_results_exist(self) -> bool:
        """Check for CI result files."""
        ci_dir = self.project_dir / ".osh" / "ci"
        if not ci_dir.is_dir():
            return False
        return any(f.suffix == ".json" for f in ci_dir.iterdir())

    def _has_sil_results(self) -> bool:
        """Check for SIL/HIL test results."""
        ci_dir = self.project_dir / ".osh" / "ci"
        if not ci_dir.is_dir():
            return False
        return any("sil" in f.name.lower() for f in ci_dir.iterdir())

    def _evidence_dir_exists(self) -> bool:
        """Check if evidence directory has generated files."""
        ev_dir = self.project_dir / ".osh" / "evidence"
        return ev_dir.is_dir() and any(ev_dir.iterdir())

    # ------------------------------------------------------------------
    # BP-level check execution
    # ------------------------------------------------------------------

    def _get_kg_store(self):
        """Try to get KG store, return None if unavailable."""
        try:
            from yuleosh.knowledge_graph import get_store
            return get_store(str(self.project_dir))
        except Exception:
            return None

    def _check_with_kg(self, check_item: str, kg_store) -> bool | None:
        """Run check against KG data. Returns True/False, or None to fallback to file check."""
        if kg_store is None:
            return None  # fallback to file check

        check_item_lower = check_item.lower()

        # ── Existing KG mappings ────────────────────────────────────────

        if "trace" in check_item_lower or "bidirectional" in check_item_lower:
            try:
                stats = self._get_kg_stats(kg_store)
                graph = stats.get("graph", {})
                if not graph:
                    return None  # KG data unavailable, fall back
                return stats.get("implements_edges", 0) > 0
            except Exception:
                return None

        if "unit test" in check_item_lower or "unit verification" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import get_aspice_coverage
                cov = get_aspice_coverage(kg_store)
                unit_covers = cov.get("unit", {}).get("total_covers", 0) if isinstance(cov, dict) else 0
                return unit_covers > 0
            except Exception:
                return None

        if "integration" in check_item_lower or "confirm" in check_item_lower or "validat" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import get_confirmation_trace
                confirms = get_confirmation_trace(kg_store)
                return len(confirms) > 0
            except Exception:
                return None

        if "snapshot" in check_item_lower or "ci result" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import list_snapshots
                snapshots = list_snapshots(kg_store)
                return len(snapshots) > 0
            except Exception:
                return None

        # ── New KG mappings (R-03) ──────────────────────────────────────

        # coverage: aggregate covers count from all layers
        if "coverage" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import get_aspice_coverage
                cov = get_aspice_coverage(kg_store)
                if not isinstance(cov, dict):
                    return None
                total_covers = sum(
                    layer.get("total_covers", 0)
                    for layer in cov.values()
                    if isinstance(layer, dict)
                )
                return total_covers > 0
            except Exception:
                return None

        # review: check for review-related content in KG
        # NOTE: must come BEFORE architecture check since check items like
        # "Architecture review is conducted" contain BOTH keywords.
        if "review" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import list_snapshots
                snapshots = list_snapshots(kg_store)
                # Check if any snapshot meta contains review evidence
                for snap in snapshots:
                    meta = snap.get("meta", {}) if isinstance(snap, dict) else {}
                    meta_str = str(meta).lower()
                    if "review" in meta_str or "comment" in meta_str:
                        return True
                # Also check for dedicated review-type nodes
                try:
                    review_nodes = kg_store.list_nodes("review")
                    if review_nodes and len(review_nodes) > 0:
                        return True
                except Exception:
                    pass
                return False
            except Exception:
                return None

        # architecture: count code_file nodes (> 5 indicates real architecture)
        if "architecture" in check_item_lower:
            try:
                stats = self._get_kg_stats(kg_store)
                graph = stats.get("graph", {})
                nodes_by_type = graph.get("nodes_by_type", {}) if isinstance(graph, dict) else {}
                code_file_count = nodes_by_type.get("code_file", 0)
                return code_file_count > 5
            except Exception:
                return None

        # standard / coding standard: check snapshot meta for misra config
        if "standard" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import list_snapshots
                snapshots = list_snapshots(kg_store)
                for snap in snapshots:
                    meta = snap.get("meta", {}) if isinstance(snap, dict) else {}
                    meta_str = str(meta).lower()
                    if "misra" in meta_str or "coding_standard" in meta_str:
                        return True
                return False
            except Exception:
                return None

        # interface: check for .h header file nodes in the graph
        if "interface" in check_item_lower:
            try:
                code_files = kg_store.list_nodes("code_file")
                header_count = sum(1 for n in code_files if n.entity_id.endswith(".h"))
                return header_count > 0
            except Exception:
                return None

        # qualification / acceptance: check integration or sil layer coverage
        if "qualification" in check_item_lower or "acceptance" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import get_aspice_coverage
                cov = get_aspice_coverage(kg_store)
                if not isinstance(cov, dict):
                    return None
                for layer in ("integration", "sil"):
                    layer_data = cov.get(layer, {})
                    if isinstance(layer_data, dict) and layer_data.get("total_covers", 0) > 0:
                        return True
                return False
            except Exception:
                return None

        # regression: need at least 4 snapshots (one full CI cycle)
        if "regression" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import list_snapshots
                snapshots = list_snapshots(kg_store)
                return len(snapshots) > 3
            except Exception:
                return None

        # impact: call impact_analysis with sample files, expect non-empty result
        if "impact" in check_item_lower:
            try:
                from yuleosh.knowledge_graph.queries import impact_analysis
                code_files = kg_store.list_nodes("code_file")
                if not code_files:
                    return False
                sample_paths = [n.entity_id for n in code_files[:3]]
                result = impact_analysis(kg_store, sample_paths)
                affected_reqs = result.get("affected_reqs", [])
                affected_tests = result.get("affected_tests", [])
                return len(affected_reqs) > 0 or len(affected_tests) > 0
            except Exception:
                return None

        return None  # fallback to file check

    def _get_kg_stats(self, kg_store) -> dict:
        """Get KG statistics for evidence reporting."""
        stats: dict[str, Any] = {}
        try:
            from yuleosh.knowledge_graph.queries import (
                get_graph_stats, get_aspice_coverage,
                get_confirmation_trace, list_snapshots
            )
            stats["graph"] = get_graph_stats(kg_store)
            coverages = get_aspice_coverage(kg_store)
            if isinstance(coverages, dict):
                stats["coverage"] = coverages
            confirms = get_confirmation_trace(kg_store)
            stats["confirms_count"] = len(confirms)
            snapshots = list_snapshots(kg_store)
            stats["snapshots_count"] = len(snapshots)

            # Extract implements edge count from graph stats
            graph = stats.get("graph", {})
            edge_types = graph.get("edges_by_type", {}) if isinstance(graph, dict) else {}
            stats["implements_edges"] = edge_types.get("implements", 0)
            stats["covers_edges"] = edge_types.get("covers", 0)
            stats["validates_edges"] = edge_types.get("validates", 0)
        except Exception:
            pass
        return stats

    def _check_bp(self, bp: dict, swe_id: str, kg_store=None) -> dict:
        """Run checks for a single base practice and return status."""
        bp_id = bp["id"]
        bp_title = bp["title"]
        checks = bp.get("check", [])
        evidence_paths = bp.get("output_evidence", [])

        passed = 0
        failed = 0
        details: list[str] = []

        # Check for expected output evidence paths
        has_evidence = False
        for ev in evidence_paths:
            ev_path = ev.get("path", "")
            ev_type = ev.get("type", "")
            found = False

            if ev_type == "document":
                found = self._file_exists(ev_path)
            elif ev_type == "source":
                found = self._dir_has_files(ev_path) if ev_path.endswith("/") else self._file_exists(ev_path)
            elif ev_type == "test":
                found = self._dir_has_files(ev_path)
                if not found and ev_path == "tests/":
                    found = self._count_unit_tests() > 0
            elif ev_type == "ci":
                found = self._ci_results_exist()
            elif ev_type == "sil":
                found = self._has_sil_results()
            elif ev_type == "evidence":
                found = self._evidence_dir_exists()
                if not found:
                    found = self._has_traced_requirements()

            if found:
                has_evidence = True
                details.append(f"  ✅ Evidence found: {ev.get('description', ev_path)}")
            else:
                details.append(f"  ❌ Missing evidence: {ev.get('description', ev_path)}")

        # Run specific check items
        for check_item in checks:
            # Try KG-aware check first
            kg_result = self._check_with_kg(check_item, kg_store)
            if kg_result is True:
                passed += 1
                details.append(f"  ✅ Check: {check_item} [KG]")
                continue
            elif kg_result is False:
                failed += 1
                details.append(f"  ❌ Check: {check_item} [KG]")
                continue
            # KG returned None — fall through to file-based check

            if "SHALL" in check_item or "shall" in check_item:
                # Requirement-related checks
                has_req = False
                for req_doc in ["docs/requirements.md", "docs/software-requirements.md", "docs/spec.md"]:
                    if self._file_exists(req_doc):
                        has_req = True
                        break
                if has_req:
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "test" in check_item.lower() or "unit test" in check_item.lower():
                ntests = self._count_unit_tests()
                if ntests > 0:
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "architecture" in check_item.lower():
                if self._file_exists("docs", "architecture.md") or self._file_exists("ARCHITECTURE.md") or self._file_exists("docs", "arch"):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "traceability" in check_item.lower() or "traced" in check_item.lower() or "trace" in check_item.lower():
                if self._has_traced_requirements():
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "review" in check_item.lower():
                rev_dir = self.project_dir / ".osh" / "reviews"
                if rev_dir.is_dir() and any(rev_dir.iterdir()):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "standard" in check_item.lower() or "coding standard" in check_item.lower():
                if self._file_exists(".clang-format") or self._file_exists(".editorconfig") or self._file_exists("pyproject.toml"):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "interface" in check_item.lower():
                inc_dirs = ["include", "inc", "src/include", "src/inc"]
                found = any(self._dir_has_files(d) for d in inc_dirs)
                if found:
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "coverage" in check_item.lower():
                if self._evidence_dir_exists():
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "integration" in check_item.lower():
                if self._file_exists("tests", "integration") or self._dir_has_files("tests", "integration"):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                elif self._ci_results_exist():
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "qualification" in check_item.lower() or "acceptance" in check_item.lower():
                if self._file_exists(".osh", "evidence", "acceptance-matrix.md"):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "regression" in check_item.lower():
                if self._ci_results_exist():
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "impact" in check_item.lower():
                if self._file_exists("docs", "impact-analysis.md"):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            elif "function" in check_item.lower() or "complexity" in check_item.lower():
                src_dir = self.project_dir / "src"
                if src_dir.is_dir() and any(src_dir.rglob("*.c")):
                    passed += 1
                    details.append(f"  ✅ Check: {check_item} (source code present)")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")
            else:
                # Fallback: if evidence directory exists, assume check is passed
                if has_evidence:
                    passed += 1
                    details.append(f"  ✅ Check: {check_item}")
                else:
                    failed += 1
                    details.append(f"  ❌ Check: {check_item}")

        total = passed + failed
        if total == 0:
            status = "⚠️"
        elif failed == 0:
            status = "✅"
        elif passed >= failed:
            status = "⚠️"
        else:
            status = "❌"

        return {
            "id": bp_id,
            "title": bp_title,
            "status": status,
            "passed_checks": passed,
            "failed_checks": failed,
            "total_checks": total,
            "details": details,
        }

    # ------------------------------------------------------------------
    # Full compliance check
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Run the full compliance check and return the report."""
        # Support both 'swe' key grouping and flat swe.1/swe.2/... keys
        swe_sections = self.template.get("swe", {})
        if not swe_sections:
            # Flat structure: collect keys starting with 'swe.'
            swe_sections = {k: v for k, v in self.template.items() if k.startswith("swe.")}
        report: dict = {
            "generated_at": self.generated_at,
            "project_dir": str(self.project_dir),
            "standard": self.template.get("meta", {}).get("standard", "ASPICE"),
            "version": self.template.get("meta", {}).get("version", "3.1"),
            "summary": {
                "total_bps": 0,
                "passed": 0,
                "partial": 0,
                "failed": 0,
            },
            "swe_sections": {},
        }

        # Try to get KG store for semantic checks
        kg_store = self._get_kg_store()
        kg_stats = self._get_kg_stats(kg_store) if kg_store is not None else {}
        report["kg_data"] = kg_stats

        for swe_key in sorted(swe_sections.keys()):
            swe = swe_sections[swe_key]
            swe_id = swe.get("id", swe_key.upper())
            bps = swe.get("base_practices", [])

            bp_results = []
            for bp in bps:
                result = self._check_bp(bp, swe_id, kg_store=kg_store)
                bp_results.append(result)
                report["summary"]["total_bps"] += 1
                if result["status"] == "✅":
                    report["summary"]["passed"] += 1
                elif result["status"] == "⚠️":
                    report["summary"]["partial"] += 1
                else:
                    report["summary"]["failed"] += 1

            report["swe_sections"][swe_key] = {
                "id": swe_id,
                "title": swe.get("title", ""),
                "description": swe.get("description", "").strip(),
                "base_practices": bp_results,
            }

        return report

    # ------------------------------------------------------------------
    # Report output
    # ------------------------------------------------------------------

    def generate_report_markdown(self, report: dict) -> str:
        """Format the compliance check report as markdown."""
        lines = [
            f"# ASPICE {report['version']} Compliance Check Report",
            f"",
            f"> Generated: {report['generated_at']}",
            f"> Project: `{report['project_dir']}`",
            f"> Standard: {report['standard']} v{report['version']}",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Count |",
            f"|:-------|------:|",
            f"| Total Base Practices | {report['summary']['total_bps']} |",
            f"| ✅ Passed | {report['summary']['passed']} |",
            f"| ⚠️  Partial | {report['summary']['partial']} |",
            f"| ❌ Failed | {report['summary']['failed']} |",
            f"",
        ]

        # ── KG Data (Real Traceability) block ──────────────────────────────
        kg_data = report.get("kg_data", {})
        if kg_data:
            graph = kg_data.get("graph", {})
            coverage = kg_data.get("coverage", {})
            lines.append("## KG Data (Real Traceability)")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|:-------|------:|")
            if isinstance(graph, dict):
                lines.append(f"| Total Nodes | {graph.get('total_nodes', 'N/A')} |")
                lines.append(f"| Total Edges | {graph.get('total_edges', 'N/A')} |")
                ebt = graph.get("edges_by_type", {})
                if isinstance(ebt, dict):
                    for etype in ["implements", "covers", "validates", "verifies"]:
                        cnt = ebt.get(etype, 0)
                        if cnt:
                            lines.append(f"| {etype} Edges | {cnt} |")
            lines.append(f"| Confirmation Traces (validates) | {kg_data.get('confirms_count', 'N/A')} |")
            lines.append(f"| CI Snapshots | {kg_data.get('snapshots_count', 'N/A')} |")
            lines.append("")
            if isinstance(coverage, dict):
                lines.append("### Per-Layer Coverage")
                lines.append("")
                lines.append("| Layer | Total Covers | Files |")
                lines.append("|:------|------------:|:------|")
                for layer_name in ["unit", "integration", "sil", "hil", "system"]:
                    layer = coverage.get(layer_name, {})
                    if layer:
                        files = layer.get("files", [])
                        files_str = ", ".join(files[:5])
                        if len(files) > 5:
                            files_str += f" (+{len(files)-5} more)"
                        lines.append(f"| {layer_name} | {layer.get('total_covers', 0)} | {files_str} |")
                unknown = coverage.get("_unknown", {})
                if unknown:
                    lines.append(f"| _unknown_ | {unknown.get('total_covers', 0)} | — |")
                lines.append("")

        for swe_key in sorted(report["swe_sections"].keys()):
            section = report["swe_sections"][swe_key]
            lines.append(f"## {section['id']}: {section['title']}")
            lines.append(f"")
            lines.append(f"{section['description']}")
            lines.append(f"")

            for bp in section["base_practices"]:
                lines.append(f"### {bp['id']}: {bp['title']}")
                lines.append(f"")
                lines.append(f"**Status**: {bp['status']} (Checks: {bp['passed_checks']}/{bp['total_checks']} passed)")
                lines.append(f"")
                for detail in bp["details"]:
                    lines.append(detail)
                lines.append(f"")

        lines.append("---")
        lines.append(f"*Report generated by yuleOSH Compliance Checker*")
        return "\n".join(lines)

    def run_and_save(self, output_path: Optional[str] = None) -> str:
        """Run compliance check, save markdown report, return file path."""
        report = self.run()
        if output_path is None:
            output_path = str(self.project_dir / ".osh" / "compliance-report.md")
        markdown = self.generate_report_markdown(report)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(markdown, encoding="utf-8")
        print(f"  ✅ Compliance report saved: {output_path}")
        return output_path
