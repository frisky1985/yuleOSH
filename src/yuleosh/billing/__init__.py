# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Billing — Usage metering & Stripe integration (SAAS-5).

Plans:
  Free (community):  1 project, 1 user, 50 CI runs/month
  Pro:              10 projects, 5 users, 500 CI runs/month
  Enterprise:       Unlimited projects, unlimited users, unlimited CI runs

Stripe integration in mock mode (no real API key required).
"""

from yuleosh.billing.metering import (
    UsageMeter,
    BillingManager,
    PLAN_FREE,
    PLAN_PRO,
    PLAN_ENTERPRISE,
    PLAN_LIMITS,
)
