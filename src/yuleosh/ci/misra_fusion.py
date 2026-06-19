# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH MISRA 3-Layer Fusion — G-15

Three-layer redundant cross-validation for MISRA C:2023 violations:
  Layer 1: cppcheck --addon=misra   (static analysis, rule-based)
  Layer 2: clang-tidy                (static analysis, check-based)
  Layer 3: AI-based review           (LLM model, context-aware)

This module merges results from all three layers into a single,
cross-validated report. Each violation is classified as:

  - ALL CONFIRM  : All 3 layers agree on the violation
  - MAJORITY     : 2 of 3 layers agree
  - SINGLE       : Only 1 layer detected the violation
  - CONTRADICT   : Layers disagree (e.g., one flags, another clears)

Usage:
    from yuleosh.ci.misra_fusion import FusionReport, LayerResult, Violation

    cppcheck = LayerResult(tool="cppcheck", violations=[...])
    clang = LayerResult(tool="clang-tidy", violations=[...])
    ai = LayerResult(tool="ai-review", violations=[...])

    report = FusionReport.merge(cppcheck, clang, ai)
    report.to_json("reports/misra-fusion-report.json")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.ci.misra_fusion")


# ── Data Types ────────────────────────────────────────────────────────────────


@dataclass
class Violation:
    """A single MISRA violation from any analysis layer."""
    file: str
    line: int
    column: int = 0
    rule_id: str = ""
    severity: str = "style"
    message: str = ""
    layer: str = "unknown"          # which tool reported it
    category: str = ""              # rule severity: required/advisory/unknown
    false_positive_chance: float = 0.0  # AI assessment: 0.0 = definite, 1.0 = unlikely


@dataclass
class LayerResult:
    """Results from a single analysis layer."""
    tool: str                        # "cppcheck" | "clang-tidy" | "ai-review"
    violations: list[Violation] = field(default_factory=list)
    files_analyzed: int = 0
    duration_seconds: float = 0.0
    error: str = ""


@dataclass
class FusedViolation:
    """A fused/cross-validated violation across layers."""
    file: str
    line: int
    rule_id: str
    message: str
    confidence: str                   # ALL_CONFIRM | MAJORITY | SINGLE | CONTRADICT
    layers_found: list[str]          # which layers flagged it
    layers_cleared: list[str]        # which layers explicitly passed this line+rule
    severity: str = "style"
    category: str = ""
    false_positive_probability: float = 0.0
    original_violations: list[Violation] = field(default_factory=list)


@dataclass
class FusionReport:
    """Complete 3-layer fusion report."""
    generated_at: str = ""
    cppcheck: LayerResult = field(default_factory=lambda: LayerResult(tool="cppcheck"))
    clang_tidy: LayerResult = field(default_factory=lambda: LayerResult(tool="clang-tidy"))
    ai_review: LayerResult = field(default_factory=lambda: LayerResult(tool="ai-review"))
    fused_violations: list[FusedViolation] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    # ── Class methods ─────────────────────────────────────────────────────

    @classmethod
    def merge(cls,
              cppcheck: LayerResult,
              clang_tidy: LayerResult,
              ai_review: LayerResult) -> FusionReport:
        """Merge three layers into a single cross-validated report."""
        report = cls(
            generated_at=datetime.now().isoformat(),
            cppcheck=cppcheck,
            clang_tidy=clang_tidy,
            ai_review=ai_review,
        )

        # Build signature maps: (file, line, rule_id) → True if flagged
        layer_sigs: dict[str, dict[tuple, bool]] = {
            "cppcheck": {(v.file, v.line, v.rule_id): True for v in cppcheck.violations if v.rule_id},
            "clang-tidy": {(v.file, v.line, v.rule_id): True for v in clang_tidy.violations if v.rule_id},
            "ai-review": {(v.file, v.line, v.rule_id): True for v in ai_review.violations if v.rule_id},
        }

        # Build violation maps: (file, line, rule_id) → list[Violation]
        violation_map: dict[tuple, list[Violation]] = {}
        for v in cppcheck.violations + clang_tidy.violations + ai_review.violations:
            key = (v.file, v.line, v.rule_id)
            if key not in violation_map:
                violation_map[key] = []
            violation_map[key].append(v)

        all_keys = set()
        for sigs in layer_sigs.values():
            all_keys.update(sigs.keys())

        # Also include keys from violation_map that might not have exact rule match
        all_keys.update(violation_map.keys())

        for key in sorted(all_keys, key=lambda k: (k[0], k[1], k[2])):
            file, line, rule_id = key

            # Which layers flagged this?
            flagged = [layer for layer, sigs in layer_sigs.items() if key in sigs]
            cleared = [layer for layer in layer_sigs if key not in layer_sigs[layer]]

            # Determine confidence
            n_flagged = len(flagged)
            total_layers = 3
            if n_flagged == total_layers:
                confidence = "ALL_CONFIRM"
            elif n_flagged >= 2:
                confidence = "MAJORITY"
            elif n_flagged == 1:
                confidence = "SINGLE"
                # Check if other layers explicitly cleared
                if cleared == total_layers - 1:
                    confidence = "SINGLE"  # still single — only one found it
            else:
                confidence = "CONTRADICT"  # no one flagged it (shouldn't happen)

            # Compute false positive probability
            fp_probs = [
                v.false_positive_chance for v in violation_map.get(key, [])
                if v.false_positive_chance > 0
            ]
            fp_prob = sum(fp_probs) / len(fp_probs) if fp_probs else 0.0

            orig_vs = violation_map.get(key, [])
            sev = orig_vs[0].severity if orig_vs else "style"
            cat = orig_vs[0].category if orig_vs else ""
            msg = orig_vs[0].message if orig_vs else ""

            fused = FusedViolation(
                file=file,
                line=line,
                rule_id=rule_id,
                message=msg,
                confidence=confidence,
                layers_found=flagged,
                layers_cleared=cleared,
                severity=sev,
                category=cat,
                false_positive_probability=fp_prob,
                original_violations=orig_vs,
            )
            report.fused_violations.append(fused)

        report._compute_summary()
        return report

    # ── Internal ──────────────────────────────────────────────────────────

    def _compute_summary(self) -> None:
        """Compute aggregate summary from fused violations."""
        all_count = len(self.fused_violations)
        confirmed = [v for v in self.fused_violations if v.confidence == "ALL_CONFIRM"]
        majority = [v for v in self.fused_violations if v.confidence == "MAJORITY"]
        single = [v for v in self.fused_violations if v.confidence == "SINGLE"]
        contradict = [v for v in self.fused_violations if v.confidence == "CONTRADICT"]

        severity_counts: dict[str, int] = {}
        rule_counts: dict[str, int] = {}
        file_counts: dict[str, int] = {}

        for v in self.fused_violations:
            severity_counts[v.severity] = severity_counts.get(v.severity, 0) + 1
            if v.rule_id:
                rule_counts[v.rule_id] = rule_counts.get(v.rule_id, 0) + 1
            if v.file:
                file_counts[v.file] = file_counts.get(v.file, 0) + 1

        self.summary = {
            "total_fused_violations": all_count,
            "all_confirmed": len(confirmed),
            "majority": len(majority),
            "single_source": len(single),
            "contradictory": len(contradict),
            "high_confidence_pct": round((len(confirmed) + len(majority)) / max(all_count, 1) * 100, 2),
            "severity_breakdown": {
                "error": severity_counts.get("error", 0),
                "warning": severity_counts.get("warning", 0),
                "style": severity_counts.get("style", 0),
                "performance": severity_counts.get("performance", 0),
                "portability": severity_counts.get("portability", 0),
                "information": severity_counts.get("information", 0),
            },
            "unique_rules_violated": len(rule_counts),
            "unique_files_affected": len(file_counts),
            "top_rules": dict(sorted(rule_counts.items(), key=lambda x: -x[1])[:10]),
            "cppcheck_count": len(self.cppcheck.violations),
            "clang_tidy_count": len(self.clang_tidy.violations),
            "ai_review_count": len(self.ai_review.violations),
        }

    # ── Output methods ────────────────────────────────────────────────────

    def to_json(self, output_path: str | Path) -> str:
        """Save fused report as JSON."""
        data = asdict(self, dict_factory=self._clean_dict)
        # Remove full violation details from serialization to keep size manageable
        for fv in data.get("fused_violations", []):
            fv.pop("original_violations", None)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("Fusion report saved: %s", path)
        return str(path)

    def to_markdown(self) -> str:
        """Generate Markdown fusion report."""
        s = self.summary
        lines = [
            "# MISRA 三层工具冗余检查报告",
            "",
            f"> 生成时间：{self.generated_at}",
            f"> 三层交叉验证：cppcheck + clang-tidy + AI Review",
            "",
            "## 汇总",
            "",
            f"| 指标 | 值 |",
            f"|:-----|:----|",
            f"| 融合后违规模数 | {s['total_fused_violations']} |",
            f"| 三层确认 | {s['all_confirmed']} |",
            f"| 两层确认 | {s['majority']} |",
            f"| 单一来源 | {s['single_source']} |",
            f"| 矛盾 | {s['contradictory']} |",
            f"| 高置信度占比 | {s['high_confidence_pct']}% |",
            f"| 涉及的规则数 | {s['unique_rules_violated']} |",
            f"| 涉及的文件数 | {s['unique_files_affected']} |",
            "",
            "### 各层检测量",
            "",
            f"- **cppcheck**: {s['cppcheck_count']} violations",
            f"- **clang-tidy**: {s['clang_tidy_count']} violations",
            f"- **AI Review**: {s['ai_review_count']} violations",
            "",
            "### 严重级别分布",
            "",
            "| 级别 | 数量 |",
            "|:-----|:-----|",
        ]
        for sev, count in s["severity_breakdown"].items():
            if count > 0:
                lines.append(f"| {sev} | {count} |")

        lines.append("")
        lines.append("### 违规规则 Top 10")
        lines.append("")
        lines.append("| 规则 | 次数 |")
        lines.append("|:-----|:-----|")
        for rule, count in s.get("top_rules", {}).items():
            lines.append(f"| {rule} | {count} |")

        lines.append("")
        lines.append("## 融合结果明细")
        lines.append("")
        lines.append("| 文件 | 行 | 规则 | 置信度 | 来源层 | FP概率 |")
        lines.append("|:-----|:---|:-----|:-------|:-------|:-------|")

        confidence_emoji = {
            "ALL_CONFIRM": "🟢",
            "MAJORITY": "🟡",
            "SINGLE": "🟠",
            "CONTRADICT": "🔴",
        }

        for v in self.fused_violations[:50]:
            emoji = confidence_emoji.get(v.confidence, "⚪")
            layers = ", ".join(v.layers_found)
            fp = f"{v.false_positive_probability:.0%}" if v.false_positive_probability > 0 else "-"
            short_file = v.file.split("/")[-1] if "/" in v.file else v.file
            lines.append(f"| `{short_file}` | {v.line} | {v.rule_id} | {emoji} {v.confidence} | {layers} | {fp} |")

        if len(self.fused_violations) > 50:
            lines.append(f"| ... | ... | ... | ... | ...（共 {len(self.fused_violations)} 条）|")

        lines.append("")
        filtered = [v for v in self.fused_violations if v.confidence in ("ALL_CONFIRM", "MAJORITY")]
        fake_positives = [v for v in self.fused_violations if v.false_positive_probability > 0.5]
        lines.append("## 分析")
        lines.append("")
        lines.append(f"- 高置信度违规（三层+两层确认）：{len(filtered)} 条 — 应优先修复")
        lines.append(f"- 单一来源违规（仅一个工具检测到）：{s['single_source']} 条 — 需人工审查")
        lines.append(f"- 疑似误报（FP概率 > 50%）：{len(fake_positives)} 条")
        lines.append(f"- 矛盾结果：{s['contradictory']} 条 — 需进一步调查")
        lines.append("")
        lines.append("### 建议")
        lines.append("")
        lines.append("1. 优先修复三层确认的违规（修复风险低、收益高）")
        lines.append("2. 对单一来源违规进行人工审查，确认工具间的差异原因")
        lines.append("3. 记录已知误报模式到 suppress 列表")
        lines.append("4. 将 clang-tidy 未覆盖的 cppcheck 规则添加到 clang-tidy 配置")

        lines.append("")
        lines.append("---")
        lines.append("*报告由 yuleOSH MISRA Fusion Engine 自动生成*")
        return "\n".join(lines)

    @staticmethod
    def _clean_dict(d: list) -> dict:
        """Custom dict factory that handles non-serializable types."""
        result = {}
        for k, v in d:
            if isinstance(v, set):
                result[k] = list(v)
            elif isinstance(v, float) and (v != v):  # NaN
                result[k] = None
            else:
                result[k] = v
        return result


# ── Layer parsers ──────────────────────────────────────────────────────────────


def parse_cppcheck_layer(text: str) -> LayerResult:
    """Parse cppcheck MISRA addon output into a LayerResult.

    Accepts the same text format as ci/misra_report.py.
    """
    import re
    violations = []

    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
        r"(?P<severity>error|warning|style|performance|portability|information):\s*"
        r"(?P<message>.+)$", re.MULTILINE
    )

    files_seen = set()
    for m in pattern.finditer(text):
        v = Violation(
            file=m.group("file"),
            line=int(m.group("line")),
            column=int(m.group("col")),
            severity=m.group("severity"),
            message=m.group("message"),
            layer="cppcheck",
        )
        # Extract MISRA rule ID
        rule_match = re.search(r"misra-c\d{4}-(?P<rule>\d+\.\d+)", m.group("message"), re.IGNORECASE)
        if rule_match:
            v.rule_id = f"misra-c2023-{rule_match.group('rule')}"
        else:
            alt_match = re.search(r"MISRA rule[:\s]+(?P<rule>\d+\.\d+)", m.group("message"), re.IGNORECASE)
            if alt_match:
                v.rule_id = f"misra-c2023-{alt_match.group('rule')}"
        violations.append(v)
        files_seen.add(v.file)

    return LayerResult(
        tool="cppcheck",
        violations=violations,
        files_analyzed=len(files_seen),
    )


def parse_clang_tidy_layer(text: str) -> LayerResult:
    """Parse clang-tidy MISRA output into a LayerResult.

    Typical clang-tidy output:
        /path/file.c:42:5: warning: MISRA rule 10.1 [misra-c2023-10.1]
    """
    import re
    violations = []

    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
        r"(?P<severity>error|warning|note):\s*"
        r"(?P<message>.+)$", re.MULTILINE
    )

    files_seen = set()
    for m in pattern.finditer(text):
        v = Violation(
            file=m.group("file"),
            line=int(m.group("line")),
            column=int(m.group("col")),
            severity=m.group("severity"),
            message=m.group("message"),
            layer="clang-tidy",
        )
        rule_match = re.search(r"misra-c\d{4}-(?P<rule>\d+\.\d+)", m.group("message"), re.IGNORECASE)
        if rule_match:
            v.rule_id = f"misra-c2023-{rule_match.group('rule')}"
        violations.append(v)
        files_seen.add(v.file)

    return LayerResult(
        tool="clang-tidy",
        violations=violations,
        files_analyzed=len(files_seen),
    )


def parse_ai_review_layer(ai_json: str | dict) -> LayerResult:
    """Parse AI review JSON output into a LayerResult.

    Expected JSON format:
    {
      "files_analyzed": 5,
      "duration_seconds": 12.3,
      "violations": [
        {
          "file": "src/main.c",
          "line": 42,
          "column": 5,
          "rule_id": "misra-c2023-10.1",
          "severity": "required",
          "message": "...",
          "false_positive_chance": 0.1
        }
      ]
    }
    """
    if isinstance(ai_json, str):
        try:
            data = json.loads(ai_json)
        except json.JSONDecodeError:
            return LayerResult(tool="ai-review", error="Invalid JSON input")
    else:
        data = ai_json

    violations = []
    for item in data.get("violations", []):
        v = Violation(
            file=item.get("file", ""),
            line=item.get("line", 0),
            column=item.get("column", 0),
            rule_id=item.get("rule_id", ""),
            severity=item.get("severity", "style"),
            message=item.get("message", ""),
            layer="ai-review",
            false_positive_chance=item.get("false_positive_chance", 0.0),
        )
        v.category = item.get("category", "")
        violations.append(v)

    return LayerResult(
        tool="ai-review",
        violations=violations,
        files_analyzed=data.get("files_analyzed", 0),
        duration_seconds=data.get("duration_seconds", 0.0),
    )


# ── CLI entry point ──────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MISRA 3-Layer Fusion Report — cppcheck + clang-tidy + AI",
    )
    parser.add_argument("--cppcheck", help="Path to cppcheck MISRA output file")
    parser.add_argument("--clang-tidy", help="Path to clang-tidy output file")
    parser.add_argument("--ai-review", help="Path to AI review JSON file")
    parser.add_argument("--output", "-o", default="reports/misra-fusion-report.json",
                        help="Output path for JSON report (default: reports/misra-fusion-report.json)")
    parser.add_argument("--markdown", action="store_true",
                        help="Also generate Markdown report")
    args = parser.parse_args()

    # Parse layers
    cppcheck = LayerResult(tool="cppcheck")
    clang = LayerResult(tool="clang-tidy")
    ai = LayerResult(tool="ai-review")

    if args.cppcheck:
        text = Path(args.cppcheck).read_text(encoding="utf-8")
        cppcheck = parse_cppcheck_layer(text)

    if args.clang_tidy:
        text = Path(args.clang_tidy).read_text(encoding="utf-8")
        clang = parse_clang_tidy_layer(text)

    if args.ai_review:
        text = Path(args.ai_review).read_text(encoding="utf-8")
        ai = parse_ai_review_layer(text)

    # Merge
    report = FusionReport.merge(cppcheck, clang, ai)
    json_path = report.to_json(args.output)

    print(f"Fusion report saved: {json_path}")
    print(f"  Total fused: {report.summary['total_fused_violations']}")
    print(f"  Confirmed (3/3): {report.summary['all_confirmed']}")
    print(f"  Majority (2/3): {report.summary['majority']}")
    print(f"  Single: {report.summary['single_source']}")

    if args.markdown:
        md = report.to_markdown()
        md_path = Path(args.output).with_suffix(".md")
        md_path.write_text(md, encoding="utf-8")
        print(f"Markdown report: {md_path}")


if __name__ == "__main__":
    main()
