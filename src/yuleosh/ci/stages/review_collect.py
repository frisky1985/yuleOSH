# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""CI Stages — Review source collection domain (TD-005, split from review.py).

C/C++ source file discovery, delta collection, header-dependent expansion,
include-path detection and exclusion/categorization for the MISRA review
stage.  Moved verbatim from yuleosh/ci/stages/review.py (pure relocation).
"""

import fnmatch
import logging
import os
import re
import subprocess

log = logging.getLogger("ci.stages")

def _categorize_file(filepath: str, categories: dict) -> tuple[str, dict]:
    """根据文件路径判断代码类别，返回 (category_name, category_config)。

    匹配优先级: template > third_party > business。
    无匹配时默认返回 ("business", business_config).
    """
    basename = os.path.basename(filepath)
    # Priority order: template, third_party, business
    priority_order = ["template", "third_party", "business"]
    for cat_name in priority_order:
        cat_cfg = categories.get(cat_name, {})
        for pattern in cat_cfg.get("paths", []):
            if fnmatch.fnmatch(filepath, pattern) or \
               fnmatch.fnmatch(basename, pattern):
                return cat_name, cat_cfg
    # Fallback: business
    return "business", categories.get("business", {})

def _find_c_sources(project_dir: str, scan_dirs: list[str]) -> list[str]:
    """Walk *scan_dirs* (configurable, default src/benchmark/ref) for C/C++ files."""
    c_files: list[str] = []
    for scan_subdir in scan_dirs:
        subdir = os.path.join(project_dir, scan_subdir)
        if os.path.isdir(subdir):
            for root, dirs, files in os.walk(subdir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in files:
                    if f.endswith((".c", ".cpp")):
                        c_files.append(os.path.join(root, f))
    return c_files

def _collect_delta_files(project_dir: str, depth: int = 3) -> list[str]:
    """Collect changed C/C++ files from three sources (union, no dedup loss).

    Sources (per brainstorm-yuleosh-efficiency-20260808 §1.3):
      1. ``git diff HEAD~1 --name-only``   — already committed changes
      2. ``git diff --name-only``          — working tree (staged + unstaged)
      3. ``git ls-files --others --exclude-standard`` — untracked new files

    2026-08-16 盲区修复：committed 源从固定 ``HEAD~1`` 改为回看最近
    ``depth`` 个提交（从 HEAD~1 递减尝试，HEAD~N 不存在的浅仓库自动
    落到 HEAD~1）。根因：先提交 C 变更、再单独提交 docs 时，HEAD~1
    只含 docs → L1 MISRA delta 空扫（window-anti-pinch 8/16 实测）。

    Returns project-relative paths filtered to ``*.c/*.cpp/*.h`` (headers are
    expanded into dependents by :func:`_expand_header_dependents`).
    """
    changed: set[str] = set()
    # 1. committed changes — walk back up to `depth` commits so a
    #    docs-only HEAD~1 can't hide a recent C change from L1 delta.
    for n in range(min(depth, 16), 0, -1):
        cmd = ["git", "diff", "--name-only", f"HEAD~{n}"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=project_dir,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            f = line.strip()
            if f and f.endswith((".c", ".cpp", ".h")):
                changed.add(f)
        break  # 首个成功的 git diff 即覆盖 [HEAD~n, HEAD] 全部变更
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=project_dir,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            f = line.strip()
            if f and f.endswith((".c", ".cpp", ".h")):
                changed.add(f)
    return sorted(changed)

def _expand_header_dependents(project_dir: str, changed_files: list[str]) -> list[str]:
    """Expand changed headers into the .c/.cpp files that include them.

    When a header changes (macros / inline functions / declarations), every
    translation unit that ``#include``-s it can gain or lose MISRA violations.
    A naive delta that only scans the changed ``.c/.cpp`` files would miss
    these — e.g. changing ``string.h`` alone yields an empty scan set.

    Uses a lightweight include graph (grep of ``#include`` lines) across the
    project source tree.  Only files that already exist on disk are added.

    Returns the union of the original changed files plus dependent .c/.cpp
    files (project-relative paths).
    """
    headers = [f for f in changed_files if f.endswith(".h")]
    if not headers:
        return changed_files

    # Map header basename -> changed header paths (include name may differ in path)
    header_names = {os.path.basename(h) for h in headers}

    # Find all .c/.cpp files in the project that #include any changed header.
    dependents: set[str] = set()
    include_re = re.compile(r'^\s*#\s*include\s*[<"]([^">]+)[>"]')
    for root, dirs, files in os.walk(project_dir):
        # Skip VCS / build / dependency dirs — same policy as _find_c_sources
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d != "__pycache__"
                   and d not in ("node_modules", "build", "dist", "third_party")]
        for name in files:
            if not name.endswith((".c", ".cpp")):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, project_dir)
            if rel.startswith(".."):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        m = include_re.match(line)
                        if not m:
                            continue
                        inc = os.path.basename(m.group(1))
                        if inc in header_names:
                            dependents.add(rel)
                            break
            except OSError:
                continue

    merged = list(dict.fromkeys(changed_files + sorted(dependents)))
    return merged

def _glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a glob pattern (with recursive ``**``) to an anchored regex.

    ``**`` matches across path separators (any depth), single ``*`` matches
    within one segment, ``?`` matches one character.  Everything else is
    matched literally.
    """
    # ``**`` must be handled before single ``*``
    segments = []
    for seg in pattern.split("/"):
        if seg == "**":
            segments.append(".*")
        elif "**" in seg:
            segments.append(seg.replace("**", ".*"))
        else:
            escaped = re.escape(seg)
            escaped = escaped.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
            segments.append(escaped)
    return re.compile("^" + "/".join(segments) + "$")

def _matches_glob(rel: str, pattern: str) -> bool:
    """Glob-style match supporting recursive ``**``.

    ``fnmatch`` treats ``**`` as a single ``*`` (does not cross path
    separators), so patterns like ``tests/**`` silently fail to match
    nested paths such as ``src/foo/tests/bar.c``.  This helper converts
    the pattern to a regex with true ``**`` recursion, and additionally
    tries a ``**/``-prefixed form so patterns written as ``tests/**``
    also match at any depth (``src/**/tests/**``).
    """
    if _glob_to_regex(pattern).match(rel):
        return True
    if not pattern.startswith("**/"):
        return bool(_glob_to_regex("**/" + pattern).match(rel))
    return False

def _exclude_paths(files: list[str], exclude_patterns: list[str], project_dir: str) -> list[str]:
    """Filter out files matching any of the exclude patterns (glob-style).

    Patterns like "tests/**" are matched relative to project_dir.
    """
    if not exclude_patterns:
        return files

    filtered = []
    for f in files:
        # Get relative path
        if os.path.isabs(f):
            try:
                rel = os.path.relpath(f, project_dir)
            except ValueError:
                rel = f
        else:
            rel = f
        # Normalize — strip "./" prefixes so patterns like "embedded/**" match
        rel = os.path.normpath(rel)

        excluded = False
        for pattern in exclude_patterns:
            if _matches_glob(rel, pattern):
                excluded = True
                break

        if not excluded:
            filtered.append(f)

    excluded_count = len(files) - len(filtered)
    if excluded_count > 0:
        log.info("Excluded %d file(s) via exclude_paths patterns", excluded_count)

    return filtered

def _detect_include_paths(project_dir: str) -> list[str]:
    """Auto-detect common include directories for cppcheck -I flags.

    Dynamically discovers all **/include/ directories under the project
    tree (excluding build/artifacts) plus standard project-level paths.
    This is the single source of truth — the hardcoded path lists have been
    replaced by filesystem scanning so that new modules are picked up
    automatically without manual updates.

    Only returns paths that exist on disk.
    """
    # Standard project-level directories (always relevant)
    candidates = [
        ".",
        "src",
        "include",
        "inc",
        "config",
        "config/common",
        "tests",
        "tests/unity/src",
        "third_party",
        "lib",
        "common",
        "Drivers",
        "Drivers/CMSIS",
        "Drivers/CMSIS/Include",
        "Drivers/STM32F4xx_HAL_Driver",
        "Drivers/STM32F4xx_HAL_Driver/Inc",
        "Middlewares",
    ]

    # Dynamically discover every **/include/ directory
    auto_scanned = _scan_include_dirs(project_dir)

    all_candidates = candidates + auto_scanned

    found = []
    seen = set()
    for c in all_candidates:
        full = os.path.join(project_dir, c)
        norm = os.path.normpath(full)
        if norm not in seen and os.path.isdir(norm):
            seen.add(norm)
            found.append(norm)

    return found

def _scan_include_dirs(project_dir: str) -> list[str]:
    """Walk project source dirs and collect every **/include/ directory
    plus module-level **/src directories that contain .h files.
    """
    skip_prefixes = (
        ".git", "build", "website", "node_modules", "__pycache__",
        ".docusaurus", "backups", ".yuleosh", ".osh", ".claude",
        ".build", "CMakeFiles", "coverage-report", "examples",
    )

    scan_roots = ["src", "include", "tests", "third_party"]
    # Extend with configurable misra.scan_dirs so mixed-language repos
    # (e.g. yuleDKCS embedded/) get their include dirs discovered too.
    try:
        from yuleosh.ci.config import _get_ci_config
        _cfg = _get_ci_config(project_dir)
        if _cfg and _cfg.misra.scan_dirs:
            for _sd in _cfg.misra.scan_dirs:
                if _sd not in scan_roots:
                    scan_roots.append(_sd)
    except Exception:
        pass

    found: list[str] = []
    seen: set[str] = set()

    for root in scan_roots:
        abs_root = os.path.join(project_dir, root)
        if not os.path.isdir(abs_root):
            continue

        rel_root = os.path.relpath(abs_root, project_dir)
        if rel_root not in seen and os.path.isdir(abs_root):
            seen.add(rel_root)
            found.append(rel_root)

        for dirpath, dirnames, _ in os.walk(abs_root):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d != "__pycache__"
                and not any(d.startswith(p) for p in skip_prefixes)
            ]

            rel = os.path.relpath(dirpath, project_dir)
            dirname = os.path.basename(dirpath)
            parts = rel.split(os.sep)

            skip = False
            for p in parts:
                if any(p.startswith(s) for s in skip_prefixes):
                    skip = True
                    break
            if skip:
                continue

            if dirname == "include" and rel not in seen:
                seen.add(rel)
                found.append(rel)

            if dirname == "src" and len(parts) >= 3 and rel not in seen:
                has_headers = any(
                    f.endswith((".h", ".hpp")) for f in os.listdir(dirpath)
                )
                if has_headers:
                    seen.add(rel)
                    found.append(rel)

    return found

def _get_git_commit(project_dir: str) -> str:
    """Get short git commit hash from the project directory."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=project_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"
