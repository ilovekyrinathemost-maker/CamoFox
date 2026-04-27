#!/bin/sh
# CamoFox Health Monitor
# Periodically checks if the SOCKS5 proxy on the iPhone is reachable.
# If unreachable and kill_switch is enabled, blocks all internet traffic.
# When proxy returns, restores connectivity.
#
# Designed to run as a background daemon, started by the init script.
# Uses only POSIX sh and busybox utilities (no bash, no nc -z on all builds).

PIDFILE="/var/run/camofox_health.pid"
STATEFILE="/tmp/camofox_proxy_state"
FW_SCRIPT="/etc/camofox/firewall.rules"

. /lib/functions.sh

# ---------------------------------------------------------------------------
# Load configuration from UCI
# ---------------------------------------------------------------------------
load_config() {
    config_load camofox
    config_get PROXY_IP         main proxy_ip          '172.20.10.1'
    config_get PROXY_PORT       main proxy_port        '1080'
    config_get KILL_SWITCH      main kill_switch       '1'
    config_get HEALTH_INTERVAL  main health_interval   '30'
    config_get FAIL_THRESHOLD   main health_fail_threshold '3'
    config_get LOG_LEVEL        main log_level         '1'
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_msg() {
    logger -t camofox-health "$1"
    [ "$LOG_LEVEL" -ge 2 ] && echo "camofox-health: $1"
}

log_warn() {
    logger -t camofox-health -p daemon.warn "$1"
    [ "$LOG_LEVEL" -ge 1 ] && echo "camofox-health: WARNING: $1"
}

log_err() {
    logger -t camofox-health -p daemon.err "$1"
    echo "camofox-health: ERROR: $1" >&2
}

# ---------------------------------------------------------------------------
# TCP connect test using /dev/tcp emulation via shell redirect
# Falls back to timeout+wget probe if /dev/tcp unavailable
# ---------------------------------------------------------------------------
check_proxy() {
    # Method 1: Try using busybox nc (netcat) with timeout
    if command -v nc >/dev/null 2>&1; then
        if echo "" | nc -w 3 "$PROXY_IP" "$PROXY_PORT" >/dev/null 2>&1; then
            return 0
        fi
    fi

    # Method 2: Try using wget to test TCP connectivity
    # wget --spider does a HEAD request; we just care about TCP connect
    if command -v wget >/dev/null 2>&1; then
        if wget -q --spider --timeout=3 "http://${PROXY_IP}:${PROXY_PORT}/" 2>/dev/null; then
            return 0
        fi
        # wget may return error on non-HTTP port but still means TCP connected
        # Check if it got a connection refused vs timeout
        # Connection refused = port closed; timeout = host unreachable
        WGET_OUT=$(wget -q --spider --timeout=3 "http://${PROXY_IP}:${PROXY_PORT}/" 2>&1)
        case "$WGET_OUT" in
            *"Connection refused"*)
                # Port is closed - proxy not running
                return 1
                ;;
            *"connected"*|*"200"*|*"Bad Request"*|*"error"*)
                # Got a TCP response (even if HTTP error) - proxy is alive
                return 0
                ;;
        esac
    fi

    # Method 3: Attempt raw TCP connect via shell (ash/busybox may support)
    if (echo > /dev/tcp/"$PROXY_IP"/"$PROXY_PORT") 2>/dev/null; then
        return 0
    fi

    # All methods failed - consider proxy unreachable
    return 1
}

# ---------------------------------------------------------------------------
# Read / write proxy state
# ---------------------------------------------------------------------------
get_state() {
    if [ -f "$STATEFILE" ]; then
        cat "$STATEFILE"
    else
        echo "unknown"
    fi
}

set_state() {
    echo "$1" > "$STATEFILE"
}

# ---------------------------------------------------------------------------
# LED notification (optional, best-effort)
# ---------------------------------------------------------------------------
blink_led() {
    # GL-iNet Opal has a power LED; attempt to blink on error
    LED_PATH="/sys/class/leds/gl-sft1200:white:power/brightness"
    if [ -f "$LED_PATH" ]; then
        case "$1" in
            error)
                # Rapid blink 3 times
                for i in 1 2 3; do
                    echo 0 > "$LED_PATH" 2>/dev/null
                    sleep 0.2
                    echo 255 > "$LED_PATH" 2>/dev/null
                    sleep 0.2
                done
                ;;
            ok)
                # Solid on
                echo 255 > "$LED_PATH" 2>/dev/null
                ;;
        esac
    fi
}

# ---------------------------------------------------------------------------
# Main health check loop
# ---------------------------------------------------------------------------
run_monitor() {
    # Write PID file
    echo $$ > "$PIDFILE"

    fail_count=0
    set_state "starting"
    log_msg "Health monitor started (interval=${HEALTH_INTERVAL}s, threshold=${FAIL_THRESHOLD})"
    log_msg "Monitoring proxy at ${PROXY_IP}:${PROXY_PORT}"

    while true; do
        if check_proxy; then
            # Proxy is reachable
            if [ "$fail_count" -gt 0 ] || [ "$(get_state)" != "up" ]; then
                log_msg "Proxy is reachable at ${PROXY_IP}:${PROXY_PORT}"
                if [ "$(get_state)" = "down" ] && [ "$KILL_SWITCH" = "1" ]; then
                    log_msg "Restoring connectivity (deactivating kill switch)"
                    "$FW_SCRIPT" kill_off
                    blink_led ok
                fi
                set_state "up"
            fi
            fail_count=0
        else
            # Proxy is unreachable
            fail_count=$((fail_count + 1))
            log_warn "Proxy unreachable at ${PROXY_IP}:${PROXY_PORT} (failure ${fail_count}/${FAIL_THRESHOLD})"

            if [ "$fail_count" -ge "$FAIL_THRESHOLD" ]; then
                if [ "$(get_state)" != "down" ]; then
                    log_err "Proxy down for ${FAIL_THRESHOLD} consecutive checks"
                    if [ "$KILL_SWITCH" = "1" ]; then
                        log_err "Activating kill switch — blocking all internet traffic"
                        "$FW_SCRIPT" kill_on
                    fi
                    set_state "down"
                    blink_led error
                fi
            fi
        fi

        sleep "$HEALTH_INTERVAL"
    done
}

# ---------------------------------------------------------------------------
# Stop the monitor
# ---------------------------------------------------------------------------
stop_monitor() {
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_msg "Stopping health monitor (PID $pid)"
            kill "$pid" 2>/dev/null
            rm -f "$PIDFILE" "$STATEFILE"
        else
            log_msg "Health monitor not running (stale PID file)"
            rm -f "$PIDFILE" "$STATEFILE"
        fi
    else
        log_msg "Health monitor not running (no PID file)"
    fi
}

# ---------------------------------------------------------------------------
# Check current status
# ---------------------------------------------------------------------------
show_status() {
    echo "=== CamoFox Health Monitor ==="
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  Monitor: running (PID $pid)"
        else
            echo "  Monitor: not running (stale PID)"
        fi
    else
        echo "  Monitor: not running"
    fi
    echo "  Proxy target: ${PROXY_IP}:${PROXY_PORT}"
    echo "  Proxy state: $(get_state)"
    echo "  Kill switch: $([ "$KILL_SWITCH" = '1' ] && echo 'enabled' || echo 'disabled')"
    echo "  Check interval: ${HEALTH_INTERVAL}s"
    echo "  Fail threshold: ${FAIL_THRESHOLD}"
}

# ---------------------------------------------------------------------------
# One-shot connectivity test
# ---------------------------------------------------------------------------
test_proxy() {
    echo "Testing SOCKS5 proxy at ${PROXY_IP}:${PROXY_PORT}..."
    if check_proxy; then
        echo "  Result: REACHABLE"
        return 0
    else
        echo "  Result: UNREACHABLE"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
load_config

case "$1" in
    start)
        run_monitor
        ;;
    stop)
        stop_monitor
        ;;
    status)
        show_status
        ;;
    test)
        test_proxy
        ;;
    *)
        echo "Usage: $0 {start|stop|status|test}"
        exit 1
        ;;
esac
