#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Code Scanner — AST-based function/class parser.

Scans source and test directories recursively, extracting:
  - Module-level functions (name, start_line, end_line)
  - Classes and their methods (name, start_line, end_line)
  - Test functions (prefixed with test_)

Creates nodes:
  - code_file  → for every .py file in src/
  - code_function → for every function/method in code files
  - test_file  → for every test_*.py file
  - test_function → for every function in test files

Creates edges:
  - contains   → file → function

Complements the regex-based scan_code_directory() in importer.py
with full AST accuracy (handles nested classes, decorators, etc.).
"""

import ast
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge

log = logging.getLogger("yuleosh.knowledge_graph.code_scanner")

# Directory aliases for test detection
_TEST_PREFIXES = {"test_", "test"}


# ── AST Visitor ─────────────────────────────────────────────────────────

class FunctionCollector(ast.NodeVisitor):
    """Collects all function/class definitions from a Python AST.

    Records only *module-level* items:
      - function: name, start_line, end_line, docstring
      - class:    name, start_line, end_line, docstring
      - method:   name, class_name, start_line, end_line, docstring

    Methods are collected by visit_ClassDef manually processing children
    WITHOUT calling generic_visit on class bodies, so visit_FunctionDef
    never fires for methods. Nested classes inside classes are handled
    by recursive visit_ClassDef calls.
    """

    def __init__(self):
        self.functions: list[dict] = []      # module-level functions
        self.classes: list[dict] = []         # classes
        self.methods: list[dict] = []         # class methods

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Record a module-level function definition."""
        entry = self._make_entry(node)
        self.functions.append(entry)
        # Visit children to catch nested functions
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Record a module-level async function definition."""
        entry = self._make_entry(node)
        self.functions.append(entry)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Record a class and its methods (without double-counting).

        Does NOT call generic_visit on the class body — instead processes
        children manually so that FunctionDef/AsyncFunctionDef children
        are collected as methods rather than triggering visit_FunctionDef.
        """
        cls_entry = {
            "kind": "class",
            "name": node.name,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": ast.get_docstring(node) or "",
        }
        self.classes.append(cls_entry)

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_entry = self._make_entry(child)
                method_entry["kind"] = "method"
                method_entry["class_name"] = node.name
                self.methods.append(method_entry)
            elif isinstance(child, ast.ClassDef):
                # Recurse into nested classes
                self.visit_ClassDef(child)
            else:
                self.generic_visit(child)

    @staticmethod
    def _make_entry(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
        return {
            "kind": "function",
            "name": node.name,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": ast.get_docstring(node) or "",
        }


def _parse_file_ast(filepath: Path) -> Optional[FunctionCollector]:
    """Parse a Python file with AST and collect functions/classes.

    Returns None on parse error.
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
        collector = FunctionCollector()
        collector.visit(tree)
        return collector
    except SyntaxError as e:
        log.warning("Syntax error in %s: %s", filepath, e)
        return None
    except Exception as e:
        log.warning("Failed to parse %s: %s", filepath, e)
        return None


# ── Core scan function ─────────────────────────────────────────────────

def scan_directory(store: KGStore, project_base: str) -> dict:
    """Scan Python source and test directories using AST parsing.

    Scans:
      - <project_base>/src/yuleosh/  → code_file / code_function nodes
      - <project_base>/tests/        → test_file / test_function nodes

    Uses AST to extract precise line ranges for functions and methods.
    Handles classes, nested classes, and async functions.

    Returns summary dict with counts.
    """
    project_path = Path(project_base)

    code_count = 0
    test_count = 0
    func_count = 0
    edge_count = 0
    method_count = 0
    class_count = 0

    # Define scan targets
    scan_targets: list[tuple[Path, str, str]] = []

    # Source directory
    src_dir = project_path / "src"
    if src_dir.exists():
        scan_targets.append((src_dir, "code_file", "code_function"))
    else:
        log.debug("No src/ directory found at %s", src_dir)

    # Test directory
    tests_dir = project_path / "tests"
    if tests_dir.exists():
        scan_targets.append((tests_dir, "test_file", "test_function"))
    else:
        log.debug("No tests/ directory found at %s", tests_dir)

    if not scan_targets:
        log.warning("No scan targets found under %s", project_base)
        return {
            "code_files": 0,
            "test_files": 0,
            "functions": 0,
            "classes": 0,
            "methods": 0,
            "edges": 0,
        }

    # Non-Python file extensions to scan (P0-4a)
    _NON_PYTHON_EXTENSIONS = {".c", ".h", ".cfg", ".yaml", ".yml", ".json"}

    # For each scan target, walk all .py files
    for scan_root, file_type, func_type in scan_targets:
        for py_file in sorted(scan_root.rglob("*.py")):
            # Skip __pycache__ and hidden directories (relative to project)
            parts = py_file.relative_to(project_path).parts
            if any(part.startswith(".") for part in parts):
                continue
            if "__pycache__" in parts:
                continue

            # Determine relative path (within project_base)
            try:
                rel_path = str(py_file.relative_to(project_path))
            except ValueError:
                rel_path = str(py_file)
            rel_path = rel_path.replace("\\", "/")

            # For test directory scanning, check if actually a test file
            if file_type == "test_file":
                # All .py files in tests/ are test files
                pass

            # Create the file node
            file_node = Node(
                entity_type=file_type,
                entity_id=rel_path,
                label=py_file.name,
                properties={
                    "language": "python",
                    "path": rel_path,
                    "source": "code_scanner",
                },
            )
            file_nid = store.upsert_node(file_node)

            if file_type == "code_file":
                code_count += 1
            else:
                test_count += 1

            # Parse with AST
            collector = _parse_file_ast(py_file)
            if collector is None:
                # Fall back to regex-based scan for basic function extraction
                _regex_fallback(store, file_nid, rel_path, py_file, func_type, edge_count_func=lambda ec: ec + 1)
                continue

            # Create function nodes from AST results
            # Module-level functions
            for func_entry in collector.functions:
                _create_function_node(
                    store, file_nid, func_entry, rel_path, func_type,
                )
                func_count += 1
                edge_count += 1

            # Classes
            for cls_entry in collector.classes:
                cls_func_node = _create_function_node(
                    store, file_nid, cls_entry, rel_path, func_type,
                    extra_kind="class",
                )
                class_count += 1
                edge_count += 1

            # Methods (also attached to their class via 'contains')
            for method_entry in collector.methods:
                # Create a code_function / test_function node for the method
                _create_function_node(
                    store, file_nid, method_entry, rel_path, func_type,
                    extra_kind="method",
                )
                method_count += 1
                edge_count += 1

    # ── P0-4a: Scan non-Python files (C, headers, config, etc.) ──
    # Only scan source directories (not tests) for non-Python files
    for scan_root, file_type, func_type in scan_targets:
        if file_type != "code_file":
            continue
        for ext in _NON_PYTHON_EXTENSIONS:
            for non_py_file in sorted(scan_root.rglob(f"*{ext}")):
                # Skip hidden files/dirs, __pycache__
                parts = non_py_file.relative_to(project_path).parts
                if any(part.startswith(".") for part in parts):
                    continue
                if "__pycache__" in parts:
                    continue

                try:
                    rel_path = str(non_py_file.relative_to(project_path))
                except ValueError:
                    rel_path = str(non_py_file)
                rel_path = rel_path.replace("\\", "/")

                # Skip if already exists as a .py file node (shouldn't happen)
                existing = store.get_node("code_file", rel_path)
                if existing is not None:
                    continue

                lang = "c" if ext == ".c" else (
                    "c_header" if ext == ".h" else (
                        "json" if ext == ".json" else "yaml" if ext in (".yaml", ".yml") else "config"
                    )
                )

                # Create code_file node
                # Build properties for the code_file node
                props = {
                    "language": lang,
                    "path": rel_path,
                    "source": "code_scanner_p0_4a",
                }

                # P0-4a: For .c/.h files, extract function definitions via simple regex
                if ext in (".c", ".h"):
                    try:
                        content = non_py_file.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    except Exception:
                        content = ""
                    c_funcs = _extract_c_functions(content)
                    props["c_functions"] = json.dumps(c_funcs)
                    props["c_function_count"] = len(c_funcs)

                file_node = Node(
                    entity_type="code_file",
                    entity_id=rel_path,
                    label=non_py_file.name,
                    properties=props,
                )
                _ = store.upsert_node(file_node)
                code_count += 1
                # P0-4a: No code_function or contains edge created for non-Python files

    log.info(
        "Code scan complete: %d code files, %d test files, "
        "%d functions, %d classes, %d methods, %d edges",
        code_count, test_count, func_count, class_count, method_count, edge_count,
    )

    return {
        "code_files": code_count,
        "test_files": test_count,
        "functions": func_count,
        "classes": class_count,
        "methods": method_count,
        "edges": edge_count,
    }


def _create_function_node(
    store: KGStore,
    file_nid: int,
    entry: dict,
    rel_path: str,
    func_type: str,
    extra_kind: Optional[str] = None,
) -> int:
    """Create a function/class node and its 'contains' edge.

    Returns the node ID.
    """
    name = entry["name"]
    start_line = entry["start_line"]
    end_line = entry["end_line"]
    kind = extra_kind or entry.get("kind", "function")
    class_name = entry.get("class_name")
    docstring = entry.get("docstring", "")

    # Build FQN (fully qualified name)
    if kind == "method" and class_name:
        fqn = f"{rel_path}::{class_name}.{name}"
    elif kind == "class":
        fqn = f"{rel_path}::{name}"
    else:
        fqn = f"{rel_path}::{name}"

    # Build properties
    props = {
        "file_path": rel_path,
        "start_line": start_line,
        "end_line": end_line,
        "kind": kind,
        "source": "code_scanner",
    }
    if class_name:
        props["class_name"] = class_name
    if docstring:
        # Store first line of docstring as summary
        props["docstring_summary"] = docstring.split("\n")[0].strip()
        props["has_docstring"] = True

    func_node = Node(
        entity_type=func_type,
        entity_id=fqn,
        label=name,
        properties=props,
    )
    func_nid = store.upsert_node(func_node)

    # Contains edge: file → function
    store.upsert_edge(Edge(
        source_id=file_nid,
        target_id=func_nid,
        edge_type="contains",
        properties={"function": name, "kind": kind},
    ))

    return func_nid


def _regex_fallback(store, file_nid, rel_path, py_file, func_type, edge_count_func=lambda ec: ec + 1):
    """Fallback regex-based function extraction when AST parsing fails."""
    import re
    try:
        content = py_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""

    func_re = re.compile(r"^def (test_\w+|\w+)\s*\(", re.MULTILINE)
    for m in func_re.finditer(content):
        func_name = m.group(1)
        fqn = f"{rel_path}::{func_name}"
        func_node = Node(
            entity_type=func_type,
            entity_id=fqn,
            label=func_name,
            properties={
                "file_path": rel_path,
                "source": "code_scanner_fallback",
            },
        )
        func_nid = store.upsert_node(func_node)

        store.upsert_edge(Edge(
            source_id=file_nid,
            target_id=func_nid,
            edge_type="contains",
            properties={"function": func_name},
        ))


def _extract_c_functions(content: str) -> list[dict]:
    """Extract C function definitions from source text using simple regex.

    P0-4a: Non-Python file support. Uses regex (not AST) to find function
    definition lines in .c and .h files. Returns a list of dicts with
    name, start_line keys.
    """
    if not content:
        return []

    C_FUNC_RE = re.compile(
        r'^\s*'
        r'(?:static\s+|extern\s+|inline\s+)?'
        r'(?:const\s+|volatile\s+)?'
        r'\w[\w\s\*]+\s+'
        r'(\w[\w\d_]*)'
        r'\s*\([^;{}]*\)'
        r'\s*{?'
        r'\s*(?://.*)?$',
        re.MULTILINE,
    )

    # Identifiers that should NOT be treated as function definitions
    _CONTROL_KW = {
        "if", "else", "for", "while", "do", "switch", "case",
        "return", "typedef", "struct", "enum", "union",
    }

    results = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        m = C_FUNC_RE.match(line)
        if m:
            name = m.group(1)
            if name not in _CONTROL_KW:
                results.append({
                    "name": name,
                    "start_line": i,
                })
    return results


def scan_single_file(store: KGStore, project_base: str, rel_path: str) -> dict:
    """Scan a single Python file and create/update its nodes.

    Used by incremental_bootstrap() in importer.py for incremental
    knowledge graph updates. Scans one file at a time, creating
    the file node and all function/class/method nodes.

    Args:
        store: KGStore instance
        project_base: Project root directory
        rel_path: Relative path of the file to scan (e.g. 'src/yuleosh/engine.py')

    Returns:
        dict with counts of created nodes and edges
    """
    project_path = Path(project_base).resolve()
    py_file = (project_path / rel_path).resolve()

    if not py_file.exists() or not py_file.is_file():
        log.warning("scan_single_file: file not found: %s", py_file)
        return {"functions": 0, "classes": 0, "methods": 0, "edges": 0}

    # Determine entity type
    fname = py_file.name
    if fname.startswith("test_") or "test_" in fname:
        file_type = "test_file"
        func_type = "test_function"
    else:
        file_type = "code_file"
        func_type = "code_function"

    # Normalise path (it should already be relative to project_base)
    norm_path = rel_path.replace("\\", "/")

    # Create the file node
    file_node = Node(
        entity_type=file_type,
        entity_id=norm_path,
        label=py_file.name,
        properties={
            "language": "python",
            "path": norm_path,
            "source": "code_scanner",
        },
    )
    file_nid = store.upsert_node(file_node)

    # Parse with AST
    collector = _parse_file_ast(py_file)
    if collector is None:
        # Fall back to regex
        _regex_fallback(store, file_nid, norm_path, py_file, func_type)
        return {"functions": 0, "classes": 0, "methods": 0, "edges": 1}

    func_count = 0
    class_count = 0
    method_count = 0
    edge_count = 0

    # Module-level functions
    for func_entry in collector.functions:
        _create_function_node(store, file_nid, func_entry, norm_path, func_type)
        func_count += 1
        edge_count += 1

    # Classes
    for cls_entry in collector.classes:
        _create_function_node(store, file_nid, cls_entry, norm_path, func_type, extra_kind="class")
        class_count += 1
        edge_count += 1

    # Methods
    for method_entry in collector.methods:
        _create_function_node(store, file_nid, method_entry, norm_path, func_type, extra_kind="method")
        method_count += 1
        edge_count += 1

    log.debug(
        "Scanned single file %s: %d funcs, %d classes, %d methods, %d edges",
        norm_path, func_count, class_count, method_count, edge_count,
    )
    return {
        "functions": func_count,
        "classes": class_count,
        "methods": method_count,
        "edges": edge_count,
    }
