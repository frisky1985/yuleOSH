#!/usr/bin/env bash
# ============================================================================
# yuleOSH 部署端到端验证脚本
# Deploy Verification — Pre-flight checks before go-live
#
# Usage:
#   bash scripts/deploy-verify.sh
#   bash scripts/deploy-verify.sh --quiet    (minimal output)
#   bash scripts/deploy-verify.sh --json     (JSON report)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="${1:-normal}"  # normal / quiet / json
PASS=0
FAIL=0
WARN=0
RESULTS=()

log()   { [[ "$MODE" != "json" ]] && echo -e "$1"; }
ok()    { PASS=$((PASS+1)); log "  ✅ $1"; RESULTS+=("{\"status\":\"PASS\",\"check\":\"$1\"}"); }
fail()  { FAIL=$((FAIL+1)); log "  ❌ $1"; RESULTS+=("{\"status\":\"FAIL\",\"check\":\"$1\"}"); }
warn()  { WARN=$((WARN+1)); log "  ⚠️  $1"; RESULTS+=("{\"status\":\"WARN\",\"check\":\"$1\"}"); }

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   yuleOSH 部署验证 (Deploy Verification)     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo "  Date:    $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "  Project: $PROJECT_DIR"
echo ""

# ------------------------------------------------------------------
# 1. 前置检查 — SSL证书 / 环境变量 / Config文件
# ------------------------------------------------------------------
echo ""
echo "  ── [1/5] 前置检查 ──"
echo ""

# 1a. SSL certificate files
SSL_DIR="$PROJECT_DIR/deploy/ssl"
if [[ -d "$SSL_DIR" ]]; then
    if ls "$SSL_DIR"/*.pem "$SSL_DIR"/*.crt "$SSL_DIR"/*.key 2>/dev/null | head -5 | grep -q .; then
        ok "SSL certificate files found in deploy/ssl/"
        CERT_COUNT=$(find "$SSL_DIR" -maxdepth 1 \( -name '*.pem' -o -name '*.crt' -o -name '*.key' \) | wc -l | tr -d ' ')
        log "       ($CERT_COUNT file(s) present)"
    else
        warn "No SSL certificate files found in deploy/ssl/ (expected for production)"
    fi
else
    warn "deploy/ssl/ directory not found — SSL not configured"
fi

# 1b. Critical environment variables
ENV_FILE="$PROJECT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    ok ".env file exists"
    # Check for critical vars
    while IFS='=' read -r key val; do
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        val="${val//\"/}"
        val="${val//\'/}"
        if [[ -z "$val" || "$val" == "your-"* || "$val" == "YOUR_"* ]]; then
            warn "Environment variable $key appears unset or placeholder"
        fi
    done < "$ENV_FILE"
else
    warn ".env file not found (expected for production deployment)"
fi

# 1c. Config files existence
CONFIG_FILES=(
    "docker-compose.yml.legacy"
    "Dockerfile"
    "pyproject.toml"
    ".coveragerc"
    "pytest.ini"
)
for cfg in "${CONFIG_FILES[@]}"; do
    if [[ -f "$PROJECT_DIR/$cfg" ]]; then
        ok "Config file exists: $cfg"
    else
        warn "Config file missing: $cfg"
    fi
done

# ------------------------------------------------------------------
# 2. Docker Compose 配置语法验证
# ------------------------------------------------------------------
echo ""
echo "  ── [2/5] Docker Compose 配置语法 ──"
echo ""

if command -v docker &>/dev/null; then
    COMPOSE_FILES=("$PROJECT_DIR/docker-compose.yml" "$PROJECT_DIR/docker-compose.yml.legacy")
    COMPOSE_FOUND=0
    for cf in "${COMPOSE_FILES[@]}"; do
        if [[ -f "$cf" ]]; then
            COMPOSE_FOUND=1
            log "    Validating: $(basename "$cf")"
            if docker compose -f "$cf" config --quiet 2>/dev/null; then
                ok "Docker Compose config valid: $(basename "$cf")"
            else
                fail "Docker Compose config INVALID: $(basename "$cf")"
            fi
        fi
    done
    if [[ $COMPOSE_FOUND -eq 0 ]]; then
        warn "No docker-compose.yml found — skipping compose validation"
    fi
else
    warn "docker command not found — skipping Docker Compose validation"
fi

# ------------------------------------------------------------------
# 3. Stripe API Key 格式校验
# ------------------------------------------------------------------
echo ""
echo "  ── [3/5] Stripe API Key 校验 ──"
echo ""

STRIPE_KEY=""
if [[ -f "$ENV_FILE" ]]; then
    STRIPE_KEY=$(grep -E '^STRIPE_?(API_KEY|SECRET_KEY|KEY)?=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi

if [[ -n "$STRIPE_KEY" ]]; then
    if [[ "$STRIPE_KEY" =~ ^sk_live_ ]]; then
        ok "Stripe live API key (sk_live_*) — production mode"
    elif [[ "$STRIPE_KEY" =~ ^sk_test_ ]]; then
        ok "Stripe test API key (sk_test_*) — test mode"
    else
        fail "Stripe API key format invalid (expected sk_live_* or sk_test_*)"
    fi
else
    warn "STRIPE_API_KEY not found in .env — skipping validation"
fi

# ------------------------------------------------------------------
# 4. 端口冲突检测
# ------------------------------------------------------------------
echo ""
echo "  ── [4/5] 端口冲突检测 ──"
echo ""

CRITICAL_PORTS=(8000 8080 5432 6379 3000 9090)
for port in "${CRITICAL_PORTS[@]}"; do
    case "$(uname -s)" in
        Linux)
            if ss -tlnp "sport = :$port" 2>/dev/null | grep -q LISTEN; then
                PROC=$(ss -tlnp "sport = :$port" 2>/dev/null | tr -s ' ' | cut -d' ' -f7 | head -1)
                warn "Port $port is in use by: $PROC"
            else
                ok "Port $port is free"
            fi
            ;;
        Darwin)
            if lsof -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | grep -q .; then
                PROC=$(lsof -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tail -1 | awk '{print $1}')
                warn "Port $port is in use by: $PROC"
            else
                ok "Port $port is free"
            fi
            ;;
        *)
            if (echo >/dev/tcp/localhost/$port) 2>/dev/null; then
                warn "Port $port is in use"
            else
                ok "Port $port is free"
            fi
            ;;
    esac
done

# ------------------------------------------------------------------
# 5. 报告汇总
# ------------------------------------------------------------------
echo ""
echo "  ── [5/5] 验证报告 ──"
echo ""
echo "  ╔══════════════════════════════╗"
printf "  ║  ✅ PASS:  %-3d                    ║\n" "$PASS"
printf "  ║  ⚠️  WARN:  %-3d                    ║\n" "$WARN"
printf "  ║  ❌ FAIL:  %-3d                    ║\n" "$FAIL"
echo "  ╚══════════════════════════════╝"
echo ""

# Exit code
if [[ $FAIL -gt 0 ]]; then
    echo "  ❌ 部署验证未通过 — $FAIL 项检查失败"
else
    echo "  ✅ 部署验证通过 — 所有关键检查已通过"
fi
echo ""

# JSON output mode
if [[ "$MODE" == "--json" ]]; then
    JSON=$(printf '%s\n' "${RESULTS[@]}" | jq -s --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{date: $date, summary: {pass: $pass, warn: $warn, fail: $fail}, checks: .}' \
        --arg pass "$PASS" --arg warn "$WARN" --arg fail "$FAIL" \
        '.summary.pass = ($pass|tonumber) | .summary.warn = ($warn|tonumber) | .summary.fail = ($fail|tonumber)')
    echo "$JSON"
fi

exit $FAIL
