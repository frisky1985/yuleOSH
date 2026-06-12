#!/bin/bash
# =============================================================================
# yuleOSH — Database Initialization Script
# =============================================================================
# This script runs automatically on first PostgreSQL container start
# (placed in /docker-entrypoint-initdb.d/).
#
# It creates:
#   - Database user (if not exists)
#   - Database (if not exists)
#   - Initial schema (via Alembic migrations or raw SQL)
#   - Default organization and admin user
# =============================================================================
set -euo pipefail

echo "[init-db] Starting yuleOSH database initialization..."

# ──────────────────────────────────────────────
# Configuration (override via env)
# ──────────────────────────────────────────────
DB_NAME="${POSTGRES_DB:-yuleosh}"
DB_USER="${POSTGRES_USER:-yuleosh}"
DB_PASS="${POSTGRES_PASSWORD:-yuleosh}"

# Admin seed credentials (change after first login!)
ADMIN_EMAIL="${YULEOSH_ADMIN_EMAIL:-admin@yuleosh.io}"
ADMIN_PASSWORD="${YULEOSH_ADMIN_PASSWORD:-admin123}"
ORG_NAME="${YULEOSH_ORG_NAME:-yuleOSH Inc.}"

# ──────────────────────────────────────────────
# Step 1: Ensure database exists
# ──────────────────────────────────────────────
echo "[init-db] Verifying database '${DB_NAME}' and user '${DB_USER}'..."

# The postgres:16 Docker image already creates the user+db from POSTGRES_USER/POSTGRES_DB,
# so this is idempotent. We just verify connectivity.
psql -v ON_ERROR_STOP=1 --username "${DB_USER}" --dbname "${DB_NAME}" -c "SELECT 1;" > /dev/null 2>&1
echo "[init-db] ✓ Database '${DB_NAME}' is accessible."

# ──────────────────────────────────────────────
# Step 2: Create schema extensions
# ──────────────────────────────────────────────
echo "[init-db] Enabling extensions..."
psql -v ON_ERROR_STOP=1 --username "${DB_USER}" --dbname "${DB_NAME}" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";
    CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
EOSQL
echo "[init-db] ✓ Extensions created."

# ──────────────────────────────────────────────
# Step 3: Run Alembic migrations (if available)
# ──────────────────────────────────────────────
if command -v alembic &> /dev/null && [ -f /app/alembic.ini ]; then
    echo "[init-db] Running Alembic migrations..."
    cd /app
    alembic upgrade head
    echo "[init-db] ✓ Alembic migrations applied."
else
    echo "[init-db] ⚠ Alembic not available, applying raw SQL schema..."
    # Fallback: minimal schema for standalone operation
    psql -v ON_ERROR_STOP=1 --username "${DB_USER}" --dbname "${DB_NAME}" <<-EOSQL
    -- ── Organizations ──────────────────────────
    CREATE TABLE IF NOT EXISTS organizations (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name        VARCHAR(255) NOT NULL,
        slug        VARCHAR(128) UNIQUE NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ── Users ─────────────────────────────────
    CREATE TABLE IF NOT EXISTS users (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email           VARCHAR(255) UNIQUE NOT NULL,
        password_hash   VARCHAR(255) NOT NULL,
        display_name    VARCHAR(255) NOT NULL DEFAULT '',
        role            VARCHAR(64) NOT NULL DEFAULT 'member',
        organization_id UUID REFERENCES organizations(id),
        email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ── Sessions ───────────────────────────────
    CREATE TABLE IF NOT EXISTS sessions (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token       VARCHAR(512) UNIQUE NOT NULL,
        expires_at  TIMESTAMPTZ NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ── Projects ───────────────────────────────
    CREATE TABLE IF NOT EXISTS projects (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name            VARCHAR(255) NOT NULL,
        description     TEXT DEFAULT '',
        organization_id UUID NOT NULL REFERENCES organizations(id),
        owner_id        UUID NOT NULL REFERENCES users(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- ── API Keys ───────────────────────────────
    CREATE TABLE IF NOT EXISTS api_keys (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        key_hash        VARCHAR(255) NOT NULL,
        name            VARCHAR(255) NOT NULL,
        organization_id UUID NOT NULL REFERENCES organizations(id),
        created_by      UUID NOT NULL REFERENCES users(id),
        expires_at      TIMESTAMPTZ,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);
    CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(organization_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
    CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(organization_id);
EOSQL
    echo "[init-db] ✓ Raw SQL schema applied."
fi

# ──────────────────────────────────────────────
# Step 4: Seed initial organization and admin
# ──────────────────────────────────────────────
echo "[init-db] Seeding initial organization and admin user..."

psql -v ON_ERROR_STOP=1 --username "${DB_USER}" --dbname "${DB_NAME}" <<-EOSQL
    -- Create default organization if not exists
    INSERT INTO organizations (name, slug)
    SELECT '${ORG_NAME}', lower(regexp_replace('${ORG_NAME}', '[^a-zA-Z0-9]+', '-', 'g'))
    WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE slug = 'yuleosh-inc');

    DO \$\$
    DECLARE
        org_id UUID;
    BEGIN
        SELECT id INTO org_id FROM organizations ORDER BY created_at ASC LIMIT 1;

        -- Create admin user if not exists
        IF NOT EXISTS (SELECT 1 FROM users WHERE email = '${ADMIN_EMAIL}') THEN
            INSERT INTO users (email, password_hash, display_name, role, organization_id, email_verified)
            VALUES (
                '${ADMIN_EMAIL}',
                crypt('${ADMIN_PASSWORD}', gen_salt('bf')),
                'Admin',
                'admin',
                org_id,
                TRUE
            );
            RAISE NOTICE '✓ Admin user created: ${ADMIN_EMAIL}';
        ELSE
            RAISE NOTICE 'ℹ Admin user already exists: ${ADMIN_EMAIL}';
        END IF;
    END \$\$;
EOSQL

echo "[init-db] ✓ Seed data created."
echo "[init-db] ========================================="
echo "[init-db]  Admin email:   ${ADMIN_EMAIL}"
echo "[init-db]  Admin pass:    ${ADMIN_PASSWORD}"
echo "[init-db]  *** CHANGE PASSWORD ON FIRST LOGIN ***"
echo "[init-db] ========================================="
echo "[init-db] yuleOSH database initialization complete."
