#!python3
"""CamoFox Quick Start — Universal proxy launcher for iOS.

Works on all supported iOS Python environments:
  - a-Shell (FREE)    — Recommended free option
  - iSH (FREE)        — Best background persistence
  - Pyto (FREE)       — Python 3 with iOS integration
  - Pythonista ($9.99) — Premium iOS Python environment

Usage:
  python3 camofox_start.py

Platform-specific launch methods:
  a-Shell:    Open a-Shell, run: python3 camofox_start.py
  iSH:        Open iSH, run: python3 camofox_start.py
  Pyto:       Open camofox_start.py in Pyto, tap Run
  Pythonista: Open camofox_start.py, tap Play button
              Or use URL: pythonista3://camofox-ios/camofox_start.py?action=run
"""

import os
import sys

# ---------------------------------------------------------------------------
# Path setup — ensure we can find all modules regardless of cwd
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

for _p in (_PROJECT_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def main():
    """Start the CamoFox proxy with default settings."""
    # Show a quick banner immediately
    print("\033[36m"  # cyan
          "  _____                     _____          \n"
          " / ____|                   |  ___|         \n"
          "| |     __ _ _ __ ___   ___|  |_ _____  __ \n"
          "| |    / _` | '_ ` _ \\ / _ \\  _/ _ \\ \\/ / \n"
          "| |___| (_| | | | | | | (_) | || (_) >  <  \n"
          " \\_____\\__,_|_| |_| |_|\\___/|_| \\___/_/\\_\\ \n"
          "\033[0m")

    # Detect and display platform
    try:
        from platform_detect import PLATFORM, CAPABILITIES, get_platform_info, get_platform_tips
        print(get_platform_info())
        print()
    except ImportError:
        PLATFORM = 'generic'
        CAPABILITIES = {}
        print(f"Platform:     Generic Python")
        print(f"Python:       {sys.version.split()[0]}")
        print()

    print("Starting proxy...")
    print()

    try:
        import dns.asyncresolver  # noqa: F401
    except ImportError:
        print("\033[31mERROR: dnspython is required (dns.asyncresolver).\033[0m")
        print("Copy the repo dns/ folder next to lib/, or install dnspython:")
        print("  pip install dnspython")
        print(f"Looked in: {_PROJECT_ROOT}")
        sys.exit(1)

    try:
        from camofox_proxy import CamoFoxProxy, ProxyConfig
    except ImportError as e:
        print(f"\033[31mERROR: Could not import CamoFox proxy: {e}\033[0m")
        print(f"Make sure all files are in: {_THIS_DIR}")
        print(f"Project root should be: {_PROJECT_ROOT}")
        print()
        print("Required directories:")
        print(f"  camofox-ios/  (this folder)")
        print(f"  lib/          (proxy server library)")
        print(f"  dns/          (required — bundled dnspython, or: pip install dnspython)")
        sys.exit(1)

    # Default configuration — optimised for CamoFox + GL-iNet Opal
    config = ProxyConfig(
        # Ports match the router's redsocks configuration
        socks_port=9876,
        http_port=9877,
        wpad_port=8088,

        # Auto-restart is critical — recover fast from any hiccup
        auto_restart=True,
        max_restart_attempts=50,   # be very persistent
        restart_delay=1.0,         # restart quickly

        # Keepalive — prevent iOS from killing the app
        # Universal strategies (all platforms)
        enable_keepalive=True,
        keepalive_network=True,    # HTTP pings (all platforms)
        keepalive_file_io=True,    # File heartbeat (all platforms)

        # Pythonista-only strategies (graceful no-op on other platforms)
        keepalive_audio=True,      # silent audio trick
        keepalive_location=False,  # set True if proxy keeps getting killed
    )

    proxy = CamoFoxProxy(config)

    # Show platform-specific tips
    try:
        print(get_platform_tips())
        print()
    except NameError:
        pass

    try:
        proxy.run()
    except KeyboardInterrupt:
        print("\n\033[36m\U0001f98a CamoFox stopped.\033[0m")
    except Exception as e:
        print(f"\n\033[31m\U0001f98a CamoFox error: {e}\033[0m")
        # Keep console open so the user can see the error
        try:
            input("Press Enter to exit...")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    main()
