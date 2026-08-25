#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Golden sample registry for template regression testing.

Each template may ship a 'golden/' subdirectory with canonical reference files.
This module validates that a freshly-instantiated template matches the golden
structurally (same file tree + same critical file content).

Usage:
    golden = load_golden(Path("src/yuleosh/templates/generic-embedded-c"))
    result = compare_to_golden(generated_dir, golden)
    # result["status"] in ("pass", "warn", "fail")
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GoldenSample:
    template_name: str
    golden_dir: Path
    critical_files: list[str] = field(default_factory=list)
    structure_files: list[str] = field(default_factory=list)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_golden(template_dir: Path) -> Optional[GoldenSample]:
    """Load golden sample metadata from *template_dir*.

    Returns None if no golden/ subdir exists.
    """
    golden_dir = template_dir / "golden"
    if not golden_dir.is_dir():
        return None

    manifest_path = golden_dir / "golden_manifest.json"
    critical: list[str] = []
    structure: list[str] = []

    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        critical = data.get("critical_files", [])
        structure = data.get("structure_files", [])
    else:
        for p in sorted(golden_dir.rglob("*")):
            if p.is_file() and p.name != "golden_manifest.json":
                critical.append(str(p.relative_to(golden_dir)))

    return GoldenSample(
        template_name=template_dir.name,
        golden_dir=golden_dir,
        critical_files=critical,
        structure_files=structure,
    )


def compare_to_golden(generated_dir: Path, golden: GoldenSample) -> dict:
    """Compare *generated_dir* against the golden sample.

    Returns:
        {
            status: "pass" | "warn" | "fail",
            diffs: [{file, type: "missing"|"extra"|"content_changed", detail}],
            critical_failures: int,
            warn_count: int,
        }
    """
    diffs: list[dict] = []
    critical_failures = 0

    all_expected = set(golden.critical_files) | set(golden.structure_files)

    for rel in golden.critical_files:
        golden_file = golden.golden_dir / rel
        gen_file = generated_dir / rel
        if not gen_file.exists():
            diffs.append({"file": rel, "type": "missing", "detail": "absent in generated output"})
            critical_failures += 1
        elif golden_file.exists() and gen_file.read_bytes() != golden_file.read_bytes():
            diffs.append({
                "file": rel,
                "type": "content_changed",
                "detail": (
                    f"sha256 mismatch: golden={_sha256_file(golden_file)[:8]} "
                    f"gen={_sha256_file(gen_file)[:8]}"
                ),
            })
            critical_failures += 1

    for rel in golden.structure_files:
        gen_file = generated_dir / rel
        if not gen_file.exists():
            diffs.append({"file": rel, "type": "missing", "detail": "structure file absent"})
            critical_failures += 1

    warn_count = 0
    if generated_dir.is_dir():
        for p in sorted(generated_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(generated_dir))
            if rel not in all_expected:
                diffs.append({"file": rel, "type": "extra", "detail": "not in golden"})
                warn_count += 1

    if critical_failures > 0:
        status = "fail"
    elif warn_count > 0:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "diffs": diffs,
        "critical_failures": critical_failures,
        "warn_count": warn_count,
    }


def generate_golden(template_dir: Path, output_dir: Path) -> None:
    """Capture *output_dir* as the new golden sample for *template_dir*.

    Copies output_dir → template_dir/golden/ and writes golden_manifest.json.
    """
    golden_dir = template_dir / "golden"
    if golden_dir.exists():
        shutil.rmtree(golden_dir)
    shutil.copytree(output_dir, golden_dir)

    manifest: dict = {"critical_files": [], "structure_files": [], "file_hashes": {}}
    for p in sorted(golden_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(golden_dir))
        if rel == "golden_manifest.json":
            continue
        manifest["critical_files"].append(rel)
        manifest["file_hashes"][rel] = _sha256_file(p)

    (golden_dir / "golden_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
