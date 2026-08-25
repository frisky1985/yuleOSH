#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Layered codegen strategy — HAL → BSP → App three-phase generation.

Instead of asking the LLM to generate the full project in one shot (which causes
cross-layer inconsistency), this module orchestrates three sequential
CodegenEngine runs. The output of each lower layer becomes the seed for the
next, so App always sees the real HAL/BSP API surface.

Layers (in order):
  1. hal  — Hardware Abstraction Layer: register maps, peripheral init, typed API headers
  2. bsp  — Board Support Package: clock init, pinmux, board-level startup
  3. app  — Application logic: state machines, business logic, main loop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class LayerConfig:
    name: str
    file_globs: list[str]
    system_prompt_fragment: str
    structural_features: dict[str, list[str]] = field(default_factory=dict)
    forbidden_features: dict[str, list[str]] = field(default_factory=dict)


LAYER_CONFIGS: dict[str, LayerConfig] = {
    "hal": LayerConfig(
        name="hal",
        file_globs=["src/hal/**", "include/hal/**", "hal/**"],
        system_prompt_fragment=(
            "## Layer Constraint: HAL (Hardware Abstraction Layer)\n"
            "You are generating ONLY the Hardware Abstraction Layer.\n"
            "- Output typed API headers under src/hal/ or include/hal/\n"
            "- Define register maps, peripheral init functions, and typed HAL APIs\n"
            "- HAL functions MUST be pure C with no business logic\n"
            "- Every HAL function SHALL have a corresponding declaration in a header\n"
            "- DO NOT output BSP or application code\n"
        ),
        structural_features={
            "src/hal/**/*.h": ["void", "typedef"],
        },
        forbidden_features={
            "src/hal/**/*.c": ["int64_t", "double", "printf(", "malloc("],
        },
    ),
    "bsp": LayerConfig(
        name="bsp",
        file_globs=["src/bsp/**", "include/bsp/**", "bsp/**"],
        system_prompt_fragment=(
            "## Layer Constraint: BSP (Board Support Package)\n"
            "You are generating ONLY the Board Support Package.\n"
            "- Output clock init, pinmux, board-level startup under src/bsp/\n"
            "- BSP code MAY call HAL functions (already present in seed)\n"
            "- DO NOT duplicate HAL-layer register definitions\n"
            "- DO NOT output application business logic\n"
            "- Board init function SHALL be named BSP_Init() or board_init()\n"
        ),
        structural_features={
            "src/bsp/**/*.c": ["init(", "clock"],
        },
        forbidden_features={
            "src/bsp/**/*.c": ["int64_t", "malloc("],
        },
    ),
    "app": LayerConfig(
        name="app",
        file_globs=["src/app/**", "src/main.c", "app/**"],
        system_prompt_fragment=(
            "## Layer Constraint: Application Layer\n"
            "You are generating ONLY the Application Layer.\n"
            "- Implement state machines, business logic, and main loop\n"
            "- Call HAL and BSP functions (already present in seed)\n"
            "- DO NOT re-implement HAL or BSP functions\n"
            "- Application entry point SHALL call board_init() or BSP_Init() first\n"
        ),
        structural_features={
            "src/main.c": ["main("],
        },
        forbidden_features={
            "src/app/**/*.c": ["int64_t"],
        },
    ),
}


class LayeredCodegenEngine:
    """Orchestrates HAL → BSP → App three-phase codegen.

    Each phase runs a fresh CodegenEngine with the previous phase's output
    as the seed directory, preventing the LLM from re-generating lower layers.
    """

    def __init__(
        self,
        layers: list[str] | None = None,
        base_engine_kwargs: dict | None = None,
    ) -> None:
        self.layers = layers if layers is not None else ["hal", "bsp", "app"]
        self.base_engine_kwargs = base_engine_kwargs or {}

    def generate_layered(
        self,
        session: Any,
        base_system_prompt: str,
        base_user_prompt: str,
        language_hint: str = "c",
        **kw: Any,
    ) -> dict:
        """Run all configured layers sequentially.

        Returns:
            {
                layers: {hal: result_dict, ...},
                overall_status: "verified" | "partial" | "failed",
                summary: str,
            }
        """
        from yuleosh.codegen.engine import CodegenEngine, default_output_dir

        layer_results: dict[str, dict] = {}
        prev_output_dir: Optional[Path] = None
        hal_failed = False

        for layer_name in self.layers:
            cfg = LAYER_CONFIGS.get(layer_name)
            if cfg is None:
                continue

            layer_output_dir = (
                default_output_dir(session.project_dir, session.name) / layer_name
            )
            layer_output_dir.mkdir(parents=True, exist_ok=True)

            engine_kwargs = dict(self.base_engine_kwargs)
            engine_kwargs["output_dir"] = layer_output_dir
            engine_kwargs.setdefault("max_retries", 3)

            # Merge layer structural/forbidden features on top of base
            base_sf = dict(engine_kwargs.pop("structural_features", {}) or {})
            base_ff = dict(engine_kwargs.pop("forbidden_features", {}) or {})
            base_sf.update(cfg.structural_features)
            base_ff.update(cfg.forbidden_features)
            engine_kwargs["structural_features"] = base_sf
            engine_kwargs["forbidden_features"] = base_ff

            if prev_output_dir is not None:
                engine_kwargs["seed_dir"] = prev_output_dir

            engine = CodegenEngine(**engine_kwargs)

            system_prompt = cfg.system_prompt_fragment + "\n\n" + base_system_prompt
            user_prompt = (
                base_user_prompt
                + f"\n\nSCOPE: Output ONLY files matching {cfg.file_globs}. "
                "Do NOT output files for other layers."
            )

            result = engine.generate(
                session,
                system_prompt,
                user_prompt,
                language_hint=language_hint,
                **kw,
            )
            layer_results[layer_name] = result.to_dict()

            if layer_name == "hal" and result.status not in ("verified", "generated"):
                hal_failed = True
                break

            if result.status in ("verified", "generated"):
                prev_output_dir = layer_output_dir

        statuses = [r.get("status") for r in layer_results.values()]
        if hal_failed or "failed" in statuses:
            overall = "failed"
        elif all(s == "verified" for s in statuses):
            overall = "verified"
        else:
            overall = "partial"

        summary_parts = [
            f"{name}: {layer_results[name].get('status', 'skipped')}"
            for name in self.layers
            if name in layer_results
        ]
        return {
            "layers": layer_results,
            "overall_status": overall,
            "summary": " | ".join(summary_parts),
        }
