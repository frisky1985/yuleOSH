"""
yuleOSH Evidence Engine — Report generation.

Provides the ``ReportBuilderMixin`` mixin class that implements report
generation methods (traceability matrix, coverage, acceptance, review logs)
for ``EvidenceCollector``.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from yuleosh.evidence.analysis import categorize_uncovered

log = logging.getLogger("evidence.report_builder")


class ReportBuilderMixin:
    """Mixin adding report-generation methods to EvidenceCollector."""

    def generate_traceability_matrix(self) -> str:
        """Generate a markdown traceability matrix + JSON export."""
        if not hasattr(self, 'req_to_tests') or not self.req_to_tests:
            self._build_requirement_to_test_map()
        uncovered = self._check_traceability_completeness()

        lines = [
            f"# Traceability Matrix\n",
            f"> Generated: {self.generated_at}",
            f"> Version: {self.version}\n",
            f"## Requirements → Implementation → Tests\n",
        ]

        for req in self.requirements:
            name = req.get("name", "Unknown")
            shall_count = req.get("shall_count", 0)
            req_id = req.get("req_id", "")
            lines.append(f"### {name}")
            if req_id:
                lines.append(f"- Req ID: {req_id}")
            lines.append(f"- SHALL statements: {shall_count}")
            impl_status = '✅ Covered' if shall_count > 0 else '❌ No implementation'
            lines.append(f"- Status: {impl_status}")

            matching_scenarios = [
                s for s in self.scenarios
                if name.lower() in s.get("name", "").lower()
            ]
            if matching_scenarios:
                lines.append(f"- Scenarios: {len(matching_scenarios)}")
                for s in matching_scenarios:
                    lines.append(f"  - {s['name']}: GIVEN({len(s['given'])}) → WHEN({len(s['when'])}) → THEN({len(s['then'])})")
            else:
                lines.append(f"- Scenarios: 0 ⚠️")

            matching_tests = self.req_to_tests.get(name, [])
            if matching_tests:
                lines.append(f"- Test files ({len(matching_tests)}):")
                for tf in matching_tests:
                    mode = self.match_modes.get(name, {}).get(tf, "keyword")
                    conf = self.match_confidences.get(name, {}).get(tf, 0.5)
                    mode_icon = "🎯" if mode == "exact" else "🔍"
                    lines.append(f"  - {tf} ({mode_icon} {mode}, confidence: {conf:.0%})")
            else:
                lines.append(f"- Test files: 0 ❌ Not covered by any test")

            lines.append(f"- SHALL details:")
            for shall in req.get("shall", []):
                is_covered = bool(matching_tests)
                icon = "✅" if is_covered else "❌"
                lines.append(f"  {icon} {shall[:80]}{'...' if len(shall) > 80 else ''}")

            matching_reviews = [
                r for r in self.reviews
                if name.lower() in r.get("task", "").lower()
            ]
            if matching_reviews:
                for r in matching_reviews:
                    lines.append(f"- Review: {r.get('decision', 'unknown')} by {len(r.get('reviews', []))} agent(s)")
            lines.append("")

        total = len(self.requirements)
        covered = sum(1 for r in self.requirements if r.get("shall_count", 0) > 0)
        test_covered = sum(1 for r in self.requirements if self.req_to_tests.get(r.get("name", ""), []))
        total_str = total if total > 0 else 1
        lines.extend([
            f"## Summary",
            f"- Total Requirements: {total}",
            f"- Requirements with implementation: {covered} ({covered/total_str*100:.0f}%)",
            f"- Requirements with test coverage: {test_covered} ({test_covered/total_str*100:.0f}%)",
            f"- Uncovered SHALLs: {len(uncovered)}",
            f"- Scenarios: {len(self.scenarios)}",
            f"- Reviews: {len(self.reviews)}",
            f"- CI Runs: {len(self.ci_results)}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "traceability-matrix.md"
        output_path.write_text(content)
        print(f"  ✅ Traceability matrix generated: {output_path}")

        ci_env = {
            "build_id": os.environ.get("BUILD_ID", ""),
            "commit_sha": os.environ.get("GIT_COMMIT", ""),
            "branch": os.environ.get("GIT_BRANCH", ""),
        }

        json_data: dict = {
            "generated": self.generated_at,
            "version": self.version,
            "build_id": ci_env["build_id"],
            "commit_sha": ci_env["commit_sha"],
            "branch": ci_env["branch"],
            "summary": {
                "total_requirements": total,
                "with_implementation": covered,
                "with_test_coverage": test_covered,
                "uncovered_shalls": len(uncovered),
                "total_scenarios": len(self.scenarios),
                "total_reviews": len(self.reviews),
                "total_ci_runs": len(self.ci_results),
            },
            "requirements": [],
        }
        for req in self.requirements:
            req_name = req.get("name", "Unknown")
            matching_tests = self.req_to_tests.get(req_name, [])
            json_data["requirements"].append({
                "name": req_name,
                "req_id": req.get("req_id", ""),
                "shall_count": req.get("shall_count", 0),
                "shall_statements": req.get("shall", []),
                "matched_tests": [
                    {"file": tf, "mode": self.match_modes.get(req_name, {}).get(tf, "keyword"),
                     "confidence": self.match_confidences.get(req_name, {}).get(tf, 0.0)}
                    for tf in matching_tests
                ],
            })

        json_path = self.evidence_dir / "traceability-matrix.json"
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
        print(f"  ✅ Traceability JSON generated: {json_path}")
        return str(output_path)

    def generate_requirement_coverage(self) -> str:
        """Generate a markdown requirements coverage report.

        Uses actual test coverage (req_to_tests) to determine status,
        not shall_count. A requirement is only "Covered" when at least
        one test file maps to it.
        """
        if not hasattr(self, 'req_to_tests') or not self.req_to_tests:
            self._build_requirement_to_test_map()

        lines = [
            f"# Requirements Coverage Report\n",
            f"> Generated: {self.generated_at}\n",
            f"| Requirement | SHALLs | Tests | Status |",
            f"|:-----------|:------:|:-----:|:------:|",
        ]
        for req in self.requirements:
            name = req.get("name", "Unknown")
            sc = req.get("shall_count", 0)
            matching_tests = self.req_to_tests.get(name, [])
            test_count = len(matching_tests)
            status_icon = '✅' if matching_tests else '❌'
            lines.append(f"| {name} | {sc} | {test_count} | {status_icon} |")

        total = len(self.requirements)
        covered = sum(1 for r in self.requirements
                      if self.req_to_tests.get(r.get("name", ""), []))
        pct = (covered / total * 100) if total > 0 else 0
        lines.extend([
            "", f"**Requirement Coverage**: {covered}/{total} ({pct:.0f}%)",
            f"  (Status based on actual test-file mapping, not SHALL presence)",
            f"**Scenarios**: {len(self.scenarios)}",
            f"**Threshold**: 100%",
            f"**Pass**: {'✅' if pct >= 100 else '❌'}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "requirement-coverage.md"
        output_path.write_text(content)
        print(f"  ✅ Requirement coverage report: {output_path}")
        return str(output_path)

    def generate_code_coverage_report(self) -> str:
        """Generate a markdown code coverage report."""
        lines = [f"# Code Coverage Report\n", f"> Generated: {self.generated_at}\n"]
        if self.coverage_data:
            lines.extend([
                f"| Metric | Value | Threshold | Status |",
                f"|:-------|:-----:|:---------:|:------:|",
                f"| Line Coverage | {self.coverage_data.get('line_coverage', 'N/A')}% | {self.coverage_data.get('threshold_line', 80)}% | {'✅' if self.coverage_data.get('line_pass') else '❌'} |",
                f"| Condition Coverage | {self.coverage_data.get('condition_coverage', 'N/A')}% | {self.coverage_data.get('threshold_condition', 75)}% | {'✅' if self.coverage_data.get('condition_pass') else '❌'} |",
            ])
        else:
            lines.append("No coverage data available — run CI Layer 1 first.")

        content = "\n".join(lines)
        output_path = self.evidence_dir / "code-coverage-report.md"
        output_path.write_text(content)
        print(f"  ✅ Code coverage report: {output_path}")
        return str(output_path)

    def aggregate_review_logs(self) -> str:
        """Aggregate review logs into a markdown summary + JSON export.

        Handles both the legacy review-session.json format (with
        task/decision/reviews) and the newer flat format (with
        review_type/status/findings/summary/agent).  Raw review JSON
        files are also copied to a reviews/ subdirectory in the
        evidence output for audit traceability.
        """
        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄", "running": "⏳"}
        lines = []

        for r in self.reviews:
            if "task" in r:
                # Legacy format: task/decision/reviews
                lines.append(f"## Task: {r.get('task', 'N/A')}")
                lines.append(f"- Decision: {r.get('decision', 'N/A')}")
                lines.append(f"- Created: {r.get('created_at', 'N/A')}")
                lines.append(f"- Reviews ({len(r.get('reviews', []))} agents):")
                for rev in r.get("reviews", []):
                    icon = status_icon.get(rev.get("status", ""), "❓")
                    findings = rev.get("finding_breakdown", {})
                    lines.append(f"  {icon} {rev.get('reviewer', 'N/A')}: {rev.get('status', 'N/A')} "
                               f"(C:{findings.get('critical',0)} M:{findings.get('major',0)} "
                               f"m:{findings.get('minor',0)})")
                    lines.append(f"    Summary: {rev.get('summary', 'N/A')}")
            else:
                # New flat format: review_type/status/findings/summary/agent
                review_type = r.get("review_type", "unknown")
                status = r.get("status", "unknown")
                agent = r.get("agent", "N/A")
                icon = status_icon.get(status, "❓")
                lines.append(f"## {icon} Review: {review_type.upper()}")
                lines.append(f"- Status: {status}")
                lines.append(f"- Agent: {agent}")
                lines.append(f"- Generated: {r.get('generated_at', 'N/A')}")
                lines.append(f"- Build: {r.get('build_id', 'N/A')}")
                lines.append(f"- Summary: {r.get('summary', 'N/A')}")
                findings = r.get("findings", [])
                if findings:
                    lines.append(f"- Findings ({len(findings)}):")
                    for f_item in findings:
                        sev = f_item.get("severity", "info")
                        sev_icon = {"critical": "🔴", "major": "🟡", "minor": "🔵", "info": "ℹ️"}.get(sev, "❓")
                        lines.append(f"  {sev_icon} [{sev}] {f_item.get('file', '?')}:{f_item.get('line', '?')} "
                                   f"- {f_item.get('message', '')}")
            lines.append("")

        content = "\n".join(lines)
        output_path = self.evidence_dir / "review-log-summary.md"
        output_path.write_text(content)

        json_path = self.evidence_dir / "review-log.json"
        with open(json_path, "w") as f:
            json.dump(self.reviews, f, indent=2, ensure_ascii=False)

        # ── Copy raw review JSON files to evidence/reviews/ subdir ──
        raw_reviews_dir = self.evidence_dir / "reviews"
        raw_reviews_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        rev_dir = Path(self.project_dir) / ".osh" / "evidence" / "reviews"
        if rev_dir.exists():
            for f in sorted(rev_dir.rglob("*.json")):
                dest = raw_reviews_dir / f.name
                # Avoid overwriting collisions by prepending subdir name
                if dest.exists():
                    dest = raw_reviews_dir / f"{f.parent.name}-{f.name}"
                import shutil
                shutil.copy2(str(f), str(dest))
                copied += 1
        if copied:
            print(f"  📁 Copied {copied} raw review file(s) to {raw_reviews_dir}")

        print(f"  ✅ Review logs aggregated: {output_path}")
        return str(output_path)

    def generate_acceptance_matrix(self) -> str:
        """Generate a markdown acceptance matrix."""
        if not hasattr(self, 'req_to_tests') or not self.req_to_tests:
            self._build_requirement_to_test_map()

        lines = [
            f"# Acceptance Matrix\n",
            f"> Generated: {self.generated_at}",
            f"> Version: {self.version}\n",
            f"| Req ID | Requirement | SHALL | 验证方法 | 测试文件 | 匹配方式 | 置信度 | 状态 |",
            f"|:------:|:-----------|:------|:---------|:--------|:--------:|:------:|:----:|",
        ]

        total_shalls = 0
        covered_shalls = 0
        for req in self.requirements:
            name = req.get("name", "Unknown")
            req_id = req.get("req_id", "RS---")
            shall_list = req.get("shall", [])
            matching_tests = self.req_to_tests.get(name, [])
            test_str = ", ".join(matching_tests) if matching_tests else "—"
            status = "✅" if matching_tests else "❌"

            modes = self.match_modes.get(name, {})
            confs = self.match_confidences.get(name, {})
            if matching_tests:
                dominant_mode = "exact" if any(m == "exact" for m in modes.values()) else "keyword"
                best_conf = max(confs.values()) if confs else 0.0
            else:
                dominant_mode = "—"
                best_conf = 0.0

            for idx, shall in enumerate(shall_list):
                total_shalls += 1
                shall_status = status if matching_tests else "❌"
                if matching_tests:
                    covered_shalls += 1
                mode_str = dominant_mode if idx == 0 else ""
                conf_str = f"{best_conf:.0%}" if idx == 0 and matching_tests else ""
                lines.append(
                    f"| {req_id} | {name} | {shall} | Unit Test | {test_str} | {mode_str} | {conf_str} | {shall_status} |"
                )

        pct = (covered_shalls / total_shalls * 100) if total_shalls > 0 else 0
        lines.extend([
            "", f"## Summary",
            f"- Total SHALL statements: {total_shalls}",
            f"- Covered by tests: {covered_shalls} ({pct:.0f}%)",
            f"- Uncovered: {total_shalls - covered_shalls}",
            f"- Threshold: 100% → {'✅ PASS' if pct >= 100 else '❌ FAIL'}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "acceptance-matrix.md"
        output_path.write_text(content)
        print(f"  ✅ Acceptance matrix generated: {output_path}")
        return str(output_path)

    def pack_compliance_zip(self) -> str:
        """Delegate compliance ZIP packing to the compliance module."""
        from yuleosh.evidence.compliance import pack_compliance_zip as _pack
        return _pack(self)
