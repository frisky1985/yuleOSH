# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Pipeline steps list endpoint — returns all defined pipeline steps."""

from . import json_ok


def handle_pipeline_steps(method: str, **kwargs):
    """GET /api/v1/pipeline/steps — return all pipeline step definitions."""
    from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

    steps = []
    for idx, (step_key, agent, name, _handler) in enumerate(PIPELINE_STEPS, start=1):
        steps.append({
            "index": idx,
            "key": step_key,
            "agent": agent,
            "name": name,
        })

    return json_ok({
        "steps": steps,
        "count": len(steps),
    })
