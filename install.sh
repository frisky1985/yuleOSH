#!/usr/bin/env bash
# yuleOSH 一键安装脚本
# curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash
set -euo pipefail

YULEOSH_VERSION="${1:-latest}"
INSTALL_DIR="${YULEOSH_DIR:-$HOME/.yuleosh}"
GITHUB="https://github.com/frisky1985/yuleOSH"

echo "🔱 Installing yuleOSH v${YULEOSH_VERSION}..."
echo "   Target: ${INSTALL_DIR}"

# Create install directory
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

# Clone or download
if [ -d ".git" ]; then
    echo "   Updating existing installation..."
    git pull
else
    echo "   Downloading..."
    git clone --depth 1 "${GITHUB}.git" tmp 2>/dev/null || {
        curl -fsSL "${GITHUB}/archive/refs/heads/main.tar.gz" | tar xz --strip=1
        echo "   Extracted from archive"
    }
    if [ -d "tmp" ]; then
        mv tmp/* . 2>/dev/null; mv tmp/.[!.]* . 2>/dev/null; rmdir tmp
    fi
    echo "   Downloaded v${YULEOSH_VERSION}"
fi

# Create symlink
ln -sf "${INSTALL_DIR}/src/cli/yuleosh.sh" /usr/local/bin/yuleosh 2>/dev/null || {
    echo "   ⚠️  Could not create symlink to /usr/local/bin"
    echo "   You can add to PATH: export PATH=\$PATH:${INSTALL_DIR}/src/cli"
}

# Install Python deps
pip3 install pytest coverage 2>/dev/null || true

# Initialize
YULEOSH_DIR="${INSTALL_DIR}" yuleosh init "${INSTALL_DIR}"

echo ""
echo "✅ yuleOSH v${YULEOSH_VERSION} installed!"
echo "   Run: yuleosh help"
echo "   Docs: ${INSTALL_DIR}/docs/"
echo "   GitHub: ${GITHUB}"
