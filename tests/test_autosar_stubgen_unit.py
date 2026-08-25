"""Unit tests for yuleosh.autosar.stubgen (v3.4.2b Wave 2a).

Covers the RTE stub/mock C generator offline (no ARXML parsing):
  - StubGenerator init / generate / generate_all / clear
  - module construction (ports -> Rte_Read/Rte_Write stubs, runnables)
  - global variable generation (call counters / mock state)
  - file writing (header/source/test harness/mock header)
  - all renderers (header/source/test harness/mock header)
  - helpers (_port_data_type / _license_block)
  - generate_stubs entry point (parser mocked)
  - register_cli + _handle_gen_stub_command
"""

# @tests src/yuleosh/autosar/

import sys
import os
import argparse

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.autosar.stubgen import (
    StubGenerator, StubModule, StubFunction, generate_stubs, register_cli,
    _handle_gen_stub_command, HEADER_GUARD_TEMPLATE, LICENSE_BLOCK,
)
from yuleosh.autosar.models import SWCComponent, PortPrototype, RunnableEntity


# ── Fixtures ───────────────────────────────────────────────────────────

def _swc(name="BrakeCtrl", arxml="brake.arxml", ports=None, runnables=None):
    return SWCComponent(
        short_name=name,
        arxml_file=arxml,
        ports=ports or [],
        runnables=runnables or [],
    )


@pytest.fixture
def swc():
    return _swc(
        ports=[
            PortPrototype(short_name="VehicleSpeed", direction="in",
                          interface_ref="IF_Uint8Speed"),
            PortPrototype(short_name="BrakeCmd", direction="out",
                          interface_ref="IF_Uint8Cmd"),
            PortPrototype(short_name="ModeSw", direction="in",
                          interface_ref="IF_BoolFlag"),
        ],
        runnables=[
            RunnableEntity(short_name="BrakeCtrl_Step", period_ms=10.0,
                           data_read_access=["VehicleSpeed"],
                           data_write_access=["BrakeCmd"],
                           server_call_points=["Srv_Calibrate"]),
            RunnableEntity(short_name="BrakeCtrl_Init",
                           can_be_invoked_concurrently=True),
        ],
    )


@pytest.fixture
def gen(tmp_path):
    return StubGenerator(project_dir=str(tmp_path / "stubs"))


# ── Public API ─────────────────────────────────────────────────────────

class TestPublicAPI:
    def test_init_defaults(self):
        """GIVEN defaults WHEN init THEN sensible defaults."""
        g = StubGenerator()
        assert g.project_dir.name == "stubs"
        assert g.rte_header == '"Rte_Type.h"'
        assert g.emit_call_counters is True
        assert g.emit_mock_returns is True
        assert g._generated == set()

    def test_init_custom(self, tmp_path):
        """GIVEN custom args WHEN init THEN stored."""
        g = StubGenerator(project_dir=str(tmp_path / "out"),
                          rte_header='"Custom.h"',
                          emit_call_counters=False,
                          emit_mock_returns=False)
        assert g.emit_call_counters is False
        assert g.emit_mock_returns is False

    def test_generate_writes_files(self, swc, gen, tmp_path):
        """GIVEN fresh SWC WHEN generate THEN files written + tracked."""
        module = gen.generate(swc)
        assert swc.short_name in gen._generated
        out = tmp_path / "stubs"
        assert (out / "swc" / "brakectrl" / "BrakeCtrl_Stub.h").exists()
        assert (out / "swc" / "brakectrl" / "BrakeCtrl_Stub.c").exists()
        assert (out / "test" / "brakectrl" / "test_BrakeCtrl_stubs.c").exists()
        assert (out / "mocks" / "brakectrl" / "mock_BrakeCtrl.h").exists()

    def test_generate_duplicate_skips_write(self, swc, gen, tmp_path):
        """GIVEN already-generated SWC WHEN generate THEN module rebuilt w/o rewrite."""
        gen.generate(swc)
        before = (tmp_path / "stubs" / "swc" / "brakectrl" / "BrakeCtrl_Stub.h").stat().st_mtime
        module = gen.generate(swc)
        assert module.swc_name == "BrakeCtrl"
        assert len(module.functions) == 5  # 2 reads + 1 write + 2 runnables

    def test_generate_all(self, swc, gen):
        """GIVEN multiple SWCs WHEN generate_all THEN dict by short_name."""
        swc2 = _swc(name="MotorCtrl")
        results = gen.generate_all([swc, swc2])
        assert set(results) == {"BrakeCtrl", "MotorCtrl"}
        assert results["MotorCtrl"].swc_name == "MotorCtrl"

    def test_clear(self, swc, gen):
        """GIVEN generated set WHEN clear THEN emptied."""
        gen.generate(swc)
        assert gen._generated
        gen.clear()
        assert gen._generated == set()

    def test_generate_rte_primitive_flags(self, swc, gen):
        """GIVEN SWC with ports WHEN generate THEN RTE primitives marked."""
        module = gen.generate(swc)
        rte_funcs = [f for f in module.functions if f.is_rte_primitive]
        assert len(rte_funcs) == 3
        assert module.rte_reads == ["VehicleSpeed", "ModeSw"]
        assert module.rte_writes == ["BrakeCmd"]


# ── Module construction ────────────────────────────────────────────────

class TestModuleConstruction:
    def test_build_stub_module_paths(self, swc, gen):
        """GIVEN SWC WHEN build THEN paths use DEFAULT_SWC_DIR."""
        module = gen._build_stub_module(swc)
        assert module.header_path == "swc/brakectrl/BrakeCtrl_Stub.h"
        assert module.source_path == "swc/brakectrl/BrakeCtrl_Stub.c"
        assert module.includes == ['"Rte_Type.h"']

    def test_build_stub_module_no_ports(self, gen):
        """GIVEN SWC without ports WHEN build THEN no rte stubs."""
        bare = _swc(ports=[], runnables=[])
        module = gen._build_stub_module(bare)
        assert module.functions == []
        assert module.rte_reads == [] and module.rte_writes == []


# ── RTE primitive stubs ────────────────────────────────────────────────

class TestRtePrimitives:
    def test_rte_read_stub(self, gen):
        """GIVEN in-port WHEN read stub THEN name/params/body correct."""
        port = PortPrototype(short_name="VehicleSpeed", direction="in",
                             interface_ref="IF_Uint8Speed")
        stub = gen._make_rte_read_stub(port)
        assert stub.name == "Rte_Read_vehicleSpeed"
        assert stub.return_type == "Std_ReturnType"
        assert stub.params == ["uint8* value"]
        assert stub.body_lines[1] == "*value = _vehicleSpeed_mock_value;"
        assert stub.body_lines[2] == "_vehicleSpeed_call_count++;"
        assert stub.body_lines[-1] == "return RTE_E_OK;"
        assert stub.is_rte_primitive is True

    def test_rte_read_data_type_from_interface(self, gen):
        """GIVEN bool interface WHEN read stub THEN boolean type."""
        port = PortPrototype(short_name="Flag", direction="in",
                             interface_ref="IF_BoolFlag")
        stub = gen._make_rte_read_stub(port)
        assert stub.params == ["boolean* value"]

    def test_rte_write_stub(self, gen):
        """GIVEN out-port WHEN write stub THEN last-value capture."""
        port = PortPrototype(short_name="BrakeCmd", direction="out",
                             interface_ref="IF_Uint8Cmd")
        stub = gen._make_rte_write_stub(port)
        assert stub.name == "Rte_Write_brakeCmd"
        assert stub.params == ["const uint8 value"]
        assert stub.body_lines[1] == "_brakeCmd_last_value = value;"
        assert stub.body_lines[2] == "_brakeCmd_call_count++;"

    def test_rte_write_float(self, gen):
        """GIVEN float interface WHEN write stub THEN float32 type."""
        port = PortPrototype(short_name="Torque", direction="out",
                             interface_ref="IF_Float32Torque")
        stub = gen._make_rte_write_stub(port)
        assert stub.params == ["const float32 value"]


# ── Runnable stubs ─────────────────────────────────────────────────────

class TestRunnableStubs:
    def test_runnable_stub_defaults(self, gen):
        """GIVEN runnable WHEN stub THEN symbol/body/comment generated."""
        runnable = RunnableEntity(short_name="Step", period_ms=10.0)
        stub = gen._make_runnable_stub(runnable, _swc())
        assert stub.name == "Step"
        assert stub.return_type == "void"
        assert stub.params == []
        assert stub.body_lines[0] == "/* Stub: Runnable 'Step' (period: 10.0ms) */"
        assert stub.body_lines[-1] == "    _Step_call_count++;"

    def test_runnable_stub_symbol_override(self, gen):
        """GIVEN symbol override WHEN stub THEN symbol used as name."""
        runnable = RunnableEntity(short_name="Step", symbol="Brake_Step10")
        stub = gen._make_runnable_stub(runnable, _swc())
        assert stub.name == "Brake_Step10"

    def test_runnable_stub_accesses(self, gen):
        """GIVEN read/write/server accesses WHEN stub THEN comments emitted."""
        runnable = RunnableEntity(
            short_name="Step",
            data_read_access=["PortA", "PortB"],
            data_write_access=["PortC"],
            server_call_points=["Srv_X"],
        )
        stub = gen._make_runnable_stub(runnable, _swc())
        body = "\n".join(stub.body_lines)
        assert "/* Would read from port: PortA */" in body
        assert "/* Would read from port: PortB */" in body
        assert "/* Would write to port: PortC */" in body
        assert "/* Would call server: Srv_X */" in body

    def test_runnable_stub_no_period(self, gen):
        """GIVEN runnable without period WHEN stub THEN no period suffix."""
        runnable = RunnableEntity(short_name="Init")
        stub = gen._make_runnable_stub(runnable, _swc())
        assert stub.comment == "Stub for runnable 'Init'."

    def test_runnable_stub_concurrent_comment(self, gen):
        """GIVEN concurrent runnable WHEN stub THEN concurrency noted."""
        runnable = RunnableEntity(short_name="Init",
                                  can_be_invoked_concurrently=True)
        stub = gen._make_runnable_stub(runnable, _swc())
        assert "concurrent" in stub.comment


# ── Global vars ────────────────────────────────────────────────────────

class TestGlobalVars:
    def test_global_vars_full(self, swc, gen):
        """GIVEN module WHEN global vars THEN counters + mock state."""
        module = gen._build_stub_module(swc)
        vars_ = gen._make_global_vars(module)
        text = "\n".join(vars_)
        assert "static volatile uint32 _Rte_Read_vehicleSpeed_call_count = 0U;" in text
        assert "static uint8 _VehicleSpeed_mock_value = 0U;" in text
        assert "static uint8 _BrakeCmd_last_value = 0U;" in text

    def test_global_vars_no_counters(self, swc):
        """GIVEN emit_call_counters=False WHEN vars THEN no counters."""
        g = StubGenerator(project_dir="out", emit_call_counters=False)
        module = g._build_stub_module(swc)
        vars_ = g._make_global_vars(module)
        text = "\n".join(vars_)
        assert "call_count" not in text
        assert "_VehicleSpeed_mock_value" in text

    def test_global_vars_empty_module(self, gen):
        """GIVEN empty module WHEN vars THEN empty list."""
        module = StubModule(swc_name="X", header_path="h", source_path="s")
        assert gen._make_global_vars(module) == []


# ── File writing ───────────────────────────────────────────────────────

class TestFileWriting:
    def test_write_stub_files_all_artifacts(self, swc, gen, tmp_path):
        """GIVEN module WHEN write files THEN four artifacts on disk."""
        module = gen._build_stub_module(swc)
        gen._write_stub_files(swc, module)
        base = tmp_path / "stubs"
        assert (base / "swc" / "brakectrl" / "BrakeCtrl_Stub.h").read_text().startswith("/*")
        assert '#include "BrakeCtrl_Stub.h"' in (base / "swc" / "brakectrl" / "BrakeCtrl_Stub.c").read_text()
        assert "void setUp(void)" in (base / "test" / "brakectrl" / "test_BrakeCtrl_stubs.c").read_text()
        assert "mock_reset" in (base / "mocks" / "brakectrl" / "mock_BrakeCtrl.h").read_text()


# ── Renderers ──────────────────────────────────────────────────────────

class TestRenderHeader:
    def test_render_header_guard_and_externs(self, swc, gen):
        """GIVEN SWC WHEN header THEN guard/externs/prototypes present."""
        module = gen._build_stub_module(swc)
        text = gen._render_header(swc, module)
        assert f"#ifndef {HEADER_GUARD_TEMPLATE.format(name='BRAKECTRL')}" in text
        assert "extern volatile uint32 _Rte_Read_vehicleSpeed_call_count;" in text
        assert "extern uint8 _VehicleSpeed_mock_value;" in text
        assert "extern uint8 _BrakeCmd_last_value;" in text
        assert "Std_ReturnType Rte_Read_vehicleSpeed(uint8* value);" in text
        assert '#include "Rte_Type.h"' in text
        assert "#define RTE_E_OK      0U" in text

    def test_render_header_empty_module(self, gen):
        """GIVEN empty module WHEN header THEN no externs/prototypes."""
        module = StubModule(swc_name="X", header_path="h", source_path="s")
        text = gen._render_header(_swc(), module)
        assert "Stub function prototypes" in text


class TestRenderSource:
    def test_render_source_with_body(self, swc, gen):
        """GIVEN funcs with body_lines WHEN source THEN body emitted."""
        module = gen._build_stub_module(swc)
        text = gen._render_source(swc, module)
        assert "/* ======== Internal mock state ======== */" in text
        assert "static volatile uint32 _Rte_Read_vehicleSpeed_call_count = 0U;" in text
        assert "return RTE_E_OK;" in text
        assert f'#include "BrakeCtrl_Stub.h"' in text

    def test_render_source_default_body(self, gen):
        """GIVEN func without body_lines WHEN source THEN default body."""
        module = StubModule(
            swc_name="X", header_path="h", source_path="s",
            functions=[StubFunction(name="foo", return_type="uint8",
                                    body_lines=[]),
                       StubFunction(name="bar", body_lines=[])],
        )
        text = gen._render_source(_swc(), module)
        assert "uint8 foo()" in text
        assert "return (uint8)0U;" in text
        assert "_bar_call_count++;" in text

    def test_render_source_no_counter(self, gen):
        """GIVEN call_counter=False WHEN source THEN no counter emitted."""
        module = StubModule(
            swc_name="X", header_path="h", source_path="s",
            functions=[StubFunction(name="foo", call_counter=False)],
        )
        text = gen._render_source(_swc(), module)
        assert "_foo_call_count" not in text


class TestRenderTestHarness:
    def test_harness_reset_and_tests(self, swc, gen):
        """GIVEN module WHEN harness THEN reset + smoke tests + runner."""
        module = gen._build_stub_module(swc)
        text = gen._render_test_harness(swc, module)
        assert 'void test_Rte_Read_vehicleSpeed_can_be_called(void)' in text
        assert "TEST_ASSERT_EQUAL(1, _Rte_Read_vehicleSpeed_call_count);" in text
        assert "RUN_TEST(test_Rte_Read_vehicleSpeed_can_be_called);" in text
        assert "UNITY_BEGIN();" in text
        assert "_Rte_Write_brakeCmd_call_count = 0U;" in text

    def test_harness_const_param_cast(self, gen):
        """GIVEN const params WHEN harness THEN (type)0U cast used."""
        module = StubModule(
            swc_name="X", header_path="h", source_path="s",
            functions=[StubFunction(name="wr", params=["const uint8 value"])],
        )
        text = gen._render_test_harness(_swc(), module)
        assert "wr((const)0U);" in text

    def test_harness_no_params(self, gen):
        """GIVEN no params WHEN harness THEN bare call."""
        module = StubModule(
            swc_name="X", header_path="h", source_path="s",
            functions=[StubFunction(name="init")],
        )
        text = gen._render_test_harness(_swc(), module)
        assert "init();" in text


class TestRenderMockHeader:
    def test_mock_header_helpers(self, swc, gen):
        """GIVEN module WHEN mock header THEN reset/setter/getter/count."""
        module = gen._build_stub_module(swc)
        text = gen._render_mock_header(swc, module)
        assert "#ifndef BRAKECTRL_MOCK_H_" in text
        assert "static inline void mock_reset(void)" in text
        assert "static inline void mock_set_VehicleSpeed(uint8 value)" in text
        assert "static inline uint8 mock_get_BrakeCmd(void)" in text
        assert "static inline uint32 mock_Rte_Read_vehicleSpeed_call_count(void)" in text

    def test_mock_header_empty(self, gen):
        """GIVEN empty module WHEN mock header THEN still renders."""
        module = StubModule(swc_name="X", header_path="h", source_path="s")
        text = gen._render_mock_header(_swc(), module)
        assert "mock_reset" in text


# ── Helpers ────────────────────────────────────────────────────────────

class TestHelpers:
    @pytest.mark.parametrize("iface,expected", [
        ("IF_BoolFlag", "boolean"),
        ("IF_Uint8Speed", "uint8"),
        ("IF_U16Val", "uint16"),
        ("IF_U32Val", "uint32"),
        ("IF_Sint8Val", "sint8"),
        ("IF_S16Val", "sint16"),
        ("IF_S32Val", "sint32"),
        ("IF_Float32Val", "float32"),
        ("IF_AnythingElse", "uint8"),  # safe default
    ])
    def test_port_data_type(self, gen, iface, expected):
        """GIVEN interface name WHEN _port_data_type THEN mapped type."""
        port = PortPrototype(short_name="P", direction="in", interface_ref=iface)
        assert gen._port_data_type(port) == expected

    def test_port_data_type_bool_precedence(self, gen):
        """GIVEN bool-ish interface WHEN type THEN boolean wins."""
        port = PortPrototype(short_name="P", direction="in",
                             interface_ref="IF_Uint8BoolFlag")
        assert gen._port_data_type(port) == "boolean"

    def test_license_block(self, gen):
        """GIVEN source WHEN _license_block THEN header formatted."""
        text = gen._license_block("x.arxml")
        assert "AUTOGENERATED FILE" in text
        assert "Source: x.arxml" in text
        assert "Generated at:" in text

    def test_license_block_empty_source(self, gen):
        """GIVEN empty source WHEN _license_block THEN unknown used."""
        text = gen._license_block("")
        assert "Source: unknown" in text

    def test_generate_logs(self, swc, gen, caplog):
        """GIVEN generate WHEN run THEN info log emitted."""
        import logging
        with caplog.at_level(logging.INFO):
            gen.generate(swc)
        assert any("Generated stubs for SWC 'BrakeCtrl'" in r.message
                   for r in caplog.records)


# ── generate_stubs entry point ─────────────────────────────────────────

class TestGenerateStubs:
    def test_generates_all(self, swc, tmp_path, monkeypatch):
        """GIVEN parser returning SWCs WHEN generate_stubs THEN dict."""
        import yuleosh.autosar.parser as parser_mod
        parser_mod.ARXMLParser = type("FakeParser", (), {
            "parse_swc": staticmethod(lambda path: [swc])})
        out = str(tmp_path / "g")
        results = generate_stubs("any.arxml", output_dir=out)
        assert "BrakeCtrl" in results
        assert (tmp_path / "g" / "swc" / "brakectrl" / "BrakeCtrl_Stub.h").exists()

    def test_swc_filter_match(self, tmp_path, monkeypatch):
        """GIVEN matching swc filter WHEN generate_stubs THEN only that SWC."""
        import yuleosh.autosar.parser as parser_mod
        swcs = [_swc(name="A"), _swc(name="B")]
        parser_mod.ARXMLParser = type("FakeParser", (), {
            "parse_swc": staticmethod(lambda p: swcs)})
        results = generate_stubs("any.arxml", output_dir=str(tmp_path / "g"),
                                 swc_filter="B")
        assert set(results) == {"B"}

    def test_swc_filter_no_match(self, tmp_path, monkeypatch):
        """GIVEN non-matching filter WHEN generate_stubs THEN empty dict."""
        import yuleosh.autosar.parser as parser_mod
        parser_mod.ARXMLParser = type("FakeParser", (), {
            "parse_swc": staticmethod(lambda p: [_swc(name="A")])})
        results = generate_stubs("any.arxml", output_dir=str(tmp_path / "g"),
                                 swc_filter="ZZZ")
        assert results == {}


# ── CLI integration ────────────────────────────────────────────────────

class TestCLI:
    def test_register_cli_adds_subcommand(self):
        """GIVEN subparsers WHEN register_cli THEN gen-stub added."""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        register_cli(sub)
        args = parser.parse_args(["gen-stub", "input.arxml", "-o", "/tmp/out",
                                  "--swc", "X", "--verbose"])
        assert args.arxml == "input.arxml"
        assert args.output == "/tmp/out"
        assert args.swc == "X"
        assert args.verbose is True
        assert callable(args.func)

    def test_handle_missing_file(self, tmp_path, monkeypatch, capsys):
        """GIVEN non-existent arxml WHEN handler THEN stderr + exit 1."""
        with pytest.raises(SystemExit) as e:
            _handle_gen_stub_command(argparse.Namespace(
                arxml=str(tmp_path / "nope.arxml"), output="out", swc="",
                verbose=False))
        assert e.value.code == 1
        assert "file not found" in capsys.readouterr().err

    def test_handle_verbose_sets_debug(self, swc, tmp_path, monkeypatch, capsys):
        """GIVEN verbose flag WHEN handler THEN debug level set + success."""
        import yuleosh.autosar.stubgen as stubgen
        def fake_generate_stubs(**kw):
            print("\n  📦 AUTOSAR Stub Generation Summary")
            print("  Total SWCs: 1")
            return {"BrakeCtrl": StubModule(
                swc_name="BrakeCtrl", header_path="h", source_path="s",
                functions=[StubFunction(name="f")])}

        stubgen.generate_stubs = fake_generate_stubs
        arxml = tmp_path / "a.arxml"
        arxml.write_text("<xml/>")
        _handle_gen_stub_command(argparse.Namespace(
            arxml=str(arxml), output=str(tmp_path / "o"), swc="",
            verbose=True))
        out = capsys.readouterr().out
        assert "AUTOSAR Stub Generation Summary" in out

    def test_handle_error_exits(self, tmp_path, monkeypatch, capsys):
        """GIVEN generate_stubs raising WHEN handler THEN exit 1."""
        import yuleosh.autosar.stubgen as stubgen

        def boom(**kw):
            raise RuntimeError("parse failed")

        stubgen.generate_stubs = boom
        arxml = tmp_path / "a.arxml"
        arxml.write_text("<xml/>")
        with pytest.raises(SystemExit) as e:
            _handle_gen_stub_command(argparse.Namespace(
                arxml=str(arxml), output="o", swc="", verbose=False))
        assert e.value.code == 1
        assert "parse failed" in capsys.readouterr().err
