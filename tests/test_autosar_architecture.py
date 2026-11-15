# @tests src/yuleosh/desktop/autosar_seed.py
# @tests src/yuleosh/codegen/prompts.py

import shutil
import subprocess

import pytest

from yuleosh.codegen.prompts import build_codegen_prompt
from yuleosh.desktop.autosar_seed import seed_autosar_artifacts


def test_seed_generates_autosar_classic_layer_directories(tmp_path):
    seed_autosar_artifacts(tmp_path)

    expected = {
        "code/src/application/HeadlightSwc.c",
        "code/src/application/HeadlightSwc.h",
        "code/src/rte/Rte.c",
        "code/src/rte/Rte_HeadlightSwc.h",
        "code/src/bsw/services/EcuM.c",
        "code/src/bsw/ecu_abstraction/IoHwAb.c",
        "code/src/bsw/mcal/Adc.c",
        "code/src/bsw/mcal/Dio.c",
        "code/src/common/Std_Types.h",
        "tests/test_headlight_swc.c",
    }
    assert expected <= {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file()}


def test_seed_enforces_dependency_direction_and_composition_root(tmp_path):
    seed_autosar_artifacts(tmp_path)

    app = (tmp_path / "code/src/application/HeadlightSwc.c").read_text(encoding="utf-8")
    rte = (tmp_path / "code/src/rte/Rte.c").read_text(encoding="utf-8")
    main = (tmp_path / "code/src/main.c").read_text(encoding="utf-8")

    assert '#include "Rte_HeadlightSwc.h"' in app
    for forbidden in ('#include "IoHwAb.h"', '#include "Adc.h"', '#include "Dio.h"'):
        assert forbidden not in app
    assert '#include "IoHwAb.h"' in rte
    assert "Rte_Write_Headlight_Beam" not in main
    assert "EcuM_Init" in main
    assert "HeadlightSwc_Run" in main


def test_seed_never_overwrites_real_pipeline_output(tmp_path):
    seed_autosar_artifacts(tmp_path)
    app_path = tmp_path / "code/src/application/HeadlightSwc.c"
    app_path.write_text("// real pipeline output\n", encoding="utf-8")

    seed_autosar_artifacts(tmp_path)

    assert app_path.read_text(encoding="utf-8") == "// real pipeline output\n"


def test_codegen_prompt_requires_autosar_layout_for_c_only():
    default_prompt, _ = build_codegen_prompt("SPEC", "spec.md")
    c_prompt, _ = build_codegen_prompt("SPEC", "spec.md", target_language="C")
    python_prompt, _ = build_codegen_prompt("SPEC", "spec.md", target_language="Python")

    assert "AUTOSAR CLASSIC LAYERING HARD RULE" in default_prompt
    assert "AUTOSAR CLASSIC LAYERING HARD RULE" in c_prompt
    assert "src/application/" in c_prompt
    assert "src/bsw/ecu_abstraction/" in c_prompt
    assert "src/bsw/mcal/" in c_prompt
    assert "NEVER place all requirements in `main.c`" in c_prompt
    assert "AUTOSAR CLASSIC LAYERING HARD RULE" not in python_prompt


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_generated_autosar_code_compiles_and_tests_pass(tmp_path):
    seed_autosar_artifacts(tmp_path)
    include_dirs = [
        "code/src/common",
        "code/src/application",
        "code/src/rte",
        "code/src/bsw/services",
        "code/src/bsw/ecu_abstraction",
        "code/src/bsw/mcal",
    ]
    sources = [
        "code/src/application/HeadlightSwc.c",
        "code/src/rte/Rte.c",
        "code/src/bsw/services/EcuM.c",
        "code/src/bsw/ecu_abstraction/IoHwAb.c",
        "code/src/bsw/mcal/Adc.c",
        "code/src/bsw/mcal/Dio.c",
        "tests/test_headlight_swc.c",
    ]
    executable = tmp_path / "test_headlight_swc"
    compile_result = subprocess.run(
        [
            "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
            *[f"-I{tmp_path / d}" for d in include_dirs],
            *[str(tmp_path / s) for s in sources],
            "-o", str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    test_result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False,
    )
    assert test_result.returncode == 0, test_result.stderr
