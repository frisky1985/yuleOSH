# @tests src/yuleosh/desktop/autosar_seed.py
# @tests src/yuleosh/codegen/prompts.py

import shutil
import subprocess
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import yaml

from yuleosh.codegen.autosar import (
    DEFAULT_AUTOSAR_RULES,
    normalize_autosar_rules,
    validate_autosar_output,
)
from yuleosh.codegen.engine import CodegenEngine
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


def _write_required_layers(root):
    for directory in DEFAULT_AUTOSAR_RULES["required_dirs"]:
        path = root / directory / f"{directory.rsplit('/', 1)[-1]}.c"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"void {directory.rsplit('/', 1)[-1]}_run(void) {{}}\n", encoding="utf-8")


def test_pipeline_template_owns_the_rules_and_prompt_uses_them():
    template = (
        Path(__file__).parents[1]
        / "src/yuleosh/templates/autosar-classic/pipeline/config.yaml"
    )
    raw = yaml.safe_load(template.read_text(encoding="utf-8"))
    rules = normalize_autosar_rules(raw["codegen"]["autosar_classic"])

    prompt, _ = build_codegen_prompt("SPEC", "spec.md", autosar_rules=rules)

    assert rules["required_dirs"] == raw["codegen"]["autosar_classic"]["required_dirs"]
    assert "AUTOSAR CLASSIC LAYERING HARD RULE (pipeline-enforced)" in prompt
    assert "src/bsw/ecu_abstraction/" in prompt
    assert "Violations are returned for repair" in prompt


def test_autosar_validator_rejects_cross_layer_mcal_include(tmp_path):
    _write_required_layers(tmp_path)
    header = tmp_path / "src/bsw/mcal/Dio.h"
    header.write_text("#ifndef DIO_H\n#define DIO_H\n#endif\n", encoding="utf-8")
    app = tmp_path / "src/application/application.c"
    app.write_text('#include "Dio.h"\nvoid application_run(void) {}\n', encoding="utf-8")

    errors = validate_autosar_output(tmp_path, DEFAULT_AUTOSAR_RULES)

    assert "illegally includes" in errors
    assert "src/application/application.c" in errors
    assert "src/bsw/mcal" in errors


def test_flat_model_output_is_returned_for_regeneration_until_compliant(tmp_path):
    compliant_files = [
        {
            "path": f"{directory}/{directory.rsplit('/', 1)[-1]}.c",
            "content": f"void generated_{idx}(void) {{}}\n",
            "requirements": [],
        }
        for idx, directory in enumerate(DEFAULT_AUTOSAR_RULES["required_dirs"])
    ]
    calls = []

    def fake_llm(system, user, **kwargs):
        calls.append(user)
        files = (
            [{"path": "src/main.c", "content": "int main(void) { return 0; }\n", "requirements": []}]
            if len(calls) == 1 else compliant_files
        )
        return {"content": json.dumps({"files": files})}

    session = SimpleNamespace(
        name="autosar-test", project_dir=str(tmp_path),
        spec_path=str(tmp_path / "requirements.md"), llm_client=fake_llm,
    )
    engine = CodegenEngine(
        output_dir=tmp_path / "out",
        max_retries=1,
        llm_client=fake_llm,
        verifier=lambda *args, **kwargs: {"ok": True, "errors": "", "command": "fake"},
        autosar_rules=DEFAULT_AUTOSAR_RULES,
    )
    result = engine.generate(session, "system", "generate", language_hint="c")

    assert result.status == "verified"
    assert result.rounds == 2
    assert len(calls) == 2
    assert "AUTOSAR: missing required layer" in calls[1]
    assert (tmp_path / "out/src/application/application.c").exists()
    assert (tmp_path / "out/src/bsw/mcal/mcal.c").exists()


def test_desktop_stage_calls_yuleosh_model_and_deploys_only_verified_layers(tmp_path):
    from yuleosh.api.desktop import _ensure_artifact_baseline
    from yuleosh.pipeline.async_runner import _stage_code_generation

    project = tmp_path / "project"
    project.mkdir()
    _ensure_artifact_baseline(
        project, {"project_id": "p1", "project_name": "Model Demo"}, seed_code=False,
    )
    assert not (project / "code/src").exists()
    assert (project / "pipeline/config.yaml").exists()

    files = [
        {
            "path": f"{directory}/Generated{idx}.c",
            "content": f"void generated_{idx}(void) {{}}\n",
            "requirements": [],
        }
        for idx, directory in enumerate(DEFAULT_AUTOSAR_RULES["required_dirs"])
    ]
    calls = []

    def fake_yuleosh(system, user, **kwargs):
        calls.append(system)
        return {"content": json.dumps({"files": files})}

    with mock.patch("yuleosh.pipeline.run.chat_completion", side_effect=fake_yuleosh):
        report = _stage_code_generation(str(project), "job-llm", {})

    assert Path(report).exists()
    assert len(calls) == 1
    assert "AUTOSAR CLASSIC LAYERING HARD RULE (pipeline-enforced)" in calls[0]
    assert "src/bsw/ecu_abstraction/" in calls[0]
    for idx, directory in enumerate(DEFAULT_AUTOSAR_RULES["required_dirs"]):
        deployed = project / "code" / directory / f"Generated{idx}.c"
        assert deployed.read_text(encoding="utf-8") == f"void generated_{idx}(void) {{}}\n"


def test_desktop_stage_rejects_flat_model_output_without_seed_fallback(tmp_path):
    from yuleosh.api.desktop import _ensure_artifact_baseline
    from yuleosh.pipeline.async_runner import _stage_code_generation
    from yuleosh.pipeline.session import PipelineStepError

    project = tmp_path / "project"
    project.mkdir()
    _ensure_artifact_baseline(
        project, {"project_id": "p1", "project_name": "Model Demo"}, seed_code=False,
    )
    pipeline_path = project / "pipeline/config.yaml"
    pipeline_raw = yaml.safe_load(pipeline_path.read_text(encoding="utf-8"))
    pipeline_raw["codegen"]["max_retries"] = 0
    pipeline_path.write_text(yaml.safe_dump(pipeline_raw, allow_unicode=True), encoding="utf-8")

    flat_output = {
        "files": [{
            "path": "src/main.c", "content": "int main(void) { return 0; }\n",
            "requirements": [],
        }],
    }
    with mock.patch(
        "yuleosh.pipeline.run.chat_completion",
        return_value={"content": json.dumps(flat_output)},
    ):
        with pytest.raises(PipelineStepError, match="pipeline rules"):
            _stage_code_generation(str(project), "job-flat", {})

    assert not (project / "code/src").exists()
