# yuleOSH — Database Migration System

> Built-in SQLite migration framework (no Alembic dependency)

## Schema Version: v7

## Migration History

| Version | Tables Added | Description |
|:--------|:-------------|:------------|
| v1 | `pipelines`, `ci_runs`, `reviews`, `evidence`, `projects` | Core engine tables |
| v2 | `_meta`, `organizations`, `users`, `org_projects`, `user_sessions` | Multi-tenant auth |
| v3 | ALTER `pipelines` (stat columns) | `_run_migration_v3()` — stat tracking |
| v4 | `api_keys` | API key management |
| v5 | `spec_cache` | Spec parsing result cache |
| v6 | `users.password_hash` (ALTER) | bcrypt password hashing (v0.8.0) |
| v7 | `usage_log` + `subscriptions` + `organizations.tier` | Metering + Payment (v0.9.0) |

## How Migrations Work

`src/store.py` :: `Store._migrate()` runs automatically on first Store instantiation:

```python
class Store:
    _MIGRATION_VERSION = 6  # v0.8.0: password_hash column on users  # bump this to trigger new migrations

    def _migrate(self):
        # CREATE TABLE IF NOT EXISTS for all current tables
        self.conn.executescript("CREATE TABLE IF NOT EXISTS ...")
        
        # Version-gated migrations for complex changes
        version = self.get_migration_version()
        if version < 3:
            self._run_migration_v3()
        
        # Record current version
        self.conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('migration_version', ?)",
            (str(self._MIGRATION_VERSION),)
        )
```

## Adding a New Migration (v6)

1. Bump `_MIGRATION_VERSION` to `6`
2. Add `CREATE TABLE IF NOT EXISTS` for new tables
3. For data migrations, add a version-gated helper:

```python
if version < 6:
    self._run_migration_v6()
```

## CLI Command

```bash
# Show current migration version
yuleosh db version

# Run migrations (auto-run on first use, but explicit available)
yuleosh db migrate

# Show schema
yuleosh db schema
```

## Design Principles

- **Zero-dependency**: No Alembic/SQLAlchemy — pure sqlite3
- **Idempotent**: All `CREATE TABLE` use `IF NOT EXISTS`
- **Forward-only**: No downgrade support (git rollback for dev)
- **Auto-run**: Migrations execute on first Store access
