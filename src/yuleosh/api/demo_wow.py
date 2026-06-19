"""
yuleOSH "Wow Moment" — Pre-built Brake Light / Wiper Control Demo (D3).

New user experience:
1. Run ONE command:  ``yuleosh demo wow``
2. Generate a complete brake-light or wiper-control project spec
3. Run the full pipeline (mock LLM, no API key needed)
4. Download evidence pack ZIP with traceability, acceptance matrix, coverage
5. Total time: **≤5 minutes from zero to evidence pack**

Usage:
    yuleosh demo wow [--example brake-light|wiper-control] [--dir <path>]
                     [--build]
"""

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# ==================================================================
# Pre-built spec templates — zero-config, ready to run
# ==================================================================

BRAKE_LIGHT_SPEC = """# Brake Light Control Unit — Demo Spec

> Version: 1.0.0-demo
> Domain: Automotive Body Electronics (ISO 26262 ASIL A)
> Generated: {timestamp}

Automotive brake light control unit. The system monitors the brake pedal
position via a digital input pin and controls the brake light output via
a high-side driver. Includes diagnostic feedback and fault monitoring.

## 1. Requirements

### REQ-BRK-001: Brake Light Activation
- The system SHALL activate the brake light within **10 ms** of brake pedal press
- The system SHALL deactivate the brake light within **10 ms** of brake pedal release

#### Reason
Regulatory requirement (ECE R13 / FMVSS 108). Brake light latency directly
affects stopping distance warning to following vehicles.

### REQ-BRK-002: Brake Pedal Debounce
- The system SHALL debounce the brake pedal input for **20 ms** to prevent chatter

#### Reason
Mechanical switch bounce on brake pedal could cause flickering brake lights,
which is both distracting and potentially dangerous.

### REQ-BRK-003: Pilot Lamp Feedback
- The system SHALL illuminate a pilot lamp in the instrument cluster when brake
  light is active

#### Reason
Driver feedback mechanism required per ISO 26262-3 for safe operation
monitoring.

### REQ-BRK-004: Open Load Detection
- The system SHALL detect an open load condition on the brake light output
  within **100 ms**

#### Reason
Broken bulb detection per ISO 26262-11 §11.3.1. Open load must be detected
to alert driver of failure.

### REQ-BRK-005: Fault Reporting
- The system SHALL set a diagnostic trouble code (DTC) when open load is detected
- The system SHALL report faults via UART diagnostic interface

#### Reason
On-board diagnostics (OBD) compliance for fault tracking.

## 2. Scenarios

### Scenario: Normal brake light activation
- GIVEN Brake pedal is released
- WHEN Brake pedal is pressed
- THEN Brake light turns on within 10 ms
- AND Pilot lamp illuminates
- AND No DTC is set

### Scenario: Brake pedal debounce
- GIVEN Brake pedal is pressed with mechanical chatter
- WHEN Brake pedal signal bounces for < 20 ms
- THEN Brake light stays in current state

### Scenario: Open load fault
- GIVEN Brake light bulb is disconnected
- WHEN Brake pedal is pressed
- THEN DTC is set within 100 ms
- AND Fault is reported via UART

## 3. Architecture

```c
// ┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
// │ Brake Pedal │────→│ BrakeLightCtrl  │────→│ Brake Light  │
// │   (GPIO)    │     │  (State Machine)│     │  (PWM/GPIO)  │
// └─────────────┘     │                 │     └──────────────┘
//                      │  • Debounce     │     ┌──────────────┐
// ┌─────────────┐     │  • Fault Detect │────→│ Pilot Lamp   │
// │ Diagnostic  │←────│  • DTC Storage  │     │  (Cluster)   │
// │   (UART)    │     └─────────────────┘     └──────────────┘
// └─────────────┘
```
"""

WIPER_CONTROL_SPEC = """# Wiper Control Unit — Demo Spec

> Version: 1.0.0-demo
> Domain: Automotive Body Electronics (ISO 26262 ASIL B)
> Generated: {timestamp}

Intelligent wiper control unit with intermittent, continuous, and rain-sense
modes. Monitors wiper switch position and rain sensor input to control the
wiper motor PWM output.

## 1. Requirements

### REQ-WPR-001: Intermittent Mode
- The system SHALL wipe at configurable intervals (2, 5, 10 seconds) in intermittent mode
- The system SHALL cycle the wiper motor once per interval

#### Reason
Basic driver convenience. Intermittent wipe is standard on all passenger vehicles.

### REQ-WPR-002: Continuous Mode (Low/High)
- The system SHALL run wiper at low speed (40 RPM) when continuous-low is selected
- The system SHALL run wiper at high speed (60 RPM) when continuous-high is selected

#### Reason
Regulatory requirement for driver visibility. Two continuous speeds required
per FMVSS 104.

### REQ-WPR-003: Rain-sense Auto Mode
- The system SHALL activate wipers automatically when rain sensor detects moisture
- The system SHALL adjust wiper speed proportionally to rain intensity

#### Reason
Driver convenience feature. Reduces cognitive load in variable rain conditions.

### REQ-WPR-004: Park Position
- The system SHALL return wiper to park position within 500 ms of switch-off
- The system SHALL NOT stop mid-wipe when turned off

#### Reason
Safety requirement. Wiper blade must not obstruct driver view when parked.

### REQ-WPR-005: Fault Detection
- The system SHALL detect wiper motor stall condition within 200 ms
- The system SHALL report motor stall via diagnostic interface

#### Reason
Motor stall can indicate mechanical jam, electrical failure, or frozen blade.
Requires timely driver notification.

## 2. Scenarios

### Scenario: Intermittent wipe
- GIVEN Wiper switch is in intermittent position
- WHEN Interval is set to 5 seconds
- THEN Wiper cycles once every 5 seconds
- AND Wiper returns to park position after each cycle

### Scenario: Rain-sense auto activation
- GIVEN Wiper is in auto mode
- WHEN Rain sensor detects moisture level > threshold
- THEN Wipers activate at proportional speed
- WHEN Rain stops
- THEN Wipers stop after 2 additional cycles

### Scenario: Motor stall detection
- GIVEN Wiper is running continuously
- WHEN Wiper motor stalls due to ice buildup
- THEN Stall fault is detected within 200 ms
- AND Wiper power is cut to prevent motor damage

## 3. Architecture

```c
// ┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
// │ Wiper Switch│────→│  WiperCtrl       │────→│ Wiper Motor  │
// │  (GPIO/ADC) │     │  State Machine   │     │  (PWM Out)   │
// └─────────────┘     │                  │     └──────────────┘
//                      │  • Mode Select   │
// ┌─────────────┐     │  • Speed Control │
// │ Rain Sensor │────→│  • Stall Detect  │
// │   (I2C)     │     │  • Park Position │
// └─────────────┘     └──────────────────┘
```
"""

DEMO_SPECS = {
    "brake-light": {
        "title": "Brake Light Control Unit",
        "spec": BRAKE_LIGHT_SPEC,
        "description": "Automotive brake light control with debounce, diagnostics, and fault reporting",
    },
    "wiper-control": {
        "title": "Wiper Control Unit",
        "spec": WIPER_CONTROL_SPEC,
        "description": "Intelligent wiper control with intermittent, continuous, and rain-sense modes",
    },
}


# ==================================================================
# Demo project creator
# ==================================================================

def create_demo_project(example: str, work_dir: str) -> Path:
    """Create the demo project directory with spec, tests, and minimal src.

    Returns path to the project directory.
    """
    demo_cfg = DEMO_SPECS.get(example, DEMO_SPECS["brake-light"])
    work_path = Path(work_dir).resolve()
    project_dir = work_path / f"demo-{example}"

    # Clean/create
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create standard dirs
    for sub in [".osh", ".osh/evidence", ".osh/ci", ".osh/reports",
                ".yuleosh", "docs", "src", "include", "tests", "specs"]:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    # Write spec
    spec_content = demo_cfg["spec"].format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    spec_path = project_dir / "docs" / "spec.md"
    spec_path.write_text(spec_content)

    # Write minimal test file with Covers markers
    test_file = project_dir / "tests" / f"test_{example.replace('-', '_')}.py"
    _write_demo_test(test_file, example)

    # Write minimal source stubs
    src_file = project_dir / "src" / f"{example.replace('-', '_')}.c"
    src_file.write_text(_DEMO_SRC_TEMPLATE.format(example=example.replace('-', '_').title().replace('_', '')))

    hdr_file = project_dir / "include" / f"{example.replace('-', '_')}.h"
    hdr_file.write_text(_DEMO_HEADER_TEMPLATE.format(
        guard=f"DEMO_{example.replace('-', '_').upper()}_H",
        example=example.replace('-', '_').title().replace('_', ''),
    ))

    # Create minimal ci-config.yaml
    ci_config = project_dir / ".yuleosh" / "ci-config.yaml"
    ci_config.write_text(f"""# yuleOSH CI config — demo project
ci:
  layers: [1, 2, 3]

misra:
  enabled: true
  fail_on_required: true
  fail_on_violation: false
  fail_on_advisory: false
  fail_threshold: 10
  violations_per_kloc: 2.0
  cppcheck_std: "c11"
  active_profile: "safety"
  rule_texts_path: "misra-rules.yaml"

coverage:
  threshold_line: 85.0
  threshold_condition: 80.0
  strict: false
  c_fail_under: 70
""")

    print(f"  📁 Project created: {project_dir}")
    print(f"  📄 Spec: {spec_path}")
    print(f"  🧪 Tests: {test_file}")
    print(f"  💻 Source: {src_file}")
    print(f"  ⚙️  Config: {ci_config}")

    return project_dir


def _write_demo_test(test_path: Path, example: str):
    """Write demo test file with Covers markers for traceability."""
    if example == "brake-light":
        test_path.write_text(f'''"""
Demo tests for Brake Light Control Unit — covering all 5 requirements.
"""
import pytest
import time


class TestBrakeLightActivation:
    """Covers: REQ-BRK-001"""

    def test_activate_on_press(self):
        """Covers: Scenario: Normal brake light activation"""
        # GIVEN Brake pedal is released
        pedal = 0
        # WHEN Brake pedal is pressed
        pedal = 1
        # THEN Brake light turns on within 10 ms
        response_time = 5  # ms
        assert response_time <= 10
        assert pedal == 1

    def test_deactivate_on_release(self):
        """Covers: REQ-BRK-001"""
        pedal = 0
        response_time = 3  # ms
        assert response_time <= 10
        assert pedal == 0


class TestDebounce:
    """Covers: REQ-BRK-002"""

    def test_debounce_chatter(self):
        """Covers: Scenario: Brake pedal debounce"""
        # GIVEN Brake pedal is pressed with mechanical chatter
        pedal_samples = [1, 0, 1, 0, 1]
        stable_after_debounce = True
        assert stable_after_debounce is True


class TestPilotLamp:
    """Covers: REQ-BRK-003"""

    def test_pilot_illuminates(self):
        pilot = True
        assert pilot is True


class TestOpenLoad:
    """Covers: REQ-BRK-004"""

    def test_open_load_detection(self):
        """Covers: Scenario: Open load fault"""
        # GIVEN Brake light bulb is disconnected
        load_current = 0  # mA, 0 = open
        # WHEN Brake pedal is pressed
        open_load_detected = load_current < 10
        # THEN DTC is set
        assert open_load_detected is True


class TestFaultReporting:
    """Covers: REQ-BRK-005"""

    def test_dtc_set_on_fault(self):
        dtc_set = True
        assert dtc_set is True

    def test_uart_report(self):
        uart_reported = True
        assert uart_reported is True
''')
    else:
        test_path.write_text(f'''"""
Demo tests for Wiper Control Unit — covering all 5 requirements.
"""
import pytest


class TestIntermittentMode:
    """Covers: REQ-WPR-001"""

    def test_intermittent_2s(self):
        """Covers: Scenario: Intermittent wipe"""
        interval = 5  # seconds
        assert interval in (2, 5, 10)

    def test_single_cycle(self):
        cycle_count = 1
        assert cycle_count == 1


class TestContinuousMode:
    """Covers: REQ-WPR-002"""

    def test_low_speed(self):
        rpm = 40
        assert rpm == 40

    def test_high_speed(self):
        rpm = 60
        assert rpm == 60


class TestRainSense:
    """Covers: REQ-WPR-003"""

    def test_auto_activation(self):
        """Covers: Scenario: Rain-sense auto activation"""
        rain_detected = True
        speed_adjusted = True
        assert rain_detected is True
        assert speed_adjusted is True


class TestParkPosition:
    """Covers: REQ-WPR-004"""

    def test_park_on_off(self):
        park_time_ms = 300
        assert park_time_ms <= 500

    def test_no_mid_stop(self):
        mid_stop = False
        assert mid_stop is False


class TestFaultDetection:
    """Covers: REQ-WPR-005"""

    def test_stall_detection(self):
        """Covers: Scenario: Motor stall detection"""
        stall_detected_ms = 150
        assert stall_detected_ms <= 200

    def test_power_cut_on_stall(self):
        power_cut = True
        assert power_cut is True
''')


_DEMO_SRC_TEMPLATE = """/**
 * {example} — Demo implementation (stub).
 *
 * This is a placeholder source file for the yuleOSH demo pipeline.
 * Replace with actual implementation for real development.
 */

#include "{example.lower()}.h"

// Placeholder: state machine runs in main loop
void {example}_init(void) {{
    // Initialize GPIO, PWM, and diagnostic interface
}}

void {example}_run_cycle(void) {{
    // Read inputs, update state, drive outputs
}}
"""

_DEMO_HEADER_TEMPLATE = """#ifndef {guard}
#define {guard}

/**
 * {example} — Demo header.
 */
#include <stdint.h>
#include <stdbool.h>

void {example}_init(void);
void {example}_run_cycle(void);

#endif /* {guard} */
"""


# ==================================================================
# Demo pipeline runner (mock LLM, no API key needed)
# ==================================================================

def run_wow_demo(example: str, work_dir: str, do_build: bool = False) -> dict:
    """Run the full Wow Moment demo pipeline.

    Returns dict with status, paths, and timing info.
    """
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"  🔥 yuleOSH Demo — \"Wow Moment\"")
    print(f"  {DEMO_SPECS[example]['title']}")
    print(f"{'='*60}")
    print()

    # Step 0: Create project (≤30s)
    print("  Step 1/4: Creating demo project...")
    project_dir = create_demo_project(example, work_dir)
    print()

    # Step 1: Set up project (≤30s)
    print("  Step 2/4: Setting up project structure...")
    old_osh = os.environ.get("OSH_HOME", "")
    os.environ["OSH_HOME"] = str(project_dir)
    spec_path = project_dir / "docs" / "spec.md"
    print(f"  ✅ Project ready at: {project_dir}")
    print()

    # Step 2: Run mock pipeline (≤2min)
    print("  Step 3/4: Running pipeline (mock LLM mode)...")
    from yuleosh.api.demo_quick import run_demo_pipeline_steps, generate_demo_spec

    spec_content = DEMO_SPECS[example]["spec"].format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    spec_path.write_text(spec_content)

    old_key = os.environ.get("LLM_API_KEY", "")
    os.environ["LLM_API_KEY"] = "demo-mock-key"

    try:
        session = run_demo_pipeline_steps(str(spec_path), project_dir)
    finally:
        if old_key:
            os.environ["LLM_API_KEY"] = old_key
        else:
            os.environ.pop("LLM_API_KEY", None)
        if old_osh:
            os.environ["OSH_HOME"] = old_osh
        else:
            os.environ.pop("OSH_HOME", None)

    if session.status == "failed":
        print(f"  ❌ Pipeline failed: {session.errors}")
        return {
            "status": "failed",
            "project_dir": str(project_dir),
            "elapsed_seconds": round(time.time() - start_time, 1),
            "errors": session.errors,
        }
    print(f"  ✅ Pipeline complete ({len(session.steps)} steps)")
    print()

    # Step 3: Generate evidence pack (≤2min)
    print("  Step 4/4: Generating evidence pack...")
    os.environ["OSH_HOME"] = str(project_dir)
    from yuleosh.evidence.generator import EvidenceCollector
    from yuleosh.evidence.compliance import pack_compliance_zip

    ev_collector = EvidenceCollector(str(project_dir))
    ev_collector.requirements = [
        {"name": "Brake Light Activation", "req_id": "REQ-BRK-001",
         "shall_count": 2, "shall": [
             "activate the brake light within 10 ms of brake pedal press",
             "deactivate the brake light within 10 ms of brake pedal release",
         ], "reason": "Regulatory ECE R13"},
        {"name": "Brake Pedal Debounce", "req_id": "REQ-BRK-002",
         "shall_count": 1, "shall": [
             "debounce the brake pedal input for 20 ms",
         ], "reason": "Mechanical switch bounce prevention"},
        {"name": "Pilot Lamp Feedback", "req_id": "REQ-BRK-003",
         "shall_count": 1, "shall": [
             "illuminate pilot lamp when brake light is active",
         ], "reason": "Driver feedback per ISO 26262-3"},
        {"name": "Open Load Detection", "req_id": "REQ-BRK-004",
         "shall_count": 1, "shall": [
             "detect open load condition within 100 ms",
         ], "reason": "Broken bulb detection per ISO 26262-11"},
        {"name": "Fault Reporting", "req_id": "REQ-BRK-005",
         "shall_count": 2, "shall": [
             "set DTC when open load detected",
             "report faults via UART",
         ], "reason": "OBD compliance"},
    ] if example == "brake-light" else [
        {"name": "Intermittent Mode", "req_id": "REQ-WPR-001",
         "shall_count": 2, "shall": [
             "wipe at configurable intervals",
             "cycle motor once per interval",
         ], "reason": "Basic driver convenience"},
        {"name": "Continuous Mode", "req_id": "REQ-WPR-002",
         "shall_count": 2, "shall": [
             "run at low speed (40 RPM)",
             "run at high speed (60 RPM)",
         ], "reason": "Regulatory FMVSS 104"},
        {"name": "Rain-sense Auto Mode", "req_id": "REQ-WPR-003",
         "shall_count": 2, "shall": [
             "activate wipers when rain detected",
             "adjust speed proportionally",
         ], "reason": "Driver convenience"},
        {"name": "Park Position", "req_id": "REQ-WPR-004",
         "shall_count": 2, "shall": [
             "return to park within 500 ms",
             "not stop mid-wipe",
         ], "reason": "Safety requirement"},
        {"name": "Fault Detection", "req_id": "REQ-WPR-005",
         "shall_count": 2, "shall": [
             "detect motor stall within 200 ms",
             "report stall via diagnostic",
         ], "reason": "Motor protection"},
    ]

    for req in ev_collector.requirements:
        req["name"] = req.get("name", "")

    if example == "brake-light":
        scenario_dicts = [
            {"name": "Normal brake light activation",
             "given": ["Brake pedal is released"],
             "when": ["Brake pedal is pressed"],
             "then": ["Brake light turns on within 10 ms",
                      "Pilot lamp illuminates",
                      "No DTC is set"]},
            {"name": "Brake pedal debounce",
             "given": ["Brake pedal is pressed with chatter"],
             "when": ["Signal bounces for < 20 ms"],
             "then": ["Brake light stays in current state"]},
            {"name": "Open load fault",
             "given": ["Brake light bulb is disconnected"],
             "when": ["Brake pedal is pressed"],
             "then": ["DTC is set within 100 ms",
                      "Fault is reported via UART"]},
        ]
    else:
        scenario_dicts = [
            {"name": "Intermittent wipe",
             "given": ["Wiper in intermittent mode"],
             "when": ["Interval set to 5 seconds"],
             "then": ["Wiper cycles every 5 seconds",
                      "Wiper returns to park"]},
            {"name": "Rain-sense auto activation",
             "given": ["Wiper in auto mode"],
             "when": ["Rain detected"],
             "then": ["Wipers activate proportionally"]},
            {"name": "Motor stall detection",
             "given": ["Wiper running continuously"],
             "when": ["Motor stalls"],
             "then": ["Stall detected within 200 ms",
                      "Power cut to prevent damage"]},
        ]

    ev_collector.scenarios = [{
        "name": s["name"],
        "given": s.get("given", []),
        "when": s.get("when", []),
        "then": s.get("then", []),
    } for s in scenario_dicts]

    # Collect evidence
    ev_collector._collect_test_coverage()
    ev_collector.collect_reviews()
    ev_collector.collect_ci_results()
    ev_collector.collect_sil_reports()

    artifacts = []
    artifacts.append(ev_collector.generate_traceability_matrix())
    artifacts.append(ev_collector.generate_requirement_coverage())
    artifacts.append(ev_collector.generate_code_coverage_report())
    artifacts.append(ev_collector.generate_acceptance_matrix())
    artifacts.append(ev_collector.aggregate_review_logs())
    zip_path_str = pack_compliance_zip(ev_collector)
    artifacts.append(zip_path_str)
    print(f"  ✅ Evidence pack generated")
    print()

    # Summary
    elapsed = round(time.time() - start_time, 1)
    evidence_dir = project_dir / ".osh" / "evidence"
    zip_path = Path(zip_path_str)
    zip_size = zip_path.stat().st_size if zip_path.exists() else 0

    print(f"{'='*60}")
    print(f"  🎉 WOW MOMENT COMPLETE!")
    print(f"  ⏱️  Total time: {elapsed}s")
    print(f"  📂 Project: {project_dir}")
    print(f"  📦 Evidence ZIP: {zip_path_str} ({zip_size:,} bytes)")
    print(f"  📊 Artifacts: {len(artifacts)}")
    print(f"{'='*60}")
    print()

    return {
        "status": "completed",
        "project_dir": str(project_dir),
        "spec_path": str(spec_path),
        "evidence_dir": str(evidence_dir),
        "evidence_zip": zip_path_str,
        "zip_size_bytes": zip_size,
        "elapsed_seconds": elapsed,
        "artifacts": artifacts,
    }


def main(example: str = "brake-light", work_dir: str = ".", do_build: bool = False) -> dict:
    """CLI entry point for ``yuleosh demo wow``."""
    if example not in DEMO_SPECS:
        available = ", ".join(DEMO_SPECS.keys())
        print(f"❌ Unknown example '{example}'. Available: {available}")
        return {"status": "error", "message": f"Unknown example: {example}"}

    return run_wow_demo(example, work_dir, do_build=do_build)


if __name__ == "__main__":
    import sys
    example = sys.argv[1] if len(sys.argv) > 1 else "brake-light"
    main(example)
