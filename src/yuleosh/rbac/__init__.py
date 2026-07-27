# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH RBAC — Role-Based Access Control (SAAS-2).

Defines roles (Admin / Developer / Reviewer / Auditor) and a permission
matrix. Provides a check_role() decorator/middleware for API endpoints.

Usage:
    from yuleosh.rbac import check_role, ROLE_ADMIN, ROLE_DEVELOPER

    @check_role(ROLE_DEVELOPER)
    def my_api_handler(handler, path):
        ...
"""

from yuleosh.rbac.model import (
    ROLE_ADMIN,
    ROLE_DEVELOPER,
    ROLE_REVIEWER,
    ROLE_AUDITOR,
    PERMISSION_MATRIX,
    Role,
    PermissionSet,
    check_role,
    require_role,
    get_role_from_user_info,
)
