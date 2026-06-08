#!/usr/bin/env python3
"""OSH Spec Diff Engine — compare two OpenSpec files and produce delta with impact analysis."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import parse_spec, diff_specs


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 diff.py <old-spec> <new-spec> [--json]", file=sys.stderr)
        sys.exit(1)

    old_path, new_path = sys.argv[1], sys.argv[2]
    to_json = "--json" in sys.argv

    try:
        delta = diff_specs(old_path, new_path)
    except Exception as e:
        print(f"❌ Diff error: {e}", file=sys.stderr)
        sys.exit(1)

    if to_json:
        print(json.dumps(delta, indent=2, ensure_ascii=False))
    else:
        _print_human(delta)


def _print_human(delta: dict):
    print(f"\n📊 Spec Delta: {delta['old']} → {delta['new']}")
    print(f"{'='*50}")
    print(f"  Total Changes: {delta['total_changes']}")
    print(f"  Added:    {delta['added_count']}")
    print(f"  Removed:  {delta['removed_count']}")
    print(f"  Modified: {delta['modified_count']}")
    print(f"  Status Chg: {delta['status_changed_count']}")
    print()

    if delta['added_requirements']:
        print("🟢 ADDED:")
        for r in delta['added_requirements']:
            print(f"  + {r}")

    if delta['removed_requirements']:
        print("🔴 REMOVED:")
        for r in delta['removed_requirements']:
            print(f"  - {r}")

    if delta['modified_requirements']:
        print("🟡 MODIFIED:")
        for m in delta['modified_requirements']:
            rid = f" [{m.get('req_id', '?')}]" if m.get('req_id') else ""
            print(f"  ~ {m['name']}{rid}:")
            for c in m['changes']:
                print(f"    {c}")

    if delta['status_changed']:
        print("\n🔀 STATUS CHANGED:")
        for s in delta['status_changed']:
            print(f"  {s.get('req_id', '?')} {s['name']}: {s['old_status']} → {s['new_status']}")

    # Impact analysis section
    impact = delta.get('impact_analysis', {})
    if impact:
        print(f"\n📌 IMPACT ANALYSIS:")
        print(f"{'-'*50}")

        if impact.get('affected_requirements'):
            print(f"  Affected Requirements ({len(impact['affected_requirements'])}):")
            for r in impact['affected_requirements']:
                print(f"    • {r}")

        if impact.get('affected_children'):
            print(f"  Affected Children ({len(impact['affected_children'])}):")
            for r in impact['affected_children']:
                print(f"    • {r}")

        if impact.get('affected_scenarios'):
            print(f"  Affected Scenarios: {', '.join(impact['affected_scenarios'])}")

        if impact.get('affected_architecture_components'):
            print(f"  Affected Components: {', '.join(impact['affected_architecture_components'])}")

        if impact.get('recommended_actions'):
            print(f"  Recommended Actions ({impact['action_count']}):")
            for a in impact['recommended_actions']:
                print(f"    ⏩ {a}")

    print()


if __name__ == "__main__":
    main()
