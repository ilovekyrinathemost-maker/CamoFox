#!python3
"""CamoFox Enhanced SOCKS5/HTTP Proxy for Pythonista.

An improved version of the iOS-SOCKS-Server proxy optimised for the
CamoFox tethering-bypass use case.  It wraps the existing ``lib/``
proxy server classes and adds:

  • Auto-detection of WiFi / cellular / VPN interfaces
  • Integrated keepalive to prevent iOS suspension
  • Rich statistics (bytes, connections, uptime, errors)
  • Auto-restart on crash with configurable retry policy
  • Reduced logging overhead to minimise Pythonista CPU
  • WPAD server for easy client auto-configuration
  • Graceful handling of network interface changes

Usage (standalone)::

    python camofox_proxy.py          # auto-detect everything
    python camofox_proxy.py --port 1080  # custom SOCKS port

Usage (as module)::

    from camofox_proxy import CamoFoxProxy
    proxy = CamoFoxProxy()
    proxy.run()                      # blocking
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import signal
import socket
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — allow importing lib/ and dns/ from the project root.
# Works whether this script is run from camofox-ios/ or from the project root.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

for _p in (_PROJECT_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Now import project modules
# ---------------------------------------------------------------------------
from lib.socks5_server import AsyncSocks5Handler  # noqa: E402
from lib.http_proxy_server import AsyncHTTPProxyHandler  # noqa: E402
from lib.proxy_server import AsyncProxyServer  # noqa: E402
from lib.status import StatusMonitor  # noqa: E402

try:
    from keepalive import KeepaliveManager  # noqa: E402
except ImportError:
    from camofox_ios.keepalive import KeepaliveManager  # type: ignore

# ---------------------------------------------------------------------------
# Configuration — edit these values to taste
# ---------------------------------------------------------------------------

@dataclass
class ProxyConfig:
    """All tuneable knobs in one place."""

    # Network ------------------------------------------------------------------
    proxy_host: str = ""               # auto-detected if empty
    listen_host: str = "0.0.0.0"       # bind address for listeners
    socks_port: int = 9876             # SOCKS5 proxy port
    http_port: int = 9877              # HTTP proxy port
    wpad_port: int = 8088              # WPAD auto-config port

    # Connectivity -------------------------------------------------------------
    connect_host_ipv4: str = ""        # auto-detected if empty
    connect_host_ipv6: Optional[str] = None  # auto-detected
    idle_timeout: int = 1800           # drop idle connections after N sec
    use_phone_vpn: bool = True         # route through utun if present

    # DNS ----------------------------------------------------------------------
    custom_resolvers: list = field(default_factory=list)
    default_resolvers: list = field(default_factory=lambda: [
        "1.0.0.1", "1.1.1.1", "8.8.8.8",
        "2606:4700:4700::1111", "2606:4700:4700::1001",
        "2001:4860:4860::8844",
    ])

    # Reliability --------------------------------------------------------------
    auto_restart: bool = True          # restart proxy on crash
    max_restart_attempts: int = 10     # give up after N consecutive failures
    restart_delay: float = 2.0         # seconds between restarts
    restart_backoff: float = 1.5       # multiply delay after each failure
    restart_max_delay: float = 60.0    # cap on backoff delay

    # Keepalive ----------------------------------------------------------------
    enable_keepalive: bool = True      # use KeepaliveManager
    keepalive_audio: bool = True       # silent audio loop
    keepalive_location: bool = False   # GPS keepalive (battery heavy)
    keepalive_ping_interval: float = 30.0

    # Logging ------------------------------------------------------------------
    log_level: int = logging.ERROR     # minimise output for Pythonista
    status_interval: float = 1.0       # status display refresh rate (sec)


# Global default instance — edit here or create a custom one.
CONFIG = ProxyConfig()


# ---------------------------------------------------------------------------
# Extended statistics tracker
# ---------------------------------------------------------------------------

@dataclass
class ProxyStats:
    """Extended statistics beyond what StatusMonitor tracks."""
    start_time: float = 0.0
    restart_count: int = 0
    total_connections: int = 0
    total_errors: int = 0
    total_bytes_in: int = 0
    total_bytes_out: int = 0
    last_error: str = ""
    last_error_time: float = 0.0

    @property
    def uptime(self) -> float:
        """Seconds since proxy started."""
        if self.start_time == 0:
            return 0.0
        return time.time() - self.start_time

    @property
    def uptime_str(self) -> str:
        """Human-readable uptime."""
        secs = int(self.uptime)
        days, secs = divmod(secs, 86400)
        hours, secs = divmod(secs, 3600)
        mins, secs = divmod(secs, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if mins:
            parts.append(f"{mins}m")
        parts.append(f"{secs}s")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Network interface detection (iOS-specific via ctypes / fallback)
# ---------------------------------------------------------------------------

def _is_globally_routable(ipv6_address: str) -> bool:
    """Return True if the IPv6 address is globally routable."""
    non_routable = [
        "ff00::/8", "fe80::/10", "fc00::/7", "::/8",
        "2001:db8::/32", "2001::/32", "2002::/16", "ff02::/16",
    ]
    addr = ipaddress.ip_address(ipv6_address)
    return not any(addr in ipaddress.ip_network(n) for n in non_routable)


def detect_interfaces(config: ProxyConfig) -> tuple[str, str, Optional[str], str]:
    """Auto-detect proxy_host, connect_host_ipv4, connect_host_ipv6.

    Returns:
        (proxy_host, connect_host_ipv4, connect_host_ipv6, info_text)
    """
    proxy_host = config.proxy_host or "172.20.10.1"
    connect_ipv4 = config.connect_host_ipv4 or "0.0.0.0"
    connect_ipv6: Optional[str] = config.connect_host_ipv6
    info_lines: list[str] = []

    try:
        from lib import ifaddrs

        interfaces = ifaddrs.get_interfaces()
        iftypes: dict[str, list] = defaultdict(list)

        for iface in interfaces:
            if not iface.addr:
                continue
            if iface.name.startswith("lo"):
                continue
            if iface.name.startswith("en"):
                iftypes["en"].append(iface)
            elif iface.name.startswith("bridge"):
                iftypes["bridge"].append(iface)
            elif iface.name.startswith("utun"):
                iftypes["vpn"].append(iface)
            else:
                iftypes["cell"].append(iface)

        # VPN handling
        if iftypes["vpn"] and config.use_phone_vpn:
            info_lines.append("VPN use enabled")
            iftypes["cell"] = list(iftypes["vpn"]) + list(iftypes["cell"])

        # Detect WiFi/bridge interface for proxy host
        if iftypes["bridge"]:
            iface = next(
                (i for i in iftypes["bridge"] if i.addr.family == socket.AF_INET),
                None,
            )
            if iface:
                proxy_host = iface.addr.address
                info_lines.append(
                    f"Proxy host: {proxy_host} (hotspot {iface.name})"
                )
        elif iftypes["en"]:
            iface = next(
                (i for i in iftypes["en"] if i.addr.family == socket.AF_INET),
                None,
            )
            if iface:
                proxy_host = iface.addr.address
                info_lines.append(
                    f"Proxy host: {proxy_host} (WiFi {iface.name})"
                )
        else:
            info_lines.append(f"Proxy host: {proxy_host} (default — no WiFi detected)")

        # Detect cellular/VPN interface for outbound connections
        if iftypes["cell"]:
            ipv4_iface = next(
                (i for i in iftypes["cell"] if i.addr.family == socket.AF_INET),
                None,
            )
            is_vpn = ipv4_iface and ipv4_iface.name.startswith("utun")

            if ipv4_iface:
                connect_ipv4 = ipv4_iface.addr.address
                info_lines.append(
                    f"Connect IPv4: {connect_ipv4} ({ipv4_iface.name})"
                )

                # Find IPv6 on same interface
                ipv6_list = [
                    i for i in iftypes["cell"]
                    if i.addr.family == socket.AF_INET6
                    and i.addr.address
                    and (_is_globally_routable(i.addr.address) if not is_vpn else True)
                    and i.name == ipv4_iface.name
                ]
                ipv6_iface = ipv6_list[-1] if ipv6_list else None

            if ipv6_iface is None and not is_vpn:
                ipv6_list = [
                    i for i in iftypes["cell"]
                    if i.addr.family == socket.AF_INET6
                    and i.addr.address
                    and _is_globally_routable(i.addr.address)
                ]
                ipv6_iface = ipv6_list[-1] if ipv6_list else None

            if ipv6_iface:
                # Test IPv6 connectivity
                try:
                    test_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    test_sock.settimeout(5)
                    test_sock.bind((ipv6_iface.addr.address, 0))
                    test_sock.connect(("2606:4700:4700::1111", 80))
                    test_sock.close()
                    connect_ipv6 = ipv6_iface.addr.address
                    info_lines.append(
                        f"Connect IPv6: {connect_ipv6} ({ipv6_iface.name})"
                    )
                except Exception as exc:
                    info_lines.append(f"IPv6 test failed: {exc}")
                    connect_ipv6 = None
                finally:
                    try:
                        test_sock.close()
                    except Exception:
                        pass

    except Exception as exc:
        info_lines.append(f"Interface detection failed: {exc}")
        # Try simple fallback
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            proxy_host = s.getsockname()[0]
            s.close()
            info_lines.append(f"Fallback proxy host: {proxy_host}")
        except Exception:
            pass

    return proxy_host, connect_ipv4, connect_ipv6, "\n".join(info_lines)


# ---------------------------------------------------------------------------
# DNS resolver setup
# ---------------------------------------------------------------------------

def setup_resolver(config: ProxyConfig):
    """Configure dnspython resolver or return None for system DNS."""
    try:
        import dns.asyncresolver
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers += config.custom_resolvers or config.default_resolvers
        return resolver
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# WPAD server
# ---------------------------------------------------------------------------

def create_wpad_server(
    listen_host: str, wpad_port: int, proxy_host: str, socks_port: int
) -> HTTPServer:
    """Create a minimal WPAD/PAC server for client auto-configuration."""

    class WPADHandler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-type", "application/x-ns-proxy-autoconfig")
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "application/x-ns-proxy-autoconfig")
            self.end_headers()
            pac = (
                'function FindProxyForURL(url, host) {\n'
                '  if (isInNet(host, "192.168.0.0", "255.255.0.0")) return "DIRECT";\n'
                '  if (isInNet(host, "172.16.0.0", "255.240.0.0")) return "DIRECT";\n'
                '  if (isInNet(host, "10.0.0.0", "255.0.0.0")) return "DIRECT";\n'
                '  return "SOCKS5 %s:%d; SOCKS %s:%d";\n'
                '}\n'
            ) % (proxy_host, socks_port, proxy_host, socks_port)
            self.wfile.write(pac.encode())

        def log_message(self, fmt, *args):
            pass  # suppress WPAD request logging

    HTTPServer.allow_reuse_address = True
    return HTTPServer((listen_host, wpad_port), WPADHandler)


# ---------------------------------------------------------------------------
# Main proxy orchestrator
# ---------------------------------------------------------------------------

class CamoFoxProxy:
    """Enhanced SOCKS5/HTTP proxy with auto-restart and keepalive.

    Wraps the existing ``lib/`` proxy server classes and adds reliability
    features specific to running on iOS via Pythonista.
    """

    def __init__(self, config: Optional[ProxyConfig] = None):
        self.config = config or CONFIG
        self.stats = ProxyStats()
        self._keepalive: Optional[KeepaliveManager] = None
        self._wpad_server: Optional[HTTPServer] = None
        self._running = False
        self._shutdown_event = threading.Event()

        # Configure logging
        logging.basicConfig(level=self.config.log_level)

    def run(self) -> None:
        """Start the proxy (blocking).  Handles auto-restart internally."""
        self.stats.start_time = time.time()
        self._running = True

        # Start keepalive
        if self.config.enable_keepalive:
            self._keepalive = KeepaliveManager(
                use_audio=self.config.keepalive_audio,
                use_location=self.config.keepalive_location,
                ping_interval=self.config.keepalive_ping_interval,
            )
            ka_results = self._keepalive.start()
            for k, v in ka_results.items():
                if v:
                    logging.info("Keepalive: %s active", k)

        # Auto-restart loop
        delay = self.config.restart_delay
        consecutive_failures = 0

        while self._running:
            try:
                self._run_once()
                # Clean exit — no restart needed
                break
            except KeyboardInterrupt:
                print("\nShutting down (Ctrl+C)...")
                break
            except Exception as exc:
                consecutive_failures += 1
                self.stats.restart_count += 1
                self.stats.total_errors += 1
                self.stats.last_error = str(exc)
                self.stats.last_error_time = time.time()

                if not self.config.auto_restart:
                    logging.error("Proxy crashed: %s (auto-restart disabled)", exc)
                    break

                if consecutive_failures >= self.config.max_restart_attempts:
                    logging.error(
                        "Proxy crashed %d times — giving up: %s",
                        consecutive_failures, exc,
                    )
                    break

                logging.warning(
                    "Proxy crashed (attempt %d/%d): %s — restarting in %.1fs",
                    consecutive_failures,
                    self.config.max_restart_attempts,
                    exc,
                    delay,
                )
                if self._shutdown_event.wait(delay):
                    break  # shutdown requested during wait
                delay = min(delay * self.config.restart_backoff,
                            self.config.restart_max_delay)
            else:
                consecutive_failures = 0
                delay = self.config.restart_delay

        self._cleanup()

    def stop(self) -> None:
        """Request a graceful shutdown."""
        self._running = False
        self._shutdown_event.set()

    def _run_once(self) -> None:
        """Single run of the proxy servers (may raise on crash)."""
        # Detect interfaces
        proxy_host, connect_ipv4, connect_ipv6, info_text = detect_interfaces(
            self.config
        )

        # Override with explicit config values if set
        if self.config.proxy_host:
            proxy_host = self.config.proxy_host
        if self.config.connect_host_ipv4:
            connect_ipv4 = self.config.connect_host_ipv4

        # Setup resolver
        resolver = setup_resolver(self.config)
        if resolver is None:
            info_text += "\nDNS: using system resolver (dnspython not available)"
        else:
            info_text += "\nDNS: using custom resolvers"

        # Build banner
        banner = (
            "╔══════════════════════════════════════════════════╗\n"
            "║           CamoFox SOCKS5/HTTP Proxy              ║\n"
            "╚══════════════════════════════════════════════════╝\n"
            f"{info_text}\n"
            f"SOCKS5:     {proxy_host}:{self.config.socks_port}\n"
            f"HTTP Proxy: {proxy_host}:{self.config.http_port}\n"
            f"PAC URL:    http://{proxy_host}:{self.config.wpad_port}/wpad.dat\n"
        )

        if self.stats.restart_count > 0:
            banner += f"Restarts:   {self.stats.restart_count}\n"

        # Status monitor
        status_monitor = StatusMonitor(
            banner, interval=self.config.status_interval
        )
        logging.getLogger().addHandler(status_monitor)

        # WPAD server
        self._wpad_server = create_wpad_server(
            self.config.listen_host,
            self.config.wpad_port,
            proxy_host,
            self.config.socks_port,
        )
        wpad_thread = threading.Thread(
            target=self._run_wpad, daemon=True, name="wpad"
        )
        wpad_thread.start()

        # Run async proxy servers
        asyncio.run(self._async_main(
            status_monitor, resolver,
            connect_ipv4, connect_ipv6,
        ))

    async def _async_main(
        self,
        status_monitor: StatusMonitor,
        resolver,
        connect_ipv4: str,
        connect_ipv6: Optional[str],
    ) -> None:
        """Async entry point — start SOCKS5 + HTTP servers."""
        # SOCKS5 server
        socks_server = AsyncProxyServer(
            AsyncSocks5Handler,
            listen_hosts=self.config.listen_host,
            listen_port=self.config.socks_port,
            traffic_stats=status_monitor,
            resolver=resolver,
            connect_host_ipv4=connect_ipv4,
            connect_host_ipv6=connect_ipv6,
        )
        asyncio.create_task(socks_server.run())

        # HTTP proxy server
        http_server = AsyncProxyServer(
            AsyncHTTPProxyHandler,
            listen_hosts=self.config.listen_host,
            listen_port=self.config.http_port,
            traffic_stats=status_monitor,
            resolver=resolver,
            connect_host_ipv4=connect_ipv4,
            connect_host_ipv6=connect_ipv6,
        )
        asyncio.create_task(http_server.run())

        # Render status forever (blocks until cancelled)
        await status_monitor.render_forever()

    def _run_wpad(self) -> None:
        """Run WPAD server in a thread."""
        try:
            if self._wpad_server:
                self._wpad_server.serve_forever()
        except Exception:
            pass

    def _cleanup(self) -> None:
        """Clean shutdown of all components."""
        if self._wpad_server:
            try:
                self._wpad_server.shutdown()
            except Exception:
                pass

        if self._keepalive:
            self._keepalive.stop()

        logging.info("CamoFox proxy shut down cleanly")

    def get_stats(self) -> dict:
        """Return current proxy statistics."""
        return {
            "uptime": self.stats.uptime_str,
            "uptime_seconds": self.stats.uptime,
            "restart_count": self.stats.restart_count,
            "total_errors": self.stats.total_errors,
            "last_error": self.stats.last_error,
            "running": self._running,
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Parse CLI args and run the proxy."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CamoFox Enhanced SOCKS5/HTTP Proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python camofox_proxy.py                    # auto-detect everything\n"
            "  python camofox_proxy.py --socks-port 1080  # custom SOCKS port\n"
            "  python camofox_proxy.py --host 192.168.2.1 # explicit host\n"
            "  python camofox_proxy.py --no-restart       # disable auto-restart\n"
        ),
    )
    parser.add_argument(
        "--host", default="",
        help="Proxy host IP (auto-detected if omitted)",
    )
    parser.add_argument(
        "--socks-port", type=int, default=9876,
        help="SOCKS5 port (default: 9876)",
    )
    parser.add_argument(
        "--http-port", type=int, default=9877,
        help="HTTP proxy port (default: 9877)",
    )
    parser.add_argument(
        "--no-restart", action="store_true",
        help="Disable auto-restart on crash",
    )
    parser.add_argument(
        "--no-keepalive", action="store_true",
        help="Disable iOS keepalive strategies",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    config = ProxyConfig(
        proxy_host=args.host,
        socks_port=args.socks_port,
        http_port=args.http_port,
        auto_restart=not args.no_restart,
        enable_keepalive=not args.no_keepalive,
        log_level=logging.DEBUG if args.verbose else logging.ERROR,
    )

    proxy = CamoFoxProxy(config)

    # Handle signals for clean shutdown
    def sig_handler(signum, frame):
        proxy.stop()

    try:
        signal.signal(signal.SIGTERM, sig_handler)
        signal.signal(signal.SIGINT, sig_handler)
    except (OSError, ValueError):
        pass  # signal handling not available in all contexts

    proxy.run()


if __name__ == "__main__":
    main()
