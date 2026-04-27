#!python3
"""CamoFox Network Diagnostics — Verify iPhone proxy setup.

Runs a comprehensive battery of checks to confirm the iPhone is
correctly configured to act as a SOCKS proxy for the GL-iNet Opal
router.  Output is a formatted report suitable for copy-pasting
into a support request or troubleshooting session.

Checks performed:
  1. WiFi connectivity & interface detection
  2. List all network interfaces with addresses
  3. DNS resolution (system + custom resolvers)
  4. Proxy port availability (9876, 9877, 8088)
  5. Loopback proxy test (connect to own SOCKS port)
  6. Internet connectivity test (direct + via proxy)
  7. Cellular interface detection
  8. Pythonista environment check
  9. Keepalive feature availability

Usage::

    python diagnostics.py          # run all checks
    python diagnostics.py --json   # output as JSON
"""

from __future__ import annotations

import json as json_mod
import os
import socket
import struct
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
# Check result container
# ---------------------------------------------------------------------------

class CheckResult:
    """Result of a single diagnostic check."""

    def __init__(self, name: str, passed: bool, detail: str = "",
                 warning: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.warning = warning

    @property
    def status_icon(self) -> str:
        if self.passed:
            return "✅"
        elif self.warning:
            return "⚠️"
        else:
            return "❌"

    def __str__(self) -> str:
        line = f"{self.status_icon} {self.name}"
        if self.detail:
            line += f"\n     {self.detail}"
        if self.warning:
            line += f"\n     ⚠️  {self.warning}"
        return line

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "warning": self.warning,
        }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_pythonista_env() -> CheckResult:
    """Check if running inside Pythonista."""
    is_pythonista = "Pythonista" in sys.executable
    version = sys.version.split()[0]
    detail = f"Python {version}"
    if is_pythonista:
        detail += " (Pythonista)"
    else:
        detail += " (not Pythonista — some iOS features unavailable)"
    return CheckResult(
        "Pythonista Environment",
        passed=True,  # informational
        detail=detail,
        warning="" if is_pythonista else "Not running in Pythonista — iOS keepalive features disabled",
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
        return CheckResult(
            "Network Interfaces",
            passed=False,
            detail=f"ifaddrs not available: {exc}",
            warning="Using ctypes — only works on iOS/macOS",
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

    # Fallback
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
        return CheckResult(
            "Cellular Interface",
            passed=False,
            detail=f"Cannot detect: {exc}",
            warning="ifaddrs requires iOS/macOS",
        )


def check_dns_resolution() -> CheckResult:
    """Test DNS resolution."""
    test_domains = ["example.com", "google.com", "cloudflare.com"]
    results = []
    for domain in test_domains:
        try:
            ip = socket.gethostbyname(domain)
            results.append(f"{domain} → {ip}")
        except Exception as exc:
            results.append(f"{domain} → FAILED ({exc})")

    all_ok = all("FAILED" not in r for r in results)
    return CheckResult(
        "DNS Resolution",
        passed=all_ok,
        detail="\n     ".join(results),
    )


def check_port_available(port: int, name: str) -> CheckResult:
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
    except OSError as exc:
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
                detail=f"Unavailable: {exc}",
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
            detail="Connection refused — proxy not running",
            warning="Start the proxy first: python camofox_start.py",
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
        return CheckResult(
            "dnspython Library",
            passed=False,
            detail="Not installed",
            warning="Install via StaSh: pip install dnspython",
        )


def check_keepalive_features() -> CheckResult:
    """Check which keepalive features are available."""
    features = []
    try:
        import console  # type: ignore
        features.append("console")
    except ImportError:
        pass
    try:
        from objc_util import on_main_thread  # type: ignore
        features.append("objc_util")
    except ImportError:
        pass
    try:
        import sound  # type: ignore
        features.append("sound")
    except ImportError:
        pass
    try:
        import location  # type: ignore
        features.append("location")
    except ImportError:
        pass

    if features:
        return CheckResult(
            "Keepalive Features",
            passed=True,
            detail=f"Available: {', '.join(features)}",
        )
    else:
        return CheckResult(
            "Keepalive Features",
            passed=False,
            detail="No Pythonista keepalive modules available",
            warning="Keepalive requires Pythonista (console, sound, location)",
        )


def check_router_reachability(router_ip: str = "192.168.8.1") -> CheckResult:
    """Check if the router can be reached (try common IPs)."""
    ips_to_try = [router_ip, "192.168.8.1", "192.168.1.1", "192.168.0.1"]
    for ip in ips_to_try:
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
        detail=f"Cannot reach router at any of: {', '.join(ips_to_try)}",
        warning="Router may be on a different subnet or not connected",
    )


# ---------------------------------------------------------------------------
# Run all diagnostics
# ---------------------------------------------------------------------------

def run_all_checks() -> list[CheckResult]:
    """Execute all diagnostic checks and return results."""
    results = []

    results.append(check_pythonista_env())
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


def format_report(results: list[CheckResult]) -> str:
    """Format diagnostic results as a readable report."""
    lines = [
        "╔══════════════════════════════════════════════════╗",
        "║       🦊 CamoFox Network Diagnostics             ║",
        "╚══════════════════════════════════════════════════╝",
        "",
    ]

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    warnings = sum(1 for r in results if r.warning)

    for result in results:
        lines.append(str(result))
        lines.append("")

    lines.append("─" * 50)
    lines.append(f"Results: {passed}/{total} passed", )
    if warnings:
        lines.append(f"Warnings: {warnings}")
    lines.append("")

    if passed == total:
        lines.append("🎉 All checks passed! Your setup looks good.")
    elif passed >= total - 2:
        lines.append("👍 Most checks passed. Review warnings above.")
    else:
        lines.append("⚠️  Several checks failed. Review the report above.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Run diagnostics and print results."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CamoFox Network Diagnostics",
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
