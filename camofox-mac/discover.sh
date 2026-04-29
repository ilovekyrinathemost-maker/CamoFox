#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# CamoFox Mac — iPhone Auto-Discovery
# ═══════════════════════════════════════════════════════════════════════════
# Scans the local network for an iPhone running the CamoFox SOCKS5 proxy.
#
# Usage:
#   ./discover.sh              # Scan with defaults
#   ./discover.sh --port 1080  # Custom SOCKS port
#   ./discover.sh --timeout 2  # Custom timeout per host
#   ./discover.sh --json       # Output as JSON
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Defaults
SOCKS_PORT=${SOCKS_PORT:-9876}
HTTP_PORT=${HTTP_PORT:-9877}
TIMEOUT=${DISCOVER_TIMEOUT:-1}
JSON_OUTPUT=false
VERBOSE=false

# Colors
BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
CYAN="\033[36m"
DIM="\033[2m"
RESET="\033[0m"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)   SOCKS_PORT="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --json)   JSON_OUTPUT=true; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --help|-h)
            echo "Usage: discover.sh [--port PORT] [--timeout SECS] [--json] [--verbose]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        printf "  ${CYAN}•${RESET} %s\n" "$1"
    fi
}

log_verbose() {
    if [[ "$VERBOSE" == "true" && "$JSON_OUTPUT" == "false" ]]; then
        printf "  ${DIM}  %s${RESET}\n" "$1"
    fi
}

log_found() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        printf "  ${GREEN}✓${RESET} %s\n" "$1"
    fi
}

log_warn() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        printf "  ${YELLOW}!${RESET} %s\n" "$1"
    fi
}

# ---------------------------------------------------------------------------
# Get local network information
# ---------------------------------------------------------------------------
get_local_info() {
    # Detect active Wi-Fi interface
    local iface
    iface=$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}') || iface="en0"

    # Get local IP
    local local_ip
    local_ip=$(ipconfig getifaddr "$iface" 2>/dev/null) || local_ip=""

    if [[ -z "$local_ip" ]]; then
        # Fallback: try en0 and en1
        for ifc in en0 en1; do
            local_ip=$(ipconfig getifaddr "$ifc" 2>/dev/null) || continue
            if [[ -n "$local_ip" ]]; then
                iface="$ifc"
                break
            fi
        done
    fi

    if [[ -z "$local_ip" ]]; then
        echo "" "" ""
        return 1
    fi

    # Get subnet mask and compute network
    local netmask
    netmask=$(ifconfig "$iface" 2>/dev/null | awk '/netmask/ {print $4}') || netmask="0xffffff00"

    echo "$iface" "$local_ip" "$netmask"
}

# ---------------------------------------------------------------------------
# Compute scan range from IP and netmask
# ---------------------------------------------------------------------------
compute_scan_range() {
    local ip="$1"
    local netmask="$2"

    # Convert hex netmask to decimal if needed
    if [[ "$netmask" == 0x* ]]; then
        local hex=${netmask#0x}
        local a=$((16#${hex:0:2}))
        local b=$((16#${hex:2:2}))
        local c=$((16#${hex:4:2}))
        local d=$((16#${hex:6:2}))
        netmask="$a.$b.$c.$d"
    fi

    # Parse IP octets
    IFS='.' read -r ip1 ip2 ip3 ip4 <<< "$ip"
    IFS='.' read -r nm1 nm2 nm3 nm4 <<< "$netmask"

    # Network address
    local net1=$(( ip1 & nm1 ))
    local net2=$(( ip2 & nm2 ))
    local net3=$(( ip3 & nm3 ))
    local net4=$(( ip4 & nm4 ))

    # Host bits (inverted mask)
    local inv4=$(( 255 - nm4 ))

    # For /24 or smaller, scan the last octet
    # For larger subnets, limit scan to avoid taking forever
    local start_ip="$net1.$net2.$net3"
    local range_start=$(( net4 + 1 ))
    local range_end=$(( net4 + inv4 - 1 ))

    # Cap at 254 hosts to prevent huge scans
    if (( range_end - range_start > 254 )); then
        range_end=$(( range_start + 253 ))
    fi

    echo "$start_ip" "$range_start" "$range_end"
}

# ---------------------------------------------------------------------------
# Check if a SOCKS5 proxy is running on a given host:port
# Sends a minimal SOCKS5 greeting and checks the response.
# ---------------------------------------------------------------------------
check_socks5() {
    local host="$1"
    local port="$2"

    # First, quick TCP connect check
    if ! nc -z -G "$TIMEOUT" "$host" "$port" 2>/dev/null; then
        return 1
    fi

    # Send SOCKS5 handshake: version=5, nmethods=1, method=0 (no auth)
    # Expected response: version=5, method=0
    local response
    response=$(printf '\x05\x01\x00' | \
        nc -G "$TIMEOUT" -w "$TIMEOUT" "$host" "$port" 2>/dev/null | \
        xxd -p -l 2 2>/dev/null) || return 1

    # Verify SOCKS5 response: "0500" means version 5, no auth required
    if [[ "$response" == "0500" ]]; then
        return 0
    fi

    return 1
}

# ---------------------------------------------------------------------------
# Check if HTTP proxy is running
# ---------------------------------------------------------------------------
check_http_proxy() {
    local host="$1"
    local port="$2"
    nc -z -G "$TIMEOUT" "$host" "$port" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Scan ARP table for quick candidates (known hosts)
# ---------------------------------------------------------------------------
scan_arp_table() {
    log "Checking ARP table for known hosts..."
    local candidates=()

    while IFS= read -r line; do
        # Parse: hostname (ip) at mac on iface ...
        local ip
        ip=$(echo "$line" | grep -oE '\([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\)' | tr -d '()')
        if [[ -n "$ip" ]]; then
            candidates+=("$ip")
        fi
    done < <(arp -a 2>/dev/null)

    log_verbose "Found ${#candidates[@]} hosts in ARP table"
    echo "${candidates[@]}"
}

# ---------------------------------------------------------------------------
# Scan common iPhone IP ranges first (quick check)
# ---------------------------------------------------------------------------
scan_common_ips() {
    local local_ip="$1"
    local candidates=()

    # iPhone hotspot default range
    candidates+=("172.20.10.1")

    # Common router-assigned IPs for iPhones
    IFS='.' read -r o1 o2 o3 o4 <<< "$local_ip"
    # Check .1 (gateway/iPhone might be here)
    candidates+=("$o1.$o2.$o3.1")
    # Check nearby IPs
    for i in $(seq 2 10); do
        candidates+=("$o1.$o2.$o3.$i")
    done

    echo "${candidates[@]}"
}

# ---------------------------------------------------------------------------
# Full subnet scan (parallel, batched)
# ---------------------------------------------------------------------------
scan_subnet() {
    local base="$1"
    local start="$2"
    local end="$3"
    local local_ip="$4"
    local found_ips=()

    log "Scanning subnet ${base}.${start}-${end} ($(( end - start + 1 )) hosts)..."

    # Parallel scan using background jobs
    local pids=()
    local tmpdir
    tmpdir=$(mktemp -d)

    for i in $(seq "$start" "$end"); do
        local target="$base.$i"
        # Skip our own IP
        [[ "$target" == "$local_ip" ]] && continue

        (
            if nc -z -G "$TIMEOUT" "$target" "$SOCKS_PORT" 2>/dev/null; then
                echo "$target" > "$tmpdir/$i"
            fi
        ) &
        pids+=($!)

        # Limit parallelism to 50 concurrent probes
        if (( ${#pids[@]} >= 50 )); then
            wait "${pids[0]}" 2>/dev/null || true
            pids=("${pids[@]:1}")
        fi
    done

    # Wait for remaining
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    # Collect results
    for f in "$tmpdir"/*; do
        [[ -f "$f" ]] && found_ips+=("$(cat "$f")")
    done

    rm -rf "$tmpdir"
    echo "${found_ips[@]}"
}

# ---------------------------------------------------------------------------
# Main discovery routine
# ---------------------------------------------------------------------------
main() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        printf "\n${BOLD}${CYAN}CamoFox — iPhone Discovery${RESET}\n\n"
    fi

    # Get local network info
    local net_info
    net_info=$(get_local_info)
    if [[ -z "$net_info" ]]; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"error": "No active network interface found", "found": false}'
        else
            printf "  ${RED}✗${RESET} No active network interface found\n"
        fi
        exit 1
    fi

    read -r iface local_ip netmask <<< "$net_info"
    log "Interface: $iface  IP: $local_ip"

    # Phase 1: Check common / known IPs first
    log "Phase 1: Checking common iPhone IPs..."
    local common_ips
    common_ips=$(scan_common_ips "$local_ip")

    for ip in $common_ips; do
        [[ "$ip" == "$local_ip" ]] && continue
        log_verbose "Probing $ip:$SOCKS_PORT"
        if check_socks5 "$ip" "$SOCKS_PORT"; then
            local has_http=false
            check_http_proxy "$ip" "$HTTP_PORT" && has_http=true

            if [[ "$JSON_OUTPUT" == "true" ]]; then
                echo "{\"ip\": \"$ip\", \"socks_port\": $SOCKS_PORT, \"http_port\": $HTTP_PORT, \"http_available\": $has_http, \"found\": true, \"method\": \"common_ip\"}"
            else
                log_found "iPhone SOCKS5 proxy found at $ip:$SOCKS_PORT"
                [[ "$has_http" == "true" ]] && log_found "HTTP proxy also available at $ip:$HTTP_PORT"
                echo ""
                printf "  ${BOLD}PROXY_IP=${ip}${RESET}\n\n"
            fi
            exit 0
        fi
    done

    # Phase 2: Check ARP table
    log "Phase 2: Checking ARP-known hosts..."
    local arp_ips
    arp_ips=$(scan_arp_table)

    for ip in $arp_ips; do
        [[ "$ip" == "$local_ip" ]] && continue
        # Skip IPs we already checked
        local already_checked=false
        for cip in $common_ips; do
            [[ "$ip" == "$cip" ]] && already_checked=true && break
        done
        [[ "$already_checked" == "true" ]] && continue

        log_verbose "Probing $ip:$SOCKS_PORT"
        if check_socks5 "$ip" "$SOCKS_PORT"; then
            local has_http=false
            check_http_proxy "$ip" "$HTTP_PORT" && has_http=true

            if [[ "$JSON_OUTPUT" == "true" ]]; then
                echo "{\"ip\": \"$ip\", \"socks_port\": $SOCKS_PORT, \"http_port\": $HTTP_PORT, \"http_available\": $has_http, \"found\": true, \"method\": \"arp_table\"}"
            else
                log_found "iPhone SOCKS5 proxy found at $ip:$SOCKS_PORT"
                [[ "$has_http" == "true" ]] && log_found "HTTP proxy also available at $ip:$HTTP_PORT"
                echo ""
                printf "  ${BOLD}PROXY_IP=${ip}${RESET}\n\n"
            fi
            exit 0
        fi
    done

    # Phase 3: Full subnet scan
    log "Phase 3: Full subnet scan..."
    local range_info
    range_info=$(compute_scan_range "$local_ip" "$netmask")
    read -r base range_start range_end <<< "$range_info"

    local subnet_ips
    subnet_ips=$(scan_subnet "$base" "$range_start" "$range_end" "$local_ip")

    for ip in $subnet_ips; do
        log_verbose "Verifying SOCKS5 on $ip:$SOCKS_PORT"
        if check_socks5 "$ip" "$SOCKS_PORT"; then
            local has_http=false
            check_http_proxy "$ip" "$HTTP_PORT" && has_http=true

            if [[ "$JSON_OUTPUT" == "true" ]]; then
                echo "{\"ip\": \"$ip\", \"socks_port\": $SOCKS_PORT, \"http_port\": $HTTP_PORT, \"http_available\": $has_http, \"found\": true, \"method\": \"subnet_scan\"}"
            else
                log_found "iPhone SOCKS5 proxy found at $ip:$SOCKS_PORT"
                [[ "$has_http" == "true" ]] && log_found "HTTP proxy also available at $ip:$HTTP_PORT"
                echo ""
                printf "  ${BOLD}PROXY_IP=${ip}${RESET}\n\n"
            fi
            exit 0
        fi
    done

    # Not found
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo '{"found": false, "error": "No SOCKS5 proxy found on local network"}'
    else
        echo ""
        printf "  ${RED}✗${RESET} No CamoFox SOCKS5 proxy found on the local network.\n"
        echo ""
        printf "  ${BOLD}Checklist:${RESET}\n"
        printf "    1. Is Pythonista running CamoFox proxy on the iPhone?\n"
        printf "    2. Is the iPhone on the same Wi-Fi network as this Mac?\n"
        printf "    3. Is the proxy listening on port %s?\n" "$SOCKS_PORT"
        printf "    4. Does iOS firewall allow incoming connections?\n"
        echo ""
    fi
    exit 1
}

main
