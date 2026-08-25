#!/usr/bin/env python3

# @req RS-005  @req SWR-001.2
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Traceability matrix generator.

Generates Requirement ↔ Code ↔ Test ↔ Review bidirectional
traceability reports (LRM / LRT) for ASPICE CL2 compliance.

Sources:
  1. Spec SHALL statements (from docs/spec.md or specs/*.md)
  2. Review artifacts (.yuleosh/sessions/*/code-review.json)
  3. Test reports (.yuleosh/sessions/*/*test*.json)
  4. CI results (.osh/ci/layer1-*.json)
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.alm.traceability")

# Source file extensions to scan for requirement annotations and code
_SOURCE_EXTENSIONS = (".py", ".c", ".h", ".cpp", ".hpp")

# Regex for @req annotation: matches @req RS-001, @req(RS-001), @req RS-001, RS-002
_REQ_ANNOTATION_RE = re.compile(
    r'@req\s*[\(\s]\s*([A-Z][A-Z0-9_\-\.]+(?:\s*,\s*[A-Z][A-Z0-9_\-\.]+)*)',
    re.IGNORECASE,
)

# Regex for @tests annotation: matches @tests src/init.py, @tests src/init.py:init()
# Captures: (file_path, optional_function_list)
_TEST_ANNOTATION_RE = re.compile(
    r'@tests\s+([\w./\\\-]+(?:\.[\w]+))'  # file path (e.g., src/init.py)
    r'(?:\s*:\s*([^\n\r]+))?',             # optional function list after colon (rest of line)
    re.IGNORECASE,
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _is_table_separator(line: str) -> bool:
    """Check if a line is a markdown table separator.

    Accepts both ``|:---|---:|`` (with colons) and ``|---|---|`` (plain dashes) formats.
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    # Allowable chars: |, -, :, and optional spaces
    for c in stripped:
        if c not in "|:- ":
            return False
    # Must have at least 2 dashes somewhere
    stripped_dashes = stripped.replace("|", "").replace(":", "").replace(" ", "")
    return len(stripped_dashes) >= 2 and all(c == "-" for c in stripped_dashes)


def _is_shall_table_header(col_names: list[str]) -> bool:
    """Detect if a list of column names indicates a SHALL requirement table.

    A SHALL table has:
      - Column 1 containing "ID"
      - Column 2 containing "描述", "SHALL", "Description", or "Statement"
    """
    if len(col_names) < 2:
        return False
    id_found = col_names[0].upper() == "ID" or "ID" in col_names[0].upper()
    desc_found = (
        "描述" in col_names[1]
        or "需求" in col_names[1]
        or "REQUIREMENT" in col_names[1].upper()
        or "SHALL" in col_names[1].upper()
        or "DESCRIPTION" in col_names[1].upper()
        or "STATEMENT" in col_names[1].upper()
    )
    return id_found and desc_found


def scan_req_annotations(src_dir: Path) -> dict[str, list[str]]:
    """Scan source files for @req annotations linking code to requirements.

    Supports annotation syntax:
      - ``# @req RS-001`` (Python/shell line comment)
      - ``// @req RS-001`` (C/C++ line comment)
      - ``/* @req RS-001 */`` (C/C++ block comment)
      - ``@req(RS-001)`` (decorator style)
      - ``@req RS-001, RS-002`` (multiple IDs on one line)

    Returns dict mapping req_id (uppercased) to list of relative file paths.
    Annotation matches are authoritative — they take priority over keyword
    heuristics in generate_lrm().
    """
    if not src_dir.exists():
        return {}

    annotation_map: dict[str, list[str]] = {}

    for ext in _SOURCE_EXTENSIONS:
        for source_file in sorted(src_dir.rglob(f"*{ext}")):
            if not source_file.is_file():
                continue
            try:
                text = source_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # For C/C++ files, strip block comments to avoid false positives
            # from commented-out code (but keep line comments)
            if ext in (".c", ".h", ".cpp", ".hpp"):
                # Strip /* ... */ block comments but preserve // line comments
                text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

            # Find all @req annotations
            for match in _REQ_ANNOTATION_RE.finditer(text):
                id_group = match.group(1)
                # Split comma-separated IDs and normalize to uppercase
                for req_id in id_group.split(","):
                    req_id = req_id.strip().upper()
                    if req_id:
                        rel_path = str(source_file.relative_to(src_dir.parent))
                        if req_id not in annotation_map:
                            annotation_map[req_id] = []
                        if rel_path not in annotation_map[req_id]:
                            annotation_map[req_id].append(rel_path)

    return annotation_map


def scan_test_code_links(project_dir: Path) -> dict[str, dict]:
    """Scan test files for @tests annotations linking tests to source code.

    Supports annotation syntax:
      - ``@tests src/init.py`` (test file tests this source file)
      - ``@tests src/init.py:init()`` (test file tests this specific function)
      - ``@tests src/init.py:init, helper`` (multiple functions)

    Returns dict mapping test_file (relative path) to:
      {
        "source_file": str,       # source file being tested
        "functions": list[str],   # specific functions being tested (may be empty)
      }

    This enables direct test → code traceability, complementing the indirect
    link via requirement IDs.
    """
    if not project_dir.exists():
        return {}

    test_links: dict[str, dict] = {}
    tests_dir = project_dir / "tests"

    if not tests_dir.exists():
        return {}

    # Scan all test files: Python (test_*.py) + C/C++ (test_*.c / test_*.cpp)
    # C projects (e.g. AUTOSAR BSW) keep tests as .c files with @tests
    # annotations in // comments. (fix 2026-08-25: yuleASR 271 test files)
    test_files = sorted(tests_dir.rglob("test_*.py")) + sorted(tests_dir.rglob("test_*.c"))
    for test_file in test_files:
        if not test_file.is_file():
            continue
        try:
            text = test_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Find all @tests annotations
        for match in _TEST_ANNOTATION_RE.finditer(text):
            source_path = match.group(1)
            functions_str = match.group(2)

            # Parse function list if present
            functions = []
            if functions_str:
                functions = [f.strip().rstrip("()") for f in functions_str.split(",")]
                functions = [f for f in functions if f]

            rel_test_path = str(test_file.relative_to(project_dir))
            test_links[rel_test_path] = {
                "source_file": source_path,
                "functions": functions,
            }

    return test_links


# ── SHALL statement extraction ──────────────────────────────────────────


def extract_shall_statements(spec_path: str) -> list[dict]:
    """Extract SHALL statements from a specification file (markdown).

    Supports two formats:
      1. List format: ``- The system SHALL ...`` under a requirement heading.
      2. Table format: ``| ID | 描述 | ASIL | 端 |`` rows where ID contains "-SHALL".

    Returns list of dicts with keys:
      - id:          Requirement ID (e.g. KL-SHALL-01) or auto-generated SHALL-{n}
      - req_id:      Spec-defined ID if available
      - statement:   The full SHALL text
      - line:        Line number in the spec file
      - section:     Section heading (if available)
    """
    spec_file = Path(spec_path)
    if not spec_file.exists():
        log.warning("Spec file not found: %s", spec_path)
        return []

    try:
        text = spec_file.read_text(encoding="utf-8")
    except OSError as e:
        log.error("Cannot read spec file: %s", e)
        return []

    lines = text.split("\n")
    shall_statements = []
    current_section = ""
    current_req_id: str | None = None
    in_given_when_then = False  # Skip GIVEN/WHEN/THEN scenario blocks

    # Pattern to match spec-defined IDs like **SWE-MISRA-S1**: or [REQ-MISRA-S1.1]
    spec_id_pattern = re.compile(r'(?:\*\*([\w][\w.\-]+)\*\*\s*:|\[([\w][\w.\-]+)\])')

    # Pattern to match requirement section headers
    section_req_id_pattern = re.compile(
        r'^#{1,6}\s+([A-Z][A-Z0-9]*(?:-REQ)?-\d+(?:\.\d+)?)\b', re.IGNORECASE
    )

    # Broad SHALL keyword search — works for both English and Chinese text
    shall_keyword_pattern = re.compile(r'\bSHALL\b|\bshall\b|\bMUST\b|\bmust\b')

    # ── Markdown table parsing state ──
    in_shall_table = False     # currently parsing a SHALL requirement table
    table_sep_seen = False     # separator row seen after table header

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()

        # ── Exit table mode on any non-pipe line (blank or heading) ──
        if in_shall_table and not stripped.startswith("|"):
            in_shall_table = False
            table_sep_seen = False

        # Track section headings
        if stripped.startswith("#"):
            # Exit table mode on headings
            in_shall_table = False
            table_sep_seen = False

            current_section = stripped.lstrip("#").strip()
            # Check if this section header has a requirement ID
            section_match = section_req_id_pattern.match(stripped)
            if section_match:
                current_req_id = section_match.group(1).upper()

            # Track GIVEN/WHEN/THEN blocks — skip these
            in_given_when_then = stripped.startswith("#####")
            # Skip Reason headings — they contain explanatory text, not requirements
            if "reason" in stripped.lower() and not in_given_when_then:
                continue

            continue

        # ── Detect markdown table with SHALL requirements ──
        if stripped.startswith("|") and not in_shall_table:
            cols = [c.strip() for c in stripped.split("|")]
            col_names = [c for c in cols if c]  # Remove empty leading/trailing
            if _is_shall_table_header(col_names):
                in_shall_table = True
                table_sep_seen = False
                continue

        # ── Parse table separator row ──
        if in_shall_table and not table_sep_seen and _is_table_separator(stripped):
            table_sep_seen = True
            continue

        # ── Parse table rows (SHALL requirements in table format) ──
        if in_shall_table and table_sep_seen and stripped.startswith("|"):
            cols = [c.strip() for c in stripped.split("|")]
            # cols[0] is empty (before first |), cols[1] is ID, cols[2] is description
            if len(cols) >= 3:
                row_id = cols[1].strip()
                row_desc = cols[2].strip()

                # Capture rows with SHALL IDs (e.g. KL-SHALL-01, PE-SHALL-NOT-01)
                # or REQ-style IDs where description starts with SHALL
                is_shall_row = "-SHALL" in row_id
                if not is_shall_row and row_desc.upper().startswith("SHALL"):
                    is_shall_row = True

                if is_shall_row:
                    shall_statement = row_desc.strip()
                    shall_statements.append({
                        "id": row_id,       # Use the actual spec ID (e.g. KL-SHALL-01)
                        "req_id": row_id,
                        "statement": shall_statement,
                        "line": idx,
                        "section": current_section,
                    })
            continue

        # ── Legacy: bullet-point format SHALLs ──
        if shall_keyword_pattern.search(stripped):
            if in_given_when_then:
                continue
            if in_shall_table:
                continue

            # Only capture bullet-point format (`- `, `* `, `+ `)
            if not (stripped.startswith("- ") or stripped.startswith("* ")
                    or stripped.startswith("+ ")):
                continue

            statement = stripped.strip()
            # Trim leading list markers
            statement = re.sub(r"^[\s]*[-*+]\s+", "", statement)
            statement = re.sub(r"^\d+[.)]\s+", "", statement)

            # Parse spec-defined ID from **ID**: prefix or [REQ-xxx] marker
            req_id = None
            spec_id_match = spec_id_pattern.match(statement)
            if spec_id_match:
                req_id = spec_id_match.group(1) or spec_id_match.group(2)

            # If no inline req_id, use the section-level req_id
            if not req_id:
                req_id = current_req_id

            shall_statements.append({
                "id": f"SHALL-{len(shall_statements) + 1}",
                "req_id": req_id,
                "statement": statement,
                "line": idx,
                "section": current_section,
            })

    log.info("Extracted %d SHALL statements from %s", len(shall_statements), spec_path)
    return shall_statements


def extract_shall_from_text(text: str) -> list[dict]:
    """Extract SHALL statements from raw text (no file I/O).

    Supports both list format and table format.
    """
    lines = text.split("\n")
    shall_statements = []
    current_section = ""

    shall_keyword_pattern = re.compile(r'\bSHALL\b|\bshall\b|\bMUST\b|\bmust\b')
    spec_id_pattern = re.compile(r'(?:\*\*([\w][\w.\-]+)\*\*\s*:|\[([\w][\w.\-]+)\])')

    # Table parsing state
    in_shall_table = False
    table_sep_seen = False

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()

        # Exit table mode
        if in_shall_table and not stripped.startswith("|"):
            in_shall_table = False
            table_sep_seen = False

        if stripped.startswith("#"):
            in_shall_table = False
            table_sep_seen = False
            current_section = stripped.lstrip("#").strip()
            continue

        # Detect table
        if stripped.startswith("|") and not in_shall_table:
            cols = [c.strip() for c in stripped.split("|")]
            col_names = [c for c in cols if c]
            if _is_shall_table_header(col_names):
                in_shall_table = True
                table_sep_seen = False
                continue

        # Parse table separator
        if in_shall_table and not table_sep_seen and _is_table_separator(stripped):
            table_sep_seen = True
            continue

        # Parse table rows
        if in_shall_table and table_sep_seen and stripped.startswith("|"):
            cols = [c.strip() for c in stripped.split("|")]
            if len(cols) >= 3:
                row_id = cols[1].strip()
                row_desc = cols[2].strip()
                # Capture rows with SHALL IDs or REQ-style IDs with SHALL in description
                is_shall_row = "-SHALL" in row_id
                if not is_shall_row and row_desc.upper().startswith("SHALL"):
                    is_shall_row = True
                if is_shall_row:
                    shall_statement = row_desc.strip()
                    shall_statements.append({
                        "id": row_id,
                        "req_id": row_id,
                        "statement": shall_statement,
                        "line": idx,
                        "section": current_section,
                    })
            continue

        # Legacy list format
        if shall_keyword_pattern.search(stripped):
            if in_shall_table:
                continue
            statement = stripped.strip()
            statement = re.sub(r"^[\s]*[-*+]\s+", "", statement)
            statement = re.sub(r"^\d+[.)]\s+", "", statement)

            req_id = None
            spec_id_match = spec_id_pattern.match(statement)
            if spec_id_match:
                req_id = spec_id_match.group(1) or spec_id_match.group(2)

            shall_statements.append({
                "id": f"SHALL-{len(shall_statements) + 1}",
                "req_id": req_id,
                "statement": statement,
                "line": idx,
                "section": current_section,
            })

    return shall_statements


# ── Review artifact scan ────────────────────────────────────────────────


def scan_review_artifacts(project_dir: str) -> list[dict]:
    """Scan .yuleosh/sessions/ for code-review.json artifacts.

    Returns list of dicts with keys:
      - session: Session name
      - agent:   Agent that performed the review
      - reviewed_files: List of file paths reviewed
      - findings: List of finding descriptions
    """
    # Try .osh/sessions/ first (primary), fall back to .yuleosh/sessions/
    sessions_dir = Path(project_dir) / ".osh" / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"
    if not sessions_dir.exists():
        log.info("No sessions directory found (tried .osh/sessions/ and .yuleosh/sessions/)")
        return []

    reviews = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        review_file = session_dir / "code-review.json"
        if not review_file.exists():
            # Also check for .osh/evidence/reviews/ files
            evidence_reviews = (Path(project_dir) / ".osh" / "evidence" / "reviews").glob("*.json")
            for evf in evidence_reviews:
                try:
                    data = json.loads(evf.read_text(encoding="utf-8"))
                    reviewed_files = []
                    findings = []
                    if isinstance(data, dict):
                        reviewed_files = data.get("reviewed_files", data.get("files", []))
                        if isinstance(reviewed_files, dict):
                            reviewed_files = list(reviewed_files.keys())
                        findings_text = data.get("findings", data.get("issues", []))
                        if isinstance(findings_text, list):
                            for f in findings_text:
                                if isinstance(f, dict):
                                    findings.append(f.get("description", str(f)))
                                elif isinstance(f, str):
                                    findings.append(f)
                    reviews.append({
                        "session": evf.stem,
                        "agent": data.get("agent", "unknown") if isinstance(data, dict) else "unknown",
                        "reviewed_files": reviewed_files,
                        "findings": findings,
                    })
                except (json.JSONDecodeError, OSError) as e:
                    log.warning("Cannot parse %s: %s", evf, e)
            continue

        try:
            data = json.loads(review_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot parse %s: %s", review_file, e)
            continue

        reviewed_files = []
        findings = []
        if isinstance(data, dict):
            reviewed_files = data.get("reviewed_files", data.get("files", []))
            if isinstance(reviewed_files, dict):
                reviewed_files = list(reviewed_files.keys())
            findings_text = data.get("findings", data.get("issues", []))
            if isinstance(findings_text, list):
                for f in findings_text:
                    if isinstance(f, dict):
                        findings.append(f.get("description", str(f)))
                    elif isinstance(f, str):
                        findings.append(f)

        reviews.append({
            "session": session_dir.name,
            "agent": data.get("agent", "unknown") if isinstance(data, dict) else "unknown",
            "reviewed_files": reviewed_files,
            "findings": findings,
        })

    log.info("Found %d review artifacts", len(reviews))
    return reviews


# ── Test report scan ────────────────────────────────────────────────────


def scan_test_reports(project_dir: str) -> list[dict]:
    """Scan .yuleosh/sessions/ for *test*.json reports.

    Returns list of dicts with keys:
      - session:  Session name
      - step:     Test step name
      - status:   Test status (passed/failed/skipped)
      - passed:   Number of passed tests
      - failed:   Number of failed tests
      - output:   Test output (truncated)
    """
    sessions_dir = Path(project_dir) / ".osh" / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"
    if not sessions_dir.exists():
        log.info("No sessions directory found (tried .osh/sessions/ and .yuleosh/sessions/)")
        return []

    reports = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        for test_file in session_dir.glob("*test*.json"):
            try:
                data = json.loads(test_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Cannot parse %s: %s", test_file, e)
                continue

            if isinstance(data, dict):
                reports.append({
                    "session": session_dir.name,
                    "step": data.get("step", test_file.stem),
                    "status": data.get("status", "unknown"),
                    "passed": data.get("passed", 0),
                    "failed": data.get("failed", 0),
                    "runner": data.get("test_runner", data.get("runner", "unknown")),
                    "file": str(test_file),
                })

    log.info("Found %d test reports", len(reports))
    return reports


# ── CI result scan ──────────────────────────────────────────────────────


def scan_ci_results(project_dir: str) -> list[dict]:
    """Scan .osh/ci/ for layer result JSON files.

    Returns list of dicts with keys:
      - layer: CI layer name
      - status: Layer status
      - timestamp: Run timestamp
    """
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        log.info("No CI results directory at %s", ci_dir)
        return []

    results = []
    for result_file in sorted(ci_dir.glob("layer*.json")):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot parse %s: %s", result_file, e)
            continue

        if isinstance(data, dict):
            results.append({
                "layer": data.get("layer", result_file.stem),
                "status": data.get("status", "unknown"),
                "timestamp": data.get("timestamp", ""),
                "file": str(result_file),
            })

    log.info("Found %d CI results", len(results))
    return results


# ── LRM: Lateral Requirements Matrix ────────────────────────────────────


# ── SWR mapping table (requirement-traceability-matrix.md) ─────────────


#: Header detection for the SWR mapping table:
#: ``| SHALL ID | Spec Source | Test File | Test Function | Status |``
_SWR_MAPPING_HEADER_RE = re.compile(
    r"SHALL\s*ID.*(?:Test\s*File|测试|用例).*Status", re.IGNORECASE
)


#: SWR-style requirement IDs: SWR-001.1-01, SWR-002.1-01, SWR-003.2 ...
_SWR_ID_RE = re.compile(r"SWR-\d+(?:\.\d+)*(?:-\d+)?")


#: Requirement IDs that count as traceable requirement rows in any table.
_REQ_ROW_ID_RE = re.compile(
    r"(?:SWR-\d+(?:\.\d+)*(?:-\d+)?|REQ-\d+(?:-S\d+)?|"
    r"[A-Z][A-Z0-9]*-(?:REQ|SHALL)-\d+|SHALL-\d+)",
    re.IGNORECASE,
)


def load_swr_mapping_table(project_dir: str) -> list[dict]:
    """Read ``docs/requirement-traceability-matrix.md`` (SWR mapping table).

    The SWR mapping table is the authoritative requirement → test mapping
    produced for the project (SWR ID | Spec Source | Test File | Test
    Function | Status).  Rows with a ✅/PASS status become requirements
    marked as covered by the mapped test file.

    Returns list of dicts:
        - id:           SWR requirement ID (e.g. SWR-001.1-01)
        - req_id:       same as id
        - statement:    human-readable statement (``SWR-xxx test mapping``)
        - test_file:    mapped test file path
        - test_function: mapped test function name
        - status:       row status token (✅/PASS/...) or ""
        - has_test:     True when the row is a covered mapping
    """
    candidates = [
        Path(project_dir) / "docs" / "requirement-traceability-matrix.md",
        Path(project_dir) / "docs" / "traceability-matrix.md",
    ]
    for cand in candidates:
        if not cand.is_file():
            continue
        try:
            lines = cand.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            log.warning("Cannot read mapping table %s: %s", cand, e)
            continue
        rows: list[dict] = []
        in_table = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and _SWR_MAPPING_HEADER_RE.search(stripped):
                in_table = True
                continue
            if not in_table:
                continue
            if not stripped.startswith("|") or _is_table_separator(stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 3:
                continue
            row_id = cells[0]
            if not _SWR_ID_RE.fullmatch(row_id):
                continue
            test_file = cells[2] if len(cells) > 2 else ""
            test_function = cells[3] if len(cells) > 3 else ""
            status = cells[4] if len(cells) > 4 else ""
            covered = bool(re.search(r"✅|PASS", status)) or status.strip() in {"Implemented", "Covered"}
            rows.append({
                "id": row_id,
                "req_id": row_id,
                "statement": f"SWR requirement {row_id} (mapped to test)",
                "section": "SWR Mapping Table",
                "test_file": test_file,
                "test_function": test_function,
                "status": status,
                "has_test": covered,
            })
        if rows:
            log.info("Loaded %d SWR mapping rows from %s", len(rows), cand)
            return rows
    return []


def generate_lrm(project_dir: str, spec_path: Optional[str] = None) -> dict:
    """Generate LRM (Lateral Requirements Matrix).

    Maps each SHALL statement to:
      - Source files implementing it (Code)
      - Tests verifying it (Test)
      - Reviews covering it (Review)

    Scans ALL spec files under specs/ and docs/ for SHALL statements.

    Returns dict with 'requirements' list and summary stats.
    """
    # Collect all spec files: primary spec + all specs/*.md
    spec_files = []

    # Primary spec file (docs/spec.md or explicit path)
    if spec_path and Path(spec_path).exists():
        spec_files.append(str(spec_path))

    # Auto-discover docs/spec.md
    docs_spec = Path(project_dir) / "docs" / "spec.md"
    if str(docs_spec) not in spec_files and docs_spec.exists():
        spec_files.append(str(docs_spec))

    # Auto-discover docs/software-requirements.md (SWR-xxx SRS)
    docs_swr = Path(project_dir) / "docs" / "software-requirements.md"
    if str(docs_swr) not in spec_files and docs_swr.exists():
        spec_files.append(str(docs_swr))

    # Auto-discover ALL specs/*.md files
    specs_dir = Path(project_dir) / "specs"
    if specs_dir.exists():
        for sf in sorted(specs_dir.glob("*.md")):
            s = str(sf)
            if s not in spec_files:
                spec_files.append(s)

    if not spec_files:
        log.warning("No spec files found for LRM generation")
        return {"requirements": [], "summary": {"total": 0, "no_code": 0, "no_test": 0}}

    # Extract requirements from ALL spec files
    shalls = []
    for sf in spec_files:
        sf_shalls = extract_shall_statements(sf)
        log.info("Extracted %d SHALLs from %s", len(sf_shalls), sf)
        shalls.extend(sf_shalls)
    reviews = scan_review_artifacts(project_dir)
    test_reports = scan_test_reports(project_dir)

    # Build code → requirement mapping by scanning src/ for comments
    src_dir = Path(project_dir) / "src"

    # Scan for @req annotations (authoritative, language-agnostic)
    annotation_map = scan_req_annotations(src_dir)

    # Scan for @tests annotations (test → code direct links)
    test_code_links = scan_test_code_links(Path(project_dir))

    # Scan for SHALL-N / REQ-ID comments
    code_map = _scan_comments_for_requirements(src_dir, shalls)

    # Merge annotation hits into code_map with annotation paths first
    for req_id, paths in annotation_map.items():
        existing = code_map.get(req_id, [])
        code_map[req_id] = list(dict.fromkeys(paths + existing))

    requirements = []
    for shall in shalls:
        req_id = shall["id"]
        spec_req_id = shall.get("req_id") or req_id  # Use spec-defined req_id when available

        # Find code that references this requirement
        matching_code = code_map.get(req_id, [])
        if not matching_code:
            # Fallback: search by keyword
            keywords = _extract_keywords(shall["statement"])
            matching_code = _find_code_by_keywords(src_dir, keywords)
            # Also try spec_req_id for code matching
            if spec_req_id != req_id and not matching_code:
                matching_code = _find_code_by_keywords_for_id(src_dir, spec_req_id)

        # Find tests that reference this requirement (use spec_req_id for better matches)
        matching_tests = _find_tests_for_requirement(test_reports, spec_req_id, shall["statement"])

        # Enrich test entries with @tests annotation links (test → code direct traceability)
        for test_entry in matching_tests:
            if isinstance(test_entry, dict) and "file" in test_entry:
                test_file = test_entry["file"]
                if test_file in test_code_links:
                    link = test_code_links[test_file]
                    test_entry["tested_code"] = {
                        "source_file": link["source_file"],
                        "functions": link["functions"],
                    }

        # Find reviews that reference this requirement
        matching_reviews = _find_reviews_for_requirement(reviews, spec_req_id, shall["statement"])

        # Determine match method for traceability audit
        if req_id in annotation_map or spec_req_id in annotation_map:
            match_method = "annotation"
        elif req_id in code_map and code_map[req_id]:
            match_method = "comment"
        elif matching_code:
            match_method = "keyword"
        else:
            match_method = "none"

        requirements.append({
            "id": req_id,
            "req_id": shall.get("req_id"),
            "statement": shall["statement"],
            "section": shall.get("section", ""),
            "code_files": matching_code,
            "test_reports": matching_tests,
            "reviews": matching_reviews,
            "has_code": len(matching_code) > 0,
            "has_test": len(matching_tests) > 0,
            "has_review": len(matching_reviews) > 0,
            "match_method": match_method,
            "step_handlers": _find_step_handlers_for_requirement(project_dir, req_id, shall),
        })

    # Merge SWR mapping table rows (docs/requirement-traceability-matrix.md):
    #   1. Enrich existing requirements whose req_id matches a mapped SWR row.
    #   2. Add mapped rows that have no matching SHALL statement yet, so the
    #      SWR requirement → test links are present in the matrix.
    swr_mapping = load_swr_mapping_table(project_dir)
    if swr_mapping:
        by_id: dict[str, dict] = {}
        for m in swr_mapping:
            by_id.setdefault(m["id"].upper(), m)
        # Enrich existing requirements — the SWR mapping table is the
        # authoritative requirement → test mapping, so the mapped test link
        # is always attached (deduplicated against pytest-scanned matches).
        for req in requirements:
            for key in (str(req.get("req_id") or "").upper(), str(req.get("id") or "").upper()):
                mapped = by_id.get(key)
                if mapped is not None:
                    if mapped["has_test"]:
                        mapped_entry = {
                            "file": mapped["test_file"],
                            "function": mapped["test_function"],
                            "status": "passed",
                            "source": "SWR mapping table",
                        }
                        existing = [
                            t for t in req["test_reports"]
                            if isinstance(t, dict)
                            and t.get("file") == mapped["test_file"]
                            and t.get("function") == mapped["test_function"]
                        ]
                        if not existing:
                            req["test_reports"].insert(0, mapped_entry)
                        req["has_test"] = True
                    break
        # Add mapping rows with no matching requirement.
        existing_ids = {
            str(r.get("req_id") or r.get("id") or "").upper()
            for r in requirements
        }
        for m in swr_mapping:
            if m["id"].upper() in existing_ids:
                continue
            test_entry = []
            if m["has_test"]:
                test_entry = [{
                    "file": m["test_file"],
                    "function": m["test_function"],
                    "status": "passed",
                    "source": "SWR mapping table",
                }]
            requirements.append({
                "id": m["id"],
                "req_id": m["id"],
                "statement": m["statement"],
                "section": m["section"],
                "code_files": _find_code_by_keywords_for_id(src_dir, m["id"]),
                "test_reports": test_entry,
                "reviews": [],
                "has_code": False,
                "has_test": m["has_test"],
                "has_review": False,
                "step_handlers": [],
                "swr_mapping": True,
            })

    # Summary
    total = len(requirements)
    no_code = sum(1 for r in requirements if not r["has_code"])
    no_test = sum(1 for r in requirements if not r["has_test"])
    no_review = sum(1 for r in requirements if not r["has_review"])

    return {
        "requirements": requirements,
        "summary": {
            "total": total,
            "with_code": total - no_code,
            "without_code": no_code,
            "with_test": total - no_test,
            "without_test": no_test,
            "with_review": total - no_review,
            "without_review": no_review,
            "coverage_pct": round((total - no_test) / total * 100, 1) if total > 0 else 0.0,
        },
        "generated_at": datetime.now().isoformat(),
    }


# ── LRT: Lateral Requirements Traceability ─────────────────────────────


def generate_lrt(project_dir: str, spec_path: Optional[str] = None) -> dict:
    """Generate LRT (Lateral Requirements Traceability).

    Full bidirectional trace: Spec Requirement ↔ Code ↔ Test ↔ Review,
    plus a coverage gap analysis.

    Contains all LRM data plus additional cross-reference details.
    """
    lrm = generate_lrm(project_dir, spec_path)
    reviews = scan_review_artifacts(project_dir)
    test_reports = scan_test_reports(project_dir)
    ci_results = scan_ci_results(project_dir)

    # Cross-reference: list orphaned test files (no matching SHALL)
    orphaned_tests = _find_orphaned_tests(test_reports, lrm["requirements"])

    # Gap analysis
    gaps = []
    for req in lrm["requirements"]:
        if not req["has_code"]:
            gaps.append({
                "type": "no_code",
                "req_id": req["id"],
                "statement": req["statement"],
            })
        if not req["has_test"]:
            gaps.append({
                "type": "no_test",
                "req_id": req["id"],
                "statement": req["statement"],
            })
        if not req["has_review"]:
            gaps.append({
                "type": "no_review",
                "req_id": req["id"],
                "statement": req["statement"],
            })

    return {
        "lrm": lrm,
        "reviews_available": len(reviews),
        "test_reports_available": len(test_reports),
        "ci_results_available": len(ci_results),
        "orphaned_test_files": orphaned_tests,
        "gap_analysis": {
            "total_gaps": len(gaps),
            "gaps": gaps,
            "missing_code_count": sum(1 for g in gaps if g["type"] == "no_code"),
            "missing_test_count": sum(1 for g in gaps if g["type"] == "no_test"),
            "missing_review_count": sum(1 for g in gaps if g["type"] == "no_review"),
        },
        "generated_at": datetime.now().isoformat(),
    }


# ── Full traceability report ────────────────────────────────────────────


def generate_traceability_report(project_dir: str,
                                  spec_path: Optional[str] = None,
                                  output_dir: Optional[str] = None) -> dict:
    """Generate full traceability report with LRM + LRT + recommendations.

    Args:
        project_dir: Project root directory.
        spec_path:   Path to spec file (optional, auto-detected).
        output_dir:  Directory for output files (optional, defaults to .yuleosh/).

    Returns:
        Dict with keys: lrm, lrt, coverage_summary, recommendations.
    """
    project_path = Path(project_dir).resolve()

    # Generate LRT (includes LRM + gap analysis)
    lrt = generate_lrt(project_dir, spec_path)

    # Coverage summary
    summary = lrt.get("lrm", {}).get("summary", {})
    gaps = lrt.get("gap_analysis", {})

    coverage_summary = {
        "requirements_total": summary.get("total", 0),
        "test_coverage_pct": summary.get("coverage_pct", 0.0),
        "code_coverage": f"{summary.get('with_code', 0)}/{summary.get('total', 0)}",
        "review_coverage": f"{summary.get('with_review', 0)}/{summary.get('total', 0)}",
        "total_gaps": gaps.get("total_gaps", 0),
        "orphaned_tests": len(lrt.get("orphaned_test_files", [])),
    }

    # Recommendations
    recommendations = []
    total = summary.get("total", 0)
    if total > 0:
        if summary.get("without_code", 0) > total * 0.3:
            recommendations.append(
                "⚠️ 超过 30% 的需求缺少代码实现映射 — 建议在注释中添加 'REQ-ID: SHALL-N' 标记"
            )
        if summary.get("without_test", 0) > total * 0.2:
            recommendations.append(
                "⚠️ 超过 20% 的需求缺少测试覆盖 — 建议补充对应测试用例"
            )
        if summary.get("coverage_pct", 100) < 60:
            recommendations.append(
                "🔴 测试覆盖率低于 60% — 可能影响 ASPICE CL1 审计通过"
            )

    if lrt.get("orphaned_test_files"):
        recommendations.append(
            f"📋 发现 {len(lrt['orphaned_test_files'])} 个测试文件无对应需求关联 — "
            "建议在测试报告中添加 'SHALL-N' 引用"
        )

    # Write output if requested
    out = {
        "lrm": lrt.get("lrm", {}),
        "lrt": lrt,
        "coverage_summary": coverage_summary,
        "recommendations": recommendations,
        "generated_at": datetime.now().isoformat(),
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_file = out_path / "traceability-report.json"
        try:
            report_file.write_text(
                json.dumps(out, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("Traceability report written to %s", report_file)
        except OSError as e:
            log.error("Cannot write traceability report: %s", e)

    return out


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _find_step_handlers_for_requirement(project_dir: str, req_id: str,
                                              shall: dict) -> list[dict]:
    """Find step handler reports that reference a given requirement.

    Scans .yuleosh/sessions/ for JSON reports from pipeline step handlers
    that contain a ``req_ids`` or ``spec_ref`` field matching the req_id
    or SHALL id.
    """
    sessions_dir = Path(project_dir) / ".osh" / "sessions"
    if not sessions_dir.exists():
        sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"
    if not sessions_dir.exists():
        return []

    matching = []
    req_id_pattern = re.compile(re.escape(req_id))
    shall_id_pattern = re.compile(re.escape(shall["id"]))

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        for report_file in session_dir.glob("*.json"):
            try:
                data = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            # Check req_ids field in step handler report
            report_req_ids = data.get("req_ids", [])
            if isinstance(report_req_ids, list):
                if req_id in report_req_ids or shall["id"] in report_req_ids:
                    matching.append({
                        "session": session_dir.name,
                        "step": data.get("step", report_file.stem),
                        "file": str(report_file),
                    })
                    continue

            # Check spec_ref field
            spec_ref = data.get("spec_ref", "")
            if isinstance(spec_ref, str) and (req_id in spec_ref or shall["id"] in spec_ref):
                matching.append({
                    "session": session_dir.name,
                    "step": data.get("step", report_file.stem),
                    "file": str(report_file),
                })
                continue

            # Scan full JSON text for req_id
            text = json.dumps(data)
            if req_id_pattern.search(text) or shall_id_pattern.search(text):
                matching.append({
                    "session": session_dir.name,
                    "step": data.get("step", report_file.stem),
                    "file": str(report_file),
                })

    return matching


def _scan_comments_for_requirements(src_dir: Path, shalls: list[dict]) -> dict:
    """Scan source files for comments referencing SHALL IDs.

    Looks for patterns like::
        // REQ: SHALL-1
        /* REQ-ID: SHALL-3, SHALL-5 */
    """
    if not src_dir.exists():
        return {}

    code_map: dict[str, list[str]] = {}
    for s in shalls:
        code_map[s["id"]] = []

    req_pattern = re.compile(r'SHALL-\d+')
    comment_pattern = re.compile(r'REQ[- ]?(?:ID)?[:\s]+(.*?)(?:\*/|$)', re.IGNORECASE)

    for ext in _SOURCE_EXTENSIONS:
        for source_file in sorted(src_dir.rglob(f"*{ext}")):
            if not source_file.is_file():
                continue
            try:
                text = source_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # For C/C++ files, strip block comments to avoid false positives
            if ext in (".c", ".h", ".cpp", ".hpp"):
                text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

            # Scan for SHALL references in both comments and code
            found_ids = set()
            for match in req_pattern.findall(text):
                if match in code_map:
                    found_ids.add(match)

            for req_id in found_ids:
                rel_path = str(source_file.relative_to(src_dir.parent))
                if rel_path not in code_map.get(req_id, []):
                    if req_id in code_map:
                        code_map[req_id].append(rel_path)

    return code_map


def _extract_keywords(statement: str, project_dir: str | None = None) -> list[str]:
    """Extract meaningful keywords from a SHALL statement."""
    try:
        from yuleosh.alm.traceability_config import get_stop_words
        stop_words = get_stop_words(project_dir)
    except Exception:
        stop_words = frozenset({
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "as", "is", "was", "be",
            "are", "been", "being", "have", "has", "had", "do", "does",
            "did", "will", "would", "could", "should", "may", "might",
            "shall", "must", "not", "no", "its", "it's", "their", "them",
            "they", "this", "that", "these", "those",
        })
    tokens = re.findall(r'\b[a-zA-Z_]\w+\b', statement.lower())
    keywords = [t for t in tokens if t not in stop_words and len(t) > 2]

    # CJK bigrams — slide 2-char window over each contiguous CJK run
    cjk_runs = re.findall(r'[\u4e00-\u9fff]+', statement)
    for run in cjk_runs:
        if len(run) == 1:
            if run not in stop_words:
                keywords.append(run)
        else:
            for i in range(len(run) - 1):
                bigram = run[i:i+2]
                if bigram not in stop_words:
                    keywords.append(bigram)

    # Deduplicate while preserving order
    return list(dict.fromkeys(keywords))


def _find_code_by_keywords(src_dir: Path, keywords: list[str]) -> list[str]:
    """Find source files matching the given keywords."""
    if not src_dir.exists() or not keywords:
        return []

    matching = []
    for ext in _SOURCE_EXTENSIONS:
        for source_file in sorted(src_dir.rglob(f"*{ext}")):
            if not source_file.is_file():
                continue
            try:
                text = source_file.read_text(encoding="utf-8", errors="replace")
                if ext in (".c", ".h", ".cpp", ".hpp"):
                    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
                text = text.lower()
            except OSError:
                continue
            # Count matching keywords
            matches = sum(1 for kw in keywords if kw in text)
            if matches > 0:
                rel = str(source_file.relative_to(src_dir.parent))
                matching.append(rel)

    return matching[:20]  # limit


def _find_code_by_keywords_for_id(src_dir: Path, req_id: str) -> list[str]:
    """Find source files matching a req_id (RS-001, SWR-001.1, etc.)."""
    if not src_dir.exists() or not req_id:
        return []

    matching = []
    id_lower = req_id.lower()
    for ext in _SOURCE_EXTENSIONS:
        for source_file in sorted(src_dir.rglob(f"*{ext}")):
            if not source_file.is_file():
                continue
            try:
                text = source_file.read_text(encoding="utf-8", errors="replace")
                if ext in (".c", ".h", ".cpp", ".hpp"):
                    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
                text = text.lower()
            except OSError:
                continue
            if id_lower in text:
                rel = str(source_file.relative_to(src_dir.parent))
                matching.append(rel)

    return matching[:20]


def _find_reviews_for_requirement(reviews: list[dict], req_id: str,
                                   statement: str) -> list[dict]:
    """Find reviews referencing a specific requirement."""
    matching = []
    keywords = _extract_keywords(statement)

    for review in reviews:
        review_text = json.dumps(review).lower()

        if req_id.lower() in review_text:
            matching.append(review)
            continue

        kw_matches = sum(1 for kw in keywords if kw in review_text)
        if len(keywords) > 0 and kw_matches >= max(2, len(keywords) // 3):
            matching.append(review)

    return matching


def _find_orphaned_tests(test_reports: list[dict],
                          requirements: list[dict]) -> list[str]:
    """Find test files not associated with any requirement."""
    req_ids = {r["id"] for r in requirements}
    orphaned = []

    for report in test_reports:
        report_text = json.dumps(report)
        has_ref = any(req_id in report_text for req_id in req_ids)
        if not has_ref:
            orphaned.append(report.get("file", "unknown"))

    return orphaned


def _scan_test_pytest_files(project_dir: str, req_id: str) -> list[dict]:
    """Scan pytest files for test functions matching a requirement ID.

    Looks for patterns like req_id, requirement IDs in test function names,
    in docstrings, or in comments.
    """
    tests_dir = Path(project_dir) / "tests"
    if not tests_dir.exists():
        return []

    matching = []
    req_id_lower = req_id.lower()
    # Exact match variants
    variants = {req_id_lower, req_id.upper()}
    # Also look for normalized version (underscores instead of dashes/dots)
    id_normalized = req_id_lower.replace(".", "_").replace("-", "_")
    normalized_variants = {id_normalized, id_normalized.upper()}
    all_variants = variants | normalized_variants

    for test_file in sorted(tests_dir.rglob("test_*.py")):
        if not test_file.is_file():
            continue
        try:
            text = test_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        found_match = any(variant in text for variant in all_variants)

        if found_match:
            test_funcs = re.findall(r'def\s+(test_\w+|check_\w+)\(', text)
            matching.append({
                "file": str(test_file),
                "test_functions": test_funcs,
                "test_count": len(test_funcs),
            })

    return matching


# Override the _find_tests_for_requirement to also scan pytest files
def _find_tests_for_requirement(test_reports: list[dict], req_id: str,
                                 statement: str) -> list[dict]:
    """Find test reports and pytest files referencing a specific requirement."""
    matching = []

    # First check test report artifacts
    keywords = _extract_keywords(statement)
    for report in test_reports:
        output_text = json.dumps(report).lower()
        if req_id.lower() in output_text:
            matching.append(report)
            continue
        kw_matches = sum(1 for kw in keywords if kw in output_text)
        if len(keywords) > 0 and kw_matches >= max(2, len(keywords) // 3):
            matching.append(report)

    # Also scan pytest files for direct req_id references
    # (this is the authoritative source for the acceptance matrix)
    # Scan for any spec-defined req_id (RS-XXX, SWR-XXX, NFR-XXX) or plain SHALL-N
    if not matching and not req_id.startswith("SHALL-"):
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
        pytest_matches = _scan_test_pytest_files(project_dir, req_id)
        if pytest_matches:
            matching.extend(pytest_matches)

    return matching


def compute_trace_integrity(project_dir: str,
                            spec_path: Optional[str] = None) -> dict:
    """Compute a tamper-evident traceability integrity summary.

    Builds on :func:`generate_lrt` (bidirectional Requirement ↔ Code ↔
    Test ↔ Review matrix + gap analysis) and distils it into a compact,
    hashable integrity record.  The record's ``integrity_hash`` covers the
    canonical JSON of the whole summary, so any later mutation of the
    report (post-hoc back-filling of a broken link) is detectable when the
    hash is anchored in the SHA-256 audit chain (see the ``check`` CLI).

    Returns a dict with:

    - ``status``: ``ok`` when no broken links and no orphaned tests,
      otherwise ``broken``.
    - ``requirements_total`` / ``requirements_with_code`` /
      ``requirements_with_test`` / ``requirements_with_review``.
    - ``test_coverage_pct``: requirements with a test mapping / total.
    - ``broken_links``: list of gap dicts (no_code / no_test / no_review).
    - ``orphaned_tests``: list of test artifacts with no requirement link.
    - ``integrity_hash``: SHA-256 over the canonical JSON of this summary
      (without the hash field itself).
    - ``generated_at``: ISO timestamp.
    """
    lrt = generate_lrt(project_dir, spec_path)
    lrm = lrt.get("lrm", {})
    summary = lrm.get("summary", {})
    gaps = lrt.get("gap_analysis", {})
    orphaned = lrt.get("orphaned_test_files", [])

    total = summary.get("total", 0)
    with_test = summary.get("with_test", 0)
    broken_links = gaps.get("gaps", []) if gaps else []

    record = {
        "requirements_total": total,
        "requirements_with_code": summary.get("with_code", 0),
        "requirements_with_test": with_test,
        "requirements_with_review": summary.get("with_review", 0),
        "test_coverage_pct": round(
            (with_test / total * 100.0) if total else 0.0, 2
        ),
        "broken_links": broken_links,
        "orphaned_tests": orphaned,
        "generated_at": lrt.get("generated_at", ""),
    }

    status = "ok"
    if broken_links or orphaned:
        status = "broken"
    record["status"] = status

    # SHA-256 over the canonical JSON of everything except the hash itself.
    digest = hashlib.sha256()
    body = {k: v for k, v in record.items() if k != "integrity_hash"}
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    digest.update(canonical.encode("utf-8"))
    record["integrity_hash"] = digest.hexdigest()

    # Q2: anchor the RTM integrity hash into the SHA-256 audit chain so any
    # post-hoc mutation of the traceability snapshot is detectable.
    try:
        from yuleosh.audit.model import AuditLog as _AuditLog
        _audit_root = os.environ.get("YULEOSH_AUDIT_ROOT")
        _audit = _AuditLog(data_root=_audit_root)
        _audit.record(
            actor="system",
            action="traceability.snapshot",
            target=f"project:{os.path.basename(project_dir)}",
            tenant="",
            detail={
                "project_dir": str(project_dir),
                "integrity_hash": record["integrity_hash"],
                "status": record["status"],
                "requirements_total": record["requirements_total"],
                "test_coverage_pct": record["test_coverage_pct"],
                "broken_link_count": len(record["broken_links"]),
                "orphaned_test_count": len(record["orphaned_tests"]),
                "generated_at": record["generated_at"],
            },
        )
    except Exception as _e:
        log.warning("compute_trace_integrity: audit anchor failed (non-fatal): %s", _e)

    return record


__all__ = [
    "extract_shall_statements",
    "extract_shall_from_text",
    "scan_review_artifacts",
    "scan_test_reports",
    "scan_ci_results",
    "generate_lrm",
    "generate_lrt",
    "generate_traceability_report",
    "compute_trace_integrity",
]
