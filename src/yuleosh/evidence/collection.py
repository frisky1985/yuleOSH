"""
yuleOSH Evidence Engine — Data collection.

Provides the ``DataCollectionMixin`` mixin class that implements data
collection methods (requirements, reviews, CI results, SIL reports) for
``EvidenceCollector``.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# JSON Schema for session.json validation
# Covers both pipeline session.json and review-session.json formats.
SESSION_JSON_SCHEMA = {
    "type": "object",
    "required": ["name", "status"],
    "properties": {
        "name": {"type": "string"},
        "status": {"type": "string", "enum": ["running", "passed", "failed", "skipped", "blocked", "in_progress", "completed", "cancelled", "pending"]},
        "spec_path": {"type": "string"},
        "commit_sha": {"type": "string"},
        "branch": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "current_step": {"type": "string"},
        "steps": {"type": "array"},
        "artifacts": {"type": "object"},
        "errors": {"type": "array"},
        "task": {"type": "string"},
        "decision": {"type": "string"},
        "reviews": {"type": "array"},
        "project_dir": {"type": "string"},
        "pipeline": {"type": "string"},
    },
    "additionalProperties": True,
}

# Schema for review-session.json (per-step review files)
REVIEW_SESSION_JSON_SCHEMA = {
    "type": "object",
    "required": ["task", "status"],
    "properties": {
        "task": {"type": "string"},
        "status": {"type": "string"},
        "decision": {"type": "string"},
        "reviews": {"type": "array"},
        "created_at": {"type": "string"},
    },
    "additionalProperties": True,
}

log = logging.getLogger("evidence.collection")


def _validate_session_json(data: dict, source: str) -> bool:
    """Validate session JSON data against the SESSION_JSON_SCHEMA.

    Returns True if valid, False if invalid (warnings logged).
    Non-blocking: schema violations emit warnings but do not raise.
    """
    return _validate_json_schema(data, source, SESSION_JSON_SCHEMA, "Session")


def _validate_review_session_json(data: dict, source: str) -> bool:
    """Validate review-session.json data against REVIEW_SESSION_JSON_SCHEMA."""
    return _validate_json_schema(data, source, REVIEW_SESSION_JSON_SCHEMA, "ReviewSession")


_SCHEMA_TYPE_CHECKERS = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "list": list,
    "dict": dict,
}


def _validate_json_schema(data: dict, source: str, schema: dict, label: str) -> bool:
    """Generic JSON schema validator (no external jsonschema lib dependency).

    Checks:
    - data is a dict
    - all required fields are present
    - enum constraints on string fields
    - type constraints on properties

    Non-blocking: violations emit warnings but do not raise.
    """
    if not isinstance(data, dict):
        log.warning(f"{label} data in {source} is not a dict (type={type(data).__name__})")
        return False

    # Check required fields
    for req in schema.get("required", []):
        if req not in data:
            log.warning(f"{label} data in {source} missing required field '{req}'")

    # Check property constraints
    props = schema.get("properties", {})
    for key, value in data.items():
        prop = props.get(key)
        if prop is None:
            continue  # additionalProperties allowed
        # Type check — map JSON schema type names to Python types safely
        expected_type = prop.get("type")
        if expected_type and expected_type != "object" and expected_type != "array":
            checker = _SCHEMA_TYPE_CHECKERS.get(expected_type)
            if checker is not None and not isinstance(value, checker):
                log.warning(f"{label} field '{key}' in {source}: expected {expected_type}, got {type(value).__name__}")
        # Enum check
        enum_vals = prop.get("enum")
        if enum_vals and isinstance(value, str) and value not in enum_vals:
            log.warning(f"{label} field '{key}' in {source}: value '{value}' not in allowed values {enum_vals}")

    return True


class DataCollectionMixin:
    """Mixin adding data-collection methods to EvidenceCollector."""

    def collect_requirements(self, spec_path: str = None):
        """Collect requirements from ALL spec files.

        Scans docs/spec.md, the specified spec_path, and ALL specs/*.md files,
        merging requirements and scenarios from each.
        """
        if spec_path is None:
            spec_path = self._find_latest_pipeline_spec()
        if spec_path is None:
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")

        # Build list of spec files to parse
        spec_files = []
        if os.path.exists(spec_path):
            spec_files.append(spec_path)

        # Always include docs/spec.md if different
        docs_path = os.path.join(self.project_dir, "docs", "spec.md")
        if docs_path not in spec_files and os.path.exists(docs_path):
            spec_files.append(docs_path)

        # Include ALL specs/*.md files
        specs_dir = os.path.join(self.project_dir, "specs")
        if os.path.isdir(specs_dir):
            for f in sorted(os.listdir(specs_dir)):
                if f.endswith(".md"):
                    fp = os.path.join(specs_dir, f)
                    if fp not in spec_files:
                        spec_files.append(fp)

        sys.path.insert(0, os.path.join(self.project_dir, "src", "spec"))
        try:
            from validate import parse_spec
        except ImportError:
            from yuleosh.spec.validate import parse_spec

        all_reqs = []
        all_scenarios = []
        seen_names = set()

        for sf in spec_files:
            try:
                doc = parse_spec(sf)
                new_reqs = 0
                for r in doc.requirements:
                    if r.name not in seen_names:
                        all_reqs.append(r.to_dict())
                        seen_names.add(r.name)
                        new_reqs += 1
                all_scenarios.extend(s.to_dict() for s in doc.scenarios)
                print(f"  📋 Parsed {sf}: {new_reqs} new requirements, {len(doc.scenarios)} scenarios")
            except Exception as e:
                print(f"  ⚠️  Skipped {sf}: {e}")

        self.requirements = all_reqs
        self.scenarios = all_scenarios
        print(f"  📋 Total: {len(self.requirements)} requirements, {len(self.scenarios)} scenarios")

        # Apply legacy → current REQ mapping (specs/legacy-shall-mapping.md)
        self._apply_legacy_mapping()

    # ------------------------------------------------------------------ #
    # Legacy SHALL ID mapping (superseded spec numbering)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_legacy_mapping(mapping_path: Path) -> list[dict]:
        """Parse specs/legacy-shall-mapping.md into filter rules.

        Expected table format (4 columns):

            | 遗留 ID 模式 | 状态 | 现需求 ID | 说明 |

        ``遗留 ID 模式`` may be an exact requirement name or a prefix ending
        in ``*``. ``状态`` must be one of ``superseded`` / ``deprecated``
        (drop from index) or ``mapped`` (rename to the target REQ ID).
        """
        rules: list[dict] = []
        try:
            lines = mapping_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return rules
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 4:
                continue
            pattern, status, target, _note = cols[0], cols[1].lower(), cols[2], cols[3]
            if "模式" in pattern or pattern in ("", "id"):
                continue  # header row
            if status not in ("superseded", "deprecated", "mapped"):
                continue  # separator or unknown status
            rules.append({"pattern": pattern, "status": status, "target": target.strip()})
        return rules

    @staticmethod
    def _match_legacy_rule(name: str, rules: list[dict]) -> Optional[dict]:
        """Return the first rule matching a requirement name (prefix or exact)."""
        for rule in rules:
            pat = rule["pattern"]
            if pat.endswith("*"):
                if name.startswith(pat[:-1]):
                    return rule
            elif pat == name:
                return rule
        return None

    def _apply_legacy_mapping(self):
        """Filter/remap legacy requirement IDs using the mapping doc.

        Projects that migrated from a legacy SHALL numbering (e.g.
        ``KL-SHALL-01``) to a current ``REQ-xxx`` numbering list the
        superseded entries in ``specs/legacy-shall-mapping.md``. Without
        this filter the evidence index double-counts legacy IDs that have
        no test mapping, which breaks the coverage gate.
        """
        mapping_path = Path(self.project_dir) / "specs" / "legacy-shall-mapping.md"
        if not mapping_path.exists():
            return

        rules = self._parse_legacy_mapping(mapping_path)
        if not rules:
            return

        # Pass 1: names of requirements NOT governed by the mapping doc are
        # authoritative (e.g. the machine-readable REQ table rows). Mapped
        # legacy entries whose target already exists there are duplicates
        # and must be dropped, so the authoritative entry (with its full
        # SHALL statements) wins.
        kept_names = {
            r.get("name", "")
            for r in self.requirements
            if self._match_legacy_rule(r.get("name", ""), rules) is None
        }

        kept: list[dict] = []
        dropped = 0
        renamed = 0
        seen: set[str] = set()
        for req in self.requirements:
            name = req.get("name", "")
            rule = self._match_legacy_rule(name, rules)
            if rule is None:
                # No rule: keep, but never duplicate an already-indexed name.
                if name in seen:
                    dropped += 1
                    continue
                kept.append(req)
                seen.add(name)
                continue
            if rule["status"] in ("superseded", "deprecated"):
                dropped += 1
                continue
            # mapped: rename to the current REQ ID — unless the authoritative
            # REQ entry already exists (dedupe, keep the authoritative one).
            target = rule["target"]
            if not target or target in kept_names or target in seen:
                dropped += 1
                continue
            req["name"] = target
            req["req_id"] = target
            kept.append(req)
            seen.add(target)
            renamed += 1

        self.requirements = kept
        print(f"  🗂️  Legacy mapping: {dropped} superseded/duplicate dropped, "
              f"{renamed} renamed → {len(kept)} requirements in index")

    def collect_reviews(self):
        """Collect review records from .osh/reviews/.

        Scans both subdirectory-based review-session.json files (e.g.
        code-review/review-session.json) and flat JSON files in
        latest/ directory (e.g. latest/code-review.json).
        Deduplicates by (commit_sha, review_type) pair.
        """
        rev_dir = Path(self.project_dir) / ".osh" / "evidence" / "reviews"
        if not rev_dir.exists():
            print("  ⏭️  No review records found")
            return

        seen_keys: set[tuple[str, str]] = set()
        for task_dir in rev_dir.iterdir():
            json_files: list[Path] = []
            if task_dir.is_dir():
                # Collect all .json files in the subdirectory
                for f in sorted(task_dir.glob("*.json")):
                    json_files.append(f)
            elif task_dir.suffix == ".json":
                # Flat JSON files at the reviews/ root level
                json_files.append(task_dir)

            for f in json_files:
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                    key = (data.get("commit_sha", ""), data.get("review_type", ""))
                    if key == ("", ""):
                        # No dedup key — always include
                        self.reviews.append(data)
                    elif key not in seen_keys:
                        seen_keys.add(key)
                        self.reviews.append(data)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"    ⚠️  Could not read review file {f}: {e}")

        print(f"  📋 Collected {len(self.reviews)} review session(s)")

    def collect_ci_results(self):
        """Collect CI layer results from .osh/ci/."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  ⏭️  No CI results found")
            return

        for f in sorted(ci_dir.glob("layer*.json")):
            with open(f) as fh:
                data = json.load(fh)
                self.ci_results.append(data)
                if data.get("coverage"):
                    self.coverage_data = data["coverage"]

        print(f"  📋 Collected {len(self.ci_results)} CI result(s)")

    def collect_sil_reports(self):
        """Collect SIL test reports from .osh/ci/."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  ⏭️  No CI directory — no SIL reports to collect")
            return

        sil_files = sorted(ci_dir.glob("*sil*.json"))
        if not sil_files:
            print("  ⏭️  No SIL test reports found (*sil*.json)")
            return

        for sf in sil_files:
            try:
                with open(sf) as f:
                    data = json.load(f)
                data["_source_file"] = sf.name
                self.sil_reports.append(data)
                self.ci_results.append(data)
            except (json.JSONDecodeError, OSError) as e:
                print(f"    ⚠️  Could not read SIL report {sf.name}: {e}")

        total_tests = sum(len(r.get("results", [])) for r in self.sil_reports)
        print(f"  🖥️  Collected {len(self.sil_reports)} SIL report(s)"
              f" ({total_tests} test case(s))")

    def collect_session_data(self):
        """Collect pipeline session data from .osh/sessions/.

        Scans all session subdirectories for session.json, spec-check.json,
        and per-step review files (arch-review.json, code-review.json, etc.),
        capturing the full pipeline lifecycle as evidence.

        This extends evidence coverage to ALL pipeline stages (not just
        review/L3), enabling traceability across spec-check, architecture
        review, devplan review, code review, MISRA review, linker review,
        memory review, startup review, selftest review, unit tests,
        integration tests, and coverage review.
        """
        sessions_dir = Path(self.project_dir) / ".osh" / "sessions"
        if not sessions_dir.exists():
            print("  ⏭️  No pipeline session data found")
            return

        session_count = 0
        step_files_found = 0
        step_coverage = {}  # step_name -> count of sessions with data

        for session_folder in sorted(sessions_dir.iterdir()):
            if not session_folder.is_dir():
                continue

            # Read session.json for metadata
            session_json = session_folder / "session.json"
            if not session_json.exists():
                continue

            try:
                with open(session_json) as f:
                    session_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            # JSON schema validation (non-blocking)
            _validate_session_json(session_data, str(session_json))

            session_count += 1
            self.session_data.append(session_data)

            # Collect per-step review files
            # These match the pattern: {step_name}-review.json or spec-check.json
            for step_file in sorted(session_folder.glob("*.json")):
                if step_file.name == "session.json":
                    continue
                step_name = step_file.stem  # e.g. "arch-review", "spec-check"
                try:
                    with open(step_file) as f:
                        step_data = json.load(f)
                    step_data["_session_name"] = session_data.get("name", session_folder.name)
                    step_data["_step_name"] = step_name
                    step_data["_session_status"] = session_data.get("status", "unknown")
                    self.pipeline_steps.append(step_data)
                    step_files_found += 1
                    step_coverage[step_name] = step_coverage.get(step_name, 0) + 1
                except (json.JSONDecodeError, OSError):
                    pass

        if session_count > 0:
            print(f"  📋 Collected {session_count} session(s) with {step_files_found} step data file(s)")
            # Print coverage summary showing which pipeline stages are covered
            covered_stages = sorted(step_coverage.keys())
            stages_summary = ", ".join(covered_stages[:10])
            if len(covered_stages) > 10:
                stages_summary += f" ... and {len(covered_stages) - 10} more"
            print(f"     Pipeline stages covered: {stages_summary}")
        else:
            print("  ⏭️  No session data found in .osh/sessions/")

    def _find_latest_pipeline_spec(self) -> Optional[str]:
        """Find the spec file path from the most recent pipeline session."""
        sessions_dir = Path(self.project_dir) / ".osh" / "sessions"
        if not sessions_dir.exists():
            return None

        latest_session = None
        latest_mtime = 0
        for sf in sessions_dir.iterdir():
            sj = sf / "session.json"
            if sj.exists():
                mtime = sj.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_session = sj

        if latest_session:
            try:
                data = json.loads(latest_session.read_text())
                spec = data.get("spec_path", "")
                if spec and os.path.exists(spec):
                    return spec
            except (json.JSONDecodeError, OSError):
                pass
        return None
