#!python3
"""CamoFox Platform Detection — Identify the iOS Python environment.

Supported platforms (in recommended order):
  1. a-Shell   (FREE) — Best free option, full Python 3 + pip
  2. iSH       (FREE) — Alpine Linux emulation, full pip
  3. Pyto      (FREE) — Python 3 with some iOS integration
  4. Pythonista ($9.99) — Full iOS integration, premium features
  5. generic   — Any standard Python 3 environment

Usage::

    from platform_detect import PLATFORM, CAPABILITIES, get_platform_info

    if CAPABILITIES['background_audio']:
        # Use silent audio keepalive
        ...

    print(get_platform_info())  # Human-readable summary
"""

from __future__ import annotations

import os
import sys
import platform as _platform


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform() -> str:
    """Detect which iOS Python environment we're running in.

    Returns one of: 'pythonista', 'ashell', 'ish', 'pyto', 'generic'
    """
    # 1. Pythonista — check executable name
    if 'Pythonista' in getattr(sys, 'executable', ''):
        return 'pythonista'

    # 2. Pythonista — check for unique module
    try:
        import console  # type: ignore
        import objc_util  # type: ignore
        return 'pythonista'
    except ImportError:
        pass

    # 3. a-Shell — check environment and paths
    term_program = os.environ.get('TERM_PROGRAM', '')
    if 'a-Shell' in term_program or 'a-shell' in term_program.lower():
        return 'ashell'
    # a-Shell sets specific env vars and has ios_system
    if os.environ.get('APPDIR', '').endswith('.app'):
        try:
            # a-Shell provides ios_system module
            import ios_system  # type: ignore
            return 'ashell'
        except ImportError:
            pass
    # a-Shell typically has ~/Documents as home and specific paths
    if os.path.exists('/usr/local/bin') and 'iSH' not in os.environ.get('container', ''):
        ashell_indicators = [
            os.environ.get('HOME', '').endswith('/Documents'),
            'a-Shell' in os.environ.get('TERM_PROGRAM', ''),
            os.path.exists(os.path.expanduser('~/Library/lib')),
        ]
        if sum(ashell_indicators) >= 2:
            return 'ashell'

    # 4. iSH — runs Alpine Linux with x86 emulation
    if os.path.exists('/etc/alpine-release'):
        return 'ish'
    if 'iSH' in os.environ.get('container', ''):
        return 'ish'
    # iSH uname returns "Linux" with specific patterns
    try:
        uname = _platform.uname()
        if uname.system == 'Linux' and 'ish' in uname.release.lower():
            return 'ish'
    except Exception:
        pass

    # 5. Pyto — check for pyto module
    try:
        import pyto  # type: ignore
        return 'pyto'
    except ImportError:
        pass
    # Pyto sets PYTO environment variable
    if os.environ.get('PYTO', ''):
        return 'pyto'
    if 'Pyto' in getattr(sys, 'executable', ''):
        return 'pyto'

    # 6. Generic Python
    return 'generic'


def get_capabilities(platform_name: str | None = None) -> dict:
    """Return a dict of available capabilities for the current platform.

    Keys:
        objc_bridge (bool)    — Can call Objective-C APIs
        gui (bool)            — Has native GUI toolkit
        terminal (bool)       — Has terminal/console output
        background_audio (bool) — Can play silent audio for keepalive
        location (bool)       — Can access GPS location
        pip (bool)            — Can install packages via pip
        ansi_colors (bool)    — Terminal supports ANSI escape codes
        url_scheme (str|None) — URL scheme for launching scripts
        background_persist (str) — How well app persists in background:
                                   'poor', 'fair', 'good'
    """
    plat = platform_name or PLATFORM

    # Start with feature detection (try importing)
    caps = {
        'objc_bridge': False,
        'gui': False,
        'terminal': True,
        'background_audio': False,
        'location': False,
        'pip': False,
        'ansi_colors': True,  # Most terminals support ANSI
        'url_scheme': None,
        'background_persist': 'poor',
    }

    if plat == 'pythonista':
        caps.update({
            'gui': True,
            'terminal': True,
            'pip': False,  # StaSh only, not real pip
            'url_scheme': 'pythonista3://',
            'background_persist': 'poor',  # iOS kills it aggressively
        })
        # Probe actual module availability
        try:
            import objc_util  # type: ignore
            caps['objc_bridge'] = True
        except ImportError:
            pass
        try:
            import sound  # type: ignore
            caps['background_audio'] = True
        except ImportError:
            pass
        try:
            import location  # type: ignore
            caps['location'] = True
        except ImportError:
            pass

    elif plat == 'ashell':
        caps.update({
            'gui': False,
            'terminal': True,
            'pip': True,
            'ansi_colors': True,
            'url_scheme': 'ashell://',
            'background_persist': 'fair',  # Better than Pythonista
        })

    elif plat == 'ish':
        caps.update({
            'gui': False,
            'terminal': True,
            'pip': True,
            'ansi_colors': True,
            'url_scheme': None,  # iSH has no URL scheme
            'background_persist': 'good',  # Best background persistence
        })

    elif plat == 'pyto':
        caps.update({
            'gui': True,  # Pyto has some UI support
            'terminal': True,
            'pip': True,
            'ansi_colors': True,
            'url_scheme': 'pyto://',
            'background_persist': 'fair',
        })
        # Pyto has its own iOS integration
        try:
            import pyto  # type: ignore
            # Pyto provides some background capabilities
        except ImportError:
            pass

    else:  # generic
        caps.update({
            'gui': False,
            'terminal': True,
            'pip': True,
            'ansi_colors': True,
            'url_scheme': None,
            'background_persist': 'good',  # Desktop/server = always runs
        })

    return caps


def get_platform_info() -> str:
    """Return a human-readable platform information string."""
    plat = PLATFORM
    caps = CAPABILITIES

    names = {
        'pythonista': 'Pythonista 3 ($9.99)',
        'ashell': 'a-Shell (FREE)',
        'ish': 'iSH (FREE)',
        'pyto': 'Pyto (FREE)',
        'generic': 'Generic Python',
    }

    lines = [
        f"Platform:     {names.get(plat, plat)}",
        f"Python:       {sys.version.split()[0]}",
        f"Executable:   {sys.executable}",
    ]

    features = []
    if caps['objc_bridge']:
        features.append('ObjC bridge')
    if caps['background_audio']:
        features.append('Audio keepalive')
    if caps['location']:
        features.append('GPS keepalive')
    if caps['gui']:
        features.append('Native GUI')
    if caps['pip']:
        features.append('pip install')
    if caps['ansi_colors']:
        features.append('ANSI colors')
    if caps['url_scheme']:
        features.append(f"URL: {caps['url_scheme']}")

    lines.append(f"Features:     {', '.join(features) if features else 'basic'}")
    lines.append(f"Background:   {caps['background_persist']}")

    return '\n'.join(lines)


def get_platform_tips() -> str:
    """Return platform-specific tips for keeping the proxy alive."""
    plat = PLATFORM

    tips = {
        'pythonista': (
            "Pythonista Tips:\n"
            "  • Keep Pythonista in the foreground\n"
            "  • Enable Guided Access (Settings → Accessibility)\n"
            "  • Keep device charging to reduce iOS suspension\n"
            "  • Silent audio keepalive is active (helps prevent suspension)\n"
            "  • Consider enabling location keepalive for long sessions"
        ),
        'ashell': (
            "a-Shell Tips:\n"
            "  • a-Shell has decent background persistence\n"
            "  • Keep the app in foreground for best results\n"
            "  • Use 'wasm' command for additional background tasks\n"
            "  • Keep device charging for extended sessions\n"
            "  • Tap the screen occasionally to prevent suspension"
        ),
        'ish': (
            "iSH Tips:\n"
            "  • iSH has the BEST background persistence of all iOS apps\n"
            "  • Enable Location Services for iSH (Settings → iSH → Location)\n"
            "    This keeps iSH alive indefinitely in background\n"
            "  • The x86 emulation adds ~1-2ms latency (negligible)\n"
            "  • Install screen/tmux for session management: apk add tmux"
        ),
        'pyto': (
            "Pyto Tips:\n"
            "  • Keep Pyto in the foreground\n"
            "  • Pyto has some background execution support\n"
            "  • Keep device charging for extended sessions\n"
            "  • Use Pyto's built-in terminal for monitoring"
        ),
        'generic': (
            "Generic Python Tips:\n"
            "  • Running on a non-iOS platform — no special keepalive needed\n"
            "  • Use screen/tmux for session persistence\n"
            "  • Consider running as a systemd service for production"
        ),
    }

    return tips.get(plat, tips['generic'])


# ---------------------------------------------------------------------------
# Module-level constants — detected once at import time
# ---------------------------------------------------------------------------
PLATFORM: str = detect_platform()
CAPABILITIES: dict = get_capabilities(PLATFORM)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print('🦊 CamoFox Platform Detection')
    print('=' * 40)
    print(get_platform_info())
    print()
    print(get_platform_tips())
    print()
    print('Raw capabilities:')
    for k, v in CAPABILITIES.items():
        print(f'  {k}: {v}')
