#!/usr/bin/env python3
"""Pre-save / CI check: detect mangled os.environ.get calls.

Some tools strip `os.environ.get(` from content, leaving `***"KEY", "default")`.
This script catches the resulting syntax errors and mangled patterns.
"""
import sys
import re
from pathlib import Path

MANGLE_PATTERNS = [
    (r'=\s*\*\*\*"[^"]+"\s*,\s*"[^"]*"\s*\)', "Mangled os.environ.get (missing prefix)"),
    (r"=\s*\*\*\*'[^']+'\s*,\s*'[^']*'\s*\)", "Mangled os.environ.get (missing prefix, single quotes)"),
]

def check_file(filepath: str) -> list[str]:
    """Check a single Python file for mangled patterns. Returns list of errors."""
    errors = []
    try:
        content = Path(filepath).read_text()
        for pattern, desc in MANGLE_PATTERNS:
            matches = re.finditer(pattern, content)
            for m in matches:
                line_no = content[:m.start()].count("\n") + 1
                snippet = m.group()[:60]
                errors.append(f"{filepath}:{line_no}: {desc}: {snippet}")
    except Exception as e:
        errors.append(f"{filepath}: READ_ERROR: {e}")
    return errors

def main():
    paths = sys.argv[1:] if len(sys.argv) > 1 else [
        str(p) for p in Path("src").rglob("*.py")
    ]
    
    all_errors = []
    for path in paths:
        all_errors.extend(check_file(path))
    
    if all_errors:
        print(f"❌ Found {len(all_errors)} mangled env var(s):")
        for e in all_errors:
            print(f"   {e}")
        print("\n   Fix: replace '***'KEY', ''...')' with 'os.environ.get('KEY', '...')'")
        sys.exit(1)
    
    print(f"✅ Checked {len(paths)} files — all clean")

if __name__ == "__main__":
    main()
