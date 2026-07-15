"""Abstract base class for yuleOSH persistent stores.

Provides a common interface for both SQLite Store and PostgresStore,
enabling polymorphic usage across the codebase.
"""

from abc import ABC, abstractmethod
from typing import Optional


class AbstractStore(ABC):
    """Abstract interface for persistent storage backends.

    Both yuleosh.store.Store (SQLite) and yuleosh.store_pg.PostgresStore
    implement this interface, allowing the codebase to use a single
    Store() factory that returns either backend transparently.
    """

    @abstractmethod
    def setup(self):
        """Explicit initialization — run migrations, create tables, etc."""
        ...

    @abstractmethod
    def close(self):
        """Close the store and release resources."""
        ...

    # ── Organizations ──────────────────────────────────────────────────

    @abstractmethod
    def create_organization(self, name: str, slug: str) -> dict: ...
    @abstractmethod
    def get_organization(self, slug: str) -> Optional[dict]: ...
    @abstractmethod
    def get_organization_by_id(self, org_id: int) -> Optional[dict]: ...
    @abstractmethod
    def list_organizations(self) -> list[dict]: ...

    # ── Users ──────────────────────────────────────────────────────────

    @abstractmethod
    def create_user(self, org_id: int, email: str, role: str = "member",
                    password_hash: str = None) -> dict: ...
    @abstractmethod
    def get_user(self, org_id: int, email: str) -> Optional[dict]: ...
    @abstractmethod
    def get_user_by_id(self, user_id: int) -> Optional[dict]: ...
    @abstractmethod
    def list_users(self, org_id: int) -> list[dict]: ...

    # ── Org-scoped projects ────────────────────────────────────────────

    @abstractmethod
    def create_org_project(self, org_id: int, name: str, slug: str,
                           description: str = "") -> dict: ...
    @abstractmethod
    def get_org_project(self, org_id: int, slug: str) -> Optional[dict]: ...
    @abstractmethod
    def get_org_project_by_id(self, project_id: int) -> Optional[dict]: ...
    @abstractmethod
    def list_org_projects(self, org_id: int) -> list[dict]: ...

    # ── Sessions ───────────────────────────────────────────────────────

    @abstractmethod
    def create_session(self, user_id: int, token: str,
                       ttl_hours: int = 24) -> dict: ...
    @abstractmethod
    def get_session(self, token: str) -> Optional[dict]: ...
    @abstractmethod
    def delete_session(self, token: str): ...
    @abstractmethod
    def cleanup_expired_sessions(self): ...

    # ── Spec cache ─────────────────────────────────────────────────────

    @abstractmethod
    def cache_spec_parse(self, spec_path: str, mtime: float,
                         result: dict): ...
    @abstractmethod
    def get_cached_spec_parse(self, spec_path: str,
                              mtime: float) -> Optional[dict]: ...

    # ── API Keys ───────────────────────────────────────────────────────

    @abstractmethod
    def create_api_key(self, key_hash: str, label: str,
                       prefix: str) -> dict: ...
    @abstractmethod
    def get_api_key_by_hash(self, key_hash: str) -> Optional[dict]: ...
    @abstractmethod
    def list_api_keys(self) -> list[dict]: ...
    @abstractmethod
    def revoke_api_key(self, key_id: int) -> bool: ...
    @abstractmethod
    def update_api_key_last_used(self, key_id: int): ...

    # ── Pipelines ──────────────────────────────────────────────────────

    @abstractmethod
    def save_pipeline(self, name: str, data: dict): ...
    @abstractmethod
    def get_pipeline(self, name: str) -> Optional[dict]: ...
    @abstractmethod
    def list_pipelines(self) -> list[dict]: ...

    # ── CI runs ────────────────────────────────────────────────────────

    @abstractmethod
    def save_ci(self, data: dict): ...
    @abstractmethod
    def list_ci(self, limit: int = 10) -> list[dict]: ...

    # ── Reviews ────────────────────────────────────────────────────────

    @abstractmethod
    def save_review(self, task_name: str, data: dict): ...
    @abstractmethod
    def list_reviews(self, limit: int = 10) -> list[dict]: ...

    # ── Evidence ───────────────────────────────────────────────────────

    @abstractmethod
    def log_evidence(self, name: str, type_: str, path: str,
                     size: int = 0): ...
    @abstractmethod
    def list_evidence(self) -> list[dict]: ...

    # ── Projects ───────────────────────────────────────────────────────

    @abstractmethod
    def init_project(self, name: str, description: str = ""): ...
    @abstractmethod
    def get_project(self, name: str) -> Optional[dict]: ...

    # ── Usage & Subscription ───────────────────────────────────────────

    @abstractmethod
    def record_usage(self, org_id: int, project_id: int,
                     resource: str, amount: int): ...
    @abstractmethod
    def get_monthly_usage(self, org_id: int) -> dict: ...
    @abstractmethod
    def get_subscription(self, org_id: int) -> Optional[dict]: ...
    @abstractmethod
    def upsert_subscription(self, org_id: int, data: dict): ...
    @abstractmethod
    def update_org_tier(self, org_id: int, tier: str): ...
    @abstractmethod
    def get_org_by_stripe_subscription(self, sub_id: str) -> Optional[dict]: ...

    # ── Stats ──────────────────────────────────────────────────────────

    @abstractmethod
    def record_activity(self, project_name: str): ...
    @abstractmethod
    def get_total_users(self) -> int: ...
    @abstractmethod
    def get_total_projects(self) -> int: ...
    @abstractmethod
    def get_usage_stats(self) -> dict: ...
    @abstractmethod
    def get_migration_version(self) -> int: ...
    @abstractmethod
    def is_wizard_completed(self) -> bool: ...
    @abstractmethod
    def complete_wizard(self, org_id: int = 0): ...
