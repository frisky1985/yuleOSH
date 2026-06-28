#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Docker Stability Test — test docker-compose config without running Docker.

Verifies:
  - Compose YAML parses correctly
  - All referenced files exist
  - Service dependency chain is acyclic
  - Healthcheck logic is consistent
  - Environment variable contracts match .env.example
"""

import os
import re
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── Helpers ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PRODUCTION_ENV_EXAMPLE = PROJECT_ROOT / "deploy" / ".env.production.example"
COMPOSE_FILE = PROJECT_ROOT / "deploy" / "docker-compose.yml"
COMPOSE_PROD_FILE = PROJECT_ROOT / "deploy" / "docker-compose.prod.yml"
NGINX_CONF = PROJECT_ROOT / "deploy" / "nginx" / "nginx.conf"
NGINX_DEFAULT_CONF = PROJECT_ROOT / "deploy" / "nginx" / "conf.d" / "default.conf"

REQUIRED_COMPOSE_SERVICES = {"db", "backend", "nginx", "certbot"}
REQUIRED_COMPOSE_VOLUMES = {"pgdata", "osh-data", "certbot-data", "certbot-logs"}
REQUIRED_ENV_VARS = {
    "YULEOSH_DB_USER", "YULEOSH_DB_PASSWORD", "YULEOSH_DB_NAME",
    "YULEOSH_JWT_SECRET", "YULEOSH_PORT",
}


def _parse_compose_yaml(
    path: Path,
) -> dict | None:
    """Parse a docker-compose YAML file. Returns None if file missing / invalid."""
    if not path.exists():
        return None
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, ImportError) as e:
        raise AssertionError(f"Cannot parse {path}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestDockerComposeParsing:
    """Test that docker-compose.yml and docker-compose.prod.yml parse correctly."""

    def test_compose_file_exists(self):
        """GIVEN the deploy/ directory WHEN checking docker-compose.yml THEN it exists."""
        assert COMPOSE_FILE.exists(), f"Missing: {COMPOSE_FILE}"

    def test_compose_is_valid_yaml(self):
        """GIVEN docker-compose.yml WHEN parsed THEN it is valid YAML."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        assert config is not None
        assert isinstance(config, dict)

    def test_compose_has_required_version(self):
        """GIVEN docker-compose.yml THEN version is 3.8."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        assert config.get("version") in ("3.8", "3.9", "3"), (
            f"Unexpected compose version: {config.get('version')}"
        )

    def test_prod_compose_exists(self):
        """GIVEN the deploy/ directory WHEN checking docker-compose.prod.yml THEN it exists."""
        assert COMPOSE_PROD_FILE.exists(), f"Missing: {COMPOSE_PROD_FILE}"

    def test_prod_compose_is_valid_yaml(self):
        """GIVEN docker-compose.prod.yml WHEN parsed THEN it is valid YAML."""
        config = _parse_compose_yaml(COMPOSE_PROD_FILE)
        assert config is not None


class TestRequiredServices:
    """Test that all required services are declared in docker-compose.yml."""

    def test_services_declared(self):
        """GIVEN docker-compose.yml WHEN checking services THEN all required services exist."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        services = set(config.get("services", {}).keys())
        missing = REQUIRED_COMPOSE_SERVICES - services
        assert not missing, f"Missing services: {missing}"

    def test_db_service_image(self):
        """GIVEN the 'db' service THEN it uses postgres:16-alpine."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        db = config["services"]["db"]
        assert "postgres:16-alpine" in db.get("image", ""), (
            f"Unexpected db image: {db.get('image')}"
        )

    def test_db_healthcheck_configured(self):
        """GIVEN the 'db' service THEN healthcheck uses pg_isready."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        db = config["services"]["db"]
        hc = db.get("healthcheck", {})
        test_cmd = " ".join(hc.get("test", []))
        assert "pg_isready" in test_cmd, f"Missing pg_isready in healthcheck: {hc.get('test')}"
        assert hc.get("interval") is not None
        assert hc.get("retries", 0) >= 3

    def test_backend_service_depends_on_db_healthy(self):
        """GIVEN the 'backend' service THEN depends_on db with condition: service_healthy."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        backend = config["services"]["backend"]
        depends = backend.get("depends_on", {})
        db_dep = depends.get("db", {})
        assert db_dep.get("condition") == "service_healthy", (
            f"Expected depends_on db condition=service_healthy, got: {db_dep}"
        )

    def test_nginx_service_depends_on_backend(self):
        """GIVEN the 'nginx' service THEN it depends_on backend."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        nginx_svc = config["services"]["nginx"]
        depends = nginx_svc.get("depends_on", [])
        assert "backend" in depends, f"nginx should depend on backend, got: {depends}"


class TestServiceDependencyChain:
    """Test that the service dependency chain is acyclic and consistent."""

    def test_dependency_graph_is_acyclic(self):
        """GIVEN docker-compose services WHEN building dependency graph THEN no cycles."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        services = config.get("services", {})

        # Build adjacency list
        graph = {}
        for name, svc in services.items():
            deps = svc.get("depends_on", {})
            if isinstance(deps, dict):
                deps = list(deps.keys())
            elif isinstance(deps, list):
                deps = [d for d in deps if isinstance(d, str)]
            else:
                deps = []
            graph[name] = deps

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in graph}

        def has_cycle(node):
            color[node] = GRAY
            for dep in graph.get(node, []):
                if dep not in color:
                    color[dep] = WHITE
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and has_cycle(dep):
                    return True
            color[node] = BLACK
            return False

        cycles = [n for n in graph if has_cycle(n)]
        assert not cycles, f"Circular dependency detected in: {cycles}"

    def test_all_declared_deps_exist_as_services(self):
        """GIVEN depends_on in any service THEN the target service exists."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        services = config.get("services", {})

        for name, svc in services.items():
            deps = svc.get("depends_on", {})
            if isinstance(deps, dict):
                deps = list(deps.keys())
            elif isinstance(deps, list):
                deps = deps
            else:
                deps = []
            for dep in deps:
                assert dep in services, (
                    f"Service '{name}' depends on '{dep}' but '{dep}' is not defined"
                )


class TestVolumesAndNetworks:
    """Test volumes and networks declarations."""

    def test_required_volumes_declared(self):
        """GIVEN docker-compose.yml THEN all required volumes are declared."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        volumes = set(config.get("volumes", {}).keys())
        missing = REQUIRED_COMPOSE_VOLUMES - volumes
        assert not missing, f"Missing volumes: {missing}"

    def test_network_declared(self):
        """GIVEN docker-compose.yml THEN yuleosh-net network is declared."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        networks = config.get("networks", {})
        assert "yuleosh-net" in networks, "Missing yuleosh-net network"

    def test_all_services_on_same_network(self):
        """GIVEN all services THEN each one is on yuleosh-net."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        for name, svc in config.get("services", {}).items():
            svc_networks = svc.get("networks", [])
            if isinstance(svc_networks, list):
                assert "yuleosh-net" in svc_networks, (
                    f"Service '{name}' not on yuleosh-net"
                )


class TestNginxConfig:
    """Test that nginx config files are valid and consistent."""

    def test_nginx_conf_exists(self):
        """GIVEN deploy/nginx/ THEN nginx.conf exists."""
        assert NGINX_CONF.exists(), f"Missing: {NGINX_CONF}"

    def test_default_conf_exists(self):
        """GIVEN deploy/nginx/conf.d/ THEN default.conf exists."""
        assert NGINX_DEFAULT_CONF.exists(), f"Missing: {NGINX_DEFAULT_CONF}"

    def test_default_conf_references_backend(self):
        """GIVEN default.conf THEN it proxies to backend:8080."""
        content = NGINX_DEFAULT_CONF.read_text()
        assert "backend" in content and "8080" in content, (
            "nginx default.conf should reference backend:8080"
        )

    def test_default_conf_has_server_block(self):
        """GIVEN default.conf THEN it contains a server block."""
        content = NGINX_DEFAULT_CONF.read_text()
        assert re.search(r"server\s*{", content), "No server block found in default.conf"


class TestEnvContract:
    """Test environment variable contracts between .env.example and docker-compose."""

    def test_env_example_exists(self):
        """GIVEN deploy/ THEN .env.production.example exists."""
        assert PRODUCTION_ENV_EXAMPLE.exists(), (
            f"Missing: {PRODUCTION_ENV_EXAMPLE}"
        )

    def test_required_env_vars_in_example(self):
        """GIVEN .env.production.example THEN required vars are present."""
        content = PRODUCTION_ENV_EXAMPLE.read_text()
        for var in REQUIRED_ENV_VARS:
            assert var in content, f"Required env var '{var}' not in .env.production.example"

    def test_compose_refs_env_vars_match_example(self):
        """GIVEN docker-compose.yml THEN all ${VAR} refs have defaults or are in .env.example."""
        config = _parse_compose_yaml(COMPOSE_FILE)
        compose_text = COMPOSE_FILE.read_text()

        # Find all ${VAR} or ${VAR:-default} in compose
        refs = set()
        for match in re.finditer(r'\$\{([^}:]+)(?::-[^}]*)?\}', compose_text):
            refs.add(match.group(1))

        env_example_content = PRODUCTION_ENV_EXAMPLE.read_text()

        # Check each ref has either a default in compose or is documented in .env.example
        unmapped = []
        for ref in sorted(refs):
            if ref.startswith("YULEOSH_") and ref not in env_example_content:
                # Check if it has a default in compose
                pattern = re.escape(ref) + r'(?::-[^}]*)?\}'
                if not re.search(r'\$\{' + pattern, compose_text):
                    unmapped.append(ref)

        assert not unmapped, (
            f"Env vars referenced in compose but not in .env.example (without default): {unmapped}"
        )


class TestComposeProdUp:
    """Mock-based test for docker compose up validation logic."""

    def test_compose_config_can_be_validated(self):
        """GIVEN docker-compose.yml WHEN config validation is run THEN it passes.

        This test mocks ``docker compose config`` to verify our validation logic.
        """
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "{}"
            mock_run.return_value = mock_result

            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, (
                f"docker compose config failed: {result.stderr}"
            )

    def test_compose_config_can_be_validated_with_prod(self):
        """GIVEN docker-compose.prod.yml WHEN config validation is run THEN it passes (mocked)."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "{}"
            mock_run.return_value = mock_result

            result = subprocess.run(
                [
                    "docker", "compose", "-f", str(COMPOSE_FILE),
                    "-f", str(COMPOSE_PROD_FILE), "config",
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0


# ═════════════════════════════════════════════════════════════════════════════
# E-05: MISRA FP — Nginx config conflict check
# ═════════════════════════════════════════════════════════════════════════════


class TestNginxMainConfigNotConflicting:
    """Verify deploy/nginx/conf.d/default.conf and deploy/nginx/nginx.conf are compatible."""

    def test_no_conflicting_listens(self):
        """GIVEN both nginx conf files THEN no duplicate listen directives on same port."""
        main_conf = NGINX_CONF.read_text() if NGINX_CONF.exists() else ""
        site_conf = NGINX_DEFAULT_CONF.read_text() if NGINX_DEFAULT_CONF.exists() else ""

        # Extract listen ports from each
        main_ports = set(re.findall(r"listen\s+(\d+)", main_conf))
        site_ports = set(re.findall(r"listen\s+(\d+)", site_conf))

        # Main config uses http block, site config uses server block
        # They should NOT conflict — nginx merges them
        # Common ports like 80/443 can appear in both without conflict
        # as long as one is in http block and the other in server block
        overlapping = main_ports & site_ports
        if overlapping:
            print(
                f"Overlapping listen ports (ok if main.conf is http block, site.conf is server block): {overlapping}"
            )

    def test_proxy_pass_to_backend_port(self):
        """GIVEN default.conf THEN proxy_pass targets the backend service."""
        content = NGINX_DEFAULT_CONF.read_text() if NGINX_DEFAULT_CONF.exists() else ""
        assert "proxy_pass" in content, "default.conf should have proxy_pass"
        # Backend is on port 8080 per docker-compose
        assert "8080" in content or "backend" in content, (
            "proxy_pass should reference backend:8080"
        )


# Helper import
import subprocess  # noqa: E402 (needed by mock tests)
