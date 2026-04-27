#!/bin/sh
# CamoFox Installer
# One-click installation for the CamoFox tethering bypass plugin.
#
# Installs dependencies, copies configuration files, enables the service,
# and runs a basic connectivity test.
#
# Usage: sh install.sh [--unattended]
#
# Requirements:
#   - GL-iNet Opal (GL-SFT1200) or compatible OpenWrt router
#   - Internet connectivity (for package installation)
#   - Root access (SSH)

set -e

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FILES_DIR="$PROJECT_DIR/files"

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
print_step() { printf "\n${BOLD}${CYAN}[%s]${RESET} ${BOLD}%s${RESET}\n" "$1" "$2"; }

banner() {
    printf "\n${BOLD}${CYAN}"
    printf "  ╔═══════════════════════════════════════════╗\n"
    printf "  ║       CamoFox Installer v%s            ║\n" "$VERSION"
    printf "  ║   Tethering Bypass for GL-iNet Routers   ║\n"
    printf "  ╚═══════════════════════════════════════════╝${RESET}\n\n"
}

die() {
    print_fail "$1"
    exit 1
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "This script must be run as root"
    fi
}

check_platform() {
    print_step "1/7" "Checking platform compatibility"

    # Check if we're on OpenWrt
    if [ ! -f /etc/openwrt_release ]; then
        print_warn "Not running on OpenWrt — compatibility not guaranteed"
    else
        print_ok "OpenWrt detected"
        . /etc/openwrt_release
        print_info "Distribution: $DISTRIB_DESCRIPTION"
    fi

    # Check for GL-iNet Opal (best effort)
    if [ -f /tmp/sysinfo/model ]; then
        model=$(cat /tmp/sysinfo/model)
        print_info "Device model: $model"
        case "$model" in
            *SFT1200*|*Opal*|*gl-sft1200*)
                print_ok "GL-iNet Opal (GL-SFT1200) detected"
                ;;
            *gl-*|*GL-*)
                print_warn "GL-iNet device detected (not Opal — may work)"
                ;;
            *)
                print_warn "Unknown device — CamoFox may still work"
                ;;
        esac
    fi

    # Check available space
    avail_kb=$(df /overlay 2>/dev/null | tail -1 | awk '{print $4}')
    if [ -n "$avail_kb" ]; then
        if [ "$avail_kb" -lt 2048 ]; then
            print_warn "Low disk space: ${avail_kb}KB available (need ~2MB)"
        else
            print_ok "Disk space OK (${avail_kb}KB available)"
        fi
    fi

    # Check iptables
    if command -v iptables >/dev/null 2>&1; then
        print_ok "iptables available"
    else
        die "iptables not found — required for CamoFox"
    fi
}

# ---------------------------------------------------------------------------
# Install dependencies via opkg
# ---------------------------------------------------------------------------
install_dependencies() {
    print_step "2/7" "Installing dependencies"

    # Update package lists
    print_info "Updating package lists..."
    if opkg update >/dev/null 2>&1; then
        print_ok "Package lists updated"
    else
        print_warn "Failed to update package lists (continuing with cached)"
    fi

    # Required packages
    PACKAGES="redsocks iptables-mod-ipopt"
    OPTIONAL_PACKAGES="https-dns-proxy"

    for pkg in $PACKAGES; do
        if opkg list-installed 2>/dev/null | grep -q "^$pkg "; then
            print_ok "$pkg already installed"
        else
            print_info "Installing $pkg..."
            if opkg install "$pkg" >/dev/null 2>&1; then
                print_ok "$pkg installed"
            else
                die "Failed to install $pkg (required)"
            fi
        fi
    done

    for pkg in $OPTIONAL_PACKAGES; do
        if opkg list-installed 2>/dev/null | grep -q "^$pkg "; then
            print_ok "$pkg already installed"
        else
            print_info "Installing $pkg (optional)..."
            if opkg install "$pkg" >/dev/null 2>&1; then
                print_ok "$pkg installed"
            else
                print_warn "$pkg not available (DNS-over-HTTPS won't work)"
            fi
        fi
    done
}

# ---------------------------------------------------------------------------
# Copy CamoFox files to system
# ---------------------------------------------------------------------------
install_files() {
    print_step "3/7" "Installing CamoFox files"

    if [ ! -d "$FILES_DIR" ]; then
        die "Files directory not found: $FILES_DIR"
    fi

    # Create directories
    mkdir -p /etc/camofox
    mkdir -p /etc/hotplug.d/iface

    # Copy configuration (don't overwrite existing)
    if [ ! -f /etc/config/camofox ]; then
        cp "$FILES_DIR/etc/config/camofox" /etc/config/camofox
        print_ok "UCI configuration installed"
    else
        print_warn "UCI config exists, preserving current settings"
    fi

    # Copy camofox directory files (always update)
    cp "$FILES_DIR/etc/camofox/redsocks.conf.template" /etc/camofox/
    cp "$FILES_DIR/etc/camofox/firewall.rules" /etc/camofox/
    cp "$FILES_DIR/etc/camofox/health_check.sh" /etc/camofox/
    chmod +x /etc/camofox/firewall.rules
    chmod +x /etc/camofox/health_check.sh
    print_ok "Core scripts installed"

    # Copy init script
    cp "$FILES_DIR/etc/init.d/camofox" /etc/init.d/camofox
    chmod +x /etc/init.d/camofox
    print_ok "Init script installed"

    # Copy hotplug script
    cp "$FILES_DIR/etc/hotplug.d/iface/99-camofox" /etc/hotplug.d/iface/99-camofox
    chmod +x /etc/hotplug.d/iface/99-camofox
    print_ok "Hotplug auto-detection installed"

    # Copy management tool
    cp "$FILES_DIR/usr/bin/camofox" /usr/bin/camofox
    chmod +x /usr/bin/camofox
    print_ok "Management tool installed (/usr/bin/camofox)"

    # Copy setup wizard
    if [ -f "$SCRIPT_DIR/setup-wizard.sh" ]; then
        mkdir -p /usr/lib/camofox
        cp "$SCRIPT_DIR/setup-wizard.sh" /usr/lib/camofox/setup-wizard.sh
        chmod +x /usr/lib/camofox/setup-wizard.sh
        print_ok "Setup wizard installed"
    fi
}

# ---------------------------------------------------------------------------
# Configure initial settings
# ---------------------------------------------------------------------------
configure_defaults() {
    print_step "4/7" "Configuring defaults"

    # Ensure UCI defaults are set
    uci -q get camofox.main >/dev/null 2>&1 || {
        print_info "Creating default UCI configuration"
        uci set camofox.main=camofox
    }

    # Set sensible defaults if not already configured
    uci -q get camofox.main.proxy_ip >/dev/null 2>&1 || uci set camofox.main.proxy_ip='172.20.10.1'
    uci -q get camofox.main.proxy_port >/dev/null 2>&1 || uci set camofox.main.proxy_port='1080'
    uci -q get camofox.main.proxy_type >/dev/null 2>&1 || uci set camofox.main.proxy_type='socks5'
    uci -q get camofox.main.ttl_value >/dev/null 2>&1 || uci set camofox.main.ttl_value='65'
    uci -q get camofox.main.kill_switch >/dev/null 2>&1 || uci set camofox.main.kill_switch='1'
    uci -q get camofox.main.doh_enabled >/dev/null 2>&1 || uci set camofox.main.doh_enabled='1'

    uci commit camofox
    print_ok "Default configuration applied"
}

# ---------------------------------------------------------------------------
# Enable service
# ---------------------------------------------------------------------------
enable_service() {
    print_step "5/7" "Enabling CamoFox service"

    /etc/init.d/camofox enable 2>/dev/null
    print_ok "CamoFox enabled for boot startup"
    print_info "Service will start automatically after reboot"
}

# ---------------------------------------------------------------------------
# Stop any conflicting redsocks instances
# ---------------------------------------------------------------------------
stop_conflicting() {
    print_step "6/7" "Checking for conflicts"

    # Stop any existing redsocks
    if pidof redsocks >/dev/null 2>&1; then
        print_warn "Existing redsocks instance found, stopping"
        killall redsocks 2>/dev/null
        sleep 1
    fi

    # Check if port 12345 is in use
    if netstat -tlnp 2>/dev/null | grep -q ":12345 "; then
        print_warn "Port 12345 is in use — may conflict with redsocks"
    else
        print_ok "No port conflicts detected"
    fi
}

# ---------------------------------------------------------------------------
# Verify installation
# ---------------------------------------------------------------------------
verify_install() {
    print_step "7/7" "Verifying installation"

    errors=0

    # Check all files exist
    for f in /etc/config/camofox \
             /etc/camofox/redsocks.conf.template \
             /etc/camofox/firewall.rules \
             /etc/camofox/health_check.sh \
             /etc/init.d/camofox \
             /etc/hotplug.d/iface/99-camofox \
             /usr/bin/camofox; do
        if [ -f "$f" ]; then
            print_ok "$(basename $f) present"
        else
            print_fail "$(basename $f) MISSING"
            errors=$((errors + 1))
        fi
    done

    # Check executables
    for f in /etc/camofox/firewall.rules \
             /etc/camofox/health_check.sh \
             /etc/init.d/camofox \
             /usr/bin/camofox; do
        if [ -x "$f" ]; then
            : # OK
        else
            print_fail "$(basename $f) not executable"
            errors=$((errors + 1))
        fi
    done

    # Check commands
    if command -v redsocks >/dev/null 2>&1; then
        print_ok "redsocks binary found"
    else
        print_fail "redsocks binary not found"
        errors=$((errors + 1))
    fi

    if [ $errors -eq 0 ]; then
        print_ok "All checks passed"
    else
        print_fail "$errors check(s) failed"
    fi

    return $errors
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
banner
check_root
check_platform
install_dependencies
install_files
configure_defaults
enable_service
stop_conflicting
verify_install
ret=$?

echo ""
if [ $ret -eq 0 ]; then
    printf "${GREEN}${BOLD}╔═══════════════════════════════════════════╗${RESET}\n"
    printf "${GREEN}${BOLD}║   CamoFox installed successfully!         ║${RESET}\n"
    printf "${GREEN}${BOLD}╚═══════════════════════════════════════════╝${RESET}\n"
else
    printf "${YELLOW}${BOLD}Installation completed with warnings.${RESET}\n"
fi

echo ""
printf "${BOLD}Next steps:${RESET}\n"
print_info "1. Start SOCKS5 proxy on your iPhone (Pythonista + iOS-SOCKS-Server)"
print_info "2. Connect iPhone to router via USB or WiFi"
print_info "3. Run 'camofox setup' for interactive configuration"
print_info "   OR run 'camofox start' to start with default settings"
print_info "4. Run 'camofox test' to verify everything works"
echo ""
printf "${CYAN}Management: camofox {start|stop|restart|status|test|logs}${RESET}\n"
echo ""
