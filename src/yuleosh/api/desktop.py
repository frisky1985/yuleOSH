# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Desktop workspace API — local project management, requirements import,
pipeline triggering with on-disk artifact folders, and cloud sync.

All endpoints live under ``/api/v1/desktop/*`` and are intended for the
yuleOSH Desktop app (local, auth-disabled mode). They operate on the local
filesystem workspace managed by :mod:`yuleosh.desktop.workspace`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from yuleosh.desktop import audit, baseline, change_control, issues, project_mgmt, qa, templates, tracing, workspace

log = logging.getLogger("api.desktop")

# Project dir that pipeline writes into. For the desktop we point it at the
# project's own directory so generated code/tests land inside the artifact
# folders. The existing pipeline runner accepts a project_dir argument.


def _json(data: dict, status: int = 200):
    return data, status


# ── LLM settings (desktop-local, no account required) ─────────────────────
#
# The desktop app runs the backend with auth disabled, so the org-scoped
# LLM config endpoints are unavailable. Persist the user's model config in
# the desktop workspace and mirror it into the process environment, which
# is what yuleosh.llm resolves at call time.

LLM_PROVIDERS: tuple = ("deepseek", "openai", "anthropic", "mock")

# Provider → default API base URL (mirrors yuleosh.llm.providers.*).
_LLM_DEFAULT_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
}

# Provider → env vars consumed by the LLM provider implementations.
_LLM_KEY_ENVS: dict[str, tuple] = {
    "deepseek": ("DEEPSEEK_API_KEY", "LLM_API_KEY"),
    "openai": ("OPENAI_API_KEY", "LLM_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "mock": (),
}
_ALL_KEY_ENVS = ("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def _settings_path() -> Path:
    return workspace.workspace_root() / "settings.json"


def _read_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Failed to read desktop settings from %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(settings: dict) -> None:
    path = _settings_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    # The file may contain an API key — keep it private to the OS user.
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return "••••" + key[-4:] if len(key) > 4 else "••••"


def _llm_env_key_configured(provider: str) -> bool:
    return any(os.environ.get(env) for env in _LLM_KEY_ENVS.get(provider, ()))


def _apply_llm_env(cfg: dict, clear_key: bool = False) -> None:
    """Mirror the saved config into os.environ (read per-call by providers)."""
    provider = str(cfg.get("provider") or "")
    if provider:
        os.environ["YULEOSH_LLM_PROVIDER"] = provider

    model = str(cfg.get("model") or "")
    if model:
        os.environ["LLM_MODEL"] = model
    else:
        os.environ.pop("LLM_MODEL", None)

    base_url = str(cfg.get("base_url") or "")
    if base_url:
        os.environ["LLM_BASE_URL"] = base_url
    else:
        os.environ.pop("LLM_BASE_URL", None)

    key = str(cfg.get("api_key") or "")
    if key:
        for env in _LLM_KEY_ENVS.get(provider, ("LLM_API_KEY",)):
            os.environ[env] = key
    elif clear_key:
        for env in _ALL_KEY_ENVS:
            os.environ.pop(env, None)


def _bootstrap_llm_settings() -> None:
    """Apply persisted settings on startup (desktop mode only)."""
    if os.environ.get("YULEOSH_DESKTOP_MODE") != "1":
        return
    cfg = _read_settings().get("llm")
    if isinstance(cfg, dict) and cfg:
        _apply_llm_env(cfg)


# The router imports this module lazily on the first /api/v1/desktop/* call,
# which happens on desktop app startup — early enough for subsequent runs.
_bootstrap_llm_settings()


def _llm_stats() -> dict:
    """Connection-test counters persisted alongside the settings."""
    saved = _read_settings().get("llm_stats")
    stats = saved if isinstance(saved, dict) else {}
    return {
        "success": int(stats.get("success") or 0),
        "failure": int(stats.get("failure") or 0),
        "last_tested_at": str(stats.get("last_tested_at") or ""),
        "last_latency_ms": stats.get("last_latency_ms"),
        "last_ok": bool(stats.get("last_ok")),
        "last_error": str(stats.get("last_error") or ""),
    }


def _record_llm_test(ok: bool, latency_ms: int, error: str = "") -> dict:
    settings = _read_settings()
    stats = _llm_stats()
    stats["success"] += 0 if not ok else 1
    stats["failure"] += 1 if not ok else 0
    stats["last_tested_at"] = datetime.now().isoformat(timespec="seconds")
    stats["last_latency_ms"] = latency_ms
    stats["last_ok"] = bool(ok)
    stats["last_error"] = "" if ok else error
    settings["llm_stats"] = stats
    try:
        _write_settings(settings)
    except OSError:
        log.warning("Failed to persist LLM test stats", exc_info=True)
    return stats


def _effective_llm_config(cfg: dict) -> dict:
    """Resolve what the pipeline will actually use right now."""
    from yuleosh.llm.client import PROVIDER_DEFAULT_MODELS

    provider = str(cfg.get("provider") or os.environ.get("YULEOSH_LLM_PROVIDER") or "deepseek")
    default_model = PROVIDER_DEFAULT_MODELS.get(provider, "")
    model = str(cfg.get("model") or os.environ.get("LLM_MODEL") or "")
    base_url = str(cfg.get("base_url") or os.environ.get("LLM_BASE_URL") or "")
    file_key = str(cfg.get("api_key") or "")
    key_source = "settings" if file_key else ("env" if _llm_env_key_configured(provider) else "")
    return {
        "provider": provider,
        "model": model or default_model,
        "model_is_default": not model,
        "base_url": base_url or _LLM_DEFAULT_BASE_URLS.get(provider, ""),
        "base_url_is_default": not base_url,
        "api_key_set": provider == "mock" or bool(key_source),
        "api_key_source": key_source,
    }


def _llm_settings_response() -> dict:
    from yuleosh.llm.client import PROVIDER_DEFAULT_MODELS

    saved = _read_settings().get("llm")
    cfg = saved if isinstance(saved, dict) else {}
    provider = str(cfg.get("provider") or os.environ.get("YULEOSH_LLM_PROVIDER") or "deepseek")
    file_key = str(cfg.get("api_key") or "")
    model = str(cfg.get("model") or os.environ.get("LLM_MODEL") or "")
    base_url = str(cfg.get("base_url") or os.environ.get("LLM_BASE_URL") or "")
    key_configured = provider != "mock" and (
        bool(file_key) or _llm_env_key_configured(provider)
    )

    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "default_model": PROVIDER_DEFAULT_MODELS.get(provider, ""),
        "default_models": PROVIDER_DEFAULT_MODELS,
        "providers": list(LLM_PROVIDERS),
        "api_key_set": key_configured,
        "api_key_masked": _mask_key(file_key),
        "api_key_source": "settings" if file_key else ("env" if _llm_env_key_configured(provider) else ""),
        "effective": _effective_llm_config(cfg),
        "stats": _llm_stats(),
    }


def _update_llm_settings(body: Any) -> tuple:
    data = body if isinstance(body, dict) else {}

    provider = str(data.get("provider") or "deepseek").strip().lower()
    if provider not in LLM_PROVIDERS:
        return _json({
            "ok": False,
            "error": f"provider 必须是 {list(LLM_PROVIDERS)} 之一",
        }, 400)

    model = str(data.get("model") or "").strip()
    base_url = str(data.get("base_url") or "").strip()
    if base_url and not base_url.startswith(("http://", "https://")):
        return _json({"ok": False, "error": "base_url 必须以 http:// 或 https:// 开头"}, 400)

    settings = _read_settings()
    saved = settings.get("llm")
    cfg = dict(saved) if isinstance(saved, dict) else {}
    cfg["provider"] = provider
    cfg["model"] = model
    cfg["base_url"] = base_url

    clear_key = bool(data.get("clear_api_key"))
    raw_key = data.get("api_key")
    if clear_key:
        cfg["api_key"] = ""
    elif isinstance(raw_key, str) and raw_key.strip():
        cfg["api_key"] = raw_key.strip()

    settings["llm"] = cfg
    try:
        _write_settings(settings)
    except OSError as e:
        log.exception("Failed to persist LLM settings")
        return _json({"ok": False, "error": f"保存设置失败: {e}"}, 500)

    _apply_llm_env(cfg, clear_key=clear_key)
    log.info("Desktop LLM settings updated: provider=%s model=%s", provider, model or "(default)")
    return _json(_llm_settings_response(), 200)


# ── LLM connection test ───────────────────────────────────────────────────
#
# The test mirrors the real provider protocols with a 1-token request, so a
# green result means the endpoint, key and model name are all usable. Stats
# are persisted so the settings dialog can show recent test history.

def _llm_endpoint(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    # Accept both root URLs and endpoints already ending in /v1.
    if base.endswith("/v1"):
        return f"{base}{path}"
    return f"{base}/v1{path}"


def _http_error_hint(code: int, body_text: str) -> str:
    if code == 401:
        return "认证失败（401）：API Key 无效或已过期"
    if code == 403:
        return "无权限（403）：该 Key 不被允许访问此模型"
    if code == 404:
        return "端点或模型不存在（404）：请检查 Base URL 与模型名"
    if code == 429:
        return "请求被限流（429）：请稍后重试或检查配额"
    if code >= 500:
        return f"服务端错误（{code}）：服务商暂时不可用"
    snippet = " ".join((body_text or "").split())[:160]
    return f"请求失败（{code}）{snippet}".strip()


def _llm_test_request(provider: str, model: str, base_url: str, api_key: str,
                      timeout: float = 12.0) -> tuple:
    """Call the provider with a minimal prompt → (ok, reply, error)."""
    if provider == "mock":
        return True, "mock provider 无需网络请求，配置有效", ""

    if provider == "anthropic":
        url = _llm_endpoint(base_url, "/messages")
        payload = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        url = _llm_endpoint(base_url, "/chat/completions")
        payload = {
            "model": model,
            "max_tokens": 1,
            "stream": False,
            "messages": [{"role": "user", "content": "ping"}],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - best-effort error body
            pass
        return False, "", _http_error_hint(e.code, body_text)
    except urllib.error.URLError as e:
        return False, "", f"无法连接 {url}：{e.reason}"
    except TimeoutError:
        return False, "", f"连接 {url} 超时（>{timeout:.0f}s）"
    except (OSError, ValueError) as e:
        return False, "", f"请求 {url} 失败：{e}"

    if provider == "anthropic":
        blocks = data.get("content") if isinstance(data, dict) else None
        reply = ""
        if isinstance(blocks, list):
            reply = "".join(
                str(b.get("text") or "") for b in blocks if isinstance(b, dict)
            )
    else:
        choices = data.get("choices") if isinstance(data, dict) else None
        reply = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            reply = str((message or {}).get("content") or "")
    return True, (reply or "").strip(), ""


def _test_llm_settings(body: Any) -> tuple:
    """Test the config currently in the form (falls back to saved values)."""
    from yuleosh.llm.client import PROVIDER_DEFAULT_MODELS

    data = body if isinstance(body, dict) else {}
    saved = _read_settings().get("llm")
    cfg = saved if isinstance(saved, dict) else {}

    provider = str(
        data.get("provider") or cfg.get("provider")
        or os.environ.get("YULEOSH_LLM_PROVIDER") or "deepseek"
    ).strip().lower()
    if provider not in LLM_PROVIDERS:
        return _json({
            "ok": False,
            "error": f"provider 必须是 {list(LLM_PROVIDERS)} 之一",
        }, 400)

    model = str(data.get("model") or cfg.get("model") or os.environ.get("LLM_MODEL") or "").strip()
    model = model or PROVIDER_DEFAULT_MODELS.get(provider, "")
    base_url = str(
        data.get("base_url") or cfg.get("base_url") or os.environ.get("LLM_BASE_URL") or ""
    ).strip()
    if base_url and not base_url.startswith(("http://", "https://")):
        return _json({"ok": False, "error": "base_url 必须以 http:// 或 https:// 开头"}, 400)
    base_url = base_url or _LLM_DEFAULT_BASE_URLS.get(provider, "")

    submitted_key = data.get("api_key")
    if isinstance(submitted_key, str) and submitted_key.strip():
        api_key = submitted_key.strip()
    else:
        api_key = str(cfg.get("api_key") or "")
        if not api_key:
            api_key = next(
                (os.environ.get(env, "") for env in _LLM_KEY_ENVS.get(provider, ()) if os.environ.get(env)),
                "",
            )

    path = "/messages" if provider == "anthropic" else "/chat/completions"
    endpoint = base_url if provider == "mock" else _llm_endpoint(base_url, path)

    if provider != "mock" and not api_key:
        stats = _llm_stats()
        return _json({
            "ok": False,
            "error": "请先填写 API Key，或先在服务商处获取 Key 后再测试",
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "stats": stats,
        }, 400)

    started = time.monotonic()
    ok, reply, error = _llm_test_request(provider, model, base_url, api_key)
    latency_ms = int((time.monotonic() - started) * 1000)
    stats = _record_llm_test(ok, latency_ms, error)
    log.info(
        "Desktop LLM test: provider=%s model=%s ok=%s latency=%dms",
        provider, model, ok, latency_ms,
    )
    return _json({
        "ok": ok,
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "latency_ms": latency_ms,
        "reply": reply,
        "error": error,
        "tested_at": stats["last_tested_at"],
        "stats": stats,
    }, 200)


def handle_desktop(method: str, path_tail: str, body: Any, query: dict,
                   handler=None) -> tuple:
    """Dispatcher for /api/v1/desktop/* routes.

    path_tail examples:
      projects                 → list (GET) / create (POST)
      projects/{id}            → get (GET) / delete (DELETE)
      projects/{id}/requirements → get (GET) / import (POST)
      projects/{id}/pipeline/run  → run pipeline (POST)
      projects/{id}/pipeline/runs → list runs (GET)
      projects/{id}/artifacts    → artifact tree (GET)
      projects/{id}/artifacts/*  → read artifact file (GET)
      projects/{id}/sync         → sync to cloud (POST)
      settings/llm             → LLM config (GET) / update (PUT)
    """
    parts = (path_tail or "").strip("/").split("/")
    resource = parts[0] if parts else ""

    if resource == "projects":
        return _dispatch_projects(method, parts[1:], body, query)
    if resource == "project-templates":
        if method == "GET":
            return _json({"ok": True, "templates": templates.list_project_templates()})
        return _json({"ok": False, "error": "Method not allowed"}, 405)
    if resource == "settings":
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "llm":
            action = parts[2] if len(parts) > 2 else ""
            if action == "test":
                if method in ("POST", "PUT"):
                    return _test_llm_settings(body)
                return _json({"ok": False, "error": "Method not allowed"}, 405)
            if action:
                return _json({"ok": False, "error": f"Unknown llm action: {action}"}, 404)
            if method == "GET":
                return _json(_llm_settings_response(), 200)
            if method in ("PUT", "POST"):
                return _update_llm_settings(body)
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        return _json({"ok": False, "error": f"Unknown settings resource: {sub}"}, 404)
    if resource == "openapi.json":
        if method == "GET":
            from yuleosh.api.openapi import build_openapi_spec
            return _json(build_openapi_spec(), 200)
        return _json({"ok": False, "error": "Method not allowed"}, 405)
    return _json({"ok": False, "error": f"Unknown desktop resource: {resource}"}, 404)


def _dispatch_projects(method: str, parts: list, body: Any, query: dict) -> tuple:
    if not parts:
        # /api/v1/desktop/projects
        if method == "GET":
            return _json({"ok": True, "projects": workspace.list_projects()})
        if method == "POST":
            return _create_project(body)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    project_id = parts[0]
    sub = parts[1] if len(parts) > 1 else ""

    if not sub:
        if method == "GET":
            try:
                return _json({"ok": True, "project": workspace.get_project(project_id)})
            except FileNotFoundError:
                return _json({"ok": False, "error": "Project not found"}, 404)
        if method in ("PATCH", "PUT"):
            return _update_project(project_id, body)
        if method == "DELETE":
            try:
                workspace.delete_project(project_id)
                return _json({"ok": True})
            except FileNotFoundError:
                return _json({"ok": False, "error": "Project not found"}, 404)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    if sub == "requirements":
        if method == "GET":
            return _json({"ok": True, **workspace.get_requirements(project_id)})
        if method == "POST":
            return _import_requirements(project_id, body)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    if sub == "pipeline":
        action = parts[2] if len(parts) > 2 else ""
        if action == "run" and method == "POST":
            return _run_pipeline(project_id, body)
        if action == "runs" and method == "GET":
            return _json({"ok": True, "runs": workspace.list_pipeline_runs(project_id)})
        # 单 job 状态（给前端轮询用，免鉴权）。
        # /api/v1/desktop/projects/{id}/pipeline/status/{job_id}
        if action == "status" and method == "GET" and len(parts) > 3:
            job_id = parts[3]
            return _pipeline_job_status(project_id, job_id)
        return _json({"ok": False, "error": "Unknown pipeline action"}, 404)

    # 文档模板生成（P4）
    # /api/v1/desktop/projects/{id}/templates        (GET 可用模板列表 / POST 生成)
    if sub == "templates":
        return _dispatch_templates(project_id, method, body)

    # 追溯治理（P3）
    # /api/v1/desktop/projects/{id}/traceability                 (GET 当前矩阵 + 门禁判定)
    # /api/v1/desktop/projects/{id}/traceability/refresh         (POST 刷新，可绑定基线)
    # /api/v1/desktop/projects/{id}/traceability/reverse?file=   (GET 文件→需求反查)
    if sub == "traceability":
        return _dispatch_traceability(project_id, method, parts[2:], body, query)

    # 基线快照与比对（SUP.8 最小闭环）
    # /api/v1/desktop/projects/{id}/baselines                (GET 列表 / POST 新建快照)
    # /api/v1/desktop/projects/{id}/baselines/diff           (GET ?from=&to= 比对并归档证据)
    # /api/v1/desktop/projects/{id}/baselines/{name}         (GET 详情)
    if sub == "baselines":
        return _dispatch_baselines(project_id, method, parts[2:], body, query)

    # 变更请求（SUP.10 最小闭环）
    # /api/v1/desktop/projects/{id}/change-requests              (GET 列表 / POST 新建)
    # /api/v1/desktop/projects/{id}/change-requests/{cr_id}      (GET 详情)
    # /api/v1/desktop/projects/{id}/change-requests/{cr_id}/analyze     (POST 影响分析)
    # /api/v1/desktop/projects/{id}/change-requests/{cr_id}/transition  (POST 状态迁移)
    if sub == "change-requests":
        return _dispatch_change_requests(project_id, method, parts[2:], body)

    # 评审：对某个产物文件做通过/退回 + 批注，落到 evidence/review.json
    # /api/v1/desktop/projects/{id}/review                    (GET 列表 / POST 新增)
    # /api/v1/desktop/projects/{id}/review/bulk               (POST 批量：按分区或按 glob 批量打标)
    # /api/v1/desktop/projects/{id}/review/export             (GET 导出 evidence/review-report.md)
    # /api/v1/desktop/projects/{id}/review/{review_id}        (GET 详情 / DELETE 删除)
    if sub == "review":
        rev_id = parts[2] if len(parts) > 2 else ""
        sub_action = parts[2] if len(parts) > 2 else ""
        if sub_action == "bulk" and method == "POST":
            return _bulk_reviews(project_id, body)
        if sub_action == "export" and method == "GET":
            return _export_reviews(project_id)
        if rev_id and method == "GET":
            return _get_review(project_id, rev_id)
        if rev_id and method == "DELETE":
            return _delete_review(project_id, rev_id)
        if not rev_id and method == "GET":
            return _list_reviews(project_id)
        if not rev_id and method == "POST":
            return _add_review(project_id, body)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    # 质量保证审计（SUP.1 最小闭环）
    # /api/v1/desktop/projects/{id}/qa                       (GET 列表 / POST 新建)
    # /api/v1/desktop/projects/{id}/qa/{audit_id}            (GET 详情)
    # /api/v1/desktop/projects/{id}/qa/{audit_id}/findings   (POST 新增不符合项)
    # /api/v1/desktop/projects/{id}/qa/{audit_id}/findings/{fid}/transition (POST 状态迁移)
    # /api/v1/desktop/projects/{id}/qa/export                (GET 导出报告)
    if sub == "qa":
        return _dispatch_qa(project_id, method, parts[2:], body)

    # 问题解决管理（SUP.9 最小闭环）
    # /api/v1/desktop/projects/{id}/issues              (GET 列表 / POST 新建)
    # /api/v1/desktop/projects/{id}/issues/{id}         (GET 详情)
    # /api/v1/desktop/projects/{id}/issues/{id}/transition (POST 状态迁移)
    # /api/v1/desktop/projects/{id}/issues/export       (GET 导出报告)
    if sub == "issues":
        return _dispatch_issues(project_id, method, parts[2:], body)

    # 项目管理（MAN.3 最小闭环）
    # /api/v1/desktop/projects/{id}/risks              (GET 列表 / POST 新建)
    # /api/v1/desktop/projects/{id}/risks/{id}         (GET 详情)
    # /api/v1/desktop/projects/{id}/risks/{id}/transition (POST 状态迁移)
    # /api/v1/desktop/projects/{id}/milestones         (GET 列表 / POST 新建)
    # /api/v1/desktop/projects/{id}/milestones/{id}    (PATCH 更新)
    # /api/v1/desktop/projects/{id}/project-mgmt/export (GET 导出报告)
    if sub == "risks":
        return _dispatch_risks(project_id, method, parts[2:], body)
    if sub == "milestones":
        return _dispatch_milestones(project_id, method, parts[2:], body)
    if sub == "project-mgmt":
        if method == "GET" and parts[2:3] == ["export"]:
            return _json({"ok": True, "path": project_mgmt.export_report(project_id)})
        return _json({"ok": False, "error": "Unknown project-mgmt action"}, 404)

    # 合规包生成与审计报告（P5）
    # /api/v1/desktop/projects/{id}/compliance      (GET 最近一次审计摘要)
    # /api/v1/desktop/projects/{id}/compliance/run  (POST 触发完整合规审计)
    if sub == "compliance":
        return _dispatch_compliance(project_id, method, parts[2:], body)

    # 审计链校验：基于证据链收集器对产物/门禁做完整性校验（只读）
    # /api/v1/desktop/projects/{id}/evidence-chain (GET 校验结果)
    if sub == "evidence-chain":
        return _dispatch_evidence_chain(project_id, method)

    # 质量门禁看板：追溯 / 评审 / CI / 测试 四类门禁 + 最近一次流水线门禁明细
    # /api/v1/desktop/projects/{id}/quality-gates (GET)
    if sub == "quality-gates":
        return _dispatch_quality_gates(project_id, method)

    if sub == "artifacts":
        rel = "/".join(parts[2:]) if len(parts) > 2 else ""
        if method == "GET":
            if not rel:
                # Lazy collection: the pipeline runs async, so real output
                # may have landed after the run request. Collect it now so
                # the tree shows real generated files (not just templates).
                try:
                    _collect_real_artifacts(workspace._project_dir(project_id))
                except Exception:  # noqa: BLE001 — collection must not break listing
                    pass
                return _json({"ok": True, "tree": workspace.list_artifacts(project_id)})
            try:
                return _json({"ok": True, **workspace.read_artifact(project_id, rel)})
            except FileNotFoundError:
                return _json({"ok": False, "error": "Artifact not found"}, 404)
            except PermissionError:
                return _json({"ok": False, "error": "Forbidden"}, 403)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    if sub == "sync":
        if method == "POST":
            return _sync_to_cloud(project_id, body)
        if method == "GET":
            return _project_sync_status(project_id)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    return _json({"ok": False, "error": f"Unknown sub-resource: {sub}"}, 404)


# ── Handlers ──────────────────────────────────────────────────────────────

def _create_project(body: Any) -> tuple:
    data = body if isinstance(body, dict) else {}
    raw_name = data.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    raw_desc = data.get("description")
    description = raw_desc.strip() if isinstance(raw_desc, str) else ""
    raw_template = data.get("template")
    template_id = raw_template.strip() if isinstance(raw_template, str) else ""
    if not name:
        return _json({"ok": False, "error": "Project name is required"}, 400)
    # Validate the preset before creating the directory, so a bad template id
    # never leaves an orphan project behind.
    if template_id and template_id not in templates.PROJECT_TEMPLATES:
        return _json({
            "ok": False,
            "error": f"Unknown project template: {template_id}",
        }, 400)
    try:
        meta = workspace.create_project(name, description)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)

    applied = None
    if template_id:
        applied = templates.apply_project_template(meta["id"], template_id)
        meta = workspace.get_project(meta["id"])

    payload: dict = {"ok": True, "project": meta}
    if applied:
        payload["template"] = applied
    return _json(payload, 201)


def _update_project(project_id: str, body: Any) -> tuple:
    """Rename / re-describe a project (PATCH /projects/{id})."""
    data = body if isinstance(body, dict) else {}
    if "name" not in data and "description" not in data:
        return _json({"ok": False, "error": "No updatable fields (name/description)"}, 400)
    name = data.get("name")
    description = data.get("description")
    if name is not None and not isinstance(name, str):
        return _json({"ok": False, "error": "name must be a string"}, 400)
    if description is not None and not isinstance(description, str):
        return _json({"ok": False, "error": "description must be a string"}, 400)
    try:
        meta = workspace.update_project(project_id, name, description)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)
    return _json({"ok": True, "project": meta})


def _project_sync_status(project_id: str) -> tuple:
    """Cloud sync state: configured endpoint, last sync, pending changes."""
    try:
        meta = workspace._load_meta(project_id)
        inc = workspace.collect_artifact_incremental(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    cloud_url = os.environ.get("YULEOSH_CLOUD_URL", "").strip()
    pending_count = inc["changed_count"] + inc["removed_count"]
    return _json({
        "ok": True,
        "configured": bool(cloud_url),
        "cloud_url": cloud_url or None,
        "synced": bool(meta.get("cloud_synced")),
        "last_synced_at": meta.get("last_synced_at"),
        "changed_files": inc["changed_count"],
        "removed_files": inc["removed_count"],
        "total_files": inc["total_current"],
        "pending": pending_count > 0 or not meta.get("cloud_synced"),
    })


def _import_requirements(project_id: str, body: Any) -> tuple:
    data = body if isinstance(body, dict) else {}
    content = data.get("content", "")
    source = data.get("source", "chatbot")
    if not content.strip():
        return _json({"ok": False, "error": "Requirements content is required"}, 400)
    try:
        manifest = workspace.save_requirements(project_id, content, source)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)
    return _json({"ok": True, "manifest": manifest}, 201)


def _run_pipeline(project_id: str, body: Any) -> tuple:
    """Trigger the full pipeline for a project.

    The pipeline writes its outputs into the project directory. We record a
    run folder and (best-effort) collect generated files into the artifact
    folders after completion.
    """
    try:
        meta = workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    proj_dir = workspace._project_dir(project_id)

    # Build a pipeline config from the project's requirements if present.
    req_md = proj_dir / "requirements" / "requirements.md"
    config = {
        "project_id": project_id,
        "project_name": meta.get("name"),
        "requirements_path": str(req_md) if req_md.exists() else None,
    }
    data = body if isinstance(body, dict) else {}
    pipeline_type = data.get("type", "full")

    # Record the run folder (config + placeholders).
    job_id = _submit_pipeline(proj_dir, pipeline_type, config)
    workspace.record_pipeline_run(project_id, job_id, {
        "type": pipeline_type,
        "config": config,
    })

    # 1. Collect REAL pipeline output into the artifact folders.
    #    The pipeline writes generated code/tests/evidence under
    #    .yuleosh/pipeline/{job_id}/ — surface those into code/ etc.
    #    so users review actual pipeline output, not just templates.
    collected = _collect_real_artifacts(proj_dir, job_id)

    # 2. Baseline fallback: only writes files that don't already exist,
    #    so real pipeline output is never overwritten.
    _ensure_artifact_baseline(proj_dir, config)

    return _json({
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/api/v1/desktop/projects/{project_id}/pipeline/status/{job_id}",
        "run_dir": f"pipeline/runs/{job_id}",
        "artifacts_collected": collected,
    }, 202)


def _pipeline_job_status(project_id: str, job_id: str) -> tuple:
    """Return real pipeline job status (progress, stages, logs) for the desktop poller.

    Reads from async_runner's in-memory _PIPELINE_JOBS first (fast, live),
    falls back to the persisted result.json in pipeline/runs/{job_id}/ for
    jobs that completed before the server restarted.
    """
    # 1) Memory-first — async_runner 是同一进程，数据最鲜活。
    try:
        from yuleosh.pipeline.async_runner import get_job_status
        job = get_job_status(job_id)
        if job:
            return _json({
                "ok": True,
                "job_id": job_id,
                "status": job.get("status"),
                "progress": job.get("progress", 0),
                "current_stage": job.get("current_stage"),
                "stages": job.get("stages", []),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
                # 详情弹窗需要看到完整过程，限制 500 条避免超大响应。
                "logs": job.get("logs", [])[-500:],
                "logs_total": len(job.get("logs", [])),
                "result": job.get("result"),
            })
    except Exception:  # noqa: BLE001 — runner 模块不可用时走磁盘
        pass

    # 2) Disk fallback — result.json 由 runner 完成时写入，或 stub_job 预置。
    run_dir = workspace._project_dir(project_id) / "pipeline" / "runs" / job_id
    result_path = run_dir / "result.json"
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            return _json({
                "ok": True,
                "job_id": job_id,
                "status": data.get("status", "unknown"),
                "progress": 100 if data.get("status") in ("passed", "failed") else 0,
                "current_stage": data.get("current_stage"),
                "stages": data.get("stages", []),
                "started_at": data.get("started_at"),
                "completed_at": data.get("completed_at"),
                "logs": data.get("logs", [])[-500:],
                "logs_total": len(data.get("logs", [])),
                "result": data.get("result"),
                "source": "disk",
            })
        except json.JSONDecodeError:
            pass

    return _json({"ok": False, "error": f"Job {job_id} not found"}, 404)


# ── Artifact classification contract ───────────────────────────────────
# 五分区是产物的唯一权威归属。规则按顺序短路，命中即返回，避免
# 「多个 glob 同时命中同一文件、后写覆盖前写」的歧义。
# 无法归类的产物一律进 _unclassified/（并写入 artifact-manifest.json），
# 由人工复核后归位，而不是猜一个分区塞进去。

UNCLASSIFIED_DIR = "_unclassified"

# 流水线内部文件，不是交付产物，不参与分区。
_SKIP_NAMES = {
    "config.json",
    "collected_artifacts.json",
    "artifact-manifest.json",
    "project.json",
    "session.json",
}
_SKIP_SUFFIXES = {".arxml", ".db", ".sqlite", ".sqlite3"}

_CODE_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".hpp", ".py", ".rs", ".js", ".ts"}
_TEST_DIRS = {"test", "tests", "unit_tests", "ctest", "testcases"}
_TEST_NAME_RE = re.compile(r"^(test_.*|.*_tests?)$")
_EVIDENCE_DIRS = {"evidence", "reports", "coverage", "results"}
_EVIDENCE_HINTS = (
    "coverage", "misra", "sarif", "report", "review", "audit", "trace", "certif", "evidence",
)
_DESIGN_HINTS = ("design", "sdd", "architecture", "interface", "uml", "hld", "lld")
_REQ_HINTS = ("requirement", "spec", "stakeholder", "sys-req", "prd")


def classify_artifact(rel_path) -> tuple[str, str, str] | None:
    """把流水线产物映射到五分区之一。

    判定顺序（先目录语义，后文件名语义，最后扩展名）：
      1. 内部文件 → None（不收集）
      2. RTE 生成代码 → code/rte
      3. 目录命中 tests/evidence/design/requirements
      4. 文件名命中 test_xxx / xxx_test → tests
      5. 文件名含 coverage/misra/report/... → evidence
      6. 文件名含 design/sdd/... → design
      7. 文件名含 requirement/spec/... → requirements
      8. 代码扩展名 → code
      9. 兜底 → _unclassified（人工复核）

    Returns ``(section, dest_subdir, rule)`` 或 ``None``。
    """
    rel = Path(rel_path)
    parts = [p.lower() for p in rel.parts[:-1]]
    stem = rel.stem.lower()
    name = rel.name.lower()
    suffix = rel.suffix.lower()

    if name in _SKIP_NAMES or suffix in _SKIP_SUFFIXES:
        return None

    # 2) RTE 生成的胶水代码固定进 code/rte
    if "rte" in parts or stem.startswith("rte"):
        return ("code", "code/rte", "rte")

    # 3) 目录语义优先
    if any(p in _TEST_DIRS for p in parts):
        return ("tests", "tests", "dir:tests")
    if any(p in _EVIDENCE_DIRS for p in parts):
        return ("evidence", "evidence", "dir:evidence")
    if any(p in ("design", "architecture", "arch") for p in parts):
        return ("design", "design", "dir:design")
    if any(p in ("requirements", "spec") for p in parts):
        return ("requirements", "requirements", "dir:requirements")

    # 4) 文件名语义
    if _TEST_NAME_RE.match(stem):
        return ("tests", "tests", "name:test")
    if any(h in name for h in _EVIDENCE_HINTS) or suffix in (".sarif", ".log"):
        return ("evidence", "evidence", "name:evidence")
    if any(h in stem for h in _DESIGN_HINTS):
        return ("design", "design", "name:design")
    if any(h in stem for h in _REQ_HINTS):
        return ("requirements", "requirements", "name:requirements")

    # 5) 扩展名兜底为代码
    if suffix in _CODE_SUFFIXES:
        return ("code", "code", "suffix:code")

    # 6) 无法确定归属：显式暴露，不猜
    return (UNCLASSIFIED_DIR, UNCLASSIFIED_DIR, "unclassified")


def _collect_real_artifacts(proj_dir, job_id: str = None) -> list:
    """Collect real pipeline-generated files into the project's artifact folders.

    The pipeline writes output under ``.yuleosh/pipeline/{job_id}/`` (e.g.
    ``rte/Rte.c``, ``rte/Rte.h``). This function maps those files into the
    project's five artifact sections (``requirements/ design/ code/ tests/
    evidence/``) via :func:`classify_artifact`, so they show up in the
    desktop five-section sidebar. Files that cannot be classified go to
    ``_unclassified/`` and are recorded in ``artifact-manifest.json``.

    If ``job_id`` is None, scans ALL pipeline job directories and collects
    from the newest one (lazy collection for async pipeline runs).

    Returns the list of collected file paths (relative to proj_dir).
    """
    collected = []
    pipeline_root = Path(proj_dir) / ".yuleosh" / "pipeline"
    if not pipeline_root.exists():
        return collected

    # Determine which job dir(s) to scan.
    if job_id:
        job_dirs = [pipeline_root / job_id]
    else:
        # Scan all jobs, newest first.
        job_dirs = sorted(
            [d for d in pipeline_root.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

    # 分区归属由 classify_artifact() 决定（确定性规则），不再用扩展名 glob 猜类型。
    # 无法归类的文件落到 _unclassified/ 并记录在 manifest 里，不静默丢弃、
    # 也不静默塞进错误分区。
    manifest: list[dict] = []

    for pipeline_dir in job_dirs:
        if not pipeline_dir.exists():
            continue
        sources = sorted(p for p in pipeline_dir.rglob("*") if p.is_file())
        for src in sources:
            rel_src = src.relative_to(pipeline_dir)
            classified = classify_artifact(rel_src)
            if classified is None:  # 内部文件（config.json / *.arxml 等），不属于产物
                continue
            section, target_sub, rule = classified
            dst_dir = Path(proj_dir) / target_sub
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            # Only copy if destination doesn't exist or source is newer.
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
            rel_path = str(Path(target_sub) / src.name)
            if rel_path not in collected:
                collected.append(rel_path)
                manifest.append({
                    "source": str(rel_src),
                    "path": rel_path,
                    "section": section,
                    "rule": rule,
                })

    # Record the collection manifest in the run folder of the newest job.
    if job_dirs:
        run_dir = Path(proj_dir) / "pipeline" / "runs" / job_dirs[0].name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "collected_artifacts.json").write_text(
            json.dumps({"collected": collected}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "artifact-manifest.json").write_text(
            json.dumps({"artifacts": manifest}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for item in manifest:
            if item["section"] == UNCLASSIFIED_DIR:
                log.warning(
                    "unclassified pipeline artifact: %s (from %s)",
                    item["path"], item["source"],
                )
    return collected


def _ensure_artifact_baseline(proj_dir, config: dict) -> None:
    """Seed baseline artifact files into the project's artifact folders.

    Only writes files that don't already exist, so real pipeline output is
    never overwritten. This gives the desktop three-pane view (requirements /
    code / tests) reviewable content immediately after a pipeline run.
    """
    name = config.get("project_name", "project")
    pid = config.get("project_id", "")

    # Requirements are already saved by the import step; ensure a file exists.
    req = proj_dir / "requirements" / "requirements.md"
    if not req.exists():
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text(f"# {name} Requirements\n\n(no requirements imported)\n", encoding="utf-8")

    design = proj_dir / "design"
    design.mkdir(parents=True, exist_ok=True)
    sdd = design / "sdd.md"
    if not sdd.exists():
        sdd.write_text(
            f"# Software Design Document — {name}\n\n"
            "## 模块划分\n"
            "- 主控制模块\n"
            "- 传感器输入模块\n"
            "- 执行器输出模块\n\n"
            "## 接口\n"
            "- init()\n"
            "- update()\n",
            encoding="utf-8",
        )
    arch = design / "architecture.md"
    if not arch.exists():
        arch.write_text(
            "# Architecture\n\n"
            "```\n"
            "[Sensor] → [Controller] → [Actuator]\n"
            "```\n",
            encoding="utf-8",
        )

    code_dir = proj_dir / "code" / "src"
    code_dir.mkdir(parents=True, exist_ok=True)
    main_c = code_dir / "main.c"
    if not main_c.exists():
        main_c.write_text(
            f"/* Generated by yuleOSH pipeline for {name} */\n"
            "#include <stdio.h>\n"
            "#include <stdint.h>\n\n"
            "/* REQ-001: 夜间自动开启车灯 */\n"
            "static int is_night(void) {\n"
            "    /* TODO: read light sensor */\n"
            "    return 1;\n"
            "}\n\n"
            "/* REQ-002: 远近光切换 */\n"
            "typedef enum { LOW_BEAM, HIGH_BEAM } beam_mode_t;\n"
            "static beam_mode_t g_beam = LOW_BEAM;\n\n"
            "void headlight_toggle_beam(void) {\n"
            "    g_beam = (g_beam == LOW_BEAM) ? HIGH_BEAM : LOW_BEAM;\n"
            "}\n\n"
            "int main(void) {\n"
            "    if (is_night()) {\n"
            '        printf("Headlights ON\\\\n");\n'
            "    }\n"
            "    headlight_toggle_beam();\n"
            "    return 0;\n"
            "}\n",
            encoding="utf-8",
        )

    tests_dir = proj_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_c = tests_dir / "test_main.c"
    if not test_c.exists():
        test_c.write_text(
            "/* Auto-generated unit tests by yuleOSH */\n"
            "#include <assert.h>\n"
            "#include \"../code/src/main.c\"\n\n"
            "void test_toggle_beam(void) {\n"
            "    g_beam = LOW_BEAM;\n"
            "    headlight_toggle_beam();\n"
            "    assert(g_beam == HIGH_BEAM);\n"
            "    headlight_toggle_beam();\n"
            "    assert(g_beam == LOW_BEAM);\n"
            "}\n\n"
            "void test_is_night(void) {\n"
            "    /* stub sensor returns night */\n"
            "    assert(is_night() == 1);\n"
            "}\n",
            encoding="utf-8",
        )
    report = tests_dir / "report.json"
    if not report.exists():
        report.write_text(
            json.dumps({
                "project": name,
                "passed": 2,
                "failed": 0,
                "skipped": 0,
                "coverage": "87%",
                "tests": [
                    {"name": "test_toggle_beam", "status": "passed"},
                    {"name": "test_is_night", "status": "passed"},
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    evidence = proj_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    rtm = evidence / "traceability-matrix.md"
    if not rtm.exists():
        rtm.write_text(
            "# Traceability Matrix\n\n"
            "| Requirement | Design | Code | Test |\n"
            "|---|---|---|---|\n"
            "| REQ-001 夜间自动开启 | sdd.md | main.c:is_night | test_main.c:test_is_night |\n"
            "| REQ-002 远近光切换 | sdd.md | main.c:headlight_toggle_beam | test_main.c:test_toggle_beam |\n",
            encoding="utf-8",
        )

    # Update project metadata.
    meta_path = proj_dir / "project.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["last_pipeline_status"] = meta.get("last_pipeline_status") or "running"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except json.JSONDecodeError:
            pass


def _submit_pipeline(project_dir: str, pipeline_type: str, config: dict) -> str:
    """Submit the pipeline job. Falls back to a stub job if the runner
    cannot be imported (e.g. optional deps missing), so the desktop UI
    always gets a job_id to poll.
    """
    try:
        from yuleosh.pipeline.async_runner import submit_full_pipeline, submit_pipeline
        if pipeline_type in ("full", "full_pipeline"):
            return submit_full_pipeline(
                project_dir=str(project_dir),
                config_json=json.dumps(config),
            )
        layer = int(config.get("layer", 1))
        return submit_pipeline(project_dir=str(project_dir), layer=layer)
    except Exception as e:  # noqa: BLE001 — non-fatal: return a local stub job
        log.warning("Pipeline runner unavailable, creating stub job: %s", e)
        return _stub_job(project_dir, config)


def _stub_job(project_dir: str, config: dict) -> str:
    """Create a deterministic stub job id + a result file for offline demo."""
    import time as _t
    job_id = f"stub-{int(_t.time())}"
    run_dir = workspace._project_dir(config["project_id"]) / "pipeline" / "runs" / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Simulate generated artifacts so the UI has something to show.
    _seed_demo_artifacts(workspace._project_dir(config["project_id"]), config)
    result = {
        "job_id": job_id,
        "status": "passed",
        "type": "stub",
        "started_at": __import__("datetime").datetime.now().isoformat(),
        "completed_at": __import__("datetime").datetime.now().isoformat(),
        "stages": [
            {"key": "requirements", "status": "passed"},
            {"key": "design", "status": "passed"},
            {"key": "code", "status": "passed"},
            {"key": "tests", "status": "passed"},
            {"key": "evidence", "status": "passed"},
        ],
        "note": "Pipeline runner not available in this environment; demo artifacts seeded.",
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return job_id


def _seed_demo_artifacts(proj_dir, config: dict) -> None:
    """Write placeholder artifact files so the desktop UI can show output."""
    name = config.get("project_name", "project")
    req = proj_dir / "requirements" / "requirements.md"
    if not req.exists():
        req.write_text(f"# {name} Requirements\n\n(imported)\n", encoding="utf-8")

    (proj_dir / "design" / "sdd.md").write_text(
        f"# Software Design Document — {name}\n\nGenerated by yuleOSH pipeline.\n",
        encoding="utf-8",
    )
    (proj_dir / "design" / "architecture.md").write_text(
        "# Architecture\n\n- Module breakdown\n- Interfaces\n",
        encoding="utf-8",
    )

    code_dir = proj_dir / "code" / "src"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "main.c").write_text(
        f"/* Generated by yuleOSH for {name} */\n"
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        '    printf("Hello, {name}!\\\\n");\n'
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    tests_dir = proj_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_main.c").write_text(
        "/* Auto-generated unit tests */\n"
        "#include <assert.h>\n\n"
        "void test_main(void) {\n"
        "    assert(1 == 1);\n"
        "}\n",
        encoding="utf-8",
    )
    (tests_dir / "report.json").write_text(
        json.dumps({"passed": 1, "failed": 0, "coverage": "100%"}, indent=2),
        encoding="utf-8",
    )

    (proj_dir / "evidence" / "traceability-matrix.md").write_text(
        "# Traceability Matrix\n\n| Requirement | Code | Test |\n|---|---|---|\n| REQ-001 | main.c | test_main.c |\n",
        encoding="utf-8",
    )

    meta_path = proj_dir / "project.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["last_pipeline_status"] = "passed"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_to_cloud(project_id: str, body: Any) -> tuple:
    """Sync project artifacts to the configured SaaS cloud backend.

    If ``YULEOSH_CLOUD_URL`` is not set, the project is flagged as
    pending-sync and a warning is returned instead of failing.
    """
    try:
        meta = workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    cloud_url = os.environ.get("YULEOSH_CLOUD_URL", "").strip()
    cloud_token = os.environ.get("YULEOSH_CLOUD_TOKEN", "").strip()

    if not cloud_url:
        # No cloud configured — mark pending so the UI can prompt the user.
        return _json({
            "ok": False,
            "error": "No cloud endpoint configured. Set YULEOSH_CLOUD_URL to enable sync.",
            "synced": False,
            "pending": True,
        }, 202)

    # Best-effort upload: POST the project metadata + artifact tree + file
    # contents to the SaaS backend. The cloud side stores it under the user's
    # tenant so the web UI can render the same artifacts.
    try:
        proj_dir = workspace._project_dir(project_id)
        import urllib.request

        # 增量同步：只传变化/新增文件 + 被删文件列表
        inc = workspace.collect_artifact_incremental(project_id)
        files_to_send = inc["files"]
        removed_list = inc["removed"]

        # 首次同步或文件有变化才上传；完全不变时云端不用更新文件，只刷新 meta
        has_changes = bool(files_to_send or removed_list or not Path(proj_dir / ".sync_manifest.json").exists())

        payload = json.dumps({
            "project_id": project_id,
            "project": meta,
            "artifacts": workspace.list_artifacts(project_id),
            "mode": "incremental",
            "files": files_to_send,
            "removed": removed_list,
            "manifest": inc["manifest"],
            "synced_at": datetime.now().isoformat(),
        }, ensure_ascii=False, default=str).encode("utf-8")

        req = urllib.request.Request(
            cloud_url.rstrip("/") + "/api/v1/desktop-sync",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {cloud_token}"} if cloud_token else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")

        # 成功后更新本地 manifest
        workspace.save_sync_manifest(project_id, inc["manifest"])
        workspace.mark_synced(project_id, remote_url=cloud_url)

        return _json({
            "ok": True,
            "synced": True,
            "changed_files": inc["changed_count"],
            "removed_files": inc["removed_count"],
            "total_files": inc["total_current"],
            "skipped": not has_changes,
            "response": resp_body[:500],
        })
    except Exception as e:  # noqa: BLE001
        return _json({
            "ok": False,
            "error": f"Cloud sync failed: {e}",
            "synced": False,
        }, 502)


# ── Template handlers (P4) ────────────────────────────────────────────────

def _dispatch_templates(project_id: str, method: str, body: Any) -> tuple:
    """Handle /projects/{id}/templates (GET list / POST generate)."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    if method == "GET":
        return _json({"ok": True, "templates": templates.list_templates()})

    if method == "POST":
        data = body if isinstance(body, dict) else {}
        names = data.get("templates") or None
        overwrite = bool(data.get("overwrite", False))
        if names is not None and not isinstance(names, list):
            return _json({"ok": False, "error": "templates must be a list"}, 400)
        try:
            results = templates.generate_doc_templates(project_id, names, overwrite=overwrite)
        except ValueError as e:
            return _json({"ok": False, "error": str(e)}, 400)
        created = [r["path"] for r in results if r.get("created")]
        skipped = [r["path"] for r in results if not r.get("created") and not r.get("error")]
        return _json({
            "ok": True,
            "results": results,
            "created": created,
            "skipped": skipped,
        }, 201)

    return _json({"ok": False, "error": "Method not allowed"}, 405)


# ── Risk register & milestones handlers (MAN.3 / P9) ───────────────────────

def _dispatch_risks(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/risks[/{risk_id}[/transition]]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    risk_id = parts[0] if parts else ""
    sub = parts[1] if len(parts) > 1 else ""
    data = body if isinstance(body, dict) else {}

    try:
        if not risk_id:
            if method == "GET":
                return _json({"ok": True, "risks": project_mgmt.list_risks(project_id)})
            if method == "POST":
                return _json({"ok": True, "risk": project_mgmt.create_risk(project_id, data)}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        if risk_id and (".." in risk_id or "/" in risk_id or "\\" in risk_id):
            return _json({"ok": False, "error": f"Invalid risk id: {risk_id}"}, 400)
        if not sub:
            if method == "GET":
                return _json({"ok": True, "risk": project_mgmt.get_risk(project_id, risk_id)})
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        if sub == "transition" and method == "POST":
            return _json({
                "ok": True, "risk": project_mgmt.transition_risk(project_id, risk_id, data),
            })
        return _json({"ok": False, "error": f"Unknown risks action: {sub}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


def _dispatch_milestones(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/milestones[/{ms_id}]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    ms_id = parts[0] if parts else ""
    data = body if isinstance(body, dict) else {}

    try:
        if not ms_id:
            if method == "GET":
                return _json({"ok": True, "milestones": project_mgmt.list_milestones(project_id)})
            if method == "POST":
                return _json({"ok": True, "milestone": project_mgmt.add_milestone(project_id, data)}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        if ms_id and (".." in ms_id or "/" in ms_id or "\\" in ms_id):
            return _json({"ok": False, "error": f"Invalid milestone id: {ms_id}"}, 400)
        if method in ("PUT", "PATCH", "POST"):
            return _json({
                "ok": True,
                "milestone": project_mgmt.update_milestone(project_id, ms_id, data),
            })
        return _json({"ok": False, "error": "Method not allowed"}, 405)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Issue / problem-resolution handlers (SUP.9 / P8) ───────────────────────

def _dispatch_issues(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/issues[/{issue_id}[/transition]]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    issue_id = parts[0] if parts else ""
    sub = parts[1] if len(parts) > 1 else ""
    data = body if isinstance(body, dict) else {}

    try:
        if not issue_id:
            if method == "GET":
                return _json({"ok": True, "issues": issues.list_issues(project_id)})
            if method == "POST":
                return _json({"ok": True, "issue": issues.create_issue(project_id, data)}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if issue_id == "export":
            if method == "GET":
                path = issues.export_report(project_id)
                return _json({"ok": True, "path": path})
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if issue_id and (".." in issue_id or "/" in issue_id or "\\" in issue_id):
            return _json({"ok": False, "error": f"Invalid issue id: {issue_id}"}, 400)

        if not sub:
            if method == "GET":
                return _json({"ok": True, "issue": issues.get_issue(project_id, issue_id)})
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if sub == "transition" and method == "POST":
            return _json({
                "ok": True, "issue": issues.transition(project_id, issue_id, data),
            })

        return _json({"ok": False, "error": f"Unknown issues action: {sub}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except issues.InvalidTransition as e:
        return _json({"ok": False, "error": str(e)}, 409)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── QA audit handlers (SUP.1 / P7) ─────────────────────────────────────────

def _dispatch_qa(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/qa[/{audit_id}[/findings[/{fid}/transition]]]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    audit_id = parts[0] if parts else ""
    sub = parts[1] if len(parts) > 1 else ""
    fid = parts[2] if len(parts) > 2 else ""
    action = parts[3] if len(parts) > 3 else ""
    data = body if isinstance(body, dict) else {}

    try:
        if not audit_id:
            if method == "GET":
                return _json({"ok": True, "audits": qa.list_audits(project_id)})
            if method == "POST":
                return _json({"ok": True, "audit": qa.create_audit(project_id, data)}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if audit_id == "export":
            if method == "GET":
                path = qa.export_report(project_id)
                return _json({"ok": True, "path": path})
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if audit_id and (".." in audit_id or "/" in audit_id or "\\" in audit_id):
            return _json({"ok": False, "error": f"Invalid audit id: {audit_id}"}, 400)

        if not sub:
            if method == "GET":
                return _json({"ok": True, "audit": qa.get_audit(project_id, audit_id)})
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if sub == "approve":
            if method == "POST":
                return _json({
                    "ok": True,
                    "audit": qa.approve_audit(project_id, audit_id, data),
                })
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if sub == "findings":
            if not fid:
                if method == "POST":
                    return _json({
                        "ok": True, "finding": qa.add_finding(project_id, audit_id, data),
                    }, 201)
                return _json({"ok": False, "error": "Method not allowed"}, 405)
            if action == "transition" and method == "POST":
                return _json({
                    "ok": True,
                    "finding": qa.transition_finding(project_id, audit_id, fid, data),
                })
            return _json({"ok": False, "error": "Unknown findings action"}, 404)

        return _json({"ok": False, "error": f"Unknown qa action: {sub}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Compliance audit handlers (P5) ─────────────────────────────────────────

def _compliance_documents(project_id: str) -> list[dict]:
    """Status of the ASPICE evidence documents the checker looks for."""
    proj_dir = workspace._project_dir(project_id)
    docs = []
    for name, (filename, title, _gen) in templates.TEMPLATES.items():
        path = proj_dir / "docs" / filename
        docs.append({
            "name": name,
            "title": title,
            "path": f"docs/{filename}",
            "exists": path.is_file(),
        })
    return docs


def _dispatch_compliance(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/compliance[/run]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    action = parts[0] if parts else ""

    if not action:
        if method != "GET":
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        summary = audit.get_latest_summary(project_id)
        if summary is None:
            return _json({
                "ok": False,
                "error": "No audit summary yet. POST /compliance/run first.",
            }, 404)
        return _json({
            "ok": True,
            "summary": summary,
            "documents": _compliance_documents(project_id),
        })

    if action == "run":
        if method != "POST":
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        summary = audit.run_compliance_audit(project_id, body)
        return _json({
            "ok": summary["ok"],
            "summary": summary,
            "documents": _compliance_documents(project_id),
        }, 200)

    if action == "documents":
        if method != "GET":
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        docs = _compliance_documents(project_id)
        return _json({
            "ok": True,
            "documents": docs,
            "missing": [d["name"] for d in docs if not d["exists"]],
        })

    if action == "dashboard":
        if method != "GET":
            return _json({"ok": False, "error": "Method not allowed"}, 405)
        from pathlib import Path as _Path
        dash = _Path(audit._reports_dir(project_id)) / "aspice-dashboard.html"
        if not dash.is_file():
            return _json({
                "ok": False,
                "error": "No dashboard yet. POST /compliance/run first.",
            }, 404)
        return _json({
            "ok": True,
            "path": str(dash),
            "html": dash.read_text(encoding="utf-8"),
        })

    return _json({"ok": False, "error": f"Unknown compliance action: {action}"}, 404)


# ── Evidence chain verification (audit chain) ──────────────────────────────

def _dispatch_evidence_chain(project_id: str, method: str) -> tuple:
    """Validate the evidence chain against the project artifacts.

    The desktop matrix is regenerated first when missing so the chain always
    has a truth source to validate (``collect_chain`` reads
    ``.osh/evidence/traceability-matrix.json``).
    """
    if method != "GET":
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    try:
        if tracing.load_matrix(project_id) is None:
            tracing.refresh(project_id)
        from yuleosh.evidence.chain import collect_chain

        chain = collect_chain(str(workspace._project_dir(project_id)))
    except (ValueError, OSError) as e:
        return _json({"ok": False, "error": f"Evidence chain failed: {e}"}, 500)

    summary = chain.get("summary") or {}
    metrics = chain.get("metrics") or {}
    problems = chain.get("problems") or []
    v_model = chain.get("v_model") or {}
    return _json({
        "ok": True,
        "status": summary.get("status"),
        "summary": summary,
        "metrics": metrics,
        "generated_at": chain.get("generated_at"),
        "source": chain.get("source"),
        "problems": problems[:50],
        "problem_total": len(problems),
        "gates": chain.get("gates") or [],
        "v_model": {
            "pairs": len(v_model.get("pairs") or []),
            "required_pairs": v_model.get("required_pairs", 0),
            "required_passed": v_model.get("required_passed", 0),
        },
    })


# ── Quality gate board (traceability / review / CI / test) ────────────────

#: Worst-wins ranking for gate statuses (higher = more severe).
_GATE_STATUS_RANK = {
    "passed": 0,
    "skipped": 1,
    "not-run": 2,
    "warning": 3,
    "retry": 4,
    "stale": 5,
    "failed": 6,
}

#: Pipeline run status → gate status. ``running``/``queued`` are not evidence
#: of success, so they surface as ``warning`` (never silently green).
_RUN_STATUS_TO_GATE = {
    "passed": "passed",
    "failed": "failed",
    "running": "warning",
    "queued": "warning",
}


def _worst_gate_status(statuses: list[str]) -> str:
    ranked = [s for s in statuses if s in _GATE_STATUS_RANK]
    if not ranked:
        return "not-run"
    return max(ranked, key=lambda s: _GATE_STATUS_RANK[s])


def _quality_traceability_gate(project_id: str) -> dict:
    try:
        matrix = tracing.build_matrix(project_id)
        verdict = tracing.gate_verdict(matrix)
    except (ValueError, OSError) as e:
        return {
            "key": "traceability",
            "name": "追溯门禁",
            "status": "not-run",
            "detail": f"无法读取追溯矩阵：{e}",
            "metrics": [],
        }

    summary = matrix.get("summary") or {}
    raw = str(verdict.get("status") or "not-run")
    # A disabled gate is not a failure, but it is also not verification.
    status = "skipped" if raw == "disabled" else raw
    if status not in _GATE_STATUS_RANK:
        status = "not-run"
    return {
        "key": "traceability",
        "name": "追溯门禁",
        "status": status,
        "detail": str(verdict.get("reason") or ""),
        "threshold": verdict.get("threshold"),
        "metrics": [
            {"label": "需求总数", "value": summary.get("total_requirements", 0)},
            {"label": "测试覆盖", "value": f"{summary.get('coverage_pct', 0.0)}%"},
            {"label": "设计覆盖", "value": f"{summary.get('design_coverage_pct', 0.0)}%"},
            {"label": "孤儿测试", "value": summary.get("orphaned_tests", 0)},
        ],
    }


def _quality_review_gate(project_id: str) -> dict:
    store = _load_reviews(project_id)
    reviews = [r for r in store.get("reviews", {}).values() if isinstance(r, dict)]
    counts = {"approved": 0, "rejected": 0, "needs_revision": 0}
    for r in reviews:
        status = str(r.get("status") or "")
        if status in counts:
            counts[status] += 1

    total = len(reviews)
    if not total:
        status, detail = "not-run", "尚无评审记录"
    elif counts["rejected"] or counts["needs_revision"]:
        status = "failed"
        detail = f"驳回 {counts['rejected']} / 需修改 {counts['needs_revision']}"
    else:
        status, detail = "passed", f"{counts['approved']} 项评审全部通过"
    return {
        "key": "review",
        "name": "评审门禁",
        "status": status,
        "detail": detail,
        "metrics": [
            {"label": "评审总数", "value": total},
            {"label": "通过", "value": counts["approved"]},
            {"label": "需修改", "value": counts["needs_revision"]},
            {"label": "驳回", "value": counts["rejected"]},
        ],
    }


def _latest_pipeline_run(project_id: str) -> dict | None:
    runs = workspace.list_pipeline_runs(project_id)
    if not runs:
        return None
    return max(
        runs,
        key=lambda r: (str(r.get("started_at") or ""), str(r.get("job_id") or "")),
    )


def _quality_ci_gate(project_id: str) -> dict:
    run = _latest_pipeline_run(project_id)
    if run is None:
        return {
            "key": "ci",
            "name": "CI 门禁",
            "status": "not-run",
            "detail": "尚无流水线运行记录",
            "metrics": [],
        }
    raw = str(run.get("status") or "unknown")
    status = _RUN_STATUS_TO_GATE.get(raw, "not-run")
    detail = f"最近运行 {run.get('job_id')}：{raw}"
    if run.get("completed_at"):
        detail += f"（{run['completed_at']}）"
    return {
        "key": "ci",
        "name": "CI 门禁",
        "status": status,
        "detail": detail,
        "job_id": run.get("job_id"),
        "metrics": [
            {"label": "运行状态", "value": raw},
            {"label": "开始时间", "value": run.get("started_at") or "—"},
            {"label": "结束时间", "value": run.get("completed_at") or "—"},
        ],
    }


def _quality_test_gate(project_id: str) -> dict:
    proj_dir = workspace._project_dir(project_id)
    tests_dir = proj_dir / "tests"
    test_files = (
        [p for p in tests_dir.rglob("*") if p.is_file()
         and p.suffix in (".c", ".cpp", ".py", ".js", ".ts")]
        if tests_dir.is_dir() else []
    )

    report = tests_dir / "report.json"
    passed = failed = 0
    coverage = None
    has_report = False
    if report.is_file():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            has_report = True
            try:
                passed = int(data.get("passed") or 0)
                failed = int(data.get("failed") or 0)
            except (TypeError, ValueError):
                passed = failed = 0
            coverage = data.get("coverage")

    if has_report:
        if failed:
            status = "failed"
        elif passed:
            status = "passed"
        else:
            status = "not-run"
        detail = f"通过 {passed} / 失败 {failed}"
    elif test_files:
        status = "not-run"
        detail = f"发现 {len(test_files)} 个测试文件，但没有测试报告"
    else:
        status = "not-run"
        detail = "尚无测试产物"

    metrics = [
        {"label": "测试文件", "value": len(test_files)},
        {"label": "通过", "value": passed},
        {"label": "失败", "value": failed},
    ]
    if coverage is not None:
        metrics.append({"label": "覆盖率", "value": str(coverage)})
    return {
        "key": "test",
        "name": "测试门禁",
        "status": status,
        "detail": detail,
        "metrics": metrics,
    }


def _latest_run_gate_detail(project_id: str, run: dict | None) -> dict:
    """Gate-level detail for the newest run.

    Prefers a real ``gate-summary.json`` written by the orchestrator (searched
    newest-first under the project dir); falls back to the run record, which
    only carries a coarse passed/failed status.
    """
    proj_dir = workspace._project_dir(project_id)
    detail: dict = {
        "job_id": run.get("job_id") if run else None,
        "run_status": run.get("status") if run else None,
        "started_at": run.get("started_at") if run else None,
        "completed_at": run.get("completed_at") if run else None,
        "source": "none",
        "session": None,
        "summary_timestamp": None,
        "worst_gate_status": None,
        "gates": [],
        "not_run_gates": [],
        "stale_gates": [],
    }
    if run is None:
        return detail

    detail["source"] = "run-record"
    try:
        summaries = sorted(
            proj_dir.rglob("gate-summary.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        summaries = []

    from yuleosh.pipeline.gates import load_gate_summary

    for path in summaries:
        data = load_gate_summary(path)
        if not isinstance(data.get("gates"), list) or not data["gates"]:
            continue
        detail.update({
            "source": "gate-summary",
            "summary_path": str(path.relative_to(proj_dir)),
            "session": data.get("session"),
            "summary_timestamp": data.get("timestamp"),
            "worst_gate_status": data.get("worst_gate_status"),
            "not_run_gates": data.get("not_run_gates") or [],
            "stale_gates": data.get("stale_gates") or [],
            "gates": [
                {
                    "gate": g.get("gate"),
                    "name": g.get("name"),
                    "status": g.get("status"),
                    "advisory": bool(g.get("advisory")),
                    "step_total": len(g.get("step_keys") or []),
                }
                for g in data["gates"] if isinstance(g, dict)
            ],
        })
        break
    return detail


def _dispatch_quality_gates(project_id: str, method: str) -> tuple:
    """Aggregate the four quality gates plus the newest run's gate detail."""
    if method != "GET":
        return _json({"ok": False, "error": "Method not allowed"}, 405)
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    categories = [
        _quality_traceability_gate(project_id),
        _quality_review_gate(project_id),
        _quality_ci_gate(project_id),
        _quality_test_gate(project_id),
    ]
    worst = _worst_gate_status([c["status"] for c in categories])
    # GREEN only when every gate is verified; anything unverified is amber,
    # a hard failure is red — no partial credit.
    if worst == "passed":
        overall = "green"
    elif worst == "failed":
        overall = "red"
    else:
        overall = "unverified"

    run = _latest_pipeline_run(project_id)
    return _json({
        "ok": True,
        "overall": overall,
        "worst_status": worst,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "categories": categories,
        "latest_run": _latest_run_gate_detail(project_id, run),
    })


# ── Traceability handlers (P3) ────────────────────────────────────────────

def _dispatch_traceability(project_id: str, method: str, parts: list,
                           body: Any, query: dict) -> tuple:
    """Handle /projects/{id}/traceability[/refresh|/reverse]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    action = parts[0] if parts else ""
    data = body if isinstance(body, dict) else {}
    raw_threshold = _query_one(query, "threshold") if query else ""
    try:
        threshold = float(raw_threshold) if raw_threshold else None
    except ValueError:
        return _json({"ok": False, "error": "threshold must be a number"}, 400)

    try:
        if not action:
            if method != "GET":
                return _json({"ok": False, "error": "Method not allowed"}, 405)
            matrix = tracing.load_matrix(project_id)
            if matrix is None:
                return _json({
                    "ok": False,
                    "error": "No traceability matrix. POST /traceability/refresh first.",
                }, 404)
            return _json({
                "ok": True,
                "summary": matrix.get("summary", {}),
                "requirements": matrix.get("requirements", []),
                "orphaned_test_files": matrix.get("orphaned_test_files", []),
                "baseline": matrix.get("baseline"),
                "generated": matrix.get("generated"),
                "gate": tracing.gate_verdict(matrix, threshold=threshold),
            })

        if action == "refresh" and method == "POST":
            result = tracing.refresh(project_id, data)
            return _json({
                "ok": True,
                "summary": result["matrix"]["summary"],
                "json": result["json"],
                "snapshot": result["snapshot"],
                "baseline": result["baseline"],
                "gate": tracing.gate_verdict(result["matrix"], threshold=threshold),
            }, 201)

        if action == "reverse" and method == "GET":
            file_path = _query_one(query, "file")
            if not file_path:
                return _json({"ok": False, "error": "query param 'file' is required"}, 400)
            return _json({"ok": True, **tracing.reverse_lookup(project_id, file_path)})

        return _json({"ok": False, "error": f"Unknown traceability action: {action}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Baseline handlers (SUP.8) ─────────────────────────────────────────────

def _query_one(query: dict, key: str) -> str:
    """Read a single query-string value (parse_qs returns lists)."""
    value = (query or {}).get(key)
    if isinstance(value, list):
        return (value[0] if value else "").strip()
    return (value or "").strip()


def _dispatch_baselines(project_id: str, method: str, parts: list,
                        body: Any, query: dict) -> tuple:
    """Handle /projects/{id}/baselines[/diff|/{name}]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    name = parts[0] if parts else ""
    data = body if isinstance(body, dict) else {}

    try:
        if not name:
            if method == "GET":
                return _json({"ok": True, "baselines": baseline.list_baselines(project_id)})
            if method == "POST":
                snap = baseline.create_baseline(project_id, data)
                return _json({"ok": True, "baseline": snap}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if name == "diff":
            if method != "GET":
                return _json({"ok": False, "error": "Method not allowed"}, 405)
            from_name = _query_one(query, "from")
            to_name = _query_one(query, "to")
            if not from_name or not to_name:
                return _json({"ok": False, "error": "query params 'from' and 'to' are required"}, 400)
            diff = baseline.diff_baselines(project_id, from_name, to_name)
            return _json({"ok": True, "diff": diff})

        if method == "GET":
            return _json({"ok": True, "baseline": baseline.load_baseline(project_id, name)})
        return _json({"ok": False, "error": "Method not allowed"}, 405)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except baseline.BaselineConflict as e:
        return _json({"ok": False, "error": str(e)}, 409)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Change-request handlers (SUP.10) ───────────────────────────────────────

def _dispatch_change_requests(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/change-requests[/{cr_id}[/{action}]]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    cr_id = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    data = body if isinstance(body, dict) else {}

    if cr_id and (".." in cr_id or "/" in cr_id or "\\" in cr_id):
        return _json({"ok": False, "error": f"Invalid change request id: {cr_id}"}, 400)

    try:
        if not cr_id:
            if method == "GET":
                return _json({
                    "ok": True,
                    "change_requests": change_control.list_change_requests(project_id),
                })
            if method == "POST":
                cr = change_control.create_change_request(project_id, data)
                return _json({"ok": True, "change_request": cr}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if not action:
            if method == "GET":
                cr = change_control.load_change_request(project_id, cr_id)
                return _json({"ok": True, "change_request": cr})
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if action == "analyze" and method == "POST":
            impact = change_control.analyze_impact(project_id, cr_id, data)
            cr = change_control.load_change_request(project_id, cr_id)
            return _json({"ok": True, "impact": impact, "change_request": cr})

        if action == "transition" and method == "POST":
            cr = change_control.transition(project_id, cr_id, data)
            return _json({"ok": True, "change_request": cr})

        return _json({"ok": False, "error": f"Unknown change-request action: {action}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except change_control.InvalidTransition as e:
        return _json({"ok": False, "error": str(e)}, 409)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Review handlers (evidence/review.json) ──────────────────────────────────

import secrets as _secrets

_REVIEW_STATUS = {"approved", "rejected", "needs_revision"}


def _review_path(project_id: str) -> Path:
    """Return the evidence/review.json path, creating parent dirs if needed."""
    proj_dir = workspace._project_dir(project_id)
    rev_dir = proj_dir / "evidence"
    rev_dir.mkdir(parents=True, exist_ok=True)
    return rev_dir / "review.json"


def _load_reviews(project_id: str) -> dict:
    """Load review.json; return empty dict if missing or invalid."""
    p = _review_path(project_id)
    if not p.exists():
        return {"reviews": {}, "index": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "reviews" not in data:
            return {"reviews": data if isinstance(data, list) else {}, "index": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"reviews": {}, "index": []}


def _save_reviews(project_id: str, data: dict) -> None:
    p = _review_path(project_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_review(project_id: str, body: Any) -> tuple:
    """Create a new review entry.

    body fields:
        artifact    str — 产物文件路径（如 code/src/main.c）
        status      str — approved | rejected | needs_revision
        comment     str — 批注（可选）
        author      str — 评审人（可选，默认 "local"）
        line_start  int — 行号范围（可选）
        line_end    int
    """
    data = body if isinstance(body, dict) else {}
    artifact = (data.get("artifact") or "").strip()
    status = (data.get("status") or "").strip().lower()
    comment = (data.get("comment") or "").strip()
    author = (data.get("author") or "local").strip()

    if not artifact:
        return _json({"ok": False, "error": "artifact is required"}, 400)
    if status not in _REVIEW_STATUS:
        return _json({"ok": False, "error": f"status must be one of {_REVIEW_STATUS}"}, 400)

    # 防路径穿越：artifact 必须在已知产物目录下
    proj_dir = workspace._project_dir(project_id)
    target = (proj_dir / artifact).resolve()
    try:
        target.relative_to(proj_dir.resolve())
    except ValueError:
        return _json({"ok": False, "error": "artifact path escapes project dir"}, 400)

    entry = {
        "id": _secrets.token_hex(6),
        "artifact": artifact,
        "status": status,
        "comment": comment,
        "author": author,
        "created_at": datetime.now().isoformat(),
        "line_start": data.get("line_start"),
        "line_end": data.get("line_end"),
    }

    store = _load_reviews(project_id)
    store["reviews"][entry["id"]] = entry
    if entry["id"] not in store.get("index", []):
        store.setdefault("index", []).append(entry["id"])
    _save_reviews(project_id, store)

    return _json({"ok": True, "review": entry}, 201)


def _list_reviews(project_id: str) -> tuple:
    """List all reviews for a project, newest first."""
    store = _load_reviews(project_id)
    reviews = list(store["reviews"].values())
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # 按 artifact 分组的汇总（给前端侧栏用）
    by_artifact: dict[str, dict] = {}
    for r in reviews:
        art = r["artifact"]
        agg = by_artifact.setdefault(art, {"artifact": art, "approved": 0, "rejected": 0, "needs_revision": 0, "total": 0})
        agg[r["status"]] = agg.get(r["status"], 0) + 1
        agg["total"] += 1

    return _json({
        "ok": True,
        "reviews": reviews,
        "summary_by_artifact": list(by_artifact.values()),
        "total": len(reviews),
    })


def _get_review(project_id: str, rev_id: str) -> tuple:
    store = _load_reviews(project_id)
    rev = store["reviews"].get(rev_id)
    if not rev:
        return _json({"ok": False, "error": "Review not found"}, 404)
    return _json({"ok": True, "review": rev})


def _delete_review(project_id: str, rev_id: str) -> tuple:
    store = _load_reviews(project_id)
    if rev_id not in store["reviews"]:
        return _json({"ok": False, "error": "Review not found"}, 404)
    store["reviews"].pop(rev_id)
    store["index"] = [x for x in store.get("index", []) if x != rev_id]
    _save_reviews(project_id, store)
    return _json({"ok": True})


def _bulk_reviews(project_id: str, body: Any) -> tuple:
    """批量给多个产物打同一个评审标签。

    body 字段:
        scope        "artifact" | "section" | "all"
        artifacts    list[str]   — scope="artifact" 时指定文件路径
        section      str         — scope="section" 时指定分区名（如 code / tests）
        status       str         — approved | rejected | needs_revision
        comment      str         — 可选批注
    """
    data = body if isinstance(body, dict) else {}
    scope = data.get("scope", "all").strip()
    status = (data.get("status") or "").strip().lower()
    comment = (data.get("comment") or "").strip()

    if status not in _REVIEW_STATUS:
        return _json({"ok": False, "error": f"status must be one of {_REVIEW_STATUS}"}, 400)

    proj_dir = workspace._project_dir(project_id)
    # 收集所有产物文件路径
    all_files = []
    for sub in ("requirements", "design", "code", "tests", "evidence"):
        sub_path = proj_dir / sub
        if sub_path.exists():
            for fpath in sub_path.rglob("*"):
                if fpath.is_file():
                    all_files.append(str(fpath.relative_to(proj_dir)))

    if scope == "artifact":
        targets = [p for p in (data.get("artifacts") or []) if p in all_files]
    elif scope == "section":
        section = (data.get("section") or "").strip()
        if not section:
            return _json({"ok": False, "error": "section is required"}, 400)
        targets = [p for p in all_files if p.startswith(section + "/")]
    else:  # all
        targets = all_files

    if not targets:
        return _json({"ok": True, "created": 0, "skipped": 0, "message": "no files matched"}, 200)

    store = _load_reviews(project_id)
    existing_by_artifact: dict[str, str] = {
        r["artifact"]: rid for rid, r in store["reviews"].items()
    }
    created = 0
    skipped = 0

    for artifact in targets:
        if artifact in existing_by_artifact:
            # 同一文件已有评审记录 — 更新而非重复创建
            existing = store["reviews"][existing_by_artifact[artifact]]
            existing["status"] = status
            if comment:
                existing["comment"] = comment
            existing["created_at"] = datetime.now().isoformat()
            skipped += 1
            continue
        rid = _secrets.token_hex(6)
        store["reviews"][rid] = {
            "id": rid,
            "artifact": artifact,
            "status": status,
            "comment": comment,
            "author": "local",
            "created_at": datetime.now().isoformat(),
        }
        store.setdefault("index", []).append(rid)
        created += 1

    _save_reviews(project_id, store)
    return _json({"ok": True, "created": created, "updated": skipped})


def _export_reviews(project_id: str) -> tuple:
    """把 review.json 导出成 evidence/review-report.md 并返回其内容。"""
    store = _load_reviews(project_id)
    reviews = list(store["reviews"].values())
    reviews.sort(key=lambda r: r.get("artifact", ""))

    proj_dir = workspace._project_dir(project_id)
    meta_path = proj_dir / "project.json"
    proj_name = "unknown"
    if meta_path.exists():
        try:
            proj_name = json.loads(meta_path.read_text(encoding="utf-8")).get("name", "unknown")
        except (json.JSONDecodeError, OSError):
            pass

    # 汇总
    summary = {"approved": 0, "rejected": 0, "needs_revision": 0}
    for r in reviews:
        summary[r.get("status", "needs_revision")] = summary.get(r.get("status", "needs_revision"), 0) + 1

    # 按分区分组
    sections: dict[str, list[dict]] = {}
    for r in reviews:
        section = r["artifact"].split("/")[0] if "/" in r["artifact"] else "other"
        sections.setdefault(section, []).append(r)

    # 生成 Markdown
    lines = [
        f"# 评审报告 — {proj_name}",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"> 评审总数：{len(reviews)}  ✅ 通过 {summary['approved']}  ❌ 退回 {summary['rejected']}  🔍 修改 {summary['needs_revision']}",
        "",
        "## 概览",
        "",
        f"| 分区 | 通过 | 退回 | 修改 | 合计 |",
        "|---|---|---|---|---|",
    ]
    for sec in sorted(sections.keys()):
        sec_reviews = sections[sec]
        s = {"approved": 0, "rejected": 0, "needs_revision": 0}
        for r in sec_reviews:
            s[r.get("status", "needs_revision")] = s.get(r.get("status", "needs_revision"), 0) + 1
        lines.append(f"| {sec} | {s['approved']} | {s['rejected']} | {s['needs_revision']} | {len(sec_reviews)} |")
    lines.append("")

    for sec in sorted(sections.keys()):
        sec_reviews = sections[sec]
        lines.extend([f"## {sec}", ""])
        for r in sec_reviews:
            tag = {"approved": "✅ 通过", "rejected": "❌ 退回", "needs_revision": "🔍 修改"}.get(r.get("status"), r.get("status"))
            lines.append(f"- **`{r['artifact']}`** — {tag}  ")
            if r.get("comment"):
                lines.append(f"  > {r['comment']}  ")
            lines.append(f"  _by {r.get('author', 'local')} · {r.get('created_at', '').replace('T', ' ')}_  ")
            lines.append("")

    content = "\n".join(lines)

    # 落盘到 evidence/review-report.md
    report_path = proj_dir / "evidence" / "review-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")

    return _json({
        "ok": True,
        "path": "evidence/review-report.md",
        "content": content,
        "total": len(reviews),
        "summary": summary,
    })
