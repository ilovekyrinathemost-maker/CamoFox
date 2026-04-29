#!python3
"""CamoFox Status Dashboard — Cross-platform proxy monitor.

Displays real-time proxy statistics using ANSI terminal escape codes.
Works on all supported iOS Python environments:
  • a-Shell  — Full ANSI color support
  • iSH      — Full ANSI color support
  • Pyto     — ANSI colors in terminal mode
  • Pythonista — ANSI colors + optional console module enhancements

Metrics shown:
  • Proxy status (running / stopped / error)
  • Platform and keepalive info
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
# Platform detection
# ---------------------------------------------------------------------------
try:
    from platform_detect import PLATFORM, CAPABILITIES
except ImportError:
    try:
        from camofox_ios.platform_detect import PLATFORM, CAPABILITIES  # type: ignore
    except ImportError:
        PLATFORM = 'generic'
        CAPABILITIES = {'ansi_colors': True, 'gui': False}

# Pythonista console (optional enhancement)
_ios_console = None
try:
    import console as _ios_console  # type: ignore
except ImportError:
    pass


# ---------------------------------------------------------------------------
# ANSI Color helpers — work on all terminals
# ---------------------------------------------------------------------------
class _Colors:
    """ANSI escape code constants for terminal colors."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    # Foreground
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    # Background
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_BLUE = '\033[44m'


class _NoColors:
    """No-op color constants for environments without ANSI support."""
    RESET = BOLD = DIM = ''
    RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ''
    BG_RED = BG_GREEN = BG_BLUE = ''


# Auto-select based on capabilities
C = _Colors() if CAPABILITIES.get('ansi_colors', True) else _NoColors()


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
    """Human-readable speed (bits per second -> Mbps)."""
    mbps = bps * 8 / (1024 * 1024)
    if mbps < 0.01:
        return "0 Mbps"
    elif mbps < 1:
        return f"{mbps:.2f} Mbps"
    else:
        return f"{mbps:.1f} Mbps"


def _quality_indicator(active_connections: int, error_count: int) -> str:
    """Connection quality indicator with color."""
    if error_count > 10:
        return f"{C.RED}● Poor{C.RESET}"
    elif error_count > 3:
        return f"{C.YELLOW}● Fair{C.RESET}"
    elif active_connections > 0:
        return f"{C.GREEN}● Good{C.RESET}"
    else:
        return f"{C.DIM}● Idle{C.RESET}"


def _platform_badge() -> str:
    """Return a colored platform badge."""
    badges = {
        'pythonista': f"{C.MAGENTA}Pythonista{C.RESET}",
        'ashell': f"{C.GREEN}a-Shell{C.RESET}",
        'ish': f"{C.CYAN}iSH{C.RESET}",
        'pyto': f"{C.BLUE}Pyto{C.RESET}",
        'generic': f"{C.WHITE}Python{C.RESET}",
    }
    return badges.get(PLATFORM, PLATFORM)


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
    """Clear console output — cross-platform."""
    if _ios_console and PLATFORM == 'pythonista':
        try:
            _ios_console.clear()
            return
        except Exception:
            pass
    # ANSI clear — works on a-Shell, iSH, Pyto, and any terminal
    print("\033[2J\033[H", end="", flush=True)


# ---------------------------------------------------------------------------
# Dashboard class
# ---------------------------------------------------------------------------

class CamoFoxDashboard:
    """Real-time status dashboard for the CamoFox proxy.

    Uses ANSI escape codes for cross-platform colored terminal output.
    Automatically enhanced with Pythonista console features when available.

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

        # Header with color
        lines.append(f"{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════╗{C.RESET}")
        lines.append(f"{C.BOLD}{C.CYAN}║        🦊 CamoFox Status Dashboard          ║{C.RESET}")
        lines.append(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════╝{C.RESET}")
        lines.append("")

        # Platform info
        lines.append(f"  Platform:    {_platform_badge()}")

        # Proxy status
        if self._proxy:
            running = self._proxy._running
            stats = self._proxy.stats
        else:
            running = False
            stats = None

        if running:
            status_str = f"{C.GREEN}{C.BOLD}● RUNNING{C.RESET}"
        else:
            status_str = f"{C.RED}{C.BOLD}● STOPPED{C.RESET}"
        lines.append(f"  Status:      {status_str}")

        # Uptime
        if stats and stats.start_time > 0:
            lines.append(f"  Uptime:      {C.WHITE}{stats.uptime_str}{C.RESET}")
        else:
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            hours, mins = divmod(mins, 60)
            lines.append(f"  Uptime:      {C.WHITE}{hours}h {mins}m {secs}s{C.RESET}")

        lines.append("")

        # Network info
        lines.append(f"  {C.BOLD}── Network ──────────────────────────────────{C.RESET}")
        lines.append(f"  WiFi IP:     {C.YELLOW}{self._wifi_ip}{C.RESET}")

        if self._proxy:
            cfg = self._proxy.config
            lines.append(f"  SOCKS5:      {C.GREEN}{self._wifi_ip}:{cfg.socks_port}{C.RESET}")
            lines.append(f"  HTTP Proxy:  {C.GREEN}{self._wifi_ip}:{cfg.http_port}{C.RESET}")
            lines.append(f"  WPAD/PAC:    {C.DIM}http://{self._wifi_ip}:{cfg.wpad_port}/wpad.dat{C.RESET}")
        else:
            lines.append(f"  SOCKS5:      {C.DIM}(not connected){C.RESET}")

        lines.append("")

        # Traffic stats
        lines.append(f"  {C.BOLD}── Traffic ──────────────────────────────────{C.RESET}")
        if self._monitor:
            in_speed, in_total = self._monitor.inbound.update()
            out_speed, out_total = self._monitor.outbound.update()
            num_conn = self._monitor.num_connections
            num_err = self._monitor.num_errors

            lines.append(f"  Connections: {C.WHITE}{num_conn}{C.RESET}")
            lines.append(f"  Download:    {C.CYAN}{_format_speed(in_speed)}{C.RESET}  ({_format_bytes(in_total)} total)")
            lines.append(f"  Upload:      {C.CYAN}{_format_speed(out_speed)}{C.RESET}  ({_format_bytes(out_total)} total)")
            lines.append(f"  Total Data:  {C.BOLD}{_format_bytes(in_total + out_total)}{C.RESET}")
            lines.append(f"  Quality:     {_quality_indicator(num_conn, num_err)}")

            if num_err > 0:
                lines.append(f"  Errors:      {C.RED}{num_err}{C.RESET}")
        else:
            lines.append(f"  {C.DIM}(no traffic data available){C.RESET}")

        lines.append("")

        # Restart info
        if stats and stats.restart_count > 0:
            lines.append(f"  {C.BOLD}── Reliability ──────────────────────────────{C.RESET}")
            lines.append(f"  Restarts:    {C.YELLOW}{stats.restart_count}{C.RESET}")
            if stats.last_error:
                lines.append(f"  Last Error:  {C.RED}{stats.last_error[:50]}{C.RESET}")
            lines.append("")

        # Keepalive info
        if self._proxy and self._proxy._keepalive:
            ka_status = self._proxy._keepalive.status()
            active = [k for k, v in ka_status.items() if v and k not in ('running', 'platform')]
            if active:
                lines.append(f"  {C.BOLD}── Keepalive ──────────────────────────────{C.RESET}")
                lines.append(f"  Active:      {C.GREEN}{', '.join(active)}{C.RESET}")
                lines.append("")

        # Log messages
        if self._monitor and self._monitor.messages:
            lines.append(f"  {C.BOLD}── Recent Log ─────────────────────────────{C.RESET}")
            for msg in self._monitor.messages[-3:]:
                lines.append(f"  {C.DIM}{msg[:60]}{C.RESET}")
            lines.append("")

        # Footer
        lines.append(f"  {C.DIM}Press Ctrl+C to stop{C.RESET}")

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
            print(f"\n{C.DIM}Dashboard stopped.{C.RESET}")

    def refresh_wifi_ip(self) -> None:
        """Re-detect WiFi IP (call after network change)."""
        self._wifi_ip = _get_wifi_ip()


# ---------------------------------------------------------------------------
# Standalone test mode
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"CamoFox Dashboard — Standalone Test Mode")
    print(f"Platform: {_platform_badge()}")
    print(f"WiFi IP:  {_get_wifi_ip()}")
    print(f"ANSI:     {CAPABILITIES.get('ansi_colors', False)}")
    print()

    # Run without a proxy for visual testing
    dashboard = CamoFoxDashboard()
    dashboard.run_sync()
