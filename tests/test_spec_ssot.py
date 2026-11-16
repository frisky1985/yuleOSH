"""AUD-ASPICE-001 NC-02 回归：SSOT 模型与拓扑闭环校验。"""

# @tests src/yuleosh/spec/ssot.py, src/yuleosh/pipeline/step_handlers/review_arch.py

from yuleosh.spec.ssot import (
    build_model,
    extract_design_units,
    extract_requirements,
    validate_topology,
)

SPEC = """
# spec

### SR-001
- The system SHALL blink the LED every 1000 ms.

### SR-002
- The system SHALL expose a HAL boundary.

### SR-003
- The system SHALL keep phase drift below one tick.
"""

ARCH_OK = """
# architecture

## Design Units

| DES-ID | Module | Satisfies | Interfaces |
|---|---|---|---|
| DES-SWE-001 | led_blink.c | SR-001, SR-003 | IF-HAL-001 |
| DES-SWE-002 | hal_host.c | SR-002 | IF-HAL-001 |
"""

ARCH_MISSING_UNITS = """
# architecture

模块: led_blink, hal_host
"""

ARCH_ORPHAN = """
## Design Units

| DES-ID | Module | Satisfies | Interfaces |
|---|---|---|---|
| DES-SWE-001 | led_blink.c | SR-001 | IF-HAL-001 |
"""

ARCH_DANGLING = """
## Design Units

| DES-ID | Module | Satisfies | Interfaces |
|---|---|---|---|
| DES-SWE-001 | led_blink.c | SR-001, SR-999 | IF-MISSING-001 |
"""


class TestExtraction:
    def test_body_references_do_not_create_duplicate_entities(self):
        spec = SPEC + "\n正文再次引用 SR-001 不算重复实体。\n"
        ids = [r.id for r in extract_requirements(spec)]
        assert ids == ["SR-001", "SR-002", "SR-003"]

    def test_design_unit_table_is_parsed(self):
        units = extract_design_units(ARCH_OK)
        assert [u.id for u in units] == ["DES-SWE-001", "DES-SWE-002"]
        assert units[0].satisfies_reqs == ("SR-001", "SR-003")
        assert units[0].uses_interfaces == ("IF-HAL-001",)

    def test_table_header_is_not_a_design_unit(self):
        units = extract_design_units(
            "| DES-ID | Module | Satisfies | Interfaces |\n|---|---|---|---|\n")
        assert units == []


class TestTopologyValidation:
    def test_complete_model_has_no_issues(self):
        assert validate_topology(build_model(SPEC, ARCH_OK)) == []

    def test_missing_design_units_blocks(self):
        rules = {i.rule for i in validate_topology(build_model(SPEC, ARCH_MISSING_UNITS))}
        assert "SSOT-NO-DESIGN-UNITS" in rules

    def test_orphan_requirement_is_reported(self):
        issues = validate_topology(build_model(SPEC, ARCH_ORPHAN))
        orphan = next(i for i in issues if i.rule == "SSOT-ORPHAN-REQ")
        assert orphan.severity == "major"
        assert "SR-002" in orphan.message and "SR-003" in orphan.message

    def test_dangling_requirement_is_critical(self):
        issues = validate_topology(build_model(SPEC, ARCH_DANGLING))
        dangling = next(i for i in issues if i.rule == "SSOT-DANGLING-REQ")
        assert dangling.severity == "critical"
        assert "SR-999" in dangling.message

    def test_duplicate_requirement_ids_are_reported(self):
        spec = "### SR-001\n- a\n\n### SR-001\n- b\n"
        rules = {i.rule for i in validate_topology(build_model(spec, ""))}
        assert "SSOT-DUP-REQ" in rules

    def test_findings_are_gate_compatible(self):
        issue = validate_topology(build_model(SPEC, ARCH_MISSING_UNITS))[0]
        finding = issue.as_finding()
        assert finding["severity"] in ("critical", "major", "minor")
        assert finding["source"] == "deterministic"
