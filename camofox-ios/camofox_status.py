#!python3
"""CamoFox Status Dashboard — Pythonista-native proxy monitor.

Displays real-time proxy statistics using Pythonista's ``console``
module (falls back to ANSI terminal on non-iOS platforms).

Metrics shown:
  • Proxy status (running / stopped / error)
  • Connected client count
  • Bytes transferred (upload / download)
  • Uptime
  • Current WiFi IP & listening ports
  • Connection quality indicator
  • Recent log messages

Usage::

    from camofox_status import CamoFoxDashboard
    dashboard = CamoFoxDashboard(proxy)
    await dashboard.run()   # or dashboard.run_sync()
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camofox_proxy import CamoFoxProxy

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
for _p in (_PROJECT_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Pythonista detection
# ---------------------------------------------------------------------------
_IS_PYTHONISTA = "Pythonista" in sys.executable

try:
    import console as ios_console  # type: ignore
except ImportError:
    ios_console = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_bytes(nbytes: int) -> str:
    """Human-readable byte count."""
    if nbytes < 1024:
        return f"{nbytes} B"
    elif nbytes < 1024 ** 2:
        return f"{nbytes / 1024:.1f} KB"
    elif nbytes < 1024 ** 3:
        return f"{nbytes / (1024**2):.1f} MB"
    else:
        return f"{nbytes / (1024**3):.2f} GB"


def _format_speed(bps: float) -> str:
    """Human-readable speed (bits per second → Mbps)."""
    mbps = bps * 8 / (1024 * 1024)
    if mbps < 0.01:
        return "0 Mbps"
    elif mbps < 1:
        return f"{mbps:.2f} Mbps"
    else:
        return f"{mbps:.1f} Mbps"


def _quality_indicator(active_connections: int, error_count: int) -> str:
    """Simple connection quality emoji indicator."""
    if error_count > 10:
        return "🔴 Poor"
    elif error_count > 3:
        return "🟡 Fair"
    elif active_connections > 0:
        return "🟢 Good"
    else:
        return "⚪ Idle"


def _get_wifi_ip() -> str:
    """Best-effort WiFi IP detection."""
    try:
        from lib import ifaddrs
        for iface in ifaddrs.get_interfaces():
            if not iface.addr:
                continue
            if iface.name.startswith("en") and iface.addr.family == socket.AF_INET:
                return iface.addr.address
            if iface.name.startswith("bridge") and iface.addr.family == socket.AF_INET:
                return iface.addr.address
    except Exception:
        pass
    # Fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def _clear_screen() -> None:
    """Clear console output."""
    if ios_console and _IS_PYTHONISTA:
        ios_console.clear()
    else:
        print("\033c", end="")


# ---------------------------------------------------------------------------
# Dashboard class
# ---------------------------------------------------------------------------

class CamoFoxDashboard:
    """Real-time status dashboard for the CamoFox proxy.

    Args:
        proxy: A ``CamoFoxProxy`` instance (or None for standalone mode).
        status_monitor: The ``StatusMonitor`` from lib/status.py
            that's collecting traffic stats.
        refresh_interval: Seconds between display refreshes.
    """

    def __init__(
        self,
        proxy: Optional[CamoFoxProxy] = None,
        status_monitor=None,
        refresh_interval: float = 1.0,
    ):
        self._proxy = proxy
        self._monitor = status_monitor
        self._interval = refresh_interval
        self._start_time = time.time()
        self._wifi_ip = _get_wifi_ip()

    def render_frame(self) -> str:
        """Generate a single frame of the dashboard as a string."""
        lines = []

        # Header
        lines.append("╔══════════════════════════════════════════════╗")
        lines.append("║        🦊 CamoFox Status Dashboard          ║")
        lines.append("╚══════════════════════════════════════════════╝")
        lines.append("")

        # Proxy status
        if self._proxy:
            running = self._proxy._running
            stats = self._proxy.stats
        else:
            running = False
            stats = None

        status_str = "🟢 RUNNING" if running else "🔴 STOPPED"
        lines.append(f"  Status:      {status_str}")

        # Uptime
        if stats and stats.start_time > 0:
            lines.append(f"  Uptime:      {stats.uptime_str}")
        else:
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            hours, mins = divmod(mins, 60)
            lines.append(f"  Uptime:      {hours}h {mins}m {secs}s")

        lines.append("")

        # Network info
        lines.append("  ── Network ──────────────────────────────────")
        lines.append(f"  WiFi IP:     {self._wifi_ip}")

        if self._proxy:
            cfg = self._proxy.config
            lines.append(f"  SOCKS5:      {self._wifi_ip}:{cfg.socks_port}")
            lines.append(f"  HTTP Proxy:  {self._wifi_ip}:{cfg.http_port}")
            lines.append(f"  WPAD/PAC:    http://{self._wifi_ip}:{cfg.wpad_port}/wpad.dat")
        else:
            lines.append("  SOCKS5:      (not connected)")

        lines.append("")

        # Traffic stats
        lines.append("  ── Traffic ──────────────────────────────────")
        if self._monitor:
            in_speed, in_total = self._monitor.inbound.update()
            out_speed, out_total = self._monitor.outbound.update()
            num_conn = self._monitor.num_connections
            num_err = self._monitor.num_errors

            lines.append(f"  Connections: {num_conn}")
            lines.append(f"  Download:    {_format_speed(in_speed)}  ({_format_bytes(in_total)} total)")
            lines.append(f"  Upload:      {_format_speed(out_speed)}  ({_format_bytes(out_total)} total)")
            lines.append(f"  Total Data:  {_format_bytes(in_total + out_total)}")
            lines.append(f"  Quality:     {_quality_indicator(num_conn, num_err)}")

            if num_err > 0:
                lines.append(f"  Errors:      {num_err}")
        else:
            lines.append("  (no traffic data available)")

        lines.append("")

        # Restart info
        if stats and stats.restart_count > 0:
            lines.append("  ── Reliability ──────────────────────────────")
            lines.append(f"  Restarts:    {stats.restart_count}")
            if stats.last_error:
                lines.append(f"  Last Error:  {stats.last_error[:50]}")
            lines.append("")

        # Keepalive info
        if self._proxy and self._proxy._keepalive:
            ka_status = self._proxy._keepalive.status()
            active = [k for k, v in ka_status.items() if v and k != "running"]
            if active:
                lines.append("  ── Keepalive ────────────────────────────────")
                lines.append(f"  Active:      {', '.join(active)}")
                lines.append("")

        # Log messages
        if self._monitor and self._monitor.messages:
            lines.append("  ── Recent Log ───────────────────────────────")
            for msg in self._monitor.messages[-3:]:
                lines.append(f"  {msg[:60]}")
            lines.append("")

        # Footer
        lines.append("  Press Ctrl+C to stop")

        return "\n".join(lines)

    async def run(self) -> None:
        """Async dashboard loop — refreshes every ``refresh_interval`` sec."""
        while True:
            _clear_screen()
            print(self.render_frame())
            await asyncio.sleep(self._interval)

    def run_sync(self) -> None:
        """Synchronous dashboard loop (blocking)."""
        try:
            while True:
                _clear_screen()
                print(self.render_frame())
                time.sleep(self._interval)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")

    def refresh_wifi_ip(self) -> None:
        """Re-detect WiFi IP (call after network change)."""
        self._wifi_ip = _get_wifi_ip()


# ---------------------------------------------------------------------------
# Standalone test mode
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("CamoFox Dashboard — Standalone Test Mode")
    print(f"WiFi IP: {_get_wifi_ip()}")
    print(f"Platform: {'Pythonista' if _IS_PYTHONISTA else 'Desktop/Server'}")
    print()

    # Run without a proxy for visual testing
    dashboard = CamoFoxDashboard()
    dashboard.run_sync()
