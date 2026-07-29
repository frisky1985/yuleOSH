"""Project initialization commands for yuleOSH CLI"""
import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

OSH_HOME = os.environ.get("OSH_HOME", os.path.expanduser("~/.openclaw"))

def cmd_template_init(project_name, parent_dir=".", template_name=None):
    """Initialize an ECU project from template"""
    parent = Path(parent_dir).resolve()
    project_dir = parent / project_name
    if project_dir.exists():
        print(f"Error: Directory {project_dir} already exists")
        sys.exit(1)
    templates_dir = Path(OSH_HOME) / "templates" / "project"
    if not templates_dir.exists():
        print("Error: No templates available")
        sys.exit(1)
    if template_name is None:
        template_dirs = [d for d in templates_dir.iterdir() if d.is_dir()]
        if not template_dirs:
            print("Error: No templates found")
            sys.exit(1)
        template_name = template_dirs[0].name
        print(f"Using template: {template_name}")
    template_path = templates_dir / template_name
    if not template_path.exists():
        print(f"Error: Template '{template_name}' not found")
        sys.exit(1)
    shutil.copytree(template_path, project_dir)
    metadata = template_path / "template.json"
    if metadata.exists():
        meta = json.loads(metadata.read_text())
        for root, dirs, files in os.walk(project_dir):
            for f in files:
                fpath = Path(root) / f
                content = fpath.read_text()
                content = content.replace("{{PROJECT_NAME}}", project_name)
                content = content.replace("{{PROJECT_DESC}}", meta.get("description", ""))
                fpath.write_text(content)
    print(f"Created project {project_name} from template {template_name}")
