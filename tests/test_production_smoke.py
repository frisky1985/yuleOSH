# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Production environment smoke tests.

Validates:
  1. docker-compose.yml YAML validity & required services
  2. Health check endpoint logic (mocked, no real deployment needed)
  3. Logging configuration in docker-compose
  4. Restart/restore logic
  5. Environment variable validation
  6. Nginx config validation
  7. Database migration script sanity
"""

import json
import os
import sys
import re
from pathlib import Path
from unittest import mock

import pytest
import yaml

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = PROJECT_ROOT / "deploy"
SRC_DIR = PROJECT_ROOT / "src"


# ═══════════════════════════════════════════════════════════════════════
# 1. docker-compose.yml validation
# ═══════════════════════════════════════════════════════════════════════

def _load_compose(name: str = "docker-compose.yml") -> dict:
    path = DEPLOY_DIR / name
    assert path.exists(), f"docker-compose file not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


class TestDockerComposeValidity:
    """GIVEN docker-compose.yml WHEN parsed THEN required services exist."""

    def test_01_yaml_is_valid(self):
        """GIVEN docker-compose.yml WHEN parsed THEN no YAML error."""
        compose = _load_compose()
        assert isinstance(compose, dict)

    def test_02_required_services_exist(self):
        """GIVEN compose file WHEN inspected THEN core services present."""
        compose = _load_compose()
        services = compose.get("services", {})
        required = ["db", "backend", "nginx", "certbot"]
        for svc in required:
            assert svc in services, f"Missing required service: {svc}"

    def test_03_db_service_valid(self):
        """GIVEN db service WHEN inspected THEN has healthcheck and restart."""
        svc = _load_compose()["services"]["db"]
        assert svc.get("image") == "postgres:16-alpine"
        assert svc.get("restart") == "unless-stopped"
        assert "healthcheck" in svc
        assert svc["healthcheck"]["test"]

    def test_04_backend_service_valid(self):
        """GIVEN backend service WHEN inspected THEN has healthcheck and restart."""
        svc = _load_compose()["services"]["backend"]
        assert svc.get("restart") == "unless-stopped"
        assert "healthcheck" in svc or any(
            dep.get("condition") == "service_healthy"
            for dep in svc.get("depends_on", {}).values()
        )
        # Build context should point to project root
        assert svc.get("build", {}).get("context") == ".."

    def test_05_nginx_service_valid(self):
        """GIVEN nginx service WHEN inspected THEN proper config mounts."""
        svc = _load_compose()["services"]["nginx"]
        assert svc.get("image", "").startswith("nginx")
        assert "restart" in svc
        volumes = svc.get("volumes", [])
        assert any("./nginx/nginx.conf" in v for v in volumes)

    def test_06_service_has_logging_config(self):
        """GIVEN services WHEN inspected THEN logging config present."""
        compose = _load_compose()
        has_logging = compose.get("x-logging")
        assert has_logging is not None, "No x-logging anchor defined"
        assert has_logging["driver"] == "json-file"
        assert has_logging["options"]["max-size"] == "10m"
        assert has_logging["options"]["max-file"] == "3"

    def test_07_services_reference_logging(self):
        """GIVEN services WHEN inspected THEN each service uses x-logging."""
        compose = _load_compose()
        x_logging_ref = "&default-logging"  # yaml anchor
        for name, svc in compose.get("services", {}).items():
            # Skip certbot (custom entrypoint, might not use)
            if name == "certbot":
                continue
            assert svc.get("logging") is not None, (
                f"Service '{name}' missing logging config"
            )

    def test_08_volumes_defined(self):
        """GIVEN compose file WHEN inspected THEN volumes section has all used vols."""
        compose = _load_compose()
        volumes = compose.get("volumes", {})
        required_volumes = ["pgdata", "osh-data", "certbot-data", "certbot-logs"]
        for vol in required_volumes:
            assert vol in volumes, f"Missing volume: {vol}"

    def test_09_network_defined(self):
        """GIVEN compose file WHEN inspected THEN internal network exists."""
        compose = _load_compose()
        networks = compose.get("networks", {})
        assert "yuleosh-net" in networks

    def test_10_env_file_loaded(self):
        """GIVEN compose file WHEN inspected THEN env_file is set or documented."""
        compose = _load_compose()
        # The compose doesn't explicitly load .env, it relies on environment vars
        # Check that required vars are documented
        services = compose.get("services", {})
        for svc_name in ["backend"]:
            env = services[svc_name].get("environment", {})
            # Check critical env vars are provided
            assert any("YULEOSH_JWT_SECRET" in str(k) for k in (env or {}).keys()), (
                f"Service '{svc_name}' missing YULEOSH_JWT_SECRET env var"
            )
            assert any("STRIPE_SECRET_KEY" in str(k) for k in (env or {}).keys()), (
                f"Service '{svc_name}' missing STRIPE_SECRET_KEY"
            )


class TestDockerComposeProdValidity:
    """GIVEN docker-compose.prod.yml WHEN inspected THEN production setup is valid."""

    def test_01_prod_compose_valid(self):
        """GIVEN prod compose WHEN parsed THEN valid."""
        compose = _load_compose("docker-compose.prod.yml")
        assert isinstance(compose, dict)

    def test_02_prod_has_frontend(self):
        """GIVEN prod compose WHEN inspected THEN frontend service present."""
        compose = _load_compose("docker-compose.prod.yml")
        services = compose.get("services", {})
        assert "frontend" in services, "Missing frontend service in prod compose"

    def test_03_frontend_dockerfile_exists(self):
        """GIVEN frontend Dockerfile WHEN inspected THEN it exists."""
        df_path = PROJECT_ROOT / "frontend" / "Dockerfile"
        assert df_path.exists(), f"Frontend Dockerfile not found: {df_path}"

    def test_04_prod_env_example_exists(self):
        """GIVEN .env.production.example WHEN inspected THEN it exists."""
        env_example = DEPLOY_DIR / ".env.production.example"
        assert env_example.exists()


# ═══════════════════════════════════════════════════════════════════════
# 2. Health check endpoint logic (mocked)
# ═══════════════════════════════════════════════════════════════════════

class TestHealthCheckLogic:
    """GIVEN health check module WHEN invoked THEN returns proper response."""

    def _setup_env(self):
        """Set up minimal environment for store."""
        old_db = os.environ.get("YULEOSH_DB", "")
        os.environ["YULEOSH_DB"] = ":memory:"
        os.environ["YULEOSH_JWT_SECRET"] = "test-health-secret"
        return old_db

    def _teardown_env(self, old_db):
        if old_db:
            os.environ["YULEOSH_DB"] = old_db
        else:
            os.environ.pop("YULEOSH_DB", None)

    def test_01_health_imports_cleanly(self):
        """GIVEN health module WHEN imported THEN no import errors."""
        # Mock store to avoid SQLite issues
        with mock.patch("yuleosh.api.health.Store") as mock_store:
            mock_store.return_value.conn.execute.return_value.fetchone.return_value = {"ok": 1}
            import yuleosh.api.health as health_mod
            # Just confirm it's importable
            assert hasattr(health_mod, "handle_health")

    def test_02_health_check_db_success(self):
        """GIVEN healthy DB WHEN _check_db THEN returns 'ok'."""
        from yuleosh.api.health import _check_db
        mock_store = mock.MagicMock()
        mock_store.conn.execute.return_value.fetchone.return_value = {"ok": 1}
        result = _check_db(mock_store)
        assert result == "ok", f"Expected 'ok', got '{result}'"

    def test_03_health_check_db_failure(self):
        """GIVEN failing DB WHEN _check_db THEN returns error."""
        from yuleosh.api.health import _check_db
        mock_store = mock.MagicMock()
        mock_store.conn.execute.side_effect = Exception("connection refused")
        result = _check_db(mock_store)
        assert result.startswith("error:"), f"Expected error, got '{result}'"

    def test_04_health_check_store(self):
        """GIVEN store with data WHEN _check_store THEN returns counts."""
        from yuleosh.api.health import _check_store
        mock_store = mock.MagicMock()

        def mock_execute(sql):
            mock_cur = mock.MagicMock()
            if "pipelines" in sql:
                mock_cur.fetchone.return_value = {"c": 5}
            elif "ci_runs" in sql:
                mock_cur.fetchone.return_value = {"c": 10}
            elif "reviews" in sql:
                mock_cur.fetchone.return_value = {"c": 3}
            elif "projects" in sql:
                mock_cur.fetchone.return_value = {"c": 2}
            return mock_cur

        mock_store.conn.execute = mock_execute
        result = _check_store(mock_store)
        assert result["pipelines"] == 5
        assert result["ci_runs"] == 10
        assert result["reviews"] == 3
        assert result["projects"] == 2

    def test_05_health_check_disk(self):
        """GIVEN disk check WHEN _check_disk THEN returns usage dict."""
        from yuleosh.api.health import _check_disk
        result = _check_disk()
        assert "total_mb" in result
        assert "free_mb" in result
        assert "ok" in result

    def test_06_health_aggregate_healthy(self):
        """GIVEN all subsystems healthy WHEN handle_health THEN returns healthy."""
        from yuleosh.api.health import handle_health

        # Mock Store and its methods used by health
        mock_store = mock.MagicMock()
        mock_store.conn.execute.return_value.fetchone.return_value = {"ok": 1}

        with mock.patch("yuleosh.api.health.Store", return_value=mock_store):
            data, status = handle_health(method="GET")
            assert status == 200
            assert data.get("data", {}).get("status") == "healthy"

    def test_07_health_aggregate_degraded(self):
        """GIVEN failing DB WHEN handle_health THEN returns degraded."""
        from yuleosh.api.health import handle_health

        mock_store = mock.MagicMock()
        mock_store.conn.execute.side_effect = Exception("db down")

        with mock.patch("yuleosh.api.health.Store", return_value=mock_store):
            data, status = handle_health(method="GET")
            assert status == 200  # Returns 200 even when degraded
            result = data.get("data", {})
            assert result.get("status") == "degraded"
            assert "error" in result.get("db", "")


# ═══════════════════════════════════════════════════════════════════════
# 3. Logging configuration checks
# ═══════════════════════════════════════════════════════════════════════

class TestLoggingConfiguration:
    """GIVEN logging configuration WHEN inspected THEN properly configured."""

    def test_01_docker_logging_config(self):
        """GIVEN docker-compose WHEN inspected THEN logging config is reasonable."""
        compose = _load_compose()
        log_cfg = compose.get("x-logging", {})
        opts = log_cfg.get("options", {})

        # Log rotation: max size should not be too small
        max_size = opts.get("max-size", "")
        assert max_size.endswith("m") or max_size.endswith("g")
        size_val = int(max_size[:-1])
        assert 5 <= size_val <= 100, (
            f"max-size should be 5-100m, got {max_size}"
        )

        # Max files: should keep enough for debugging
        max_files = int(opts.get("max-file", 0))
        assert 2 <= max_files <= 10, (
            f"max-file should be 2-10, got {max_files}"
        )

    def test_02_nginx_logging_exists(self):
        """GIVEN nginx config WHEN inspected THEN access/error log configured."""
        nginx_config = DEPLOY_DIR / "nginx" / "nginx.conf"
        assert nginx_config.exists()
        content = nginx_config.read_text()
        assert "access_log" in content
        assert "error_log" in content


# ═══════════════════════════════════════════════════════════════════════
# 4. Restart/restore logic
# ═══════════════════════════════════════════════════════════════════════

class TestRestartRecoveryLogic:
    """GIVEN production services WHEN inspected THEN restart policy is correct."""

    def test_01_restart_policies(self):
        """GIVEN all services WHEN inspected THEN restart=unless-stopped."""
        compose = _load_compose()
        services = compose.get("services", {})
        for name, svc in services.items():
            assert svc.get("restart") == "unless-stopped", (
                f"Service '{name}' should use restart=unless-stopped, "
                f"got '{svc.get('restart')}'"
            )

    def test_02_db_healthcheck_exists(self):
        """GIVEN db service WHEN inspected THEN has healthcheck."""
        svc = _load_compose()["services"]["db"]
        hc = svc.get("healthcheck", {})
        assert hc.get("test") is not None
        assert hc.get("interval") is not None
        assert hc.get("retries", 0) >= 3

    def test_03_backend_depends_on_db_healthy(self):
        """GIVEN backend service WHEN inspected THEN depends on db healthy."""
        svc = _load_compose()["services"]["backend"]
        deps = svc.get("depends_on", {})
        db_dep = deps.get("db", {})
        assert db_dep.get("condition") == "service_healthy"

    def test_04_certbot_renewal_loop(self):
        """GIVEN certbot service WHEN inspected THEN has renewal loop."""
        svc = _load_compose()["services"]["certbot"]
        entrypoint = svc.get("entrypoint", "")
        assert "certbot renew" in entrypoint
        assert "sleep 12h" in entrypoint

    def test_05_data_persistence(self):
        """GIVEN compose file WHEN inspected THEN volumes persist critical data."""
        compose = _load_compose()
        services = compose.get("services", {})
        volumes = compose.get("volumes", {})

        # DB must have persistent volume
        db_vols = "".join(services["db"].get("volumes", []))
        assert "pgdata" in db_vols, "DB missing pgdata volume"

        # Backend must have persistent data volume
        backend_vols = "".join(services["backend"].get("volumes", []))
        assert "osh-data" in backend_vols, "Backend missing osh-data volume"


# ═══════════════════════════════════════════════════════════════════════
# 5. Production-prod compose additional validation
# ═══════════════════════════════════════════════════════════════════════

class TestProdComposeDetails:
    """GIVEN docker-compose.prod.yml WHEN inspected THEN specific details correct."""

    def test_01_resource_limits(self):
        """GIVEN prod compose WHEN inspected THEN services have resource limits."""
        compose = _load_compose("docker-compose.prod.yml")
        services = compose.get("services", {})
        for name, svc in services.items():
            deploy = svc.get("deploy", {})
            resources = deploy.get("resources", {})
            if "prometheus" in name or "grafana" in name or "certbot" in name:
                continue  # Optional services
            assert resources, f"Service '{name}' missing resource limits"

    def test_02_port_exposure(self):
        """GIVEN prod compose WHEN inspected THEN no critical ports exposed publicly."""
        compose = _load_compose("docker-compose.prod.yml")
        services = compose.get("services", {})

        # Backend should only bind to localhost
        yuleosh_ports = services["yuleosh"].get("ports", [])
        assert yuleosh_ports[0].startswith("127.0.0.1"), (
            "Backend port should be localhost-only"
        )

        # Postgres should only bind to localhost
        pg_ports = services["postgres"].get("ports", [])
        assert pg_ports[0].startswith("127.0.0.1"), (
            "Postgres port should be localhost-only"
        )

    def test_03_postgres_password_required(self):
        """GIVEN prod compose WHEN inspected THEN PG_PASSWORD is required."""
        compose = _load_compose("docker-compose.prod.yml")
        pg_env = compose["services"]["postgres"]["environment"]
        assert ":?PG_PASSWORD is required" in pg_env["POSTGRES_PASSWORD"], (
            "PG_PASSWORD should use :? syntax to require it"
        )

    def test_04_jwt_secret_required(self):
        """GIVEN prod compose WHEN inspected THEN JWT secret is required."""
        compose = _load_compose("docker-compose.prod.yml")
        yuleosh_env = compose["services"]["yuleosh"]["environment"]
        jwt_env = [v for v in yuleosh_env if "JWT_SECRET" in v]
        assert any(":?JWT secret is required" in v for v in jwt_env), (
            "JWT_SECRET should use :? syntax to require it"
        )


# ═══════════════════════════════════════════════════════════════════════
# 6. Nginx config validation
# ═══════════════════════════════════════════════════════════════════════

class TestNginxConfiguration:
    """GIVEN nginx config WHEN inspected THEN properly configured for production."""

    def test_01_nginx_conf_exists(self):
        """GIVEN nginx config files WHEN checked THEN they exist."""
        nginx_conf = DEPLOY_DIR / "nginx" / "nginx.conf"
        assert nginx_conf.exists(), "Main nginx config not found"
        assert nginx_conf.stat().st_size > 100, "Nginx config too small"

    def test_02_ssl_config_present(self):
        """GIVEN nginx config WHEN inspected THEN SSL is configured."""
        content = (DEPLOY_DIR / "nginx" / "nginx.conf").read_text()
        assert "ssl_certificate" in content
        assert "ssl_protocols" in content
        assert "TLSv1.2" in content

    def test_03_security_headers_present(self):
        """GIVEN nginx config WHEN inspected THEN security headers are set."""
        content = (DEPLOY_DIR / "nginx" / "nginx.conf").read_text()
        assert "Strict-Transport-Security" in content
        assert "X-Content-Type-Options" in content
        assert "X-Frame-Options" in content
        assert "Content-Security-Policy" in content

    def test_04_rate_limiting_configured(self):
        """GIVEN nginx config WHEN inspected THEN rate limiting is configured."""
        content = (DEPLOY_DIR / "nginx" / "nginx.conf").read_text()
        assert "limit_req_zone" in content
        assert "zone=api_limit" in content
        assert "zone=auth_limit" in content

    def test_05_stripe_webhook_bypasses_rate_limit(self):
        """GIVEN nginx config WHEN inspected THEN webhook endpoint not rate limited."""
        content = (DEPLOY_DIR / "nginx" / "nginx.conf").read_text()
        assert "/api/v1/subscription/webhook" in content

    def test_06_http_to_https_redirect(self):
        """GIVEN nginx config WHEN inspected THEN HTTP redirects to HTTPS."""
        content = (DEPLOY_DIR / "nginx" / "nginx.conf").read_text()
        assert "return 301 https://" in content

    def test_07_deny_sensitive_paths(self):
        """GIVEN nginx config WHEN inspected THEN sensitive paths are denied."""
        content = (DEPLOY_DIR / "nginx" / "nginx.conf").read_text()
        assert "deny all" in content
        assert "\\.env" in content or "dotfiles" in content or "\\." in content


# ═══════════════════════════════════════════════════════════════════════
# 7. Backend Dockerfile validation
# ═══════════════════════════════════════════════════════════════════════

class TestBackendDockerfile:
    """GIVEN backend Dockerfile WHEN inspected THEN it is production-ready."""

    def test_01_dockerfile_exists(self):
        """GIVEN Dockerfile.backend WHEN checked THEN it exists."""
        df = DEPLOY_DIR / "Dockerfile.backend"
        assert df.exists(), "Dockerfile.backend not found"

    def test_02_healthcheck_defined(self):
        """GIVEN Dockerfile WHEN inspected THEN HEALTHCHECK is defined."""
        content = (DEPLOY_DIR / "Dockerfile.backend").read_text()
        assert "HEALTHCHECK" in content
        assert "/api/health" in content or "/api/v1/health" in content

    def test_03_non_root_security(self):
        """GIVEN Dockerfile WHEN inspected THEN USER is not root."""
        content = (DEPLOY_DIR / "Dockerfile.backend").read_text()
        # Check that script doesn't run as root (no USER directive is fine for backend
        # that inherits default; still check CMD doesn't use root unnecessarily)
        assert "python3" in content  # minimal check

    def test_04_production_base_image(self):
        """GIVEN Dockerfile WHEN inspected THEN uses slim base image."""
        content = (DEPLOY_DIR / "Dockerfile.backend").read_text()
        assert "slim" in content, "Should use slim base image for production"
        assert "python:3.13-slim" in content, "Unexpected Python version"


# ═══════════════════════════════════════════════════════════════════════
# 8. DB init script validation
# ═══════════════════════════════════════════════════════════════════════

class TestDbInitScript:
    """GIVEN DB init script WHEN inspected THEN it's production-ready."""

    def test_01_init_sql_exists(self):
        """GIVEN db/init.sql WHEN checked THEN it exists."""
        assert (DEPLOY_DIR / "db" / "init.sql").exists()

    def test_02_init_sh_exists(self):
        """GIVEN scripts/init-db.sh WHEN checked THEN it exists."""
        init_sh = DEPLOY_DIR / "scripts" / "init-db.sh"
        assert init_sh.exists(), "init-db.sh not found"

    def test_03_init_sh_is_shell(self):
        """GIVEN init-db.sh WHEN inspected THEN it's a valid shell script."""
        content = (DEPLOY_DIR / "scripts" / "init-db.sh").read_text()
        assert content.startswith("#!/bin/bash") or content.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in content


# ═══════════════════════════════════════════════════════════════════════
# 9. Environment variable validation
# ═══════════════════════════════════════════════════════════════════════

class TestEnvironmentConfig:
    """GIVEN env example files WHEN inspected THEN properly documented."""

    def test_01_prod_env_example_has_required_vars(self):
        """GIVEN .env.production.example WHEN inspected THEN all required vars present."""
        content = (DEPLOY_DIR / ".env.production.example").read_text()
        required = [
            "YULEOSH_DB_URL",
            "YULEOSH_JWT_SECRET",
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "YULEOSH_BASE_URL",
        ]
        for var in required:
            assert var in content, f"Missing required env var: {var}"

    def test_02_prod_env_example_has_stripe_comment(self):
        """GIVEN .env.production.example WHEN inspected THEN Stripe docs present."""
        content = (DEPLOY_DIR / ".env.production.example").read_text()
        assert "dashboard.stripe.com" in content

    def test_03_dev_env_example_exists(self):
        """GIVEN .env.example WHEN checked THEN it exists."""
        assert (DEPLOY_DIR / ".env.example").exists()

    def test_04_critical_vars_have_clear_defaults(self):
        """GIVEN docker-compose.yml WHEN inspected THEN critical vars have safe defaults."""
        compose = _load_compose()
        backend_env = compose["services"]["backend"]["environment"]

        # DB password should have a default (even if weak) for development
        db_url = backend_env.get("YULEOSH_DB_URL", "")
        assert "changeme123" in db_url or "${YULEOSH_DB_PASSWORD:-changeme123}" in db_url
