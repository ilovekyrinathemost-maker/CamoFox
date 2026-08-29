#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# CamoFox Mac — DNS Leak Prevention
# ═══════════════════════════════════════════════════════════════════════════
# Configures macOS DNS to prevent leaks when traffic is routed through
# the CamoFox SOCKS proxy.  Supports:
#
#   doh     — DNS-over-HTTPS via dnscrypt-proxy or cloudflared
#   proxy   — DNS queries routed through the SOCKS proxy
#   system  — No changes (not recommended)
#
# Usage:
#   ./dns-setup.sh start [dns_mode] [network_service]
#   ./dns-setup.sh stop  [network_service]
#   ./dns-setup.sh status [network_service]
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Defaults
DNS_MODE=${DNS_MODE:-doh}
NETWORK_SERVICE=${NETWORK_SERVICE:-Wi-Fi}
DOH_SERVER=${DOH_SERVER:-https://cloudflare-dns.com/dns-query}
FALLBACK_DNS=${FALLBACK_DNS:-1.1.1.1,1.0.0.1}

# Prefer STATE_DIR from the caller (camofox-mac.sh). Under sudo, HOME is
# /var/root; fall back to the invoking user's ~/.camofox.
if [[ -z "${STATE_DIR:-}" ]]; then
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        _dns_user="${SUDO_USER:-}"
        if [[ -z "$_dns_user" || "$_dns_user" == "root" ]]; then
            _dns_user=$(logname 2>/dev/null) || true
        fi
        if [[ -n "$_dns_user" && "$_dns_user" != "root" ]]; then
            _dns_home=$(eval echo "~$_dns_user" 2>/dev/null) || true
            if [[ -n "$_dns_home" && -d "$_dns_home" ]]; then
                STATE_DIR="${_dns_home}/.camofox"
            fi
        fi
    fi
    STATE_DIR="${STATE_DIR:-${HOME}/.camofox}"
fi
DNS_BACKUP="${STATE_DIR}/dns_backup"
DNS_PID_FILE="${STATE_DIR}/dns_helper.pid"
DNS_LISTEN_PORT=53

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

run_priv() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

# ---------------------------------------------------------------------------
# Backup current DNS settings
# ---------------------------------------------------------------------------
backup_dns() {
    mkdir -p "$STATE_DIR"
    local current_dns
    current_dns=$(networksetup -getdnsservers "$NETWORK_SERVICE" 2>/dev/null) || true

    if [[ "$current_dns" == *"aren't any"* ]]; then
        echo "auto" > "$DNS_BACKUP"
    else
        echo "$current_dns" > "$DNS_BACKUP"
    fi
    print_info "DNS backup saved to $DNS_BACKUP"
}

# ---------------------------------------------------------------------------
# Restore original DNS settings
# ---------------------------------------------------------------------------
restore_dns() {
    if [[ ! -f "$DNS_BACKUP" ]]; then
        print_warn "No DNS backup found — setting DNS to auto (DHCP)"
        networksetup -setdnsservers "$NETWORK_SERVICE" empty 2>/dev/null || true
        return
    fi

    local saved
    saved=$(cat "$DNS_BACKUP")

    if [[ "$saved" == "auto" ]]; then
        networksetup -setdnsservers "$NETWORK_SERVICE" empty 2>/dev/null || true
        print_ok "DNS restored to automatic (DHCP)"
    else
        # Convert newlines to space-separated args
        local dns_args
        dns_args=$(echo "$saved" | tr '\n' ' ')
        networksetup -setdnsservers "$NETWORK_SERVICE" $dns_args 2>/dev/null || true
        print_ok "DNS restored to: $dns_args"
    fi

    rm -f "$DNS_BACKUP"
}

# ---------------------------------------------------------------------------
# Start DNS-over-HTTPS (dnscrypt-proxy or cloudflared)
# ---------------------------------------------------------------------------
start_doh() {
    print_info "Configuring DNS-over-HTTPS..."

    # Option 1: dnscrypt-proxy (preferred — most complete DoH/DoT solution)
    if command -v dnscrypt-proxy >/dev/null 2>&1; then
        print_info "Using dnscrypt-proxy"

        # Check if already running
        if pgrep -x dnscrypt-proxy >/dev/null 2>&1; then
            print_ok "dnscrypt-proxy already running"
        else
            # Create minimal config if needed
            local dnscrypt_conf="${STATE_DIR}/dnscrypt-proxy.toml"
            if [[ ! -f "$dnscrypt_conf" ]]; then
                cat > "$dnscrypt_conf" << 'DNSCRYPT_EOF'
listen_addresses = ['127.0.0.1:53']
max_clients = 250
ipv4_servers = true
ipv6_servers = false
dnscrypt_servers = true
doh_servers = true
require_dnssec = false
require_nolog = true
require_nofilter = true
force_tcp = false

[sources]
  [sources.'public-resolvers']
    urls = ['https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/public-resolvers.md']
    cache_file = '/tmp/public-resolvers.md'
    minisign_key = 'RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3'
    refresh_delay = 72
DNSCRYPT_EOF
            fi

            sudo dnscrypt-proxy -config "$dnscrypt_conf" &
            echo $! > "$DNS_PID_FILE"
            sleep 2

            if pgrep -x dnscrypt-proxy >/dev/null 2>&1; then
                print_ok "dnscrypt-proxy started on 127.0.0.1:53"
            else
                print_fail "dnscrypt-proxy failed to start"
                return 1
            fi
        fi

        # Point macOS DNS to local dnscrypt-proxy
        networksetup -setdnsservers "$NETWORK_SERVICE" 127.0.0.1
        print_ok "DNS set to 127.0.0.1 (dnscrypt-proxy)"
        return 0
    fi

    # Option 2: cloudflared (Cloudflare's DoH proxy)
    if command -v cloudflared >/dev/null 2>&1; then
        print_info "Using cloudflared"

        if pgrep -x cloudflared >/dev/null 2>&1; then
            print_ok "cloudflared already running"
        else
            run_priv cloudflared proxy-dns \
                --address 127.0.0.1 \
                --port "$DNS_LISTEN_PORT" \
                --upstream "$DOH_SERVER" &
            echo $! > "$DNS_PID_FILE"
            sleep 2

            if pgrep -x cloudflared >/dev/null 2>&1; then
                print_ok "cloudflared started on 127.0.0.1:${DNS_LISTEN_PORT}"
            else
                print_fail "cloudflared failed to start"
                return 1
            fi
        fi

        networksetup -setdnsservers "$NETWORK_SERVICE" 127.0.0.1
        print_ok "DNS set to 127.0.0.1:${DNS_LISTEN_PORT} (cloudflared)"
        return 0
    fi

    # Option 3: Fallback — use well-known DoH-capable resolvers directly
    # These use standard DNS but at least they're privacy-focused.
    print_warn "No DoH proxy found (install dnscrypt-proxy or cloudflared via Homebrew)"
    print_info "Falling back to Cloudflare + Google DNS (standard UDP — less private)"

    IFS=',' read -ra fallback_servers <<< "$FALLBACK_DNS"
    networksetup -setdnsservers "$NETWORK_SERVICE" "${fallback_servers[@]}"
    print_warn "DNS set to ${fallback_servers[*]} (standard UDP — consider installing dnscrypt-proxy)"
    return 0
}

# ---------------------------------------------------------------------------
# Start DNS through SOCKS proxy (local UDP/53 forwarder)
# ---------------------------------------------------------------------------
start_proxy_dns() {
    local proxy_ip="${1:-}"
    local socks_port="${2:-9876}"

    print_info "Configuring DNS to route through SOCKS proxy..."

    if [[ -z "$proxy_ip" ]]; then
        print_fail "PROXY_IP required for proxy DNS mode"
        return 1
    fi

    # Use a small Python DNS forwarder that tunnels through SOCKS5
    local dns_forwarder="${STATE_DIR}/dns_forwarder.py"
    cat > "$dns_forwarder" << 'PYEOF'
#!/usr/bin/env python3
"""Minimal DNS forwarder that tunnels queries through a SOCKS5 proxy."""
import socket
import struct
import sys
import os

SOCKS_HOST = sys.argv[1]
SOCKS_PORT = int(sys.argv[2])
UPSTREAM_DNS = "1.1.1.1"
UPSTREAM_PORT = 53
LISTEN_PORT = 53

def socks5_connect(target_host, target_port):
    """Connect to target through SOCKS5 proxy."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((SOCKS_HOST, SOCKS_PORT))

    # SOCKS5 greeting
    s.send(b'\x05\x01\x00')
    resp = s.recv(2)
    if resp != b'\x05\x00':
        s.close()
        raise Exception("SOCKS5 auth failed")

    # SOCKS5 connect request (IPv4)
    addr_bytes = socket.inet_aton(target_host)
    port_bytes = struct.pack('!H', target_port)
    s.send(b'\x05\x01\x00\x01' + addr_bytes + port_bytes)

    resp = s.recv(10)
    if resp[1] != 0:
        s.close()
        raise Exception(f"SOCKS5 connect failed: {resp[1]}")

    return s

def forward_dns(data):
    """Forward a DNS query through SOCKS5 and return the response."""
    try:
        sock = socks5_connect(UPSTREAM_DNS, UPSTREAM_PORT)
        # DNS over TCP: prepend 2-byte length
        sock.send(struct.pack('!H', len(data)) + data)
        length_data = sock.recv(2)
        if len(length_data) < 2:
            return None
        resp_len = struct.unpack('!H', length_data)[0]
        response = b''
        while len(response) < resp_len:
            chunk = sock.recv(resp_len - len(response))
            if not chunk:
                break
            response += chunk
        sock.close()
        return response
    except Exception as e:
        print(f"DNS forward error: {e}", file=sys.stderr)
        return None

def main():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.bind(('127.0.0.1', LISTEN_PORT))
    print(f"DNS forwarder listening on 127.0.0.1:{LISTEN_PORT}")
    print(f"Forwarding via SOCKS5 {SOCKS_HOST}:{SOCKS_PORT} -> {UPSTREAM_DNS}:{UPSTREAM_PORT}")

    while True:
        try:
            data, addr = udp_sock.recvfrom(4096)
            response = forward_dns(data)
            if response:
                udp_sock.sendto(response, addr)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
PYEOF
    chmod +x "$dns_forwarder"

    # Kill existing forwarder
    if [[ -f "$DNS_PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$DNS_PID_FILE" 2>/dev/null) || true
        kill "$old_pid" 2>/dev/null || true
    fi

    # Start DNS forwarder on port 53 (networksetup always queries :53).
    # Binding to 53 requires root.
    run_priv python3 "$dns_forwarder" "$proxy_ip" "$socks_port" &
    echo $! > "$DNS_PID_FILE"
    sleep 1

    if kill -0 "$(cat "$DNS_PID_FILE")" 2>/dev/null; then
        print_ok "DNS forwarder started on 127.0.0.1:${DNS_LISTEN_PORT}"
        networksetup -setdnsservers "$NETWORK_SERVICE" 127.0.0.1
        print_ok "DNS set to 127.0.0.1:${DNS_LISTEN_PORT} (SOCKS-tunneled)"
    else
        print_fail "DNS forwarder failed to start"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Stop DNS helper processes
# ---------------------------------------------------------------------------
stop_dns_helpers() {
    print_info "Stopping DNS helpers..."

    # Stop our DNS forwarder / helper
    if [[ -f "$DNS_PID_FILE" ]]; then
        local pid
        pid=$(cat "$DNS_PID_FILE" 2>/dev/null) || true
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            print_ok "DNS helper stopped (PID $pid)"
        fi
        rm -f "$DNS_PID_FILE"
    fi

    # Note: we do NOT stop dnscrypt-proxy or cloudflared if they were
    # already running before CamoFox — only ones we started.
}

# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------
status_dns() {
    printf "${BOLD}DNS Configuration:${RESET}\n"

    local current_dns
    current_dns=$(networksetup -getdnsservers "$NETWORK_SERVICE" 2>/dev/null) || true
    print_info "Current DNS for '$NETWORK_SERVICE': $current_dns"

    # Check for DoH proxies
    if pgrep -x dnscrypt-proxy >/dev/null 2>&1; then
        print_ok "dnscrypt-proxy: running"
    fi
    if pgrep -x cloudflared >/dev/null 2>&1; then
        print_ok "cloudflared: running"
    fi

    # Check our helper
    if [[ -f "$DNS_PID_FILE" ]]; then
        local pid
        pid=$(cat "$DNS_PID_FILE" 2>/dev/null) || true
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            print_ok "CamoFox DNS helper: running (PID $pid)"
        else
            print_warn "CamoFox DNS helper: not running (stale PID file)"
        fi
    fi

    # Check for backup
    if [[ -f "$DNS_BACKUP" ]]; then
        print_info "Original DNS backed up: $(cat "$DNS_BACKUP")"
    fi
}

# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------
main() {
    local action="${1:-status}"
    shift || true

    # Override defaults from args if provided
    local dns_mode="${1:-$DNS_MODE}"
    local net_svc="${2:-$NETWORK_SERVICE}"
    NETWORK_SERVICE="$net_svc"

    case "$action" in
        start)
            backup_dns
            case "$dns_mode" in
                doh)
                    if ! start_doh; then
                        print_fail "DoH setup failed — restoring previous DNS"
                        restore_dns
                        exit 1
                    fi
                    ;;
                proxy)
                    if ! start_proxy_dns "${3:-}" "${4:-9876}"; then
                        print_fail "Proxy DNS setup failed — restoring previous DNS"
                        restore_dns
                        exit 1
                    fi
                    ;;
                system)
                    print_warn "DNS mode set to 'system' — no changes made"
                    print_warn "DNS queries may leak to your ISP!"
                    ;;
                *)
                    print_fail "Unknown DNS mode: $dns_mode"
                    restore_dns
                    exit 1
                    ;;
            esac
            ;;
        stop)
            stop_dns_helpers
            restore_dns
            ;;
        status)
            status_dns
            ;;
        *)
            echo "Usage: dns-setup.sh {start|stop|status} [dns_mode] [network_service]"
            exit 1
            ;;
    esac
}

main "$@"
