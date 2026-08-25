#!/usr/bin/env python3

# @req RS-002  @req SWR-002.1
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Requirement pattern library + conflict pre-checker for OpenSpec documents.

Provides:
  - REQUIREMENT_PATTERNS: common embedded requirement templates
  - detect_pattern(): keyword-based pattern matching
  - check_conflicts(): duplicate SHALLs, timing contradictions, ASIL mix, signal ownership
  - suggest_missing_patterns(): finds requirements missing key SHALL statements
  - validate_spec_with_patterns(): integrated validation with conflicts + suggestions
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .validate import SpecDocument, SpecRequirement

# ── Pattern library ───────────────────────────────────────────────────────────

REQUIREMENT_PATTERNS: dict[str, dict] = {
    "sensor_read": {
        "title": "Sensor Read",
        "keywords": ["sensor", "adc", "temperature", "pressure", "read", "sample"],
        "shall_templates": [
            "read sensor data at a configurable sampling rate",
            "validate sensor data range before use",
            "report sensor fault when reading is out of range",
        ],
        "scenario_template": {
            "given": "the sensor is powered and initialised",
            "when": "the sampling period elapses",
            "then": "a valid reading is stored and a fault flag is set on range violation",
        },
    },
    "watchdog": {
        "title": "Watchdog",
        "keywords": ["watchdog", "wdt", "wdg", "kick", "feed", "timeout reset"],
        "shall_templates": [
            "initialise the watchdog timer at startup",
            "refresh the watchdog within the configured timeout period",
            "trigger a system reset if the watchdog is not refreshed in time",
        ],
        "scenario_template": {
            "given": "the system is running normally",
            "when": "the watchdog refresh period expires without a kick",
            "then": "the MCU performs a hardware reset",
        },
    },
    "can_comm": {
        "title": "CAN Communication",
        "keywords": ["can", "canbus", "j1939", "uds", "pdu", "frame", "transmit", "receive"],
        "shall_templates": [
            "initialise the CAN controller with the configured baud rate",
            "transmit periodic CAN frames within the specified cycle time",
            "handle CAN bus-off state by attempting recovery",
        ],
        "scenario_template": {
            "given": "the CAN bus is active and baud rate is configured",
            "when": "a PDU transmission is triggered",
            "then": "the frame is sent within the cycle time and an error is reported on failure",
        },
    },
    "gpio_output": {
        "title": "GPIO Output Control",
        "keywords": ["gpio", "pin", "output", "led", "relay", "actuator", "toggle"],
        "shall_templates": [
            "configure the GPIO pin as output at initialisation",
            "set or clear the GPIO pin state based on the control signal",
            "read back the pin state to detect short-circuit faults",
        ],
        "scenario_template": {
            "given": "the GPIO pin is configured as output",
            "when": "the control command changes state",
            "then": "the pin state is updated within one scheduler tick",
        },
    },
    "uart_tx": {
        "title": "UART Transmit",
        "keywords": ["uart", "usart", "serial", "transmit", "baud", "send"],
        "shall_templates": [
            "configure the UART peripheral with the specified baud rate and frame format",
            "transmit data bytes using interrupt or DMA mode",
            "report a transmit-buffer-full error when the queue is saturated",
        ],
        "scenario_template": {
            "given": "the UART peripheral is initialised",
            "when": "a transmit request is made",
            "then": "data is queued and sent within the specified latency",
        },
    },
    "power_mode": {
        "title": "Power Mode Management",
        "keywords": ["power", "sleep", "standby", "wake", "lpm", "low power", "shutdown"],
        "shall_templates": [
            "transition to low-power mode when the idle condition is met",
            "restore full operation on a configured wake-up event",
            "ensure critical peripherals are de-initialised before sleep",
        ],
        "scenario_template": {
            "given": "the system has been idle for the configured duration",
            "when": "no active task prevents sleep",
            "then": "the MCU enters low-power mode and wakes on the next event",
        },
    },
    "error_handler": {
        "title": "Error Handler",
        "keywords": ["error", "fault", "exception", "handler", "hardfault", "assert"],
        "shall_templates": [
            "capture the fault context on a hard fault",
            "log the error to non-volatile memory before reset",
            "trigger a safe-state transition on unrecoverable errors",
        ],
        "scenario_template": {
            "given": "the system encounters an unhandled exception",
            "when": "the fault handler is entered",
            "then": "the fault is logged and the system transitions to safe state",
        },
    },
}


def detect_pattern(req: "SpecRequirement") -> str | None:
    """Return the best matching pattern key for *req*, or None."""
    text = " ".join([req.name] + req.shall + req.should + req.may).lower()
    best: tuple[int, str] | None = None
    for key, cfg in REQUIREMENT_PATTERNS.items():
        hits = sum(1 for kw in cfg["keywords"] if kw in text)
        if hits and (best is None or hits > best[0]):
            best = (hits, key)
    return best[1] if best else None


# ── Conflict detection ────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"([<>]=?)\s*(\d+(?:\.\d+)?)\s*(ms|us|µs|s)\b", re.IGNORECASE)
_ASIL_RE = re.compile(r"\bASIL[_\-]?([A-D])\b", re.IGNORECASE)
_SIGNAL_RE = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b")


def _norm_time_ms(value: float, unit: str) -> float:
    u = unit.lower()
    if u in ("us", "µs"):
        return value / 1000.0
    if u == "s":
        return value * 1000.0
    return value


def check_conflicts(doc: "SpecDocument") -> list[dict]:
    """Detect conflicts in *doc*.

    Returns list of conflict dicts: {type, severity, req_ids, message}
    """
    conflicts: list[dict] = []

    # ── 1. Duplicate SHALL ────────────────────────────────────────────────
    shall_index: dict[str, list[str]] = defaultdict(list)
    for req in doc.requirements:
        rid = req.req_id or req.name
        for s in req.shall:
            normalized = re.sub(r"\s+", " ", s.strip().lower())
            shall_index[normalized].append(rid)
    for text, owners in shall_index.items():
        if len(owners) > 1:
            conflicts.append({
                "type": "duplicate_shall",
                "severity": "WARN",
                "req_ids": owners,
                "message": f"Duplicate SHALL across {owners}: \"{text[:80]}\"",
            })

    # ── 2. Timing contradictions ─────────────────────────────────────────
    keyword_times: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for req in doc.requirements:
        rid = req.req_id or req.name
        all_text = " ".join(req.shall + req.should + req.may)
        for m in _TIME_RE.finditer(all_text):
            op, val, unit = m.group(1), float(m.group(2)), m.group(3)
            ms = _norm_time_ms(val, unit)
            ctx_start = max(0, m.start() - 20)
            ctx = re.sub(r"\s+", "_", all_text[ctx_start:m.start()].strip().lower()[-15:])
            keyword_times[ctx].append((rid, op, ms))

    for ctx, entries in keyword_times.items():
        upper_bounds = [(rid, v) for rid, op, v in entries if op in ("<", "<=")]
        lower_bounds = [(rid, v) for rid, op, v in entries if op in (">", ">=")]
        for uid, uval in upper_bounds:
            for lid, lval in lower_bounds:
                if uid != lid and lval >= uval:
                    conflicts.append({
                        "type": "timing_conflict",
                        "severity": "ERROR",
                        "req_ids": [uid, lid],
                        "message": (
                            f"Timing contradiction: {uid} requires <{uval}ms "
                            f"but {lid} requires >{lval}ms (context: '{ctx}')"
                        ),
                    })

    # ── 3. ASIL contradiction ─────────────────────────────────────────────
    asil_by_req: dict[str, set[str]] = defaultdict(set)
    for req in doc.requirements:
        rid = req.req_id or req.name
        all_text = " ".join([req.name] + req.shall)
        for m in _ASIL_RE.finditer(all_text):
            asil_by_req[rid].add(m.group(1).upper())
    for rid, levels in asil_by_req.items():
        if len(levels) > 1:
            conflicts.append({
                "type": "asil_contradiction",
                "severity": "ERROR",
                "req_ids": [rid],
                "message": f"{rid} mentions conflicting ASIL levels: {sorted(levels)}",
            })

    # ── 4. Signal ownership ───────────────────────────────────────────────
    outputs: dict[str, str] = {}
    inputs: dict[str, list[str]] = defaultdict(list)
    for req in doc.requirements:
        rid = req.req_id or req.name
        for s in req.shall:
            sl = s.lower()
            for m in _SIGNAL_RE.finditer(s):
                sig = m.group(1)
                if any(kw in sl for kw in ("output", "set", "write", "send", "transmit", "produce")):
                    if sig not in outputs:
                        outputs[sig] = rid
                if any(kw in sl for kw in ("input", "read", "receive", "consume", "monitor")):
                    inputs[sig].append(rid)
    for sig, producer in outputs.items():
        for consumer in inputs.get(sig, []):
            if consumer != producer and producer not in consumer:
                conflicts.append({
                    "type": "signal_missing_dependency",
                    "severity": "WARN",
                    "req_ids": [producer, consumer],
                    "message": (
                        f"Signal '{sig}' produced by {producer} consumed by "
                        f"{consumer} — no explicit dependency declared"
                    ),
                })

    return conflicts


# ── Suggestion engine ─────────────────────────────────────────────────────────


def suggest_missing_patterns(doc: "SpecDocument") -> list[dict]:
    """Return suggestions for requirements that match a pattern but are missing key SHALLs."""
    suggestions: list[dict] = []
    for req in doc.requirements:
        pattern_key = detect_pattern(req)
        if not pattern_key:
            continue
        template = REQUIREMENT_PATTERNS[pattern_key]
        existing = " ".join(req.shall).lower()
        missing = []
        for tmpl_shall in template["shall_templates"]:
            key_words = [w for w in tmpl_shall.split() if len(w) > 3][:4]
            # Require a strict majority of the template's keywords to be
            # present before considering it covered — a single shared word
            # (e.g. "sensor") must not mask missing SHALL obligations.
            matched = sum(1 for kw in key_words if kw.lower() in existing)
            if matched <= len(key_words) // 2:
                missing.append(tmpl_shall)
        if missing:
            suggestions.append({
                "req_id": req.req_id or req.name,
                "pattern": pattern_key,
                "missing_shalls": missing,
            })
    return suggestions


# ── Integrated validation ─────────────────────────────────────────────────────


def validate_spec_with_patterns(doc: "SpecDocument") -> dict:
    """Full validation: issues + conflict checks + pattern suggestions.

    Returns:
        {issues, conflicts, suggestions, issue_count, conflict_count, suggestion_count}
    """
    from .validate import validate_spec

    issues = validate_spec(doc)
    conflicts = check_conflicts(doc)
    suggestions = suggest_missing_patterns(doc)

    for c in conflicts:
        issues.append({
            "severity": c["severity"],
            "type": c["type"],
            "item": c["req_ids"][0] if c["req_ids"] else "unknown",
            "req_id": c["req_ids"][0] if c["req_ids"] else "",
            "message": c["message"],
        })

    return {
        "issues": issues,
        "conflicts": conflicts,
        "suggestions": suggestions,
        "issue_count": len(issues),
        "conflict_count": len(conflicts),
        "suggestion_count": len(suggestions),
    }
