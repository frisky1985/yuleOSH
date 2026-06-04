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

    # Required: python3
    if ! command -v python3 &>/dev/null; then
        fail "python3 is required but not found."
        case "$OS" in
            linux)
                info "Install: apt install python3 (Debian/Ubuntu) / yum install python3 (RHEL)"
                ;;
            macos)
                info "Install: brew install python3"
                ;;
        esac
        issues=$((issues + 1))
    else
        local pyver
        pyver=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
        if ! version_ge "$pyver" "$MIN_PYTHON"; then
            fail "Python $pyver found, but $MIN_PYTHON+ required."
            issues=$((issues + 1))
        else
            ok "Python $pyver"
        fi
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
install_deps() {
    if [ "${YULEOSH_SKIP_DEPS:-0}" = "1" ]; then
        info "Skipping dependency install (YULEOSH_SKIP_DEPS=1)"
        return 0
    fi

    info "Checking Python dependencies..."
    local missing=0

    # Check pip availability
    if ! python3 -m pip --version &>/dev/null; then
        warn "pip not available — will install packages via newer pipx or fallback"
    fi

    # Install core dependencies
    for pkg in pytest coverage; do
        if ! python3 -c "import $pkg" 2>/dev/null; then
            info "Installing $pkg..."
            python3 -m pip install --quiet --no-cache-dir "$pkg" 2>/dev/null || {
                warn "Failed to install $pkg (non-fatal)"
            }
        fi
    done

    # Verify yuleOSH can be installed
    if [ -f "${INSTALL_DIR}/pyproject.toml" ]; then
        info "Installing yuleOSH package..."
        (cd "$INSTALL_DIR" && python3 -m pip install --quiet --no-cache-dir -e . 2>/dev/null) || {
            warn "Package install skipped (non-fatal for CLI usage)"
        }
    fi

    ok "Dependencies checked"
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
    if [ -w /usr/local/bin ]; then
        ln -sf "${INSTALL_DIR}/bin/yuleosh-server" /usr/local/bin/yuleosh 2>/dev/null && \
            ok "Symlink: /usr/local/bin/yuleosh" || \
            warn "Could not create symlink in /usr/local/bin"
    elif sudo -n true 2>/dev/null; then
        sudo ln -sf "${INSTALL_DIR}/bin/yuleosh-server" /usr/local/bin/yuleosh 2>/dev/null && \
            ok "Symlink: /usr/local/bin/yuleosh (via sudo)" || \
            warn "Could not create symlink in /usr/local/bin"
    else
        warn "Cannot write to /usr/local/bin"
        info "Add to PATH: export PATH=\$PATH:${INSTALL_DIR}/bin"
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
    echo "  🚀 Start:    yuleosh"
    echo "  📚 Docs:     ${INSTALL_DIR}/docs/"
    echo "  🌐 GitHub:   ${GITHUB}"
    echo ""
    echo "  Quick start:"
    echo "    cd ${INSTALL_DIR}"
    echo '    yuleosh -h'
    echo "    # or: python3 ${INSTALL_DIR}/src/ui/server.py"
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
