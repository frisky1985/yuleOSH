"""Coverage-support guard for yuleOSH embedded CMake templates.

The coverage gate configures generated projects with ``-DENABLE_COVERAGE=ON``
(c_coverage_gate.py / execution.py). Every embedded template's CMakeLists.txt
must respond to that flag (``--coverage`` instrumentation), otherwise no
.gcno/.gcda files are produced and lcov fails with "produced no output".
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_GLOB = "src/yuleosh/templates/*/src/CMakeLists.txt"
# generic-python is a non-embedded (host Python) template, not part of the
# embedded C toolchain set covered by the coverage gate.
NON_EMBEDDED = ("generic-python",)


def _embedded_template_cmakelists() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.glob(TEMPLATES_GLOB)
        if not any(part in NON_EMBEDDED for part in p.parts)
    )


def test_all_embedded_templates_have_coverage_support() -> None:
    cmakelists = _embedded_template_cmakelists()
    assert len(cmakelists) == 10, (
        "expected exactly 10 embedded template CMakeLists.txt files, "
        f"found {len(cmakelists)}: {[str(p) for p in cmakelists]}"
    )
    for path in cmakelists:
        content = path.read_text(encoding="utf-8")
        assert "ENABLE_COVERAGE" in content, (
            f"{path}: missing ENABLE_COVERAGE support block "
            "(coverage gate -DENABLE_COVERAGE=ON would be ignored)"
        )
        assert "--coverage" in content, (
            f"{path}: ENABLE_COVERAGE block present but no --coverage flag "
            "(no .gcno/.gcda would be produced → lcov produced no output)"
        )


def test_generic_embedded_c_configure_with_coverage(tmp_path: Path) -> None:
    if shutil.which("cmake") is None:
        pytest.skip("cmake not available on this host")

    template_dir = REPO_ROOT / "src/yuleosh/templates/generic-embedded-c"
    shutil.copytree(template_dir, tmp_path, dirs_exist_ok=True)
    # Codegen materializes the template's src/ files as the project root
    # (see artifacts/generated-code/*: CMakeLists.txt at root, sources under
    # src/ — same layout as wiper-control / window-anti-pinch). Hoist the
    # CMakeLists.txt accordingly so the template's `src/main.c` references
    # resolve.
    (tmp_path / "src" / "CMakeLists.txt").rename(tmp_path / "CMakeLists.txt")

    result = subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(tmp_path / "build"),
         "-DENABLE_COVERAGE=ON"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        "cmake configure with -DENABLE_COVERAGE=ON failed "
        f"(rc={result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    flags_make = tmp_path / "build" / "CMakeFiles" / "app.elf.dir" / "flags.make"
    assert flags_make.is_file(), f"expected flags.make at {flags_make}"
    content = flags_make.read_text(encoding="utf-8")
    assert "--coverage" in content, (
        f"{flags_make}: --coverage missing from C_FLAGS after "
        "-DENABLE_COVERAGE=ON configure"
    )
    assert "-O0" in content, (
        f"{flags_make}: -O0 missing from C_FLAGS after "
        "-DENABLE_COVERAGE=ON configure"
    )


def test_methodology_template_keeps_coverage_block_after_render() -> None:
    """Jinja placeholders must not swallow the coverage block on render."""
    template_path = (
        REPO_ROOT / "src/yuleosh/templates/methodology/src/CMakeLists.txt"
    )
    rendered = template_path.read_text(encoding="utf-8").replace(
        "{{PROJECT_NAME}}", "demo"
    )
    assert "{{PROJECT_NAME}}" not in rendered, "expected placeholders substituted"
    assert "ENABLE_COVERAGE" in rendered, (
        f"{template_path}: coverage block lost during Jinja-style render"
    )
    assert "--coverage" in rendered
