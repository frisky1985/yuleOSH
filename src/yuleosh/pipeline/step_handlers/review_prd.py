#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step 1.5: 小马 — PRD/Super Analysis 质量审查。

在 Super Analysis (PRD) 生成后自动执行，审查：
- 需求是否完整覆盖了 spec 中的所有 SHALL/SHOULD/MAY
- 需求是否可测试（是否有明确的验收标准）
- 是否存在矛盾或遗漏的需求

Exports:
  step_review_prd — AI-powered PRD / Super Analysis quality review
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_prd")

__all__ = ["step_review_prd"]


# ------------------------------------------------------------------
# Spec SHALL statement extraction
# ------------------------------------------------------------------

_SHALL_RE = re.compile(
    r'(?:^|\n)\s*(?:-\s+)?(?P<kind>SHALL|SHALL\s+NOT|SHOULD|SHOULD\s+NOT|MAY)\b(.+?)(?:[.;]\s*|$)',
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _extract_shalls(spec_content: str) -> list[dict]:
    """Extract all SHALL/SHOULD/MAY statements from spec content.

    Returns a list of dicts with keys:
      - kind: "SHALL" | "SHALL NOT" | "SHOULD" | "SHOULD NOT" | "MAY"
      - statement: the extracted requirement text
      - line: approximate line number
    """
    shalls: list[dict] = []
    lines = spec_content.split("\n")
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        m = _SHALL_RE.match(stripped)
        if m:
            shalls.append({
                "kind": m.group("kind").upper().strip(),
                "statement": m.group("statement").strip(),
                "line": idx,
            })
        else:
            # Also catch inline shall statements after list markers
            for match in re.finditer(
                r'(?P<kind>SHALL\s+NOT|SHALL|SHOULD\s+NOT|SHOULD|MAY)\b(.+?)(?:[.;]\s*|$)',
                stripped,
                re.IGNORECASE,
            ):
                shalls.append({
                    "kind": match.group("kind").upper().strip(),
                    "statement": match.group("match_end") if hasattr(match, 'match_end') else stripped,
                    "line": idx,
                })
    # Deduplicate by (kind, statement)
    seen: set = set()
    unique: list[dict] = []
    for s in shalls:
        key = (s["kind"], s["statement"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _extract_prd_requirements(prd_content: str) -> list[dict]:
    """Extract requirement-like statements from the PRD artifact.

    Returns a list of dicts with:
      - id: requirement ID if present (Req-XXX)
      - text: the requirement text
    """
    reqs: list[dict] = []
    req_id_re = re.compile(r'(?:Req[-\s]*\d+|##+\s+(?:Req[-\s]*\d+|需求|功能))', re.IGNORECASE)
    lines = prd_content.split("\n")
    current_id: str = ""
    for line in lines:
        stripped = line.strip()
        if req_id_re.search(stripped):
            current_id = stripped.replace("### ", "").replace("## ", "")
        elif stripped and not stripped.startswith(">") and not stripped.startswith("```"):
            if any(kw in stripped.upper() for kw in ("SHALL", "SHOULD", "MAY", "MUST", "WILL", "验收", "测试")):
                reqs.append({
                    "id": current_id,
                    "text": stripped,
                })
    return reqs


def _check_shall_coverage(
    spec_shalls: list[dict],
    prd_requirements: list[dict],
) -> list[dict]:
    """Check each spec SHALL for corresponding coverage in the PRD.

    Returns a list of finding dicts:
      - shall: the original SHALL statement
      - covered: bool
      - matched_prd: str or "" if not found
      - confidence: "high" | "low" | "none"
    """
    findings: list[dict] = []
    prd_text_combined = " ".join(r["text"] for r in prd_requirements)

    for shall in spec_shalls:
        # Skip MAY statements (non-binding)
        if shall["kind"] == "MAY":
            continue

        statement = shall["statement"].strip().rstrip(".。;")
        covered = False
        matched_prd = ""
        confidence = "none"

        # Direct keyword matching: look for key terms from the SHALL in PRD text
        keywords = [w for w in re.split(r'[\s,;:()]+', statement) if len(w) > 3 and w.isascii()]
        if keywords:
            keyword_hits = sum(1 for kw in keywords if kw.lower() in prd_text_combined.lower())
            keyword_ratio = keyword_hits / len(keywords) if keywords else 0

            if keyword_ratio >= 0.8:
                confidence = "high"
                covered = True
            elif keyword_ratio >= 0.5:
                confidence = "low"
                covered = True
            else:
                confidence = "none"

            if covered:
                for prd_req in prd_requirements:
                    if any(kw.lower() in prd_req["text"].lower() for kw in keywords[:3]):
                        matched_prd = prd_req["text"][:120]
                        break

        findings.append({
            "shall": {"kind": shall["kind"], "statement": statement, "line": shall["line"]},
            "covered": covered,
            "matched_prd": matched_prd,
            "confidence": confidence,
        })

    return findings


def _assess_testability(prd_content: str) -> dict:
    """Assess whether the PRD content contains testable acceptance criteria.

    Returns a dict with:
      - has_acceptance_criteria: bool
      - acceptance_indicators: list[str]
      - score: int (0-100)
    """
    indicators = [
        "验收标准", "acceptance criteria", "AC:", "GIVEN", "WHEN", "THEN",
        "测试用例", "test case", "预期结果", "expected",
        "覆盖率", "coverage", "threshold",
        "验证", "verify", "validation",
        "PASS", "FAIL", "assert",
    ]

    found = []
    for indicator in indicators:
        if indicator.lower() in prd_content.lower():
            found.append(indicator)

    score = min(100, len(found) * 10 + (30 if "验收标准" in prd_content or "acceptance criteria" in prd_content.lower() else 0))

    return {
        "has_acceptance_criteria": bool(found),
        "acceptance_indicators": found,
        "score": score,
    }


def _check_super_analysis_consistency(
    spec_content: str,
    super_content: str,
) -> list[dict]:
    """Check consistency between spec and S.U.P.E.R analysis.

    Returns a list of findings describing contradictions or gaps.
    """
    findings: list[dict] = []

    # Simple checks: does the super analysis reference all spec sections?
    spec_sections = re.findall(r'^##+\s+.+$', spec_content, re.MULTILINE)
    for section in spec_sections[:20]:
        section_name = section.replace("##", "").strip()
        key_terms = [w for w in re.split(r'[\s,;:()]+', section_name) if len(w) > 3]
        if key_terms:
            matches = sum(1 for kw in key_terms if kw.lower() in super_content.lower())
            ratio = matches / len(key_terms)
            if ratio < 0.3:
                findings.append({
                    "type": "missing_reference",
                    "spec_section": section_name,
                    "risk": "Spec section may not be reflected in S.U.P.E.R analysis",
                    "severity": "minor",
                })

    return findings


# ------------------------------------------------------------------
# Main step handler
# ------------------------------------------------------------------


@timed_step
def step_review_prd(session: PipelineSession) -> str:
    """Step 1.5: 小马 — PRD/Super Analysis quality review.

    Reviews the PRD and Super Analysis artifacts for:
    - Full SHALL/SHOULD/MAY coverage
    - Testability (acceptance criteria presence)
    - Consistency between spec, super analysis, and PRD

    The step is non-blocking: findings are advisory and do not halt
    the pipeline.  Critical gaps are recorded in the review report
    for downstream awareness.
    """
    try:
        print("  🔮 [小马] Running PRD/Super Analysis quality review...")
        log.info("Running PRD/Super Analysis quality review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Read spec ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else ""

        if not spec_content:
            log.warning("Spec file not found or empty: %s", session.spec_path)
            raise PipelineStepError(f"Spec file not found: {session.spec_path}")

        # --- Read PRD artifact ---
        prd_content = ""
        if "prd" in session.artifacts:
            p = Path(session.artifacts["prd"])
            if p.exists():
                prd_content = p.read_text()

        # --- Read S.U.P.E.R analysis artifact ---
        super_content = ""
        if "super-analysis" in session.artifacts:
            p = Path(session.artifacts["super-analysis"])
            if p.exists():
                super_content = p.read_text()

        # --- 1. Extract SHALL statements from spec ---
        spec_shalls = _extract_shalls(spec_content)
        log.info("Extracted %d SHALL/SHOULD/MAY statements from spec", len(spec_shalls))

        shall_count = sum(1 for s in spec_shalls if s["kind"] in ("SHALL", "SHALL NOT"))
        should_count = sum(1 for s in spec_shalls if s["kind"] in ("SHOULD", "SHOULD NOT"))
        may_count = sum(1 for s in spec_shalls if s["kind"] == "MAY")

        # --- 2. Extract PRD requirements ---
        prd_reqs = _extract_prd_requirements(prd_content) if prd_content else []

        # --- 3. Check SHALL coverage in PRD ---
        coverage_findings = _check_shall_coverage(spec_shalls, prd_reqs)

        covered = sum(1 for f in coverage_findings if f["covered"])
        uncovered = sum(1 for f in coverage_findings if not f["covered"])
        high_conf = sum(1 for f in coverage_findings if f["confidence"] == "high")

        # --- 4. Assess testability ---
        testability = _assess_testability(prd_content) if prd_content else {"has_acceptance_criteria": False, "acceptance_indicators": [], "score": 0}

        # --- 5. Check super analysis consistency ---
        consistency_findings = _check_super_analysis_consistency(spec_content, super_content) if super_content else []

        # --- Compile report ---
        review = {
            "session": session.name,
            "reviewer": "小马",
            "timestamp": datetime.now().isoformat(),
            "status": "passed",
            "spec": str(spec_path),
            "prd_artifact": session.artifacts.get("prd", ""),
            "super_analysis_artifact": session.artifacts.get("super-analysis", ""),
            "summary": {
                "spec_shalls_total": len(spec_shalls),
                "spec_shalls": shall_count,
                "spec_shoulds": should_count,
                "spec_mays": may_count,
                "prd_requirements_extracted": len(prd_reqs),
                "shall_coverage": {
                    "covered": covered,
                    "uncovered": uncovered,
                    "high_confidence": high_conf,
                    "coverage_pct": round(covered / len(coverage_findings) * 100, 1) if coverage_findings else 0.0,
                },
                "testability_score": testability["score"],
                "consistency_issues": len(consistency_findings),
            },
            "shall_coverage_details": coverage_findings,
            "testability": testability,
            "consistency_findings": consistency_findings,
            "uncovered_shalls": [
                f["shall"] for f in coverage_findings if not f["covered"]
            ],
            "recommendations": [],
        }

        # Generate recommendations
        if uncovered > 0:
            review["recommendations"].append(
                f"{uncovered} SHALL/SHOULD statement(s) lack corresponding "
                f"PRD requirements.  Review each uncovered item and add "
                f"the missing requirement to the PRD."
            )
            review["status"] = "warning"

        if testability["score"] < 40:
            review["recommendations"].append(
                "PRD testability score is low.  Add explicit acceptance "
                "criteria (GIVEN/WHEN/THEN or 验收标准) for each requirement."
            )

        if consistency_findings:
            review["recommendations"].append(
                f"{len(consistency_findings)} section(s) in the spec lack "
                f"coverage in the S.U.P.E.R analysis.  Review the analysis "
                f"and ensure all spec sections are addressed."
            )

        if not review["recommendations"]:
            review["recommendations"].append(
                "All spec requirements are covered in the PRD with "
                "adequate testability criteria."
            )

        # --- Write output ---
        out_path = session.session_dir / "prd-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except (OSError, IOError) as e:
            log.error(f"Cannot write PRD review: {e}")
            raise PipelineStepError(f"Cannot write PRD review: {e}")

        print(f"  ✅ [小马] PRD/Super Analysis review completed:")
        print(f"       SHALLs: {shall_count} | SHOULDs: {should_count} | MAYs: {may_count}")
        print(f"       PRD coverage: {covered}/{len(coverage_findings)}"
              f" ({review['summary']['shall_coverage']['coverage_pct']}%)")
        print(f"       Testability score: {testability['score']}/100")
        print(f"       Status: {review['status']}")
        log.info("PRD review: covered=%d/%d, testability=%d, status=%s",
                 covered, len(coverage_findings), testability["score"], review["status"])
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"PRD review step failed: {e}")
        raise PipelineStepError(f"PRD review step failed: {e}")
