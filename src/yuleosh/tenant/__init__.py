# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Multi-Tenant Models — file-system-backed tenant management.

SAAS-1: Data isolation at the file-system layer.
Each tenant has:
  - data/tenants/{tenant_id}.json (metadata)
  - data/{tenant_id}/  (project files, config, evidence)
  - data/{tenant_id}/audit/ (audit logs)
"""

from yuleosh.tenant.model import (
    Tenant,
    TenantStore,
    PLAN_FREE,
    PLAN_PRO,
    PLAN_ENTERPRISE,
    TIER_LIMITS,
)
