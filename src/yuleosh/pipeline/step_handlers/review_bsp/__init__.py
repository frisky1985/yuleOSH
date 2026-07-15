"""
review_bsp — BSP 板级支持包验证 (package split from review_bsp.py).

Maintains backward compatibility by re-exporting everything from core.py.
"""

from yuleosh.pipeline.step_handlers.review_bsp.core import (
    # Types
    BspFinding,
    # File discovery
    _find_bsp_files,
    # Pin mux checks
    _check_pin_mux_gpio,
    _check_pin_mux_conflicts,
    # Clock checks
    _check_clock_hse,
    _check_clock_pll,
    _check_system_clock_frequency,
    # Memory checks
    _check_alloca_usage,
    _check_vla_usage,
    _check_dynamic_allocation,
    _check_runtime_allocation_integrity,
    # Peripheral checks
    _check_peripheral_init_order,
    _check_peripheral_conflict,
    _check_hal_api_consistency,
    _check_dma_config,
    # Review entry points
    _static_bsp_review,
    _build_bsp_review_prompt,
    step_review_bsp,
)
