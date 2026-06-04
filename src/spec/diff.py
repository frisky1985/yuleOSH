#!/usr/bin/env python3
"""OSH Spec Diff Engine — compare two OpenSpec files and produce delta."""
import json
import sys
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
            print(f"  ~ {m['name']}:")
            for c in m['changes']:
                print(f"    {c}")

    print()


if __name__ == "__main__":
    main()
