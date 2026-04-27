#!/bin/sh
# CamoFox Uninstaller
# Completely removes CamoFox from the router.
#
# Stops all services, removes firewall rules, deletes all installed files,
# and optionally removes dependencies.
#
# Usage: sh uninstall.sh [--keep-config] [--remove-deps]

set -e

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
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

# Parse arguments
KEEP_CONFIG=0
REMOVE_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --keep-config) KEEP_CONFIG=1 ;;
        --remove-deps) REMOVE_DEPS=1 ;;
    esac
done

# Check root
if [ "$(id -u)" -ne 0 ]; then
    print_fail "This script must be run as root"
    exit 1
fi

printf "\n${BOLD}${RED}"
printf "  ╔═══════════════════════════════════════════╗\n"
printf "  ║       CamoFox Uninstaller                 ║\n"
printf "  ╚═══════════════════════════════════════════╝${RESET}\n\n"

# Confirmation
if [ "$1" != "--yes" ] && [ "$2" != "--yes" ] && [ "$3" != "--yes" ]; then
    printf "${YELLOW}This will completely remove CamoFox from your router.${RESET}\n"
    printf "Continue? [y/N] "
    read -r answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
fi

echo ""

# ---------------------------------------------------------------------------
# Step 1: Stop services
# ---------------------------------------------------------------------------
printf "${BOLD}[1/5] Stopping services${RESET}\n"

if [ -x /etc/init.d/camofox ]; then
    /etc/init.d/camofox stop 2>/dev/null
    /etc/init.d/camofox disable 2>/dev/null
    print_ok "CamoFox service stopped and disabled"
else
    print_info "Init script not found (already removed?)"
fi

# Kill any remaining processes
if pidof redsocks >/dev/null 2>&1; then
    killall redsocks 2>/dev/null
    print_ok "Killed remaining redsocks process"
fi

if [ -f /var/run/camofox_health.pid ]; then
    kill "$(cat /var/run/camofox_health.pid)" 2>/dev/null
    rm -f /var/run/camofox_health.pid
    print_ok "Killed health monitor"
fi

# ---------------------------------------------------------------------------
# Step 2: Remove firewall rules
# ---------------------------------------------------------------------------
printf "\n${BOLD}[2/5] Removing firewall rules${RESET}\n"

if [ -x /etc/camofox/firewall.rules ]; then
    /etc/camofox/firewall.rules remove 2>/dev/null
    print_ok "Firewall rules removed"
else
    # Manual cleanup if script is gone
    iptables -t nat -F REDSOCKS 2>/dev/null
    iptables -t nat -X REDSOCKS 2>/dev/null
    while iptables -t nat -D PREROUTING -i br-lan -p tcp -j REDSOCKS 2>/dev/null; do :; done
    while iptables -t mangle -D POSTROUTING -j TTL --ttl-set 65 2>/dev/null; do :; done
    while ip6tables -t mangle -D POSTROUTING -j HL --hl-set 65 2>/dev/null; do :; done
    while iptables -D FORWARD -i br-lan -p udp --dport 53 -j DROP 2>/dev/null; do :; done
    iptables -F CAMOFOX_KILLSW 2>/dev/null
    iptables -X CAMOFOX_KILLSW 2>/dev/null
    print_ok "Firewall rules cleaned up manually"
fi

# ---------------------------------------------------------------------------
# Step 3: Remove installed files
# ---------------------------------------------------------------------------
printf "\n${BOLD}[3/5] Removing CamoFox files${RESET}\n"

rm -f /usr/bin/camofox && print_ok "Removed /usr/bin/camofox" || true
rm -f /etc/init.d/camofox && print_ok "Removed /etc/init.d/camofox" || true
rm -f /etc/hotplug.d/iface/99-camofox && print_ok "Removed hotplug script" || true
rm -rf /usr/lib/camofox && print_ok "Removed /usr/lib/camofox" || true

# Remove camofox directory
rm -rf /etc/camofox && print_ok "Removed /etc/camofox/" || true

# Remove generated config
rm -f /tmp/camofox_redsocks.conf
rm -f /tmp/camofox_proxy_state
rm -f /var/run/camofox_health.pid

# ---------------------------------------------------------------------------
# Step 4: Handle UCI configuration
# ---------------------------------------------------------------------------
printf "\n${BOLD}[4/5] Configuration cleanup${RESET}\n"

if [ $KEEP_CONFIG -eq 1 ]; then
    print_info "Keeping /etc/config/camofox (--keep-config)"
else
    rm -f /etc/config/camofox && print_ok "Removed UCI configuration" || true
fi

# Restore DNS settings if we modified them
if uci -q get dhcp.@dnsmasq[0].noresolv 2>/dev/null | grep -q '1'; then
    print_info "Restoring DNS settings"
    uci -q delete dhcp.@dnsmasq[0].noresolv 2>/dev/null
    uci -q delete dhcp.@dnsmasq[0].server 2>/dev/null
    uci commit dhcp 2>/dev/null
    /etc/init.d/dnsmasq restart 2>/dev/null
    print_ok "DNS settings restored to defaults"
fi

# ---------------------------------------------------------------------------
# Step 5: Optionally remove dependencies
# ---------------------------------------------------------------------------
printf "\n${BOLD}[5/5] Dependencies${RESET}\n"

if [ $REMOVE_DEPS -eq 1 ]; then
    print_info "Removing optional dependencies..."
    for pkg in redsocks https-dns-proxy iptables-mod-ipopt; do
        if opkg list-installed 2>/dev/null | grep -q "^$pkg "; then
            opkg remove "$pkg" 2>/dev/null
            print_ok "Removed $pkg"
        fi
    done
else
    print_info "Dependencies kept (use --remove-deps to remove)"
    print_info "Installed: redsocks, iptables-mod-ipopt, https-dns-proxy"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
printf "${GREEN}${BOLD}CamoFox has been removed.${RESET}\n"
print_info "Your router is back to normal operation."
if [ $KEEP_CONFIG -eq 1 ]; then
    print_info "Configuration preserved at /etc/config/camofox"
fi
echo ""
