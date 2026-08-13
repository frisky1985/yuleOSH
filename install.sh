#!/usr/bin/env bash
# ============================================================================
# yuleOSH — One-Click Install Script (Production Grade)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash
#
# Options:
#   YULEOSH_VERSION=0.1.0  curl ... | bash       # Pin a specific version
#   YULEOSH_DIR=~/.yuleosh curl ... | bash        # Custom install path
#   YULEOSH_SKIP_DEPS=1    curl ... | bash        # Skip dependency install
# ============================================================================
set -euo pipefail

# ---- Version ---------------------------------------------------------------
SCRIPT_VERSION="0.2.0"
MIN_PYTHON="3.10"
MIN_GIT="2.20"

# ---- Config ----------------------------------------------------------------
YULEOSH_VERSION="${YULEOSH_VERSION:-latest}"
INSTALL_DIR="${YULEOSH_DIR:-$HOME/.yuleosh}"
GITHUB="https://github.com/frisky1985/yuleOSH"
START_TIME=$(date +%s)
# Python 版本约束（与 pyproject.toml requires-python 一致）
REQUIRED_PYTHON="3.12"
PY_MAJOR=3
PY_MINOR=12

# ---- Color helpers ---------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "  ${CYAN}ℹ${NC} $1"; }
ok()    { echo -e "  ${GREEN}✅${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠️${NC} $1"; }
fail()  { echo -e "  ${RED}❌${NC} $1"; }
banner() {
    echo ""
    echo "  ${CYAN}🔱 yuleOSH Installer v${SCRIPT_VERSION}${NC}"
    echo "  ${CYAN}─────────────────────────────────${NC}"
}

# ---- OS Detection ----------------------------------------------------------
detect_os() {
    case "$(uname -s)" in
        Linux*)  echo "linux" ;;
        Darwin*) echo "macos" ;;
        CYGWIN*|MINGW*|MSYS*) echo "windows" ;;
        *)       echo "unknown" ;;
    esac
}

detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "${ID:-linux}"
    elif command -v sw_vers &>/dev/null; then
        sw_vers -productName 2>/dev/null || echo "macos"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
DISTRO=$(detect_distro)

# ---- Version comparison ----------------------------------------------------
version_ge() {
    # Returns 0 if $1 >= $2
    printf '%s\n' "$2" "$1" | sort -V -C
}

# ---- Pre-flight checks -----------------------------------------------------
preflight() {
    local issues=0

    # Required: python3.12 (exact minor, matches pyproject requires-python)
    if command -v python3.12 &>/dev/null; then
        PY_BIN="$(command -v python3.12)"
        ok "Python $(python3.12 --version 2>&1 | grep -oE '3\.12\.[0-9]+')"
    elif command -v python3 &>/dev/null; then
        local pyver
        pyver=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local pymajor pyminor
        pymajor="${pyver%%.*}"
        pyminor="${pyver#*.}"
        pyminor="${pyminor%%.*}"
        if [ "$pymajor" = "$PY_MAJOR" ] && [ "$pyminor" = "$PY_MINOR" ]; then
            PY_BIN="$(command -v python3)"
            ok "Python $pyver"
        else
            fail "Python $pyver found, but Python ${REQUIRED_PYTHON} is required (yuleOSH pins to 3.12 for CI reproducibility)."
            case "$OS" in
                linux)
                    info "Install: apt install python3.12 (Debian/Ubuntu) / dnf install python3.12 (RHEL/Fedora)"
                    ;;
                macos)
                    info "Install: brew install python@3.12"
                    ;;
            esac
            issues=$((issues + 1))
        fi
    else
        fail "python3 is required but not found."
        case "$OS" in
            linux)
                info "Install: apt install python3.12 (Debian/Ubuntu) / yum install python3.12 (RHEL)"
                ;;
            macos)
                info "Install: brew install python@3.12"
                ;;
        esac
        issues=$((issues + 1))
    fi

    # Required: git or curl
    if ! command -v git &>/dev/null && ! command -v curl &>/dev/null; then
        fail "git or curl is required."
        info "Install git: apt install git / brew install git"
        issues=$((issues + 1))
    fi

    # Optional: git version check
    if command -v git &>/dev/null; then
        local gitver
        gitver=$(git --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -1)
        if [ -n "$gitver" ] && ! version_ge "$gitver" "$MIN_GIT"; then
            warn "Git $gitver found — $MIN_GIT+ recommended."
        else
            ok "Git ${gitver:-detected}"
        fi
    fi

    # Check disk space (need ~100MB)
    local required_kb=$((100 * 1024))
    if command -v df &>/dev/null; then
        local available_kb
        available_kb=$(df -k "$HOME" 2>/dev/null | tail -1 | awk '{print $4}')
        if [ -n "$available_kb" ] && [ "$available_kb" -lt "$required_kb" ]; then
            warn "Low disk space: only $((available_kb / 1024))MB available, ~100MB recommended."
        fi
    fi

    # OS info
    case "$OS" in
        linux)  ok "OS: Linux ($DISTRO)" ;;
        macos)  ok "OS: macOS" ;;
        windows) warn "OS: Windows — use Git Bash or WSL for best results" ;;
        *)      warn "OS: unknown (uname: $(uname -s))" ;;
    esac

    return $issues
}

# ---- Dependency installation -----------------------------------------------
# 在 INSTALL_DIR/.venv 创建隔离虚拟环境（Python 3.12），
# 一次性装好运行时 + dev(测试) 依赖，避免污染系统 Python。
VENV_DIR="${INSTALL_DIR}/.venv"

ensure_venv() {
    if [ "${YULEOSH_SKIP_DEPS:-0}" = "1" ]; then
        info "Skipping venv creation (YULEOSH_SKIP_DEPS=1)"
        return 0
    fi

    if [ -x "${VENV_DIR}/bin/python" ]; then
        local vver
        vver=$("${VENV_DIR}/bin/python" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        info "Reusing existing venv (Python $vver)"
        return 0
    fi

    info "Creating virtual environment at ${VENV_DIR} (Python ${REQUIRED_PYTHON})..."
    mkdir -p "$(dirname "${VENV_DIR}")"
    "${PY_BIN}" -m venv "${VENV_DIR}" || {
        fail "Failed to create venv with ${PY_BIN}"
        info "Try: ${PY_BIN} -m ensurepip --upgrade"
        return 1
    }
    ok "Virtual environment created"
}

install_deps() {
    if [ "${YULEOSH_SKIP_DEPS:-0}" = "1" ]; then
        info "Skipping dependency install (YULEOSH_SKIP_DEPS=1)"
        return 0
    fi

    if ! ensure_venv; then
        return 1
    fi

    local VENV_PY="${VENV_DIR}/bin/python"
    local VENV_PIP="${VENV_DIR}/bin/pip"

    # Upgrade pip inside venv (macOS/系统 Python 常带旧 pip)
    "${VENV_PY}" -m pip install --quiet --upgrade pip setuptools wheel 2>/dev/null || {
        warn "pip upgrade failed (non-fatal)"
    }

    info "Installing yuleOSH package (editable, with dev/test deps)..."
    if [ -f "${INSTALL_DIR}/pyproject.toml" ]; then
        (cd "${INSTALL_DIR}" && "${VENV_PY}" -m pip install --quiet --no-cache-dir -e ".[dev]" 2>/dev/null) || {
            # 回退：至少装运行时依赖
            warn "Editable install with [dev] failed — retrying runtime-only"
            (cd "${INSTALL_DIR}" && "${VENV_PY}" -m pip install --quiet --no-cache-dir -e . 2>/dev/null) || {
                warn "Package install skipped (non-fatal for CLI usage)"
            }
        }
    else
        warn "No pyproject.toml found — skipping package install"
    fi

    # 验证
    if "${VENV_PY}" -c "import yuleosh" 2>/dev/null; then
        ok "yuleosh importable in venv"
    else
        warn "yuleosh not importable in venv yet (may need network for deps)"
    fi

    ok "Dependencies installed into ${VENV_DIR}"
}

# 返回 venv 内的 python 可执行路径（供后续命令/包装使用）
venv_python() {
    if [ -x "${VENV_DIR}/bin/python" ]; then
        echo "${VENV_DIR}/bin/python"
    else
        echo "${PY_BIN}"
    fi
}

# ---- Main installation -----------------------------------------------------
main() {
    banner

    echo "  Target: ${INSTALL_DIR}"
    echo "  Version: ${YULEOSH_VERSION}"
    echo ""

    # ---- Pre-flight --------------------------------------------------------
    echo "  ${CYAN}🔍 Pre-flight checks...${NC}"
    if ! preflight; then
        fail "Pre-flight checks failed. Please fix the issues above and retry."
        exit 1
    fi
    echo ""

    # ---- Download ----------------------------------------------------------
    echo "  ${CYAN}📦 Downloading yuleOSH...${NC}"
    mkdir -p "${INSTALL_DIR}"

    if [ -d "${INSTALL_DIR}/.git" ]; then
        info "Existing installation found — updating..."
        cd "${INSTALL_DIR}"
        git pull --ff-only 2>/dev/null || {
            warn "Git pull failed — trying fresh clone"
            cd /tmp
            rm -rf "${INSTALL_DIR}.bak" 2>/dev/null
            mv "${INSTALL_DIR}" "${INSTALL_DIR}.bak" 2>/dev/null || true
            git clone --depth 1 "${GITHUB}.git" "${INSTALL_DIR}"
        }
    else
        if command -v git &>/dev/null; then
            info "Cloning via git..."
            git clone --depth 1 "${GITHUB}.git" "${INSTALL_DIR}" 2>/dev/null || {
                warn "Git clone failed — falling back to archive download"
                download_archive
            }
        else
            download_archive
        fi
    fi

    if [ ! -d "${INSTALL_DIR}" ] || [ ! -f "${INSTALL_DIR}/pyproject.toml" ]; then
        fail "Download failed — ${INSTALL_DIR}/pyproject.toml not found."
        info "Check network: ${GITHUB}"
        exit 1
    fi
    ok "yuleOSH downloaded"

    # ---- Dependencies ------------------------------------------------------
    install_deps

    # ---- Symlink -----------------------------------------------------------
    echo ""
    echo "  ${CYAN}🔗 Setting up symlink...${NC}"
    # 优先指向 venv 内命令；无 venv 时回退源目录 bin
    local CMD_SRC="${INSTALL_DIR}/bin/yuleosh-server"
    if [ -x "${VENV_DIR}/bin/yuleosh-server" ]; then
        CMD_SRC="${VENV_DIR}/bin/yuleosh-server"
    elif [ -x "${VENV_DIR}/bin/yuleosh" ]; then
        CMD_SRC="${VENV_DIR}/bin/yuleosh"
    fi
    if [ -w /usr/local/bin ]; then
        ln -sf "${CMD_SRC}" /usr/local/bin/yuleosh 2>/dev/null && \
            ok "Symlink: /usr/local/bin/yuleosh → ${CMD_SRC}" || \
            warn "Could not create symlink in /usr/local/bin"
    elif sudo -n true 2>/dev/null; then
        sudo ln -sf "${CMD_SRC}" /usr/local/bin/yuleosh 2>/dev/null && \
            ok "Symlink: /usr/local/bin/yuleosh → ${CMD_SRC} (via sudo)" || \
            warn "Could not create symlink in /usr/local/bin"
    else
        warn "Cannot write to /usr/local/bin"
        info "Add to PATH: export PATH=\$PATH:${INSTALL_DIR}/.venv/bin"
    fi

    # ---- Create required dirs ----------------------------------------------
    mkdir -p "${INSTALL_DIR}/.osh/reviews"
    mkdir -p "${INSTALL_DIR}/.osh/ci"
    mkdir -p "${INSTALL_DIR}/.osh/evidence"
    mkdir -p "${INSTALL_DIR}/projects"

    # ---- Done --------------------------------------------------------------
    local elapsed=$(( $(date +%s) - START_TIME ))
    echo ""
    echo "  ${GREEN}══════════════════════════════════════${NC}"
    echo "  ${GREEN}✅ yuleOSH v${YULEOSH_VERSION} installed!${NC}"
    echo "  ${GREEN}   (${elapsed}s)${NC}"
    echo "  ${GREEN}══════════════════════════════════════${NC}"
    echo ""
    echo "  📍 Location: ${INSTALL_DIR}"
    echo "  🐍 Python:   ${VENV_DIR}/bin/python ($( "${VENV_DIR}/bin/python" --version 2>/dev/null || echo 'venv pending' ))"
    echo "  🚀 Start:    yuleosh"
    echo "  📚 Docs:     ${INSTALL_DIR}/docs/"
    echo "  🌐 GitHub:   ${GITHUB}"
    echo ""
    echo "  Quick start:"
    echo "    cd ${INSTALL_DIR}"
    echo "    source .venv/bin/activate        # 进入虚拟环境"
    echo "    yuleosh -h                       # CLI"
    echo "    python -m yuleosh.ui.server      # Dashboard: http://localhost:8080"
    echo "    # 跑测试（macOS 建议先提升 fd 限制，见 docs）:"
    echo "    ulimit -n 4096 && python -m pytest tests/ -q"
    echo ""
}

# ---- Archive fallback ------------------------------------------------------
download_archive() {
    local url="${GITHUB}/archive/refs/heads/main.tar.gz"
    info "Downloading archive from ${url}..."
    mkdir -p /tmp/yuleosh-install
    cd /tmp/yuleosh-install
    curl -fsSL "$url" | tar xz --strip=1 -C "${INSTALL_DIR}" 2>/dev/null || {
        fail "Archive download failed."
        info "Check: ${url}"
        exit 1
    }
    rm -rf /tmp/yuleosh-install
}

# ---- Entry ----------------------------------------------------------------
main "$@"
