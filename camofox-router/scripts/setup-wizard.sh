#!/bin/sh
# CamoFox Setup Wizard
# Interactive configuration for the CamoFox tethering bypass plugin.
#
# Guides the user through:
#   1. Connection mode detection (USB vs WiFi)
#   2. iPhone IP auto-detection
#   3. SOCKS5 proxy connectivity test
#   4. DNS-over-HTTPS configuration
#   5. Kill switch and TTL settings
#   6. Apply and verify configuration

. /lib/functions.sh 2>/dev/null || true

# ---------------------------------------------------------------------------
# Helpers
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

ask() {
    # ask "prompt" "default"
    printf "${BOLD}%s${RESET}" "$1"
    if [ -n "$2" ]; then
        printf " [${CYAN}%s${RESET}]" "$2"
    fi
    printf ": "
    read -r _answer
    if [ -z "$_answer" ]; then
        _answer="$2"
    fi
    echo "$_answer"
}

ask_yn() {
    # ask_yn "prompt" "default (y/n)"
    while true; do
        printf "${BOLD}%s${RESET} [%s]: " "$1" "$2"
        read -r _yn
        [ -z "$_yn" ] && _yn="$2"
        case "$_yn" in
            y|Y|yes) return 0 ;;
            n|N|no)  return 1 ;;
            *) printf "  Please answer y or n\n" ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
printf "\n${BOLD}${CYAN}"
printf "  ╔═══════════════════════════════════════════╗\n"
printf "  ║       CamoFox Setup Wizard                ║\n"
printf "  ║   Interactive Configuration               ║\n"
printf "  ╚═══════════════════════════════════════════╝${RESET}\n\n"

printf "This wizard will configure CamoFox on your router.\n"
printf "Press Enter to accept defaults shown in ${CYAN}[brackets]${RESET}.\n\n"

# ---------------------------------------------------------------------------
# Step 1: Connection Mode
# ---------------------------------------------------------------------------
printf "${BOLD}${CYAN}━━━ Step 1/6: Connection Mode ━━━${RESET}\n\n"

# Auto-detect
USB_DETECTED=0
WIFI_DETECTED=0

for dev in usb0 eth2; do
    if ip link show "$dev" 2>/dev/null | grep -q "UP"; then
        USB_DETECTED=1
        USB_DEV="$dev"
        break
    fi
done

for dev in wlan-sta0 wlan0-1 apcli0; do
    if ip link show "$dev" 2>/dev/null | grep -q "UP"; then
        WIFI_DETECTED=1
        WIFI_DEV="$dev"
        break
    fi
done

if [ $USB_DETECTED -eq 1 ]; then
    print_ok "USB tethering interface detected: $USB_DEV"
    DETECTED_MODE="usb"
elif [ $WIFI_DETECTED -eq 1 ]; then
    print_ok "WiFi client interface detected: $WIFI_DEV"
    DETECTED_MODE="wifi"
else
    print_warn "No iPhone connection detected"
    DETECTED_MODE="usb"
fi

echo ""
printf "  How is the iPhone connected?\n"
printf "  ${CYAN}1)${RESET} USB tethering (recommended)\n"
printf "  ${CYAN}2)${RESET} WiFi client (connect to iPhone hotspot)\n"
echo ""

if [ "$DETECTED_MODE" = "usb" ]; then
    default_choice="1"
else
    default_choice="2"
fi

choice=$(ask "Select connection mode" "$default_choice")
case "$choice" in
    1) CONN_MODE="usb" ;;
    2) CONN_MODE="wifi" ;;
    *) CONN_MODE="usb" ;;
esac

print_ok "Connection mode: $CONN_MODE"
echo ""

# ---------------------------------------------------------------------------
# Step 2: iPhone IP Detection
# ---------------------------------------------------------------------------
printf "${BOLD}${CYAN}━━━ Step 2/6: iPhone IP Address ━━━${RESET}\n\n"

# Try to auto-detect
DETECTED_IP=""

case "$CONN_MODE" in
    usb)
        for dev in usb0 eth2 eth1; do
            gw=$(ip route show dev "$dev" 2>/dev/null | grep default | awk '{print $3}' | head -1)
            if [ -n "$gw" ]; then
                DETECTED_IP="$gw"
                break
            fi
        done
        ;;
    wifi)
        gw=$(ip route | grep default | head -1 | awk '{print $3}')
        [ -n "$gw" ] && DETECTED_IP="$gw"
        ;;
esac

if [ -n "$DETECTED_IP" ]; then
    print_ok "Auto-detected iPhone IP: $DETECTED_IP"
else
    print_warn "Could not auto-detect iPhone IP"
    DETECTED_IP="172.20.10.1"
fi

PROXY_IP=$(ask "iPhone IP address" "$DETECTED_IP")
print_ok "Using iPhone IP: $PROXY_IP"
echo ""

# ---------------------------------------------------------------------------
# Step 3: SOCKS5 Proxy Configuration & Test
# ---------------------------------------------------------------------------
printf "${BOLD}${CYAN}━━━ Step 3/6: SOCKS5 Proxy ━━━${RESET}\n\n"

print_info "The iPhone must be running iOS-SOCKS-Server via Pythonista."
print_info "Default ports: SOCKS5=9876 (CamoFox iOS), HTTP=1081"
echo ""

PROXY_PORT=$(ask "SOCKS5 proxy port" "9876")
PROXY_TYPE=$(ask "Proxy type (socks5/http)" "socks5")

echo ""
printf "  Testing proxy connectivity...\n"

# Test connectivity
PROXY_OK=0
if command -v nc >/dev/null 2>&1; then
    if echo "" | nc -w 3 "$PROXY_IP" "$PROXY_PORT" >/dev/null 2>&1; then
        PROXY_OK=1
    fi
fi

if [ $PROXY_OK -eq 1 ]; then
    print_ok "Proxy reachable at ${PROXY_IP}:${PROXY_PORT}"
else
    print_warn "Proxy NOT reachable at ${PROXY_IP}:${PROXY_PORT}"
    print_info "Make sure iOS-SOCKS-Server is running on your iPhone"
    print_info "You can start CamoFox anyway and connect iPhone later"
    echo ""
    if ! ask_yn "Continue with these settings?" "y"; then
        echo "Setup cancelled."
        exit 0
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 4: DNS Configuration
# ---------------------------------------------------------------------------
printf "${BOLD}${CYAN}━━━ Step 4/6: DNS-over-HTTPS ━━━${RESET}\n\n"

print_info "DNS-over-HTTPS prevents DNS leak to the carrier."
print_info "Without it, T-Mobile can see which sites you visit."
echo ""

if ask_yn "Enable DNS-over-HTTPS?" "y"; then
    DOH_ENABLED="1"
    printf "\n  DNS resolver options:\n"
    printf "  ${CYAN}1)${RESET} Cloudflare (1.1.1.1) — fast, privacy-focused\n"
    printf "  ${CYAN}2)${RESET} Google (8.8.8.8)\n"
    printf "  ${CYAN}3)${RESET} Custom URL\n"
    echo ""
    dns_choice=$(ask "Select DNS resolver" "1")
    case "$dns_choice" in
        1) DOH_RESOLVER="https://cloudflare-dns.com/dns-query" ;;
        2) DOH_RESOLVER="https://dns.google/dns-query" ;;
        3) DOH_RESOLVER=$(ask "Enter DoH resolver URL" "https://cloudflare-dns.com/dns-query") ;;
        *) DOH_RESOLVER="https://cloudflare-dns.com/dns-query" ;;
    esac
    print_ok "DoH resolver: $DOH_RESOLVER"
else
    DOH_ENABLED="0"
    DOH_RESOLVER=""
    print_warn "DNS-over-HTTPS disabled — DNS queries may leak"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 5: Security Settings
# ---------------------------------------------------------------------------
printf "${BOLD}${CYAN}━━━ Step 5/6: Security Settings ━━━${RESET}\n\n"

print_info "TTL mangling sets outbound packet TTL to 65."
print_info "After iPhone decrements it, it becomes 64 (normal iOS value)."
echo ""
if ask_yn "Enable TTL mangling (recommended)?" "y"; then
    TTL_ENABLED="1"
    TTL_VALUE=$(ask "TTL value" "65")
else
    TTL_ENABLED="0"
    TTL_VALUE="65"
fi

echo ""
print_info "Kill switch blocks all internet if the proxy goes down."
print_info "Prevents accidental unproxied traffic (which would be detected)."
echo ""
if ask_yn "Enable kill switch (recommended)?" "y"; then
    KILL_SWITCH="1"
else
    KILL_SWITCH="0"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 6: Apply Configuration
# ---------------------------------------------------------------------------
printf "${BOLD}${CYAN}━━━ Step 6/6: Apply Configuration ━━━${RESET}\n\n"

printf "${BOLD}Configuration Summary:${RESET}\n"
print_info "Connection mode: $CONN_MODE"
print_info "Proxy: $PROXY_IP:$PROXY_PORT ($PROXY_TYPE)"
print_info "TTL mangling: $([ "$TTL_ENABLED" = '1' ] && echo "enabled ($TTL_VALUE)" || echo 'disabled')"
print_info "Kill switch: $([ "$KILL_SWITCH" = '1' ] && echo 'enabled' || echo 'disabled')"
print_info "DoH: $([ "$DOH_ENABLED" = '1' ] && echo "enabled ($DOH_RESOLVER)" || echo 'disabled')"
echo ""

if ! ask_yn "Apply this configuration?" "y"; then
    echo "Setup cancelled. No changes made."
    exit 0
fi

echo ""
printf "  Applying configuration...\n"

# Write UCI configuration
uci set camofox.main=camofox
uci set camofox.main.enabled='1'
uci set camofox.main.connection_mode="$CONN_MODE"
uci set camofox.main.proxy_ip="$PROXY_IP"
uci set camofox.main.proxy_port="$PROXY_PORT"
uci set camofox.main.proxy_type="$PROXY_TYPE"
uci set camofox.main.ttl_enabled="$TTL_ENABLED"
uci set camofox.main.ttl_value="$TTL_VALUE"
uci set camofox.main.kill_switch="$KILL_SWITCH"
uci set camofox.main.doh_enabled="$DOH_ENABLED"
if [ -n "$DOH_RESOLVER" ]; then
    uci set camofox.main.doh_resolver="$DOH_RESOLVER"
fi
uci set camofox.main.auto_detect='1'
uci commit camofox

print_ok "Configuration saved"

# Enable service
if [ -x /etc/init.d/camofox ]; then
    /etc/init.d/camofox enable 2>/dev/null
    print_ok "Service enabled for boot"
fi

# Ask to start now
echo ""
if ask_yn "Start CamoFox now?" "y"; then
    echo ""
    if [ -x /usr/bin/camofox ]; then
        /usr/bin/camofox start
    elif [ -x /etc/init.d/camofox ]; then
        /etc/init.d/camofox start
        print_ok "CamoFox started"
    fi
else
    print_info "Start later with: camofox start"
fi

echo ""
printf "${GREEN}${BOLD}Setup complete!${RESET}\n\n"
printf "${BOLD}Useful commands:${RESET}\n"
print_info "camofox status  — Check if everything is running"
print_info "camofox test    — Run full diagnostics"
print_info "camofox logs    — View recent logs"
print_info "camofox stop    — Stop all services"
echo ""
