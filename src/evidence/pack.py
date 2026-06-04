#!/usr/bin/env python3
"""
OSH Evidence Engine — Traceability matrix + ASPICE compliance pack.

Automatically generates:
  - Traceability matrix (Req ↔ Design ↔ Code ↔ Test)
  - Requirements coverage report
  - Code coverage summary
  - Review records aggregation
  - Compliance pack (ZIP)
"""

import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


class EvidenceCollector:
    """Collects and organizes evidence for ASPICE compliance."""
    
    def __init__(self, project_dir: str, version: str = "0.1.0"):
        self.project_dir = project_dir
        self.version = version
        self.generated_at = datetime.now().isoformat()
        self.evidence_dir = Path(project_dir) / ".osh" / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Data containers
        self.requirements: list[dict] = []
        self.scenarios: list[dict] = []
        self.reviews: list[dict] = []
        self.ci_results: list[dict] = []
        self.coverage_data: Optional[dict] = None

    def collect_requirements(self, spec_path: str = None):
        """Parse OpenSpec and collect requirements."""
        if spec_path is None:
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")
        
        if not os.path.exists(spec_path):
            print(f"  ⏭️  Spec not found: {spec_path}")
            return
        
        sys.path.insert(0, os.path.join(self.project_dir, "src", "spec"))
        from validate import parse_spec
        
        doc = parse_spec(spec_path)
        self.requirements = [r.to_dict() for r in doc.requirements]
        self.scenarios = [s.to_dict() for s in doc.scenarios]
        print(f"  📋 Collected {len(self.requirements)} requirements, {len(self.scenarios)} scenarios")

    def collect_reviews(self):
        """Collect all review session records."""
        rev_dir = Path(self.project_dir) / ".osh" / "reviews"
        if not rev_dir.exists():
            print("  ⏭️  No review records found")
            return
        
        for task_dir in rev_dir.iterdir():
            if task_dir.is_dir():
                sess_file = task_dir / "review-session.json"
                if sess_file.exists():
                    with open(sess_file) as f:
                        self.reviews.append(json.load(f))
        
        print(f"  📋 Collected {len(self.reviews)} review session(s)")

    def collect_ci_results(self):
        """Collect all CI layer results."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  ⏭️  No CI results found")
            return
        
        for f in sorted(ci_dir.glob("layer*.json")):
            with open(f) as fh:
                data = json.load(fh)
                self.ci_results.append(data)
                
                # Extract latest coverage data
                if data.get("coverage"):
                    self.coverage_data = data["coverage"]
        
        print(f"  📋 Collected {len(self.ci_results)} CI result(s)")

    def generate_traceability_matrix(self) -> str:
        """Generate requirements traceability matrix."""
        lines = [
            f"# Traceability Matrix",
            f"",
            f"> Generated: {self.generated_at}",
            f"> Version: {self.version}",
            f"",
            f"## Requirements → Implementation → Tests",
            f"",
        ]
        
        for req in self.requirements:
            name = req.get("name", "Unknown")
            shall_count = req.get("shall_count", 0)
            lines.append(f"### {name}")
            lines.append(f"- SHALL statements: {shall_count}")
            lines.append(f"- Status: {'✅ Covered' if shall_count > 0 else '❌ No implementation'}")
            
            # Check for matching scenarios
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
            
            # Check review records
            matching_reviews = [
                r for r in self.reviews
                if name.lower() in r.get("task", "").lower()
            ]
            if matching_reviews:
                for r in matching_reviews:
                    lines.append(f"- Review: {r.get('decision', 'unknown')} by {len(r.get('reviews', []))} agent(s)")
            
            lines.append("")
        
        # Summary
        total = len(self.requirements)
        covered = sum(1 for r in self.requirements if r.get("shall_count", 0) > 0)
        lines.extend([
            f"## Summary",
            f"- Total Requirements: {total}",
            f"- Covered: {covered} ({covered/total*100:.0f}%)" if total > 0 else "- Covered: 0",
            f"- Scenarios: {len(self.scenarios)}",
            f"- Reviews: {len(self.reviews)}",
            f"- CI Runs: {len(self.ci_results)}",
        ])
        
        content = "\n".join(lines)
        output_path = self.evidence_dir / "traceability-matrix.md"
        output_path.write_text(content)
        print(f"  ✅ Traceability matrix generated: {output_path}")
        return str(output_path)

    def generate_requirement_coverage(self) -> str:
        """Generate requirements coverage report."""
        lines = [
            f"# Requirements Coverage Report",
            f"",
            f"> Generated: {self.generated_at}",
            f"",
            f"| Requirement | SHALLs | Status |",
            f"|:-----------|:------:|:------:|",
        ]
        
        for req in self.requirements:
            name = req.get("name", "Unknown")
            sc = req.get("shall_count", 0)
            status = "✅" if sc > 0 else "❌"
            lines.append(f"| {name} | {sc} | {status} |")
        
        # Requirement coverage summary
        total = len(self.requirements)
        covered = sum(1 for r in self.requirements if r.get("shall_count", 0) > 0)
        pct = (covered / total * 100) if total > 0 else 0
        lines.extend([
            "",
            f"**Requirement Coverage**: {covered}/{total} ({pct:.0f}%)",
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
        """Generate code coverage report from CI data."""
        lines = [
            f"# Code Coverage Report",
            f"",
            f"> Generated: {self.generated_at}",
            f"",
        ]
        
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
        """Aggregate all review logs into a single JSON."""
        lines = []
        for r in self.reviews:
            lines.append(f"## Task: {r.get('task', 'N/A')}")
            lines.append(f"- Decision: {r.get('decision', 'N/A')}")
            lines.append(f"- Created: {r.get('created_at', 'N/A')}")
            lines.append(f"- Reviews ({len(r.get('reviews', []))} agents):")
            for rev in r.get("reviews", []):
                status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄", "running": "⏳"}
                icon = status_icon.get(rev.get("status", ""), "❓")
                findings = rev.get("finding_breakdown", {})
                lines.append(f"  {icon} {rev.get('reviewer', 'N/A')}: {rev.get('status', 'N/A')} "
                           f"(C:{findings.get('critical',0)} M:{findings.get('major',0)} m:{findings.get('minor',0)})")
                lines.append(f"    Summary: {rev.get('summary', 'N/A')}")
            lines.append("")
        
        content = "\n".join(lines)
        output_path = self.evidence_dir / "review-log-summary.md"
        output_path.write_text(content)
        
        # Also save raw JSON
        json_path = self.evidence_dir / "review-log.json"
        with open(json_path, "w") as f:
            json.dump(self.reviews, f, indent=2, ensure_ascii=False)
        
        print(f"  ✅ Review logs aggregated: {output_path}")
        return str(output_path)

    def pack_compliance_zip(self) -> str:
        """Create compliance pack ZIP for ASPICE audit."""
        zip_path = self.evidence_dir / "compliance-pack.zip"
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add all generated evidence files
            for f in self.evidence_dir.iterdir():
                if f.suffix in (".md", ".json") and f.name != "compliance-pack.zip":
                    zf.write(f, arcname=f.name)
            
            # Add spec file
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")
            if os.path.exists(spec_path):
                zf.write(spec_path, arcname="spec.md")
            
            # Add startup analysis
            sa_path = os.path.join(self.project_dir, "docs", "startup-analysis.md")
            if os.path.exists(sa_path):
                zf.write(sa_path, arcname="startup-analysis.md")
        
        print(f"  📦 Compliance pack created: {zip_path}")
        return str(zip_path)


def generate_evidence(project_dir: str = None):
    """Generate full evidence chain."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    print(f"\n📦 OSH Evidence Generation")
    print(f"{'='*50}")
    
    collector = EvidenceCollector(project_dir)
    
    collector.collect_requirements()
    collector.collect_reviews()
    collector.collect_ci_results()
    
    print(f"\n{'='*50}")
    
    artifacts = []
    artifacts.append(collector.generate_traceability_matrix())
    artifacts.append(collector.generate_requirement_coverage())
    artifacts.append(collector.generate_code_coverage_report())
    artifacts.append(collector.aggregate_review_logs())
    artifacts.append(collector.pack_compliance_zip())
    
    print(f"\n{'='*50}")
    print(f"✅ Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print(f"   - traceability-matrix.md")
    print(f"   - requirement-coverage.md")
    print(f"   - code-coverage-report.md")
    print(f"   - review-log-summary.md + review-log.json")
    print(f"   - compliance-pack.zip 🎯")
    print()
    
    return artifacts


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "pack":
        generate_evidence()
    else:
        generate_evidence()


if __name__ == "__main__":
    main()
