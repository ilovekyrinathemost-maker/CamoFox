#!python3
"""CamoFox Quick Start — One-tap proxy launcher for Pythonista.

This is the script you add to your Pythonista home screen or trigger
via an iOS Shortcut.  It starts the enhanced SOCKS5/HTTP proxy with
all keepalive strategies enabled.

To add to Pythonista home screen:
  1. Open this file in Pythonista
  2. Tap the wrench icon → Share → Add to Home Screen
  3. Name it "CamoFox" and pick an icon

To trigger via iOS Shortcuts:
  Use URL scheme:  pythonista3://camofox-ios/camofox_start.py?action=run
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
    # Show a quick banner immediately so the user knows it's starting
    print("🦊 CamoFox starting...")
    print()

    try:
        from camofox_proxy import CamoFoxProxy, ProxyConfig
    except ImportError as e:
        print(f"ERROR: Could not import CamoFox proxy: {e}")
        print(f"Make sure all files are in: {_THIS_DIR}")
        print(f"Project root should be: {_PROJECT_ROOT}")
        sys.exit(1)

    # Default configuration — optimised for CamoFox + GL-iNet Opal
    config = ProxyConfig(
        # Ports match the router's redsocks configuration
        socks_port=9876,
        http_port=9877,
        wpad_port=8088,

        # Auto-restart is critical — if Pythonista hiccups, recover fast
        auto_restart=True,
        max_restart_attempts=50,   # be very persistent
        restart_delay=1.0,         # restart quickly

        # Keepalive — prevent iOS from killing us
        enable_keepalive=True,
        keepalive_audio=True,      # silent audio trick
        keepalive_location=False,  # set True if audio alone isn't enough
    )

    proxy = CamoFoxProxy(config)

    try:
        proxy.run()
    except KeyboardInterrupt:
        print("\n🦊 CamoFox stopped.")
    except Exception as e:
        print(f"\n🦊 CamoFox error: {e}")
        # On Pythonista, keep the console open so the user can see the error
        if "Pythonista" in sys.executable:
            input("Press Enter to exit...")


if __name__ == "__main__":
    main()
