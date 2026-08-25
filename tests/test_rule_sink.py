"""Tests for memory.rule_sink extract_rules_from_diff and RuleSink (3B)."""

# @tests src/yuleosh/memory/rule_sink.py

import tempfile
from pathlib import Path

import pytest

from yuleosh.memory.rule_sink import ExtractedRule, RuleSink, extract_rules_from_diff


ORIGINAL_WITH_INT64 = """\
#include <stdint.h>

void process(int64_t value) {
    int64_t result = value * 2;
}
"""

CORRECTED_WITHOUT_INT64 = """\
#include <stdint.h>

void process(int32_t value) {
    int32_t result = value * 2;
}
"""

ORIGINAL_WITH_MALLOC = """\
#include <stdlib.h>

void init(void) {
    char *buf = malloc(256);
}
"""

CORRECTED_WITHOUT_MALLOC = """\
static char buf[256];

void init(void) {
    /* buffer is static */
}
"""

ORIGINAL_MISSING_GUARD = """\
void foo(void) {}
"""

CORRECTED_WITH_GUARD = """\
#ifndef FOO_H
#define FOO_H

void foo(void);

#endif /* FOO_H */
"""


@pytest.fixture
def tmp_project(tmp_path):
    return tmp_path


@pytest.fixture
def sink(tmp_project):
    return RuleSink(tmp_project)


class TestExtractRulesFromDiff:
    def test_returns_list(self):
        rules = extract_rules_from_diff(ORIGINAL_WITH_INT64, CORRECTED_WITHOUT_INT64, "src/a.c")
        assert isinstance(rules, list)

    def test_detects_int64_removal(self):
        rules = extract_rules_from_diff(ORIGINAL_WITH_INT64, CORRECTED_WITHOUT_INT64, "src/a.c")
        categories = [r.category for r in rules]
        descriptions = " ".join(r.description for r in rules).lower()
        assert len(rules) >= 1
        assert "int64" in descriptions or "type" in descriptions or "forbidden" in categories

    def test_detects_malloc_removal(self):
        rules = extract_rules_from_diff(ORIGINAL_WITH_MALLOC, CORRECTED_WITHOUT_MALLOC, "src/b.c")
        assert len(rules) >= 1
        descriptions = " ".join(r.description for r in rules).lower()
        assert "malloc" in descriptions or "dynamic" in descriptions or "static" in descriptions

    def test_source_file_recorded(self):
        rules = extract_rules_from_diff(ORIGINAL_WITH_INT64, CORRECTED_WITHOUT_INT64, "src/a.c")
        assert any(r.source_file == "src/a.c" for r in rules)

    def test_rule_id_generated(self):
        rules = extract_rules_from_diff(ORIGINAL_WITH_INT64, CORRECTED_WITHOUT_INT64, "src/a.c")
        for r in rules:
            assert r.id != ""

    def test_max_rules_returned(self):
        rules = extract_rules_from_diff(ORIGINAL_WITH_INT64, CORRECTED_WITHOUT_INT64, "src/a.c")
        assert len(rules) <= 3

    def test_identical_content_returns_empty(self):
        rules = extract_rules_from_diff("void foo(void) {}\n", "void foo(void) {}\n", "src/c.c")
        assert rules == []


class TestExtractedRuleFields:
    def test_required_fields_present(self):
        rule = ExtractedRule(
            id="rule-001",
            category="forbidden",
            title="No malloc",
            description="Do not use dynamic memory allocation",
            do_example="static char buf[256];",
            dont_example="char *buf = malloc(256);",
            source_file="src/a.c",
            created_at="2026-01-01T00:00:00",
        )
        assert rule.id == "rule-001"
        assert rule.category == "forbidden"
        assert rule.do_example != ""
        assert rule.dont_example != ""


class TestRuleSinkAddRules:
    def test_add_rules_writes_file(self, sink, tmp_project):
        rule = ExtractedRule(
            id="r1", category="forbidden", title="No malloc",
            description="No dynamic allocation", do_example="static buf[64];",
            dont_example="malloc(64);", source_file="src/x.c",
            created_at="2026-01-01T00:00:00",
        )
        count = sink.add_rules([rule])
        assert count >= 1
        rules_file = tmp_project / ".yuleosh" / "agents" / "LEARNED-RULES.md"
        assert rules_file.exists()

    def test_idempotent_add(self, sink):
        rule = ExtractedRule(
            id="r2", category="required", title="Header guard",
            description="All headers must have include guard",
            do_example="#ifndef H\n#define H\n#endif",
            dont_example="// no guard",
            source_file="src/y.h",
            created_at="2026-01-01T00:00:00",
        )
        sink.add_rules([rule])
        count2 = sink.add_rules([rule])
        assert count2 == 0  # idempotent: duplicate not added again

    def test_multiple_rules_written(self, sink, tmp_project):
        rules = [
            ExtractedRule(id=f"r{i}", category="forbidden", title=f"Rule {i}",
                          description=f"desc {i}", do_example="ok", dont_example="bad",
                          source_file="src/z.c", created_at="2026-01-01T00:00:00")
            for i in range(3)
        ]
        sink.add_rules(rules)
        loaded = sink.load_rules()
        ids = [r.id for r in loaded]
        assert all(f"r{i}" in ids for i in range(3))


class TestRuleSinkLoadRules:
    def test_load_empty(self, sink):
        rules = sink.load_rules()
        assert rules == []

    def test_load_after_save(self, sink):
        rule = ExtractedRule(
            id="load-test-1", category="naming", title="snake_case functions",
            description="All function names must use snake_case",
            do_example="void do_thing(void);",
            dont_example="void doThing(void);",
            source_file="src/api.h",
            created_at="2026-01-01T00:00:00",
        )
        sink.add_rules([rule])
        loaded = sink.load_rules()
        assert len(loaded) >= 1
        ids = [r.id for r in loaded]
        assert "load-test-1" in ids


class TestRuleSinkFormatForPrompt:
    def test_returns_string(self, sink):
        rule = ExtractedRule(
            id="fmt-1", category="forbidden", title="No printf",
            description="Do not use printf in embedded firmware",
            do_example="/* use UART_Send instead */",
            dont_example='printf("debug");',
            source_file="src/main.c",
            created_at="2026-01-01T00:00:00",
        )
        sink.add_rules([rule])
        rules = sink.load_rules()
        text = sink.format_for_prompt(rules)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_contains_do_dont_sections(self, sink):
        rule = ExtractedRule(
            id="fmt-2", category="required", title="Use volatile for ISR vars",
            description="Variables shared with ISR must be volatile",
            do_example="volatile uint8_t flag;",
            dont_example="uint8_t flag;",
            source_file="src/isr.c",
            created_at="2026-01-01T00:00:00",
        )
        sink.add_rules([rule])
        rules = sink.load_rules()
        text = sink.format_for_prompt(rules)
        upper = text.upper()
        assert "DO" in upper or "RULE" in upper

    def test_respects_max_chars(self, sink):
        rules = [
            ExtractedRule(id=f"c{i}", category="forbidden", title=f"Rule {i}",
                          description="x" * 200, do_example="ok", dont_example="bad",
                          source_file="s.c", created_at="2026-01-01")
            for i in range(10)
        ]
        text = sink.format_for_prompt(rules, max_chars=500)
        assert len(text) <= 600


class TestRecordCorrection:
    def test_record_correction_returns_rules(self, sink, tmp_project):
        rules = sink.record_correction(
            original_file="src/test.c",
            original_content=ORIGINAL_WITH_INT64,
            corrected_content=CORRECTED_WITHOUT_INT64,
            context="MISRA rule 10.1 compliance",
        )
        assert isinstance(rules, list)

    def test_rules_persisted_after_record_correction(self, sink, tmp_project):
        sink.record_correction(
            original_file="src/test.c",
            original_content=ORIGINAL_WITH_MALLOC,
            corrected_content=CORRECTED_WITHOUT_MALLOC,
            context="no heap in embedded",
        )
        loaded = sink.load_rules()
        assert len(loaded) >= 1
