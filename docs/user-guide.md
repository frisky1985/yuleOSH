# yuleOSH v0.8.0 — User Guide

> Quick start for new users

## Getting Started (5 minutes)

### 1. Sign Up

```bash
# Step 1: Visit your yuleOSH instance
open https://your-domain.com

# Step 2: Sign in with your email
curl -X POST https://your-domain.com/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"you@company.com"}'
# → {"token":"***", "redirect":"/org/setup", "needs_org":true}
```

### 2. Create Your Organization

```bash
curl -X POST https://your-domain.com/api/org/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "org_name":"Acme Corp",
    "org_slug":"acme",
    "project_name":"Vehicle Controller",
    "project_slug":"vcu",
    "email":"you@company.com",
    "password":"YourSecurePassword123"
  }'
```

### 3. Configure Your Project

Create `docs/spec.md` with your requirements:

```markdown
# Vehicle Controller Spec

## Requirements

### RS-001: CAN Bus Communication
Status: PROPOSED

The VCU SHALL communicate via CAN bus at 500kbps.

#### Scenario: CAN Message Transmission
GIVEN a CAN bus is connected
WHEN the VCU sends a message
THEN the message SHALL be received within 10ms
```

### 4. Run Your First Pipeline

```bash
# Validate your spec
python3 -m src.spec.validate docs/spec.md

# Run CI Layer 1 (unit tests)
python3 -m src.ci.run 1

# Run full pipeline
python3 -m src.ci.run all
```

### 5. View Results

```bash
# Health check
curl https://your-domain.com/api/health

# Evidence pack
curl https://your-domain.com/api/v1/evidence

# Traceability matrix
curl https://your-domain.com/api/v1/evidence/traceability
```

## Pipeline Overview

```
CI Layer 1 → Development Verification
  ├── plan-lint
  ├── clang-tidy
  ├── unit tests
  └── coverage check

CI Layer 2 → Integration Verification
  ├── cross-compile (ARM/RISC-V)
  ├── static analysis
  ├── SIL tests (QEMU)
  └── integration tests

CI Layer 2.5 → HIL Testing
  ├── hardware detection
  ├── flash firmware
  └── serial assertions

CI Layer 3 → System Verification
  ├── E2E tests
  ├── version check
  └── evidence pack
```

## Multi-Tenant Features

| Feature | Description |
|:--------|:------------|
| Organizations | Isolated workspaces with own users and projects |
| Projects | Per-project specs, pipelines, and evidence |
| Roles | admin (full access) / member (read + run) |
| Invite Codes | Share org slug to invite team members |
| API Keys | Per-org keys for CI/CD integration |

## Troubleshooting

| Problem | Solution |
|:--------|:---------|
| "Password required" | User has password set — include `password` in signin |
| "Invalid password" | Wrong password — use `/api/auth/signin` to retry |
| "Too many attempts" | Rate limited — wait 5 minutes |
| "Organization not found" | Check invite code / org slug |
| "Unauthorized" | Token expired — sign in again |
