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
