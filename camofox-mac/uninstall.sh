#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# CamoFox Mac — Uninstaller
# ═══════════════════════════════════════════════════════════════════════════
# Completely removes CamoFox Mac, restores all system settings, and
# cleans up configuration files.
#
# Usage:
#   ./uninstall.sh           # Interactive uninstall
#   ./uninstall.sh --force   # Non-interactive, remove everything
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

INSTALL_DIR="/usr/local/share/camofox-mac"
BIN_DIR="/usr/local/bin"
CONFIG_DIR="${HOME}/.camofox"
LAUNCH_AGENT_DIR="${HOME}/Library/LaunchAgents"
LAUNCH_AGENT="com.camofox.mac.plist"
PF_ANCHOR_NAME="com.camofox"

# Colors
BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
CYAN="\033[36m"
RESET="\033[0m"

print_ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
print_fail() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
print_warn() { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
print_info() { printf "  ${CYAN}•${RESET} %s\n" "$1"; }

banner() {
    printf "\n${BOLD}${RED}"
    printf "  ╔═══════════════════════════════════════╗\n"
    printf "  ║     CamoFox Mac — Uninstaller         ║\n"
    printf "  ╚═══════════════════════════════════════╝${RESET}\n\n"
}

# ---------------------------------------------------------------------------
# Stop running services
# ---------------------------------------------------------------------------
stop_services() {
    printf "${BOLD}Stopping CamoFox services...${RESET}\n\n"

    # Try to run camofox-mac stop first (cleanest way)
    if command -v camofox-mac >/dev/null 2>&1; then
        camofox-mac stop 2>/dev/null || true
        print_ok "Ran camofox-mac stop"
    elif [[ -f "${INSTALL_DIR}/camofox-mac.sh" ]]; then
        bash "${INSTALL_DIR}/camofox-mac.sh" stop 2>/dev/null || true
        print_ok "Ran camofox-mac.sh stop"
    fi

    # Kill any remaining processes
    local pids_to_kill=()
    for pidfile in "${CONFIG_DIR}/health_monitor.pid" "${CONFIG_DIR}/proxy_helper.pid" "${CONFIG_DIR}/dns_helper.pid"; do
        if [[ -f "$pidfile" ]]; then
            local pid
            pid=$(cat "$pidfile" 2>/dev/null) || true
            if [[ -n "$pid" ]]; then
                pids_to_kill+=("$pid")
            fi
        fi
    done

    # bash 3.2 + set -u: "${arr[@]}" on an empty array is unbound
    if [[ ${#pids_to_kill[@]} -gt 0 ]]; then
        for pid in "${pids_to_kill[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 1
        for pid in "${pids_to_kill[@]}"; do
            kill -9 "$pid" 2>/dev/null || true
        done
        print_ok "Killed remaining CamoFox processes"
    fi
}

# ---------------------------------------------------------------------------
# Restore system settings
# ---------------------------------------------------------------------------
restore_settings() {
    printf "\n${BOLD}Restoring system settings...${RESET}\n\n"

    # Detect network service
    local net_svc="Wi-Fi"
    if [[ -f "${CONFIG_DIR}/config" ]]; then
        local cfg_svc
        cfg_svc=$(grep '^NETWORK_SERVICE=' "${CONFIG_DIR}/config" 2>/dev/null | cut -d= -f2 | xargs) || true
        [[ -n "$cfg_svc" ]] && net_svc="$cfg_svc"
    fi

    # Disable proxies
    networksetup -setsocksfirewallproxystate "$net_svc" off 2>/dev/null || true
    networksetup -setwebproxystate "$net_svc" off 2>/dev/null || true
    networksetup -setsecurewebproxystate "$net_svc" off 2>/dev/null || true
    networksetup -setautoproxystate "$net_svc" off 2>/dev/null || true
    print_ok "Disabled all proxy settings on '$net_svc'"

    # Restore DNS
    if [[ -f "${CONFIG_DIR}/dns_backup" ]]; then
        local saved_dns
        saved_dns=$(cat "${CONFIG_DIR}/dns_backup")
        if [[ "$saved_dns" == "auto" ]]; then
            networksetup -setdnsservers "$net_svc" empty 2>/dev/null || true
        else
            local dns_args
            dns_args=$(echo "$saved_dns" | tr '\n' ' ')
            networksetup -setdnsservers "$net_svc" $dns_args 2>/dev/null || true
        fi
        print_ok "DNS restored from backup"
    else
        # Set to automatic as fallback
        networksetup -setdnsservers "$net_svc" empty 2>/dev/null || true
        print_ok "DNS set to automatic (DHCP)"
    fi

    # Remove pfctl rules
    if [[ $EUID -eq 0 ]]; then
        pfctl -a "$PF_ANCHOR_NAME" -F all 2>/dev/null || true

        local main_pf="/etc/pf.conf"
        if grep -q "CamoFox Mac anchor" "$main_pf" 2>/dev/null; then
            sed -i '' '/# CamoFox Mac anchor/d' "$main_pf" 2>/dev/null || true
            sed -i '' "/rdr-anchor \"$PF_ANCHOR_NAME\"/d" "$main_pf" 2>/dev/null || true
            sed -i '' "/anchor \"$PF_ANCHOR_NAME\"/d" "$main_pf" 2>/dev/null || true
            pfctl -f "$main_pf" 2>/dev/null || true
            print_ok "PF anchor removed and rules reloaded"
        fi
    else
        if pfctl -s Anchors 2>/dev/null | grep -q "$PF_ANCHOR_NAME"; then
            print_warn "PF anchor still active — run uninstaller with sudo to remove"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Remove LaunchAgent
# ---------------------------------------------------------------------------
remove_launch_agent() {
    printf "\n${BOLD}Removing LaunchAgent...${RESET}\n\n"

    local plist_path="${LAUNCH_AGENT_DIR}/${LAUNCH_AGENT}"
    if [[ -f "$plist_path" ]]; then
        launchctl unload "$plist_path" 2>/dev/null || true
        rm -f "$plist_path"
        print_ok "LaunchAgent removed: $plist_path"
    else
        print_info "LaunchAgent not installed (nothing to remove)"
    fi
}

# ---------------------------------------------------------------------------
# Remove installed files
# ---------------------------------------------------------------------------
remove_files() {
    printf "\n${BOLD}Removing CamoFox files...${RESET}\n\n"

    # Remove symlink
    if [[ -L "${BIN_DIR}/camofox-mac" ]]; then
        sudo rm -f "${BIN_DIR}/camofox-mac"
        print_ok "Removed ${BIN_DIR}/camofox-mac"
    fi

    # Remove install directory
    if [[ -d "$INSTALL_DIR" ]]; then
        sudo rm -rf "$INSTALL_DIR"
        print_ok "Removed $INSTALL_DIR"
    fi

    # Remove log files
    rm -f /tmp/camofox-mac.stdout.log /tmp/camofox-mac.stderr.log 2>/dev/null || true
    print_ok "Removed temporary log files"
}

# ---------------------------------------------------------------------------
# Remove config
# ---------------------------------------------------------------------------
remove_config() {
    local remove="$1"  # "yes" or "no"

    if [[ "$remove" != "yes" ]]; then
        print_info "Config directory preserved: $CONFIG_DIR"
        return
    fi

    printf "\n${BOLD}Removing configuration...${RESET}\n\n"

    if [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        print_ok "Removed $CONFIG_DIR"
    else
        print_info "Config directory not found (nothing to remove)"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local force=false

    for arg in "$@"; do
        case "$arg" in
            --force|-f) force=true ;;
            --help|-h)
                echo "Usage: uninstall.sh [--force]"
                exit 0
                ;;
        esac
    done

    banner

    if [[ "$force" != "true" ]]; then
        printf "  This will completely remove CamoFox Mac and restore system settings.\n"
        printf "  Are you sure? [y/N]: "
        read -r answer
        case "$answer" in
            [Yy]*) ;;
            *) echo "  Cancelled."; exit 0 ;;
        esac
        echo ""
    fi

    # Step 1: Stop services
    stop_services

    # Step 2: Restore settings
    restore_settings

    # Step 3: Remove LaunchAgent
    remove_launch_agent

    # Step 4: Remove files
    remove_files

    # Step 5: Config
    local remove_conf="yes"
    if [[ "$force" != "true" ]]; then
        printf "\n  Remove configuration directory (~/.camofox)?\n"
        printf "  This includes your config file and logs. [y/N]: "
        read -r answer
        case "$answer" in
            [Yy]*) remove_conf="yes" ;;
            *) remove_conf="no" ;;
        esac
    fi
    remove_config "$remove_conf"

    echo ""
    printf "${GREEN}${BOLD}CamoFox Mac has been completely removed.${RESET}\n"
    print_info "All system settings have been restored to their original values."
    echo ""
}

main "$@"
