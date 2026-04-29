#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# CamoFox Mac — Installer
# ═══════════════════════════════════════════════════════════════════════════
# Installs CamoFox Mac scripts, configuration, and optionally the
# LaunchAgent for auto-start on login.
#
# Usage:
#   ./install.sh           # Interactive install
#   ./install.sh --auto    # Non-interactive with defaults
#   ./install.sh --uninstall  # Remove everything
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/usr/local/share/camofox-mac"
BIN_DIR="/usr/local/bin"
CONFIG_DIR="${HOME}/.camofox"
LAUNCH_AGENT_DIR="${HOME}/Library/LaunchAgents"
LAUNCH_AGENT="com.camofox.mac.plist"

# Colors
BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
CYAN="\033[36m"
DIM="\033[2m"
RESET="\033[0m"

print_ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
print_fail() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
print_warn() { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
print_info() { printf "  ${CYAN}•${RESET} %s\n" "$1"; }

banner() {
    printf "\n${BOLD}${CYAN}"
    printf "  ╔═══════════════════════════════════════╗\n"
    printf "  ║     CamoFox Mac Installer v%s      ║\n" "$VERSION"
    printf "  ╚═══════════════════════════════════════╝${RESET}\n\n"
}

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
check_prerequisites() {
    printf "${BOLD}Checking prerequisites...${RESET}\n\n"
    local ok=true

    # macOS version
    local macos_version
    macos_version=$(sw_vers -productVersion 2>/dev/null) || macos_version="unknown"
    local major_version
    major_version=$(echo "$macos_version" | cut -d. -f1)

    if [[ "$major_version" -ge 10 ]] 2>/dev/null; then
        # Check for 10.14+ or 11+
        local minor_version
        minor_version=$(echo "$macos_version" | cut -d. -f2)
        if [[ "$major_version" -eq 10 && "$minor_version" -lt 14 ]] 2>/dev/null; then
            print_fail "macOS $macos_version — requires 10.14 (Mojave) or later"
            ok=false
        else
            print_ok "macOS $macos_version"
        fi
    else
        print_warn "Could not determine macOS version ($macos_version)"
    fi

    # Python 3
    if command -v python3 >/dev/null 2>&1; then
        local py_version
        py_version=$(python3 --version 2>&1 | awk '{print $2}')
        print_ok "Python 3 ($py_version)"
    else
        print_fail "Python 3 not found — install Xcode Command Line Tools:"
        print_info "  xcode-select --install"
        ok=false
    fi

    # bash
    if command -v bash >/dev/null 2>&1; then
        local bash_version
        bash_version=$(bash --version | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        print_ok "Bash $bash_version"
    else
        print_fail "Bash not found"
        ok=false
    fi

    # nc (netcat)
    if command -v nc >/dev/null 2>&1; then
        print_ok "netcat (nc)"
    else
        print_warn "netcat (nc) not found — discovery will be limited"
    fi

    # xxd
    if command -v xxd >/dev/null 2>&1; then
        print_ok "xxd"
    else
        print_warn "xxd not found — SOCKS5 handshake verification disabled"
    fi

    # curl
    if command -v curl >/dev/null 2>&1; then
        print_ok "curl"
    else
        print_warn "curl not found — connectivity tests will be limited"
    fi

    # Optional: dnscrypt-proxy
    if command -v dnscrypt-proxy >/dev/null 2>&1; then
        print_ok "dnscrypt-proxy (optional — recommended for DoH)"
    else
        print_info "dnscrypt-proxy not found (optional)"
        print_dim "  Install for best DNS privacy:  brew install dnscrypt-proxy"
    fi

    # Optional: cloudflared
    if command -v cloudflared >/dev/null 2>&1; then
        print_ok "cloudflared (optional — alternative DoH)"
    else
        print_info "cloudflared not found (optional)"
    fi

    echo ""

    if [[ "$ok" == "false" ]]; then
        print_fail "Prerequisites check failed.  Fix the issues above and retry."
        return 1
    fi

    print_ok "All required prerequisites met"
    return 0
}

# ---------------------------------------------------------------------------
# Install files
# ---------------------------------------------------------------------------
install_files() {
    printf "\n${BOLD}Installing CamoFox Mac...${RESET}\n\n"

    # Create install directory
    sudo mkdir -p "$INSTALL_DIR"
    print_ok "Created $INSTALL_DIR"

    # Copy scripts
    local scripts=("camofox-mac.sh" "discover.sh" "dns-setup.sh" "proxy_helper.py" "pfctl-rules.conf")
    for script in "${scripts[@]}"; do
        if [[ -f "${SCRIPT_DIR}/${script}" ]]; then
            sudo cp "${SCRIPT_DIR}/${script}" "$INSTALL_DIR/"
            sudo chmod +x "${INSTALL_DIR}/${script}"
            print_ok "Installed $script"
        else
            print_warn "$script not found in source directory"
        fi
    done

    # Create symlink in PATH
    sudo ln -sf "${INSTALL_DIR}/camofox-mac.sh" "${BIN_DIR}/camofox-mac"
    print_ok "Created symlink: ${BIN_DIR}/camofox-mac"

    # Create config directory
    mkdir -p "$CONFIG_DIR"
    print_ok "Created config directory: $CONFIG_DIR"

    # Copy example config if no config exists
    if [[ ! -f "${CONFIG_DIR}/config" ]]; then
        if [[ -f "${SCRIPT_DIR}/config.example" ]]; then
            cp "${SCRIPT_DIR}/config.example" "${CONFIG_DIR}/config"
            print_ok "Installed default config: ${CONFIG_DIR}/config"
        fi
    else
        print_info "Existing config preserved: ${CONFIG_DIR}/config"
    fi

    echo ""
}

# ---------------------------------------------------------------------------
# Install LaunchAgent
# ---------------------------------------------------------------------------
install_launch_agent() {
    local install_agent="$1"  # "yes" or "no"

    if [[ "$install_agent" != "yes" ]]; then
        print_info "Skipping LaunchAgent installation"
        return
    fi

    printf "\n${BOLD}Installing LaunchAgent...${RESET}\n\n"

    mkdir -p "$LAUNCH_AGENT_DIR"

    # Customize plist with current username
    local current_user
    current_user=$(whoami)
    local plist_source="${SCRIPT_DIR}/${LAUNCH_AGENT}"

    if [[ -f "$plist_source" ]]; then
        sed "s|REPLACE_WITH_USERNAME|$current_user|g" "$plist_source" \
            > "${LAUNCH_AGENT_DIR}/${LAUNCH_AGENT}"
        print_ok "Installed LaunchAgent: ${LAUNCH_AGENT_DIR}/${LAUNCH_AGENT}"

        # Load the agent
        launchctl load "${LAUNCH_AGENT_DIR}/${LAUNCH_AGENT}" 2>/dev/null || true
        print_ok "LaunchAgent loaded (CamoFox will start on login)"
    else
        print_warn "LaunchAgent plist not found in source directory"
    fi
}

# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------
ask_yes_no() {
    local prompt="$1"
    local default="$2"  # "yes" or "no"
    local answer

    if [[ "$default" == "yes" ]]; then
        printf "  %s [Y/n]: " "$prompt"
    else
        printf "  %s [y/N]: " "$prompt"
    fi

    read -r answer
    case "$answer" in
        [Yy]*) echo "yes" ;;
        [Nn]*) echo "no" ;;
        "")    echo "$default" ;;
        *)     echo "$default" ;;
    esac
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local auto_mode=false

    # Parse args
    for arg in "$@"; do
        case "$arg" in
            --auto)      auto_mode=true ;;
            --uninstall) exec "${SCRIPT_DIR}/uninstall.sh"; exit ;;
            --help|-h)
                echo "Usage: install.sh [--auto] [--uninstall]"
                exit 0
                ;;
        esac
    done

    banner

    # Check prerequisites
    if ! check_prerequisites; then
        exit 1
    fi

    # Install files
    install_files

    # LaunchAgent
    local install_agent="no"
    if [[ "$auto_mode" == "true" ]]; then
        install_agent="no"  # Default: don't auto-install agent
    else
        install_agent=$(ask_yes_no "Install LaunchAgent (auto-start on login)?" "no")
    fi
    install_launch_agent "$install_agent"

    # Done
    echo ""
    printf "${GREEN}${BOLD}Installation complete!${RESET}\n\n"
    printf "${BOLD}Quick Start:${RESET}\n"
    printf "  1. Start CamoFox iOS proxy on your iPhone\n"
    printf "  2. Connect Mac and iPhone to the same Wi-Fi\n"
    printf "  3. Run: ${CYAN}camofox-mac start${RESET}\n"
    echo ""
    printf "${BOLD}Configuration:${RESET} ${CONFIG_DIR}/config\n"
    printf "${BOLD}Logs:${RESET}          ${CONFIG_DIR}/camofox.log\n"
    echo ""
    printf "${DIM}For force mode (catches ALL traffic): sudo camofox-mac start${RESET}\n"
    printf "${DIM}Edit ~/.camofox/config and set MODE=force${RESET}\n"
    echo ""
}

main "$@"
