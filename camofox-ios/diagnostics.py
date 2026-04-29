#!python3
"""CamoFox Network Diagnostics — Verify iPhone proxy setup.

Cross-platform diagnostic tool that works on all iOS Python environments:
  - a-Shell (FREE)  - iSH (FREE)  - Pyto (FREE)  - Pythonista ($9.99)

Runs a comprehensive battery of checks to confirm the iPhone is
correctly configured to act as a SOCKS proxy for the GL-iNet Opal
router.

Checks performed:
  1. Platform & environment detection
  2. WiFi connectivity & interface detection
  3. List all network interfaces with addresses
  4. DNS resolution (system + custom resolvers)
  5. Proxy port availability (9876, 9877, 8088)
  6. Loopback proxy test (connect to own SOCKS port)
  7. Internet connectivity test
  8. Cellular interface detection
  9. Keepalive feature availability
  10. Router reachability

Usage::

    python3 diagnostics.py          # run all checks
    python3 diagnostics.py --json   # output as JSON
"""

from __future__ import annotations

import json as json_mod
import os
import socket
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

for _p in (_PROJECT_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
try:
    from platform_detect import PLATFORM, CAPABILITIES, get_platform_info
except ImportError:
    try:
        from camofox_ios.platform_detect import PLATFORM, CAPABILITIES, get_platform_info  # type: ignore
    except ImportError:
        PLATFORM = 'generic'
        CAPABILITIES = {}
        def get_platform_info(): return f"Platform: generic\nPython: {sys.version.split()[0]}"


# ---------------------------------------------------------------------------
# Check result container
# ---------------------------------------------------------------------------

class CheckResult:
    """Result of a single diagnostic check."""

    def __init__(self, name, passed, detail="", warning=""):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.warning = warning

    @property
    def status_icon(self):
        if self.passed:
            return "\033[32m\u2714\033[0m"  # green checkmark
        elif self.warning:
            return "\033[33m\u26a0\033[0m"  # yellow warning
        else:
            return "\033[31m\u2718\033[0m"  # red X

    def __str__(self):
        line = f"{self.status_icon} {self.name}"
        if self.detail:
            line += f"\n     {self.detail}"
        if self.warning:
            line += f"\n     \033[33m\u26a0  {self.warning}\033[0m"
        return line

    def to_dict(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "warning": self.warning,
        }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_environment() -> CheckResult:
    """Check platform and Python environment."""
    version = sys.version.split()[0]
    platform_names = {
        'pythonista': 'Pythonista 3',
        'ashell': 'a-Shell (FREE)',
        'ish': 'iSH (FREE)',
        'pyto': 'Pyto (FREE)',
        'generic': 'Generic Python',
    }
    plat_name = platform_names.get(PLATFORM, PLATFORM)
    detail = f"Python {version} on {plat_name}"

    features = []
    if CAPABILITIES.get('objc_bridge'):
        features.append('ObjC bridge')
    if CAPABILITIES.get('background_audio'):
        features.append('audio keepalive')
    if CAPABILITIES.get('location'):
        features.append('GPS keepalive')
    if CAPABILITIES.get('pip'):
        features.append('pip')
    if features:
        detail += f"\n     Features: {', '.join(features)}"
    detail += f"\n     Background persistence: {CAPABILITIES.get('background_persist', 'unknown')}"

    warning = ""
    if PLATFORM == 'generic':
        warning = "Not running on a recognized iOS platform"

    return CheckResult(
        "Platform & Environment",
        passed=True,  # informational
        detail=detail,
        warning=warning,
    )


def check_network_interfaces() -> CheckResult:
    """List all network interfaces."""
    try:
        from lib import ifaddrs
        interfaces = ifaddrs.get_interfaces()
        iface_info = []
        for iface in interfaces:
            if not iface.addr or iface.name.startswith("lo"):
                continue
            family = "IPv4" if iface.addr.family == socket.AF_INET else "IPv6"
            iface_info.append(f"{iface.name}: {iface.addr.address} ({family})")

        if not iface_info:
            return CheckResult(
                "Network Interfaces",
                passed=False,
                detail="No network interfaces found",
            )

        return CheckResult(
            "Network Interfaces",
            passed=True,
            detail="\n     ".join(iface_info),
        )
    except Exception as exc:
        # ifaddrs uses ctypes — only works on iOS/macOS natively
        # On iSH we can try ip/ifconfig instead
        if PLATFORM == 'ish':
            try:
                import subprocess
                result = subprocess.run(
                    ['ip', 'addr', 'show'], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = [l.strip() for l in result.stdout.split('\n') if 'inet' in l]
                    return CheckResult(
                        "Network Interfaces",
                        passed=True,
                        detail="\n     ".join(lines[:10]) if lines else "No interfaces found",
                        warning="Using ip command (iSH Linux mode)",
                    )
            except Exception:
                pass

        return CheckResult(
            "Network Interfaces",
            passed=False,
            detail=f"ifaddrs not available: {exc}",
            warning="Interface detection uses ctypes (iOS/macOS). On iSH try: ip addr show",
        )


def check_wifi_connectivity() -> CheckResult:
    """Check if WiFi interface has an IP address."""
    wifi_ip = None
    try:
        from lib import ifaddrs
        for iface in ifaddrs.get_interfaces():
            if not iface.addr:
                continue
            if (iface.name.startswith("en") or iface.name.startswith("bridge")) \
                    and iface.addr.family == socket.AF_INET:
                wifi_ip = iface.addr.address
                return CheckResult(
                    "WiFi Connectivity",
                    passed=True,
                    detail=f"{wifi_ip} on {iface.name}",
                )
    except Exception:
        pass

    # Fallback — works on all platforms
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        wifi_ip = s.getsockname()[0]
        s.close()
        return CheckResult(
            "WiFi Connectivity",
            passed=True,
            detail=f"{wifi_ip} (detected via fallback)",
        )
    except Exception as exc:
        return CheckResult(
            "WiFi Connectivity",
            passed=False,
            detail=f"No WiFi connection: {exc}",
        )


def check_cellular_interface() -> CheckResult:
    """Check for cellular (pdp_ip) interface."""
    try:
        from lib import ifaddrs
        for iface in ifaddrs.get_interfaces():
            if not iface.addr:
                continue
            if iface.name.startswith("lo") or iface.name.startswith("en") \
                    or iface.name.startswith("bridge"):
                continue
            if iface.addr.family == socket.AF_INET:
                return CheckResult(
                    "Cellular Interface",
                    passed=True,
                    detail=f"{iface.addr.address} on {iface.name}",
                )
        return CheckResult(
            "Cellular Interface",
            passed=False,
            detail="No cellular interface found",
            warning="Cellular data may not be active",
        )
    except Exception as exc:
        warning = "ifaddrs requires iOS/macOS"
        if PLATFORM == 'ish':
            warning = "On iSH, cellular detection requires native iOS interface"
        return CheckResult(
            "Cellular Interface",
            passed=False,
            detail=f"Cannot detect: {exc}",
            warning=warning,
        )


def check_dns_resolution() -> CheckResult:
    """Test DNS resolution."""
    test_domains = ["example.com", "google.com", "cloudflare.com"]
    results = []
    for domain in test_domains:
        try:
            ip = socket.gethostbyname(domain)
            results.append(f"{domain} -> {ip}")
        except Exception as exc:
            results.append(f"{domain} -> FAILED ({exc})")

    all_ok = all("FAILED" not in r for r in results)
    return CheckResult(
        "DNS Resolution",
        passed=all_ok,
        detail="\n     ".join(results),
    )


def check_port_available(port, name) -> CheckResult:
    """Check if a port is available for binding."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.close()
        return CheckResult(
            f"Port {port} ({name})",
            passed=True,
            detail="Available for binding",
        )
    except OSError:
        # Port might be in use because the proxy is already running
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("127.0.0.1", port))
            sock.close()
            return CheckResult(
                f"Port {port} ({name})",
                passed=True,
                detail="In use (proxy may already be running)",
            )
        except Exception:
            return CheckResult(
                f"Port {port} ({name})",
                passed=False,
                detail="Unavailable (another process may be using it)",
            )


def check_proxy_connectivity() -> CheckResult:
    """Test if we can connect to the local SOCKS5 proxy."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(("127.0.0.1", 9876))
        # Send SOCKS5 greeting
        sock.sendall(b"\x05\x01\x00")  # version 5, 1 auth method, no auth
        resp = sock.recv(2)
        sock.close()
        if resp == b"\x05\x00":
            return CheckResult(
                "SOCKS5 Proxy Test",
                passed=True,
                detail="SOCKS5 handshake successful on 127.0.0.1:9876",
            )
        else:
            return CheckResult(
                "SOCKS5 Proxy Test",
                passed=False,
                detail=f"Unexpected response: {resp.hex()}",
            )
    except ConnectionRefusedError:
        return CheckResult(
            "SOCKS5 Proxy Test",
            passed=False,
            detail="Connection refused \u2014 proxy not running",
            warning="Start the proxy first: python3 camofox_start.py",
        )
    except Exception as exc:
        return CheckResult(
            "SOCKS5 Proxy Test",
            passed=False,
            detail=f"Error: {exc}",
        )


def check_internet_connectivity() -> CheckResult:
    """Test direct internet connectivity."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        start = time.time()
        sock.connect(("1.1.1.1", 80))
        latency = (time.time() - start) * 1000
        sock.close()
        return CheckResult(
            "Internet Connectivity",
            passed=True,
            detail=f"Connected to 1.1.1.1:80 in {latency:.0f}ms",
        )
    except Exception as exc:
        return CheckResult(
            "Internet Connectivity",
            passed=False,
            detail=f"Cannot reach internet: {exc}",
        )


def check_dnspython() -> CheckResult:
    """Check if dnspython is available."""
    try:
        import dns.asyncresolver
        import dns.version
        return CheckResult(
            "dnspython Library",
            passed=True,
            detail=f"Version {dns.version.version}",
        )
    except ImportError:
        # Platform-specific install instructions
        install_hints = {
            'pythonista': "Install via StaSh: pip install dnspython",
            'ashell': "In a-Shell run: pip install dnspython",
            'ish': "In iSH run: pip3 install dnspython",
            'pyto': "In Pyto: use built-in package manager or pip",
            'generic': "Run: pip3 install dnspython",
        }
        hint = install_hints.get(PLATFORM, install_hints['generic'])
        return CheckResult(
            "dnspython Library",
            passed=False,
            detail="Not installed (proxy will use system DNS instead)",
            warning=hint,
        )


def check_keepalive_features() -> CheckResult:
    """Check which keepalive features are available on this platform."""
    universal_features = ["self-ping", "network-activity", "file-heartbeat"]
    platform_features = []

    # Check Pythonista-specific modules
    try:
        import console  # type: ignore
        platform_features.append("idle-timer (Pythonista)")
    except ImportError:
        pass
    try:
        from objc_util import on_main_thread  # type: ignore
        platform_features.append("objc-bridge (Pythonista)")
    except ImportError:
        pass
    try:
        import sound  # type: ignore
        platform_features.append("audio-keepalive (Pythonista)")
    except ImportError:
        pass
    try:
        import location  # type: ignore
        platform_features.append("gps-keepalive (Pythonista)")
    except ImportError:
        pass

    all_features = universal_features + platform_features
    detail = f"Universal: {', '.join(universal_features)}"
    if platform_features:
        detail += f"\n     Platform-specific: {', '.join(platform_features)}"
    else:
        detail += f"\n     Platform: {PLATFORM} (no extra iOS modules)"

    # Add platform-specific tip
    tips = {
        'ish': "Enable Location Services for iSH in iOS Settings for best persistence",
        'ashell': "Keep a-Shell in foreground for best results",
        'pyto': "Keep Pyto in foreground; use terminal mode",
    }
    warning = tips.get(PLATFORM, "")

    return CheckResult(
        "Keepalive Features",
        passed=True,  # Universal features always available
        detail=detail,
        warning=warning,
    )


def check_router_reachability(router_ip="192.168.8.1") -> CheckResult:
    """Check if the router can be reached."""
    ips_to_try = [router_ip, "192.168.8.1", "192.168.1.1", "192.168.0.1"]
    # Remove duplicates while preserving order
    seen = set()
    unique_ips = []
    for ip in ips_to_try:
        if ip not in seen:
            seen.add(ip)
            unique_ips.append(ip)

    for ip in unique_ips:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((ip, 80))
            sock.close()
            return CheckResult(
                "Router Reachability",
                passed=True,
                detail=f"Router found at {ip}:80",
            )
        except Exception:
            continue

    return CheckResult(
        "Router Reachability",
        passed=False,
        detail=f"Cannot reach router at any of: {', '.join(unique_ips)}",
        warning="Router may be on a different subnet or not connected",
    )


def check_python_version() -> CheckResult:
    """Check Python version meets minimum requirement (3.6+)."""
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info[2]}"
    if major >= 3 and minor >= 6:
        return CheckResult(
            "Python Version",
            passed=True,
            detail=f"Python {version_str} (minimum: 3.6)",
        )
    else:
        return CheckResult(
            "Python Version",
            passed=False,
            detail=f"Python {version_str}",
            warning="CamoFox requires Python 3.6 or later",
        )


# ---------------------------------------------------------------------------
# Run all diagnostics
# ---------------------------------------------------------------------------

def run_all_checks() -> list:
    """Execute all diagnostic checks and return results."""
    results = []

    results.append(check_environment())
    results.append(check_python_version())
    results.append(check_network_interfaces())
    results.append(check_wifi_connectivity())
    results.append(check_cellular_interface())
    results.append(check_dns_resolution())
    results.append(check_dnspython())
    results.append(check_port_available(9876, "SOCKS5"))
    results.append(check_port_available(9877, "HTTP Proxy"))
    results.append(check_port_available(8088, "WPAD"))
    results.append(check_proxy_connectivity())
    results.append(check_internet_connectivity())
    results.append(check_keepalive_features())
    results.append(check_router_reachability())

    return results


def format_report(results) -> str:
    """Format diagnostic results as a readable report."""
    lines = [
        "\033[36m\033[1m"
        "\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557"
        "\033[0m",
        "\033[36m\033[1m"
        "\u2551       \U0001f98a CamoFox Network Diagnostics             \u2551"
        "\033[0m",
        "\033[36m\033[1m"
        "\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d"
        "\033[0m",
        "",
    ]

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    warnings = sum(1 for r in results if r.warning)

    for result in results:
        lines.append(str(result))
        lines.append("")

    lines.append("\u2500" * 50)
    lines.append(f"Results: {passed}/{total} passed")
    if warnings:
        lines.append(f"Warnings: {warnings}")
    lines.append("")

    if passed == total:
        lines.append("\033[32m\U0001f389 All checks passed! Your setup looks good.\033[0m")
    elif passed >= total - 2:
        lines.append("\033[33m\U0001f44d Most checks passed. Review warnings above.\033[0m")
    else:
        lines.append("\033[31m\u26a0\ufe0f  Several checks failed. Review the report above.\033[0m")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Run diagnostics and print results."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CamoFox Network Diagnostics (cross-platform)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--router-ip", default="192.168.8.1",
        help="Router IP to check (default: 192.168.8.1)",
    )

    args = parser.parse_args()

    print("Running diagnostics...\n")
    results = run_all_checks()

    if args.json:
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "python_version": sys.version,
            "platform": PLATFORM,
            "checks": [r.to_dict() for r in results],
            "summary": {
                "passed": sum(1 for r in results if r.passed),
                "total": len(results),
                "warnings": sum(1 for r in results if r.warning),
            },
        }
        print(json_mod.dumps(output, indent=2))
    else:
        print(format_report(results))


if __name__ == "__main__":
    main()
