#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# CamoFox Mac — Tethering Bypass for macOS
# ═══════════════════════════════════════════════════════════════════════════
# Routes all MacBook traffic through an iPhone's SOCKS5 proxy, bypassing
# T-Mobile tethering detection.  The iPhone runs CamoFox iOS (Pythonista)
# and both devices share the same Wi-Fi network.
#
# Usage:
#   camofox-mac start    — Enable proxy routing
#   camofox-mac stop     — Disable and restore settings
#   camofox-mac status   — Show current status
#   camofox-mac test     — Run connectivity & leak tests
#   camofox-mac find     — Scan for iPhone proxy
#   camofox-mac version  — Show version
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

VERSION="1.0.0"
NAME="CamoFox Mac"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Under sudo, HOME is typically /var/root. Resolve the invoking user so
# sudo start and unprivileged stop/status share ~/.camofox. Non-sudo
# simple mode keeps using the current user's HOME.
_camofox_real_home() {
    local u="" h=""
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        u="${SUDO_USER:-}"
        if [[ -z "$u" || "$u" == "root" ]]; then
            u=$(logname 2>/dev/null) || true
        fi
        if [[ -n "$u" && "$u" != "root" ]]; then
            h=$(eval echo "~$u" 2>/dev/null) || true
            if [[ -n "$h" && "$h" != "~$u" && -d "$h" ]]; then
                printf '%s\n' "$h"
                return 0
            fi
            if command -v dscl >/dev/null 2>&1; then
                h=$(dscl . -read "/Users/$u" NFSHomeDirectory 2>/dev/null | awk '{print $2}') || true
                if [[ -n "$h" && -d "$h" ]]; then
                    printf '%s\n' "$h"
                    return 0
                fi
            fi
            if command -v getent >/dev/null 2>&1; then
                h=$(getent passwd "$u" 2>/dev/null | cut -d: -f6) || true
                if [[ -n "$h" && -d "$h" ]]; then
                    printf '%s\n' "$h"
                    return 0
                fi
            fi
        fi
    fi
    printf '%s\n' "${HOME}"
}

_CAMOFOX_REAL_HOME="$(_camofox_real_home)"
STATE_DIR="${_CAMOFOX_REAL_HOME}/.camofox"
CONFIG_FILE="${STATE_DIR}/config"
PROXY_BACKUP="${STATE_DIR}/proxy_backup"
HEALTH_PID_FILE="${STATE_DIR}/health_monitor.pid"
PROXY_HELPER_PID="${STATE_DIR}/proxy_helper.pid"
PF_ANCHOR_NAME="com.camofox"
PF_CONF_RUNTIME="${STATE_DIR}/pf_rules.conf"
LOG_FILE="${STATE_DIR}/camofox.log"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
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
print_dim()  { printf "  ${DIM}%s${RESET}\n" "$1"; }

banner() {
    printf "\n${BOLD}${CYAN}"
    printf "  ╔═══════════════════════════════════════╗\n"
    printf "  ║       CamoFox Mac  v%s             ║\n" "$VERSION"
    printf "  ║    Tethering Bypass for macOS         ║\n"
    printf "  ╚═══════════════════════════════════════╝${RESET}\n\n"
}

log_msg() {
    local level="$1"
    shift
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" >> "$LOG_FILE" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
load_config() {
    # Defaults
    PROXY_IP="auto"
    SOCKS_PORT=9876
    HTTP_PORT=9877
    MODE="simple"
    DNS_MODE="doh"
    DOH_SERVER="https://cloudflare-dns.com/dns-query"
    FALLBACK_DNS="1.1.1.1,1.0.0.1"
    KILL_SWITCH="true"
    AUTO_DISCOVER="true"
    DISCOVER_TIMEOUT=1
    HEALTH_INTERVAL=30
    NETWORK_SERVICE="Wi-Fi"
    LOCAL_PROXY_PORT=12345
    PF_INTERFACE="en0"
    LOG_LEVEL="info"
    BYPASS_RANGES=""
    BYPASS_DOMAINS=""

    # Load user config
    if [[ -f "$CONFIG_FILE" ]]; then
        # Source only valid KEY=value lines (ignore comments/blanks)
        while IFS='=' read -r key value; do
            # Skip comments and blank lines
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue
            # Trim whitespace
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)
            # Export known variables
            case "$key" in
                PROXY_IP|SOCKS_PORT|HTTP_PORT|MODE|DNS_MODE|DOH_SERVER|\
                FALLBACK_DNS|KILL_SWITCH|AUTO_DISCOVER|DISCOVER_TIMEOUT|\
                HEALTH_INTERVAL|NETWORK_SERVICE|LOCAL_PROXY_PORT|\
                PF_INTERFACE|LOG_FILE|LOG_LEVEL|BYPASS_RANGES|BYPASS_DOMAINS)
                    eval "$key=\"$value\""
                    ;;
            esac
        done < "$CONFIG_FILE"
    fi

    # Ensure state dir exists (and is owned by the real user under sudo)
    mkdir -p "$STATE_DIR"
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        local owner="${SUDO_USER:-}"
        if [[ -z "$owner" || "$owner" == "root" ]]; then
            owner=$(logname 2>/dev/null) || true
        fi
        if [[ -n "$owner" && "$owner" != "root" ]]; then
            chown "$owner" "$STATE_DIR" 2>/dev/null || true
        fi
    fi
}
