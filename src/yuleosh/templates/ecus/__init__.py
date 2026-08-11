"""
ECU Template Engine — Jinja2-based project scaffolding for AUTOSAR ECU templates.

Each template lives under ecus/<template_name>/ with a template.yaml manifest
and .j2 Jinja2 template files. The engine renders all .j2 files using the
provided context variables and writes the output (stripping the .j2 suffix).
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

import jinja2
import yaml

ECUS_DIR = Path(__file__).resolve().parent

# ── Template Registry ──────────────────────────────────────────────────

ECU_TEMPLATES: dict[str, dict[str, Any]] = {}
"""Populated on first call to discover_templates()."""


def discover_templates() -> dict[str, dict[str, Any]]:
    """Scan ecus/ subdirectories for template.yaml and build a registry."""
    if ECU_TEMPLATES:
        return ECU_TEMPLATES

    for d in sorted(ECUS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        tpl_yaml = d / "template.yaml"
        if tpl_yaml.exists():
            try:
                meta = yaml.safe_load(tpl_yaml.read_text(encoding="utf-8"))
                if meta and meta.get("name"):
                    meta["_dir"] = str(d)
                    ECU_TEMPLATES[meta["name"]] = meta
            except Exception as e:
                import logging
                logging.getLogger("ecus").warning("Failed to load %s: %s", tpl_yaml, e)

    return ECU_TEMPLATES


def get_template(name: str) -> Optional[dict[str, Any]]:
    """Get a template by name."""
    discover_templates()
    return ECU_TEMPLATES.get(name)


def list_ecu_templates() -> list[dict[str, Any]]:
    """List all available ECU templates with summary info."""
    discover_templates()
    result = []
    for name, meta in ECU_TEMPLATES.items():
        result.append({
            "name": name,
            "description": meta.get("description", ""),
            "mcu": meta.get("mcu", ""),
            "asil": meta.get("asil", ""),
            "version": meta.get("version", "0.1.0"),
        })
    return result


# ── Default Context ────────────────────────────────────────────────────

DEFAULT_MCU_ARCH = {
    "S32K312": {"family": "S32K3", "arch": "ARM Cortex-M7", "cores": 1, "flash_kb": 1024, "ram_kb": 192},
    "S32K314": {"family": "S32K3", "arch": "ARM Cortex-M7", "cores": 1, "flash_kb": 2048, "ram_kb": 384},
    "S32K324": {"family": "S32K3", "arch": "ARM Cortex-M7", "cores": 2, "flash_kb": 4096, "ram_kb": 512},
    "S32K344": {"family": "S32K3", "arch": "ARM Cortex-M7", "cores": 3, "flash_kb": 4096, "ram_kb": 640},
}

DEFAULT_ASIL_LABELS = {
    "QM": "QM",
    "ASIL_B": "ASIL B",
    "ASIL_C": "ASIL C",
    "ASIL_D": "ASIL D",
}


def _build_default_context(
    template_name: str,
    project_name: str,
    mcu: str,
    asil: str,
    template_meta: dict[str, Any],
) -> dict[str, Any]:
    """Build the default Jinja2 rendering context from CLI args + template metadata."""
    asil_label = DEFAULT_ASIL_LABELS.get(asil, asil)
    mcu_info = DEFAULT_MCU_ARCH.get(mcu, {"family": "S32K3", "arch": "ARM Cortex-M7", "cores": 1, "flash_kb": 0, "ram_kb": 0})

    return {
        "project_name": project_name,
        "template_name": template_name,
        "mcu": mcu,
        "mcu_family": mcu_info["family"],
        "mcu_arch": mcu_info["arch"],
        "mcu_cores": mcu_info["cores"],
        "mcu_flash_kb": mcu_info["flash_kb"],
        "mcu_ram_kb": mcu_info["ram_kb"],
        "asil": asil,
        "asil_label": asil_label,
        "generated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "generated_by": "yuleOSH init",
        # Template metadata passthrough
        "bsw_modules": template_meta.get("bsw_modules", []),
        "spec_sections": template_meta.get("spec_sections", []),
        "swc_list": template_meta.get("swcs", []),
        "num_bsw_modules": len(template_meta.get("bsw_modules", [])),
    }


# ── Rendering Engine ───────────────────────────────────────────────────


def _j2_env(tpl_dir: Path) -> jinja2.Environment:
    """Create a Jinja2 environment rooted at the template directory."""
    loader = jinja2.FileSystemLoader(str(tpl_dir))
    env = jinja2.Environment(
        loader=loader,
        autoescape=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    # Add useful filters
    env.filters["snake_case"] = lambda s: s.lower().replace("-", "_").replace(" ", "_")
    env.filters["kebab_case"] = lambda s: s.lower().replace("_", "-").replace(" ", "-")
    return env


def init_project(
    template_name: str,
    project_name: str,
    mcu: str,
    asil: str,
    output_dir: str = ".",
    extra_context: Optional[dict[str, Any]] = None,
) -> Path:
    """Render a Jinja2 ECU template into a new project directory.

    Args:
        template_name: Which ECU template to use (bcm, dcu, vcu, bms, eps).
        project_name: Project name (used for namespacing, include guards, etc.).
        mcu: MCU part number (S32K312, S32K344, etc.).
        asil: ASIL safety level (QM, ASIL_B, ASIL_C, ASIL_D).
        output_dir: Parent directory for the new project.
        extra_context: Additional Jinja2 context variables to merge in.

    Returns:
        Path to the created project directory.
    """
    tpl_meta = get_template(template_name)
    if tpl_meta is None:
        # list_ecu_templates() 返回 list[dict] — 取 name 字段拼可读提示
        available = ", ".join(t["name"] for t in list_ecu_templates())
        print(f"❌ Unknown ECU template '{template_name}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    tpl_dir = Path(tpl_meta["_dir"])
    if not tpl_dir.exists():
        print(f"❌ Template directory not found: {tpl_dir}", file=sys.stderr)
        sys.exit(1)

    project_dir = Path(output_dir).resolve() / project_name
    if project_dir.exists():
        print(f"❌ Project directory already exists: {project_dir}", file=sys.stderr)
        sys.exit(1)

    # Build rendering context
    context = _build_default_context(template_name, project_name, mcu, asil, tpl_meta)
    if extra_context:
        context.update(extra_context)

    env = _j2_env(tpl_dir)

    print(f"🔧 Creating {project_name} from '{template_name}' template")
    print(f"   MCU: {mcu} | ASIL: {context['asil_label']} | BSW: {context['num_bsw_modules']} modules")
    print()

    # Collect all template files (recursive, skip template.yaml and hidden metadata)
    template_files: list[Path] = []
    for root, dirs, files in os.walk(str(tpl_dir)):
        # Skip template.yaml root file
        for f in files:
            fp = Path(root) / f
            # Skip template.yaml itself
            if fp.name == "template.yaml":
                continue
            template_files.append(fp)

    # Sort for deterministic order
    template_files.sort()

    rendered_count = 0
    copied_count = 0

    for src_path in template_files:
        # Compute relative path from template root
        rel_path = src_path.relative_to(tpl_dir)
        dst_path = project_dir / rel_path

        # Strip .j2 suffix for output
        output_name = _strip_j2_suffix(dst_path.name)
        if output_name != dst_path.name:
            dst_path = dst_path.parent / output_name

        # Create parent directories
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # If it's a .j2 file, render it
        if src_path.name.endswith(".j2"):
            try:
                # Template name is relative to template root with forward slashes
                template_name_rel = str(rel_path).replace(os.sep, "/")
                tmpl = env.get_template(template_name_rel)
                rendered = tmpl.render(**context)
                dst_path.write_text(rendered, encoding="utf-8")
                rendered_count += 1
                print(f"   📄 {output_name}")
            except jinja2.UndefinedError as e:
                print(f"   ❌ Template error in {rel_path}: {e}", file=sys.stderr)
                # Write with error marker
                dst_path.write_text(
                    f"/* ERROR: {e} */\n/* Fix template variable then re-run */\n",
                    encoding="utf-8",
                )
        else:
            # Plain file — copy verbatim
            shutil.copy2(str(src_path), str(dst_path))
            copied_count += 1

    # Write project metadata
    metadata = {
        "project": project_name,
        "template": template_name,
        "mcu": mcu,
        "asil": asil,
        "bsw_modules_count": context["num_bsw_modules"],
        "swcs": context["swc_list"],
        "generated_at": context["generated_at"],
        "generated_by": context["generated_by"],
    }
    (project_dir / "yuleosh.yaml").write_text(yaml.dump(metadata, default_flow_style=False, allow_unicode=True))

    print()
    print(f"✅ Project '{project_name}' created at {project_dir}")
    print(f"   Rendered: {rendered_count} template file(s)")
    if copied_count:
        print(f"   Copied:   {copied_count} static file(s)")
    print()
    print(f"   Next steps:")
    print(f"   1. Review docs/spec.md and project-context.md")
    print(f"   2. Run: cd {project_name}")
    print(f"   3. Run: yuleosh spec validate docs/spec.md")
    print(f"   4. Run: yuleosh ci run 1")
    print()

    return project_dir


def _strip_j2_suffix(filename: str) -> str:
    """Remove .j2 suffix if present (handles nested suffixes like .c.j2 → .c)."""
    if filename.endswith(".j2"):
        return filename[:-3]
    return filename
