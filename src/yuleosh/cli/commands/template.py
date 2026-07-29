"""Template management commands for yuleOSH CLI"""
import os
import json
import shutil
import subprocess
import sys
from pathlib import Path
from jinja2 import Template

OSH_HOME = os.environ.get("OSH_HOME", os.path.expanduser("~/.openclaw"))

def ensure_osh_home():
    """Ensure OSH_HOME directory exists"""
    os.makedirs(OSH_HOME, exist_ok=True)

def cmd_template_list():
    """List available project templates"""
    templates_dir = Path(OSH_HOME) / "templates" / "project"
    if not templates_dir.exists():
        print("No templates found.")
        return
    print("Available templates:")
    for t in sorted(templates_dir.iterdir()):
        if t.is_dir():
            metadata = t / "template.json"
            desc = ""
            if metadata.exists():
                desc = json.loads(metadata.read_text()).get("description", "")
            print(f"  {t.name:20s} {desc}")

def cmd_ecu_template_list():
    """List available ECU templates"""
    templates_dir = Path(OSH_HOME) / "templates" / "ecu"
    if not templates_dir.exists():
        print("No ECU templates found.")
        return
    print("Available ECU templates:")
    for t in sorted(templates_dir.iterdir()):
        if t.is_dir():
            metadata = t / "template.json"
            desc = ""
            if metadata.exists():
                desc = json.loads(metadata.read_text()).get("description", "")
            print(f"  {t.name:20s} {desc}")
