#!/usr/bin/env python3
"""Generate yuleDKCS/misra-rules.yaml from yuleOSH rule library + cppcheck baseline.

Extracts only the MISRA rules actually used by yuleDKCS's cppcheck baseline
(embedded/.cppcheck), maps c2012 IDs -> c2023 IDs, and writes a compact
project-scoped rules file for the yuleOSH toolchain.
"""
import re
import sys
from pathlib import Path

RULE_LIB = Path("/Users/stefan/workspace/tasks/yuleOSH-check/misra-rules.yaml")
BASELINE = Path("/Users/stefan/.openclaw/workspace/yuleDKCS/embedded/.cppcheck")
OUT = Path("/Users/stefan/.openclaw/workspace/yuleDKCS/misra-rules.yaml")

import yaml

# 1. Load rule library
lib = yaml.safe_load(RULE_LIB.read_text(encoding="utf-8"))
print(f"Rule library: {len(lib) - 1} rules + meta")

# 2. Extract used c2012 rule numbers from baseline
used = set()
for line in BASELINE.read_text(encoding="utf-8").splitlines():
    m = re.match(r"^misra-c2012-(\d+)\.(\d+)", line.strip())
    if m:
        used.add((int(m.group(1)), int(m.group(2))))
print(f"Baseline uses {len(used)} distinct MISRA rules")

# 3. Map to c2023 IDs in library
missing = []
selected = {}
for num, sub in sorted(used):
    rid = f"misra-c2023-{num}.{sub}"
    if rid in lib:
        selected[rid] = lib[rid]
    else:
        # try c2012_ref fallback: find rule with same number
        fallback = [k for k in lib if k.startswith(f"misra-c2023-{num}.")]
        missing.append((rid, len(fallback) and fallback[0] or None))

if missing:
    print("WARN rules not found in library:")
    for rid, fb in missing:
        print(f"  {rid} -> fallback candidates: {fb}")

# 4. Write output with meta block
meta = dict(lib.get("meta", {}))
meta["description"] = (
    "yuleDKCS project-scoped MISRA C:2023 rules (subset of yuleOSH rule library "
    "used by embedded cppcheck baseline)"
)

out_lines = ["# yuleDKCS MISRA C:2023 rules — generated from yuleOSH rule library",
             "# DO NOT EDIT MANUALLY — regenerate with scripts/generate-misra-rules.py",
             "#", "meta:", f"  standard: {meta.get('standard', 'MISRA C')}",
             f"  version: '{meta.get('version', '2023')}'",
             f"  ruleset_version: '{meta.get('ruleset_version', '2023.1')}'",
             f"  description: '{meta.get('description', '')}'",
             f"  source: {meta.get('source', 'MISRA Consortium')}",
             ""]

for rid in sorted(selected):
    out_lines.append(f"{rid}:")
    rule = selected[rid]
    for k, v in rule.items():
        if isinstance(v, bool):
            out_lines.append(f"  {k}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            out_lines.append(f"  {k}: {v}")
        else:
            # escape single quotes in strings
            sv = str(v).replace("'", "''")
            out_lines.append(f"  {k}: '{sv}'")
    out_lines.append("")

OUT.write_text("\n".join(out_lines), encoding="utf-8")
print(f"Wrote {len(selected)} rules to {OUT}")
