# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tenant data model — file-system-backed, no database required.

Each tenant has:
  - data/tenants/{slug}.json  → metadata (id, name, plan, created_at, settings)
  - data/{slug}/              → tenant-scoped storage (projects, config, evidence)
  - data/{slug}/audit/        → audit log directory

Usage:
    store = TenantStore()
    tenant = store.get_or_create("my-org", "My Organization")
    store.save_project(tenant.slug, project_data)
    projects = store.list_projects(tenant.slug)
"""

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Plan definitions ────────────────────────────────────────────────────────

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"

TIER_LIMITS = {
    PLAN_FREE: {
        "max_projects": 1,
        "max_users": 1,
        "max_pipeline_runs_monthly": 50,
        "max_storage_mb": 100,
        "features": ["basic_pipeline", "misra_check"],
    },
    PLAN_PRO: {
        "max_projects": 10,
        "max_users": 5,
        "max_pipeline_runs_monthly": 500,
        "max_storage_mb": 1024,
        "features": ["basic_pipeline", "misra_check", "audit_log", "kanban",
                      "rbac", "ci_cd", "evidence_export"],
    },
    PLAN_ENTERPRISE: {
        "max_projects": 9999,
        "max_users": 9999,
        "max_pipeline_runs_monthly": 50000,
        "max_storage_mb": 102400,
        "features": ["all"],
    },
}

SUPPORTED_PLANS = [PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE]


# ── Tenant dataclass ────────────────────────────────────────────────────────

@dataclass
class Tenant:
    """A multi-tenant organization in the yuleOSH platform.

    Stored as JSON in data/tenants/{slug}.json.
    """
    id: str                    # unique slug: 'my-org'
    name: str                  # display name: 'My Organization'
    plan: str = PLAN_FREE      # free | pro | enterprise
    created_at: str = ""       # ISO 8601
    updated_at: str = ""       # ISO 8601
    settings: dict = field(default_factory=dict)  # tenant-level config

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.plan not in SUPPORTED_PLANS:
            self.plan = PLAN_FREE

    @property
    def limits(self) -> dict:
        return TIER_LIMITS.get(self.plan, TIER_LIMITS[PLAN_FREE])

    def has_feature(self, feature: str) -> bool:
        features = self.limits.get("features", [])
        return "all" in features or feature in features

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Tenant":
        return cls(**data)


# ── TenantStore ─────────────────────────────────────────────────────────────

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class TenantStore:
    """File-system-backed tenant persistence layer.

    Directory structure:
        data/tenants/           ← tenant metadata (slug.json per tenant)
        data/{slug}/            ← tenant data root
        data/{slug}/projects/   ← project definitions
        data/{slug}/config/     ← tenant configuration
        data/{slug}/evidence/   ← evidence artifacts
    """

    def __init__(self, data_root: Optional[str] = None):
        if data_root is None:
            osh_home = os.environ.get(
                "OSH_HOME",
                str(Path.home() / ".openclaw" / "workspace" / "tasks" / "yuleOSH"),
            )
            data_root = os.path.join(osh_home, "data")
        self.data_root = Path(data_root)
        self.tenants_dir = self.data_root / "tenants"
        self.tenants_dir.mkdir(parents=True, exist_ok=True)

    # ── Tenant CRUD ──────────────────────────────────────────────────────

    def get(self, slug: str) -> Optional[Tenant]:
        """Get tenant by slug. Returns None if not found."""
        path = self.tenants_dir / f"{slug}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return Tenant.from_dict(data)

    def get_or_create(self, slug: str, name: str = "", plan: str = PLAN_FREE) -> Tenant:
        """Get existing tenant or create a new one."""
        existing = self.get(slug)
        if existing:
            return existing
        return self.create(slug, name or slug, plan)

    def create(self, slug: str, name: str, plan: str = PLAN_FREE) -> Tenant:
        """Create a new tenant with the given slug."""
        if not SLUG_RE.match(slug):
            raise ValueError(
                f"Invalid slug '{slug}'. Must be lowercase alphanumeric with hyphens."
            )
        if self.get(slug):
            raise ValueError(f"Tenant '{slug}' already exists.")

        tenant = Tenant(id=slug, name=name, plan=plan)
        self._save(tenant)

        # Create tenant data directory
        tenant_dir = self.data_root / slug
        tenant_dir.mkdir(parents=True, exist_ok=True)
        (tenant_dir / "projects").mkdir(exist_ok=True)
        (tenant_dir / "config").mkdir(exist_ok=True)
        (tenant_dir / "evidence").mkdir(exist_ok=True)
        (tenant_dir / "audit").mkdir(exist_ok=True)

        return tenant

    def update(self, slug: str, **kwargs) -> Tenant:
        """Update tenant fields in-place."""
        tenant = self.get(slug)
        if not tenant:
            raise ValueError(f"Tenant '{slug}' not found.")
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        tenant.updated_at = datetime.now().isoformat()
        self._save(tenant)
        return tenant

    def delete(self, slug: str) -> bool:
        """Remove tenant metadata and data directory."""
        path = self.tenants_dir / f"{slug}.json"
        if not path.exists():
            return False
        path.unlink()
        # Remove tenant data directory
        tenant_dir = self.data_root / slug
        if tenant_dir.exists():
            shutil.rmtree(str(tenant_dir))
        return True

    def list_tenants(self) -> list[Tenant]:
        """List all tenants."""
        result = []
        for f in sorted(self.tenants_dir.glob("*.json")):
            data = json.loads(f.read_text())
            result.append(Tenant.from_dict(data))
        return result

    def _save(self, tenant: Tenant):
        path = self.tenants_dir / f"{tenant.id}.json"
        path.write_text(json.dumps(tenant.to_dict(), ensure_ascii=False, indent=2))

    # ── Project management within a tenant ───────────────────────────────

    def save_project(self, slug: str, project_data: dict) -> dict:
        """Save a project definition under the tenant's projects directory."""
        tenant_dir = self.data_root / slug
        projects_dir = tenant_dir / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_data.get("slug", project_data.get("name", "unnamed"))
        path = projects_dir / f"{project_name}.json"
        project_data["updated_at"] = datetime.now().isoformat()
        path.write_text(json.dumps(project_data, ensure_ascii=False, indent=2))
        return project_data

    def get_project(self, slug: str, project_slug: str) -> Optional[dict]:
        """Get a project by slug within a tenant."""
        path = self.data_root / slug / "projects" / f"{project_slug}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_projects(self, slug: str) -> list[dict]:
        """List all projects for a tenant."""
        projects_dir = self.data_root / slug / "projects"
        if not projects_dir.exists():
            return []
        projects = []
        for f in sorted(projects_dir.glob("*.json")):
            projects.append(json.loads(f.read_text()))
        return projects

    def delete_project(self, slug: str, project_slug: str) -> bool:
        """Delete a project by slug."""
        path = self.data_root / slug / "projects" / f"{project_slug}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    # ── Tenant config ────────────────────────────────────────────────────

    def get_config(self, slug: str, key: str, default=None):
        """Get a tenant config value."""
        path = self.data_root / slug / "config" / f"{key}.json"
        if not path.exists():
            return default
        return json.loads(path.read_text())

    def set_config(self, slug: str, key: str, value):
        """Set a tenant config value."""
        path = self.data_root / slug / "config" / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
