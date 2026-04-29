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
STATE_DIR="${HOME}/.camofox"
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

    # Ensure state dir exists
    mkdir -p "$STATE_DIR"
}

# ---------------------------------------------------------------------------
# Backup / restore macOS proxy settings
# ---------------------------------------------------------------------------
backup_proxy_settings() {
    local svc="$NETWORK_SERVICE"
    {
        echo "SOCKS_STATE=$(networksetup -getsocksfirewallproxy "$svc" 2>/dev/null | grep -i enabled | head -1 | awk '{print $2}')"
        echo "HTTP_STATE=$(networksetup -getwebproxy "$svc" 2>/dev/null | grep -i enabled | head -1 | awk '{print $2}')"
        echo "HTTPS_STATE=$(networksetup -getsecurewebproxy "$svc" 2>/dev/null | grep -i enabled | head -1 | awk '{print $2}')"
        echo "SOCKS_SERVER=$(networksetup -getsocksfirewallproxy "$svc" 2>/dev/null | grep -i server | head -1 | awk '{print $2}')"
        echo "SOCKS_SERVER_PORT=$(networksetup -getsocksfirewallproxy "$svc" 2>/dev/null | grep -i port | head -1 | awk '{print $2}')"
    } > "$PROXY_BACKUP"
    log_msg INFO "Proxy settings backed up"
}

restore_proxy_settings() {
    local svc="$NETWORK_SERVICE"

    # Disable all proxies
    networksetup -setsocksfirewallproxystate "$svc" off 2>/dev/null || true
    networksetup -setwebproxystate "$svc" off 2>/dev/null || true
    networksetup -setsecurewebproxystate "$svc" off 2>/dev/null || true
    networksetup -setautoproxystate "$svc" off 2>/dev/null || true

    print_ok "System proxy settings restored"
    log_msg INFO "Proxy settings restored"
    rm -f "$PROXY_BACKUP"
}

# ---------------------------------------------------------------------------
# iPhone discovery
# ---------------------------------------------------------------------------
discover_iphone() {
    if [[ "$PROXY_IP" != "auto" ]]; then
        print_info "Using configured proxy IP: $PROXY_IP"
        return 0
    fi

    if [[ "$AUTO_DISCOVER" != "true" ]]; then
        print_fail "PROXY_IP is 'auto' but AUTO_DISCOVER is disabled"
        print_info "Set PROXY_IP manually in $CONFIG_FILE"
        return 1
    fi

    print_info "Scanning for iPhone SOCKS5 proxy..."

    local discover_script="${SCRIPT_DIR}/discover.sh"
    if [[ ! -x "$discover_script" ]]; then
        chmod +x "$discover_script" 2>/dev/null || true
    fi

    local result
    result=$(SOCKS_PORT="$SOCKS_PORT" HTTP_PORT="$HTTP_PORT" DISCOVER_TIMEOUT="$DISCOVER_TIMEOUT" \
        bash "$discover_script" --json 2>/dev/null) || true

    if echo "$result" | grep -q '"found": true'; then
        PROXY_IP=$(echo "$result" | grep -o '"ip": "[^"]*"' | cut -d'"' -f4)
        print_ok "Found iPhone at $PROXY_IP"
        # Save for later use
        echo "$PROXY_IP" > "${STATE_DIR}/last_proxy_ip"
        return 0
    fi

    # Try last known IP
    if [[ -f "${STATE_DIR}/last_proxy_ip" ]]; then
        local last_ip
        last_ip=$(cat "${STATE_DIR}/last_proxy_ip")
        print_info "Trying last known IP: $last_ip"
        if nc -z -G 2 "$last_ip" "$SOCKS_PORT" 2>/dev/null; then
            PROXY_IP="$last_ip"
            print_ok "iPhone found at last known IP: $PROXY_IP"
            return 0
        fi
    fi

    print_fail "Could not find iPhone SOCKS5 proxy on the network"
    return 1
}

# ---------------------------------------------------------------------------
# Verify SOCKS5 proxy is responding
# ---------------------------------------------------------------------------
verify_proxy() {
    local host="$1"
    local port="$2"

    # Quick TCP check
    if ! nc -z -G 3 "$host" "$port" 2>/dev/null; then
        return 1
    fi

    # SOCKS5 handshake verification
    local response
    response=$(printf '\x05\x01\x00' | nc -G 3 -w 3 "$host" "$port" 2>/dev/null | xxd -p -l 2 2>/dev/null) || return 1

    [[ "$response" == "0500" ]]
}

# ---------------------------------------------------------------------------
# Simple mode: system proxy settings
# ---------------------------------------------------------------------------
enable_simple_mode() {
    local svc="$NETWORK_SERVICE"
    local ip="$PROXY_IP"

    print_info "Configuring system proxy (simple mode)..."

    # SOCKS5 proxy
    networksetup -setsocksfirewallproxy "$svc" "$ip" "$SOCKS_PORT" 2>/dev/null
    networksetup -setsocksfirewallproxystate "$svc" on 2>/dev/null
    print_ok "SOCKS5 proxy: $ip:$SOCKS_PORT"

    # HTTP proxy
    networksetup -setwebproxy "$svc" "$ip" "$HTTP_PORT" 2>/dev/null
    networksetup -setwebproxystate "$svc" on 2>/dev/null
    print_ok "HTTP proxy: $ip:$HTTP_PORT"

    # HTTPS proxy
    networksetup -setsecurewebproxy "$svc" "$ip" "$HTTP_PORT" 2>/dev/null
    networksetup -setsecurewebproxystate "$svc" on 2>/dev/null
    print_ok "HTTPS proxy: $ip:$HTTP_PORT"

    # Set bypass domains for local network access
    local bypass="*.local, 169.254/16, 127.0.0.1, localhost, $ip"
    if [[ -n "$BYPASS_DOMAINS" ]]; then
        bypass="$bypass, $BYPASS_DOMAINS"
    fi
    networksetup -setproxybypassdomains "$svc" $bypass 2>/dev/null || true
    print_ok "Bypass domains configured"

    log_msg INFO "Simple mode enabled: SOCKS=$ip:$SOCKS_PORT HTTP=$ip:$HTTP_PORT"
}

# ---------------------------------------------------------------------------
# Force mode: pfctl + transparent proxy
# ---------------------------------------------------------------------------
enable_force_mode() {
    print_info "Configuring force mode (pfctl + transparent proxy)..."

    # Check for root
    if [[ $EUID -ne 0 ]]; then
        print_fail "Force mode requires root.  Re-run with: sudo camofox-mac start"
        return 1
    fi

    # 1. Start the transparent proxy helper
    local helper="${SCRIPT_DIR}/proxy_helper.py"
    if [[ ! -f "$helper" ]]; then
        print_fail "proxy_helper.py not found at $helper"
        return 1
    fi

    # Kill existing helper
    if [[ -f "$PROXY_HELPER_PID" ]]; then
        local old_pid
        old_pid=$(cat "$PROXY_HELPER_PID" 2>/dev/null) || true
        kill "$old_pid" 2>/dev/null || true
        sleep 1
    fi

    python3 "$helper" \
        --socks-host "$PROXY_IP" \
        --socks-port "$SOCKS_PORT" \
        --listen-port "$LOCAL_PROXY_PORT" \
        --state-dir "$STATE_DIR" \
        $([ "$KILL_SWITCH" == "true" ] && echo "--kill-switch") \
        --log-level "$(echo "$LOG_LEVEL" | tr '[:lower:]' '[:upper:]')" &
    local helper_pid=$!
    echo "$helper_pid" > "$PROXY_HELPER_PID"
    sleep 2

    if kill -0 "$helper_pid" 2>/dev/null; then
        print_ok "Transparent proxy running on 127.0.0.1:$LOCAL_PROXY_PORT (PID $helper_pid)"
    else
        print_fail "Transparent proxy failed to start"
        return 1
    fi

    # 2. Also set system proxy for apps that respect it
    enable_simple_mode

    # 3. Configure pfctl to redirect remaining traffic
    # Generate runtime pf rules with variable substitution
    cat > "$PF_CONF_RUNTIME" << PFEOF
# CamoFox Mac — Runtime PF Rules
# Generated: $(date)

# Redirect all outbound TCP (except to proxy and localhost) to transparent proxy
rdr pass on lo0 proto tcp from any to !127.0.0.0/8 -> 127.0.0.1 port $LOCAL_PROXY_PORT

# Allow loopback
pass quick on lo0 all

# Allow traffic to iPhone SOCKS proxy
pass out quick proto tcp from any to $PROXY_IP
pass out quick proto udp from any to $PROXY_IP

# Block direct DNS to prevent leaks
block drop quick proto udp from any to !127.0.0.1 port 53
block drop quick proto tcp from any to !127.0.0.1 port 53

# Allow all other traffic (will be redirected)
pass out all
PFEOF

    # Load the anchor
    # First, ensure the anchor exists in the main ruleset
    local main_pf="/etc/pf.conf"
    if ! grep -q "$PF_ANCHOR_NAME" "$main_pf" 2>/dev/null; then
        # Add anchor reference to main pf.conf
        # We use a temporary file to avoid breaking the system pf.conf
        local tmp_pf
        tmp_pf=$(mktemp)
        cp "$main_pf" "$tmp_pf"
        echo "" >> "$tmp_pf"
        echo "# CamoFox Mac anchor" >> "$tmp_pf"
        echo "rdr-anchor \"$PF_ANCHOR_NAME\"" >> "$tmp_pf"
        echo "anchor \"$PF_ANCHOR_NAME\"" >> "$tmp_pf"
        cp "$tmp_pf" "$main_pf"
        rm -f "$tmp_pf"
        print_ok "PF anchor added to $main_pf"
    fi

    # Load anchor rules
    pfctl -a "$PF_ANCHOR_NAME" -f "$PF_CONF_RUNTIME" 2>/dev/null
    print_ok "PF rules loaded into anchor '$PF_ANCHOR_NAME'"

    # Enable pfctl
    pfctl -e 2>/dev/null || true
    print_ok "PF enabled"

    # Write mode marker
    echo "force" > "${STATE_DIR}/active_mode"

    log_msg INFO "Force mode enabled: pfctl + transparent proxy on :$LOCAL_PROXY_PORT"
}

# ---------------------------------------------------------------------------
# Disable force mode: remove pfctl rules and stop transparent proxy
# ---------------------------------------------------------------------------
disable_force_mode() {
    print_info "Disabling force mode..."

    # Flush anchor rules
    if [[ $EUID -eq 0 ]]; then
        pfctl -a "$PF_ANCHOR_NAME" -F all 2>/dev/null || true
        print_ok "PF anchor flushed"

        # Remove anchor from /etc/pf.conf if we added it
        local main_pf="/etc/pf.conf"
        if grep -q "CamoFox Mac anchor" "$main_pf" 2>/dev/null; then
            sed -i '' '/# CamoFox Mac anchor/d' "$main_pf" 2>/dev/null || true
            sed -i '' "/rdr-anchor \"$PF_ANCHOR_NAME\"/d" "$main_pf" 2>/dev/null || true
            sed -i '' "/anchor \"$PF_ANCHOR_NAME\"/d" "$main_pf" 2>/dev/null || true
            print_ok "PF anchor removed from $main_pf"
        fi

        # Reload pf with original rules
        pfctl -f "$main_pf" 2>/dev/null || true
    else
        print_warn "Not root — cannot remove pfctl rules.  Run: sudo camofox-mac stop"
    fi

    # Stop transparent proxy
    if [[ -f "$PROXY_HELPER_PID" ]]; then
        local pid
        pid=$(cat "$PROXY_HELPER_PID" 2>/dev/null) || true
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            # Force kill if still running
            kill -9 "$pid" 2>/dev/null || true
            print_ok "Transparent proxy stopped"
        fi
        rm -f "$PROXY_HELPER_PID"
    fi

    rm -f "$PF_CONF_RUNTIME" "${STATE_DIR}/active_mode"
}

# ---------------------------------------------------------------------------
# Health monitor (background daemon)
# ---------------------------------------------------------------------------
start_health_monitor() {
    print_info "Starting health monitor (interval: ${HEALTH_INTERVAL}s)..."

    # Kill existing monitor
    if [[ -f "$HEALTH_PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$HEALTH_PID_FILE" 2>/dev/null) || true
        kill "$old_pid" 2>/dev/null || true
    fi

    # Start background monitor
    (
        echo $$ > "$HEALTH_PID_FILE"
        local fail_count=0
        local max_fails=3

        while true; do
            sleep "$HEALTH_INTERVAL"

            if verify_proxy "$PROXY_IP" "$SOCKS_PORT"; then
                echo "up" > "${STATE_DIR}/proxy_state"
                fail_count=0
            else
                ((fail_count++)) || true
                echo "down" > "${STATE_DIR}/proxy_state"
                log_msg WARN "Health check failed ($fail_count/$max_fails)"

                if [[ "$KILL_SWITCH" == "true" && $fail_count -ge $max_fails ]]; then
                    log_msg ERROR "Kill switch engaged — proxy unreachable"
                    echo "killed" > "${STATE_DIR}/proxy_state"
                    # In force mode, pfctl will block traffic automatically
                    # In simple mode, we can't truly block — just disable proxy to prevent timeouts
                fi
            fi
        done
    ) &>/dev/null &
    disown

    print_ok "Health monitor started (PID $(cat "$HEALTH_PID_FILE" 2>/dev/null || echo '?'))"
}

stop_health_monitor() {
    if [[ -f "$HEALTH_PID_FILE" ]]; then
        local pid
        pid=$(cat "$HEALTH_PID_FILE" 2>/dev/null) || true
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            print_ok "Health monitor stopped"
        fi
        rm -f "$HEALTH_PID_FILE"
    fi
    rm -f "${STATE_DIR}/proxy_state"
}

# ---------------------------------------------------------------------------
# Command: start
# ---------------------------------------------------------------------------
cmd_start() {
    banner
    printf "${BOLD}Starting CamoFox Mac...${RESET}\n\n"
    load_config

    # Step 1: Discover iPhone
    printf "${BOLD}[1/4] iPhone Discovery${RESET}\n"
    if ! discover_iphone; then
        return 1
    fi
    echo ""

    # Step 2: Verify proxy
    printf "${BOLD}[2/4] Proxy Verification${RESET}\n"
    if verify_proxy "$PROXY_IP" "$SOCKS_PORT"; then
        print_ok "SOCKS5 proxy verified at $PROXY_IP:$SOCKS_PORT"
    else
        print_fail "SOCKS5 proxy not responding at $PROXY_IP:$SOCKS_PORT"
        print_info "Make sure CamoFox iOS is running on the iPhone"
        return 1
    fi
    echo ""

    # Step 3: Configure proxy routing
    printf "${BOLD}[3/4] Proxy Configuration (mode: $MODE)${RESET}\n"
    backup_proxy_settings

    case "$MODE" in
        simple)
            enable_simple_mode
            echo "simple" > "${STATE_DIR}/active_mode"
            ;;
        force)
            enable_force_mode
            ;;
        *)
            print_fail "Unknown mode: $MODE"
            return 1
            ;;
    esac
    echo ""

    # Step 4: DNS + Health
    printf "${BOLD}[4/4] DNS & Health Monitor${RESET}\n"

    # Configure DNS
    local dns_script="${SCRIPT_DIR}/dns-setup.sh"
    if [[ -x "$dns_script" ]] || chmod +x "$dns_script" 2>/dev/null; then
        DNS_MODE="$DNS_MODE" DOH_SERVER="$DOH_SERVER" FALLBACK_DNS="$FALLBACK_DNS" \
        NETWORK_SERVICE="$NETWORK_SERVICE" \
            bash "$dns_script" start "$DNS_MODE" "$NETWORK_SERVICE" "$PROXY_IP" "$SOCKS_PORT"
    else
        print_warn "DNS setup script not found — DNS may leak"
    fi

    # Start health monitor
    start_health_monitor
    echo ""

    # Save active state
    echo "$PROXY_IP" > "${STATE_DIR}/active_proxy_ip"
    echo "$SOCKS_PORT" > "${STATE_DIR}/active_socks_port"
    echo "active" > "${STATE_DIR}/camofox_state"

    printf "${GREEN}${BOLD}CamoFox Mac is active!${RESET}\n"
    print_info "Mode: $MODE | Proxy: $PROXY_IP:$SOCKS_PORT | DNS: $DNS_MODE"
    print_dim "Run 'camofox-mac test' to verify everything is working."
    echo ""
    log_msg INFO "CamoFox Mac started: mode=$MODE proxy=$PROXY_IP:$SOCKS_PORT dns=$DNS_MODE"
}

# ---------------------------------------------------------------------------
# Command: stop
# ---------------------------------------------------------------------------
cmd_stop() {
    banner
    printf "${BOLD}Stopping CamoFox Mac...${RESET}\n\n"
    load_config

    # Stop health monitor
    stop_health_monitor

    # Check what mode was active
    local active_mode="simple"
    [[ -f "${STATE_DIR}/active_mode" ]] && active_mode=$(cat "${STATE_DIR}/active_mode")

    # Disable force mode if it was active
    if [[ "$active_mode" == "force" ]]; then
        disable_force_mode
    fi

    # Restore proxy settings
    restore_proxy_settings

    # Restore DNS
    local dns_script="${SCRIPT_DIR}/dns-setup.sh"
    if [[ -x "$dns_script" ]] || chmod +x "$dns_script" 2>/dev/null; then
        NETWORK_SERVICE="$NETWORK_SERVICE" bash "$dns_script" stop
    fi

    # Clean state files
    rm -f "${STATE_DIR}/camofox_state" "${STATE_DIR}/active_proxy_ip" \
          "${STATE_DIR}/active_socks_port" "${STATE_DIR}/active_mode" \
          "${STATE_DIR}/proxy_state" "${STATE_DIR}/proxy_helper_status"

    echo ""
    printf "${GREEN}${BOLD}CamoFox Mac stopped.${RESET}\n"
    print_info "All settings restored to original values."
    echo ""
    log_msg INFO "CamoFox Mac stopped"
}

# ---------------------------------------------------------------------------
# Command: status
# ---------------------------------------------------------------------------
cmd_status() {
    banner
    load_config

    # Overall state
    local state="inactive"
    [[ -f "${STATE_DIR}/camofox_state" ]] && state=$(cat "${STATE_DIR}/camofox_state")

    if [[ "$state" == "active" ]]; then
        printf "${BOLD}Status: ${GREEN}ACTIVE${RESET}\n\n"
    else
        printf "${BOLD}Status: ${DIM}INACTIVE${RESET}\n\n"
    fi

    # Configuration
    printf "${BOLD}Configuration:${RESET}\n"
    local active_ip="$PROXY_IP"
    [[ -f "${STATE_DIR}/active_proxy_ip" ]] && active_ip=$(cat "${STATE_DIR}/active_proxy_ip")
    local active_mode="$MODE"
    [[ -f "${STATE_DIR}/active_mode" ]] && active_mode=$(cat "${STATE_DIR}/active_mode")

    print_info "Mode: $active_mode"
    print_info "iPhone IP: $active_ip"
    print_info "SOCKS port: $SOCKS_PORT"
    print_info "HTTP port: $HTTP_PORT"
    print_info "DNS mode: $DNS_MODE"
    print_info "Kill switch: $KILL_SWITCH"
    print_info "Network: $NETWORK_SERVICE"
    echo ""

    # Proxy reachability
    printf "${BOLD}Proxy:${RESET}\n"
    if [[ "$active_ip" != "auto" ]]; then
        if verify_proxy "$active_ip" "$SOCKS_PORT" 2>/dev/null; then
            print_ok "SOCKS5 proxy reachable at $active_ip:$SOCKS_PORT"
        else
            print_fail "SOCKS5 proxy NOT reachable at $active_ip:$SOCKS_PORT"
        fi
    else
        print_info "Proxy IP: auto (not resolved)"
    fi

    # Proxy state from health monitor
    if [[ -f "${STATE_DIR}/proxy_state" ]]; then
        local proxy_state
        proxy_state=$(cat "${STATE_DIR}/proxy_state")
        case "$proxy_state" in
            up)     print_ok "Health monitor: proxy UP" ;;
            down)   print_fail "Health monitor: proxy DOWN" ;;
            killed) print_fail "Health monitor: KILL SWITCH ENGAGED" ;;
            *)      print_warn "Health monitor: $proxy_state" ;;
        esac
    fi
    echo ""

    # System proxy settings
    printf "${BOLD}macOS Proxy Settings:${RESET}\n"
    local socks_info
    socks_info=$(networksetup -getsocksfirewallproxy "$NETWORK_SERVICE" 2>/dev/null) || true
    if echo "$socks_info" | grep -qi "enabled: yes"; then
        local socks_srv
        socks_srv=$(echo "$socks_info" | grep -i server | awk '{print $2}')
        local socks_prt
        socks_prt=$(echo "$socks_info" | grep -i port | head -1 | awk '{print $2}')
        print_ok "SOCKS proxy: $socks_srv:$socks_prt"
    else
        print_info "SOCKS proxy: disabled"
    fi

    local http_info
    http_info=$(networksetup -getwebproxy "$NETWORK_SERVICE" 2>/dev/null) || true
    if echo "$http_info" | grep -qi "enabled: yes"; then
        print_ok "HTTP proxy: enabled"
    else
        print_info "HTTP proxy: disabled"
    fi

    local https_info
    https_info=$(networksetup -getsecurewebproxy "$NETWORK_SERVICE" 2>/dev/null) || true
    if echo "$https_info" | grep -qi "enabled: yes"; then
        print_ok "HTTPS proxy: enabled"
    else
        print_info "HTTPS proxy: disabled"
    fi
    echo ""

    # DNS
    printf "${BOLD}DNS:${RESET}\n"
    local dns_script="${SCRIPT_DIR}/dns-setup.sh"
    if [[ -x "$dns_script" ]]; then
        NETWORK_SERVICE="$NETWORK_SERVICE" bash "$dns_script" status
    else
        local dns_servers
        dns_servers=$(networksetup -getdnsservers "$NETWORK_SERVICE" 2>/dev/null) || true
        print_info "DNS servers: $dns_servers"
    fi
    echo ""

    # Force mode components
    if [[ "$active_mode" == "force" ]]; then
        printf "${BOLD}Force Mode Components:${RESET}\n"

        # Transparent proxy
        if [[ -f "$PROXY_HELPER_PID" ]]; then
            local hp_pid
            hp_pid=$(cat "$PROXY_HELPER_PID" 2>/dev/null) || true
            if [[ -n "$hp_pid" ]] && kill -0 "$hp_pid" 2>/dev/null; then
                print_ok "Transparent proxy: running (PID $hp_pid)"
            else
                print_fail "Transparent proxy: not running (stale PID)"
            fi
        else
            print_fail "Transparent proxy: not running"
        fi

        # pfctl
        if pfctl -s Anchors 2>/dev/null | grep -q "$PF_ANCHOR_NAME"; then
            print_ok "PF anchor: active"
            local rule_count
            rule_count=$(pfctl -a "$PF_ANCHOR_NAME" -s rules 2>/dev/null | wc -l | xargs)
            print_info "  Rules: $rule_count"
        else
            print_info "PF anchor: not loaded"
        fi
        echo ""
    fi

    # Health monitor
    printf "${BOLD}Services:${RESET}\n"
    if [[ -f "$HEALTH_PID_FILE" ]]; then
        local hm_pid
        hm_pid=$(cat "$HEALTH_PID_FILE" 2>/dev/null) || true
        if [[ -n "$hm_pid" ]] && kill -0 "$hm_pid" 2>/dev/null; then
            print_ok "Health monitor: running (PID $hm_pid, interval ${HEALTH_INTERVAL}s)"
        else
            print_warn "Health monitor: not running (stale PID)"
        fi
    else
        print_info "Health monitor: not running"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Command: test
# ---------------------------------------------------------------------------
cmd_test() {
    banner
    load_config
    printf "${BOLD}Running CamoFox Mac Diagnostics...${RESET}\n\n"

    local active_ip="$PROXY_IP"
    [[ -f "${STATE_DIR}/active_proxy_ip" ]] && active_ip=$(cat "${STATE_DIR}/active_proxy_ip")

    # Test 1: Proxy connectivity
    printf "${BOLD}[1/5] SOCKS5 Proxy Connectivity${RESET}\n"
    if [[ "$active_ip" == "auto" ]]; then
        print_warn "Proxy IP not resolved — running discovery first"
        discover_iphone
        active_ip="$PROXY_IP"
    fi

    if verify_proxy "$active_ip" "$SOCKS_PORT"; then
        print_ok "SOCKS5 proxy responding at $active_ip:$SOCKS_PORT"
    else
        print_fail "SOCKS5 proxy NOT responding at $active_ip:$SOCKS_PORT"
    fi

    if nc -z -G 3 "$active_ip" "$HTTP_PORT" 2>/dev/null; then
        print_ok "HTTP proxy responding at $active_ip:$HTTP_PORT"
    else
        print_warn "HTTP proxy not responding at $active_ip:$HTTP_PORT"
    fi
    echo ""

    # Test 2: System proxy settings
    printf "${BOLD}[2/5] System Proxy Settings${RESET}\n"
    local socks_info
    socks_info=$(networksetup -getsocksfirewallproxy "$NETWORK_SERVICE" 2>/dev/null) || true
    if echo "$socks_info" | grep -qi "enabled: yes"; then
        print_ok "SOCKS proxy enabled in system settings"
    else
        print_warn "SOCKS proxy NOT enabled in system settings"
    fi
    echo ""

    # Test 3: DNS leak check
    printf "${BOLD}[3/5] DNS Leak Prevention${RESET}\n"
    local dns_servers
    dns_servers=$(networksetup -getdnsservers "$NETWORK_SERVICE" 2>/dev/null) || true
    if echo "$dns_servers" | grep -q "127.0.0.1"; then
        print_ok "DNS points to localhost (leak prevention active)"
    elif echo "$dns_servers" | grep -qE "1\.1\.1\.1|1\.0\.0\.1|8\.8\.8\.8"; then
        print_warn "DNS using public resolvers (partial protection)"
    else
        print_fail "DNS may be leaking to ISP: $dns_servers"
    fi

    # Try to resolve via proxy
    if command -v dig >/dev/null 2>&1; then
        local dns_result
        dns_result=$(dig +short +time=5 myip.opendns.com @resolver1.opendns.com 2>/dev/null) || true
        if [[ -n "$dns_result" ]]; then
            print_info "DNS resolution working (resolved: $dns_result)"
        else
            print_warn "DNS resolution test failed"
        fi
    fi
    echo ""

    # Test 4: External connectivity through proxy
    printf "${BOLD}[4/5] External Connectivity${RESET}\n"
    local ext_ip
    ext_ip=$(curl -s --max-time 15 --socks5 "$active_ip:$SOCKS_PORT" https://api.ipify.org 2>/dev/null) || true

    if [[ -n "$ext_ip" ]]; then
        print_ok "Internet reachable through SOCKS5 proxy"
        print_info "External IP (via proxy): $ext_ip"
    else
        # Try HTTP proxy
        ext_ip=$(curl -s --max-time 15 -x "http://$active_ip:$HTTP_PORT" https://api.ipify.org 2>/dev/null) || true
        if [[ -n "$ext_ip" ]]; then
            print_ok "Internet reachable through HTTP proxy"
            print_info "External IP (via proxy): $ext_ip"
        else
            print_fail "Cannot reach internet through proxy"
        fi
    fi

    # Check direct IP for comparison
    local direct_ip
    direct_ip=$(curl -s --max-time 10 --noproxy '*' https://api.ipify.org 2>/dev/null) || true
    if [[ -n "$direct_ip" ]]; then
        if [[ "$direct_ip" == "$ext_ip" ]]; then
            print_ok "Direct and proxy IPs match (traffic is proxied)"
        else
            print_warn "Direct IP ($direct_ip) differs from proxy IP ($ext_ip)"
            print_info "This is expected if proxy exits through different network"
        fi
    fi
    echo ""

    # Test 5: Speed test (simple)
    printf "${BOLD}[5/5] Quick Speed Test${RESET}\n"
    local start_time end_time duration speed
    start_time=$(date +%s%N 2>/dev/null || date +%s)
    local test_data
    test_data=$(curl -s --max-time 30 --socks5 "$active_ip:$SOCKS_PORT" \
        -o /dev/null -w '%{size_download} %{time_total}' \
        https://speed.cloudflare.com/__down?bytes=1000000 2>/dev/null) || true

    if [[ -n "$test_data" ]]; then
        local bytes time_sec
        bytes=$(echo "$test_data" | awk '{print $1}')
        time_sec=$(echo "$test_data" | awk '{print $2}')
        if [[ -n "$time_sec" ]] && (( $(echo "$time_sec > 0" | bc -l 2>/dev/null || echo 0) )); then
            speed=$(echo "scale=2; $bytes / $time_sec / 1024" | bc -l 2>/dev/null || echo "?")
            print_ok "Download: ~${speed} KB/s (1MB test file)"
        else
            print_warn "Speed test completed but could not calculate speed"
        fi
    else
        print_warn "Speed test failed — proxy may be slow or unreachable"
    fi
    echo ""

    printf "${BOLD}Diagnostics complete.${RESET}\n\n"
}

# ---------------------------------------------------------------------------
# Command: find
# ---------------------------------------------------------------------------
cmd_find() {
    banner
    load_config

    local discover_script="${SCRIPT_DIR}/discover.sh"
    if [[ -x "$discover_script" ]] || chmod +x "$discover_script" 2>/dev/null; then
        SOCKS_PORT="$SOCKS_PORT" HTTP_PORT="$HTTP_PORT" DISCOVER_TIMEOUT="$DISCOVER_TIMEOUT" \
            bash "$discover_script" --verbose
    else
        print_fail "Discovery script not found at $discover_script"
    fi
}

# ---------------------------------------------------------------------------
# Command: version
# ---------------------------------------------------------------------------
cmd_version() {
    echo "$NAME v$VERSION"
    echo "Tethering bypass for macOS via iPhone SOCKS5 proxy"
    echo "https://github.com/nneonneo/iOS-SOCKS-Server"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    banner
    printf "${BOLD}Usage:${RESET} camofox-mac <command>\n\n"
    printf "${BOLD}Commands:${RESET}\n"
    printf "  ${CYAN}start${RESET}     Enable proxy routing and DNS protection\n"
    printf "  ${CYAN}stop${RESET}      Disable everything and restore original settings\n"
    printf "  ${CYAN}status${RESET}    Show detailed status of all components\n"
    printf "  ${CYAN}test${RESET}      Run connectivity and leak diagnostics\n"
    printf "  ${CYAN}find${RESET}      Scan local network for iPhone proxy\n"
    printf "  ${CYAN}version${RESET}   Show version information\n"
    echo ""
    printf "${BOLD}Modes:${RESET}\n"
    printf "  ${CYAN}simple${RESET}    System proxy settings (works for most apps)\n"
    printf "  ${CYAN}force${RESET}     pfctl + transparent proxy (catches ALL traffic, requires sudo)\n"
    echo ""
    printf "${BOLD}Config:${RESET} ~/.camofox/config\n"
    echo ""
}

# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------
case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    test)    cmd_test ;;
    find)    cmd_find ;;
    version) cmd_version ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        printf "${RED}Unknown command: $1${RESET}\n"
        usage
        exit 1
        ;;
esac
