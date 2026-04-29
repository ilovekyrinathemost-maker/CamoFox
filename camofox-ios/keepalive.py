#!python3
"""CamoFox Keepalive Helper — Prevent iOS from suspending the proxy app.

Cross-platform keepalive strategies that work across all supported iOS
Python environments:

  • a-Shell (FREE)    — Network activity + file I/O keepalive
  • iSH (FREE)        — Network activity (iSH has great persistence)
  • Pyto (FREE)       — Network activity + file I/O keepalive
  • Pythonista ($9.99) — All strategies including audio + idle timer

Strategies (in order of universality):
  1. Periodic self-ping   — Loopback TCP activity (ALL platforms)
  2. Network activity     — Small HTTP requests (ALL platforms)
  3. File I/O activity    — Periodic disk writes (ALL platforms)
  4. Idle-timer disable   — Prevents screen lock (Pythonista only)
  5. Silent audio loop    — Keeps audio session active (Pythonista only)
  6. Location services    — GPS updates keepalive (Pythonista only)

Limitations:
  • None of these prevent iOS from killing the app when the user
    explicitly swipes it away in the app switcher.
  • If iOS is under extreme memory pressure it *will* terminate
    background apps regardless.
  • iSH with Location Services enabled has the best background
    persistence of all iOS Python environments.

Usage:
    from keepalive import KeepaliveManager
    km = KeepaliveManager()
    km.start()   # call once at proxy startup
    ...
    km.stop()    # call on clean shutdown
"""

from __future__ import annotations

import logging
import os
import socket
import tempfile
import threading
import time

logger = logging.getLogger("camofox.keepalive")

# ---------------------------------------------------------------------------
# Platform detection — import capabilities
# ---------------------------------------------------------------------------
try:
    from platform_detect import PLATFORM, CAPABILITIES
except ImportError:
    try:
        from camofox_ios.platform_detect import PLATFORM, CAPABILITIES  # type: ignore
    except ImportError:
        PLATFORM = 'generic'
        CAPABILITIES = {
            'objc_bridge': False, 'gui': False, 'terminal': True,
            'background_audio': False, 'location': False, 'pip': False,
            'ansi_colors': True, 'url_scheme': None,
            'background_persist': 'good',
        }

# ---------------------------------------------------------------------------
# Feature detection — import platform-specific modules safely
# ---------------------------------------------------------------------------
_HAS_CONSOLE = False
_HAS_OBJC = False
_HAS_SOUND = False
_HAS_LOCATION = False

try:
    import console  # type: ignore
    _HAS_CONSOLE = True
except ImportError:
    pass

try:
    from objc_util import ObjCClass, on_main_thread, ns  # type: ignore
    _HAS_OBJC = True
except ImportError:
    pass

try:
    import sound  # type: ignore
    _HAS_SOUND = True
except ImportError:
    pass

try:
    import location  # type: ignore
    _HAS_LOCATION = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Strategy 1: Periodic self-ping (loopback TCP) — ALL PLATFORMS
# ---------------------------------------------------------------------------
class SelfPingLoop:
    """Periodically connect to localhost to create network activity.

    This is the most lightweight strategy and works on ALL platforms.
    It generates minimal CPU / battery load.  Connects to the proxy's
    own SOCKS port (or gets a connection-refused — either counts as
    network activity for iOS).
    """

    def __init__(self, interval: float = 30.0, target_port: int = 9876):
        self._interval = interval
        self._target_port = target_port
        self._thread = None  # type: threading.Thread | None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="keepalive-ping", daemon=True
        )
        self._thread.start()
        logger.info("Self-ping keepalive started (interval=%ss)", self._interval)
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                try:
                    sock.connect(("127.0.0.1", self._target_port))
                except (ConnectionRefusedError, OSError):
                    pass
                finally:
                    sock.close()
            except Exception:
                pass
            self._stop_event.wait(self._interval)


# ---------------------------------------------------------------------------
# Strategy 2: Network activity (HTTP requests) — ALL PLATFORMS
# ---------------------------------------------------------------------------
class NetworkActivityLoop:
    """Periodic small HTTP requests to generate network activity.

    Works on ALL platforms.  Makes tiny HEAD requests to well-known
    endpoints.  iOS considers apps with active network connections
    as higher priority.  Uses only standard library (no requests needed).
    """

    def __init__(self, interval: float = 45.0):
        self._interval = interval
        self._thread = None  # type: threading.Thread | None
        self._stop_event = threading.Event()
        # Lightweight endpoints that return fast HEAD responses
        self._endpoints = [
            ("1.1.1.1", 80),
            ("8.8.8.8", 53),
            ("1.0.0.1", 80),
        ]
        self._endpoint_idx = 0

    def start(self) -> bool:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="keepalive-net", daemon=True
        )
        self._thread.start()
        logger.info("Network activity keepalive started (interval=%ss)", self._interval)
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                host, port = self._endpoints[self._endpoint_idx % len(self._endpoints)]
                self._endpoint_idx += 1
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                try:
                    sock.connect((host, port))
                    # Send a tiny HTTP HEAD request if port 80
                    if port == 80:
                        sock.sendall(b"HEAD / HTTP/1.0\r\nHost: detect\r\n\r\n")
                        sock.recv(64)  # Read a bit of response
                except (ConnectionRefusedError, OSError, socket.timeout):
                    pass
                finally:
                    try:
                        sock.close()
                    except Exception:
                        pass
            except Exception:
                pass
            self._stop_event.wait(self._interval)


# ---------------------------------------------------------------------------
# Strategy 3: File I/O activity — ALL PLATFORMS
# ---------------------------------------------------------------------------
class FileActivityLoop:
    """Periodic file writes to maintain app activity.

    Works on ALL platforms.  iOS monitors app activity; periodic
    file system access helps signal that the app is still active.
    Also serves as a heartbeat file that external tools can monitor.
    """

    def __init__(self, interval: float = 60.0, heartbeat_path: str = ""):
        self._interval = interval
        self._thread = None  # type: threading.Thread | None
        self._stop_event = threading.Event()
        # Default heartbeat file in the same directory as this script
        if heartbeat_path:
            self._heartbeat_path = heartbeat_path
        else:
            this_dir = os.path.dirname(os.path.abspath(__file__))
            self._heartbeat_path = os.path.join(this_dir, ".camofox_heartbeat")

    def start(self) -> bool:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="keepalive-file", daemon=True
        )
        self._thread.start()
        logger.info("File activity keepalive started (interval=%ss)", self._interval)
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        # Clean up heartbeat file
        try:
            if os.path.exists(self._heartbeat_path):
                os.remove(self._heartbeat_path)
        except Exception:
            pass

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                # Write a heartbeat file with timestamp
                with open(self._heartbeat_path, 'w') as f:
                    f.write(f"camofox-alive:{time.time():.0f}\n")
            except Exception:
                pass
            self._stop_event.wait(self._interval)


# ---------------------------------------------------------------------------
# Strategy 4: Disable idle timer (Pythonista ONLY)
# ---------------------------------------------------------------------------
def disable_idle_timer() -> bool:
    """Prevent iOS from dimming / locking the screen.

    Uses ``console.set_idle_timer_disabled(True)`` dispatched on the
    main thread via ``objc_util.on_main_thread``.

    Returns True if successfully applied.  Only works in Pythonista.
    """
    if _HAS_CONSOLE and _HAS_OBJC:
        try:
            on_main_thread(console.set_idle_timer_disabled)(True)
            logger.info("Idle timer disabled — screen will stay on (Pythonista)")
            return True
        except Exception as exc:
            logger.warning("Failed to disable idle timer: %s", exc)
    return False


def enable_idle_timer() -> None:
    """Re-enable idle timer on shutdown."""
    if _HAS_CONSOLE and _HAS_OBJC:
        try:
            on_main_thread(console.set_idle_timer_disabled)(False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Strategy 5: Silent audio loop (Pythonista ONLY)
# ---------------------------------------------------------------------------
class SilentAudioLoop:
    """Play a short silent WAV in a loop to keep the audio session active.

    iOS treats apps with an active audio session as higher priority and is
    less likely to suspend them.  Only works in Pythonista which provides
    the ``sound`` module.

    NOTE: This works best when the device is *not* in Silent Mode.
    """

    def __init__(self, interval: float = 10.0):
        self._interval = interval
        self._thread = None  # type: threading.Thread | None
        self._stop_event = threading.Event()
        self._available = _HAS_SOUND

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        if not self._available:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="keepalive-audio", daemon=True
        )
        self._thread.start()
        logger.info("Silent audio keepalive started (interval=%ss, Pythonista)", self._interval)
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        """Background loop that plays a near-silent beep."""
        while not self._stop_event.is_set():
            try:
                sound.play_effect("ui:click1", volume=0.01)
            except Exception:
                pass
            self._stop_event.wait(self._interval)


# ---------------------------------------------------------------------------
# Strategy 6: Location services keepalive (Pythonista ONLY)
# ---------------------------------------------------------------------------
class LocationKeepalive:
    """Request low-accuracy location updates to keep the app alive.

    iOS grants apps that are actively using location services additional
    background execution time.  Only works in Pythonista.

    For iSH: Enable Location Services in iOS Settings → iSH → Location
    instead — iSH handles this natively without Python code.

    WARNING: Shows the location indicator in the status bar.
    """

    def __init__(self):
        self._active = False
        self._available = _HAS_LOCATION

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        if not self._available:
            return False
        try:
            location.start_updates()
            self._active = True
            logger.info("Location keepalive started (Pythonista, shows location icon)")
            return True
        except Exception as exc:
            logger.warning("Failed to start location keepalive: %s", exc)
            return False

    def stop(self) -> None:
        if self._active:
            try:
                location.stop_updates()
            except Exception:
                pass
            self._active = False

    @property
    def is_alive(self) -> bool:
        return self._active


# ---------------------------------------------------------------------------
# Combined KeepaliveManager — Auto-selects strategies per platform
# ---------------------------------------------------------------------------
class KeepaliveManager:
    """Orchestrate multiple keepalive strategies based on detected platform.

    Automatically selects the best strategies for the current environment:

    ALL PLATFORMS (always enabled):
      - Self-ping (loopback TCP to proxy port)
      - Network activity (small HTTP connections)
      - File I/O activity (heartbeat file)

    PYTHONISTA ONLY (optional enhancements):
      - Idle timer disable (prevents screen lock)
      - Silent audio loop (keeps audio session)
      - Location services (GPS keepalive — high battery)

    Args:
        use_audio: Enable silent audio (Pythonista only). Default True.
        use_location: Enable GPS keepalive (Pythonista only). Default False.
        use_network: Enable network activity keepalive. Default True.
        use_file_io: Enable file I/O keepalive. Default True.
        ping_interval: Seconds between self-pings. Default 30.
        audio_interval: Seconds between audio pings. Default 10.
        network_interval: Seconds between HTTP pings. Default 45.
        file_interval: Seconds between file writes. Default 60.
        target_port: Port to self-ping (proxy port). Default 9876.
    """

    def __init__(
        self,
        use_audio: bool = True,
        use_location: bool = False,
        use_network: bool = True,
        use_file_io: bool = True,
        ping_interval: float = 30.0,
        audio_interval: float = 10.0,
        network_interval: float = 45.0,
        file_interval: float = 60.0,
        target_port: int = 9876,
    ):
        self._idle_disabled = False
        self._started = False

        # Universal strategies (all platforms)
        self._ping = SelfPingLoop(interval=ping_interval, target_port=target_port)
        self._network = NetworkActivityLoop(interval=network_interval) if use_network else None
        self._file_io = FileActivityLoop(interval=file_interval) if use_file_io else None

        # Pythonista-only strategies (gracefully no-op on other platforms)
        self._audio = SilentAudioLoop(interval=audio_interval) if use_audio else None
        self._location = LocationKeepalive() if use_location else None

    def start(self) -> dict:
        """Start all configured keepalive strategies.

        Returns a dict of strategy names → whether they were activated.
        """
        if self._started:
            return {"already_running": True}

        results = {}

        # --- Universal strategies (all platforms) ---

        # Always start self-ping
        results["self_ping"] = self._ping.start()

        # Network activity keepalive
        if self._network:
            results["network_activity"] = self._network.start()
        else:
            results["network_activity"] = False

        # File I/O keepalive
        if self._file_io:
            results["file_activity"] = self._file_io.start()
        else:
            results["file_activity"] = False

        # --- Pythonista-only strategies ---

        # Disable idle timer (Pythonista only — silent no-op elsewhere)
        self._idle_disabled = disable_idle_timer()
        results["idle_timer_disabled"] = self._idle_disabled

        # Silent audio (Pythonista only)
        if self._audio and self._audio.available:
            results["silent_audio"] = self._audio.start()
        else:
            results["silent_audio"] = False

        # Location (Pythonista only)
        if self._location and self._location.available:
            results["location"] = self._location.start()
        else:
            results["location"] = False

        self._started = True
        active = [k for k, v in results.items() if v]
        logger.info(
            "Keepalive active on %s: %s",
            PLATFORM,
            ", ".join(active) or "none",
        )
        return results

    def stop(self) -> None:
        """Stop all keepalive strategies and restore idle timer."""
        if not self._started:
            return

        self._ping.stop()
        if self._network:
            self._network.stop()
        if self._file_io:
            self._file_io.stop()
        if self._audio:
            self._audio.stop()
        if self._location:
            self._location.stop()
        if self._idle_disabled:
            enable_idle_timer()

        self._started = False
        logger.info("All keepalive strategies stopped")

    @property
    def is_running(self) -> bool:
        return self._started

    def status(self) -> dict:
        """Return current status of each strategy."""
        return {
            "running": self._started,
            "platform": PLATFORM,
            # Universal
            "self_ping": self._ping.is_alive,
            "network_activity": self._network.is_alive if self._network else False,
            "file_activity": self._file_io.is_alive if self._file_io else False,
            # Pythonista-only
            "idle_timer_disabled": self._idle_disabled,
            "silent_audio": self._audio.is_alive if self._audio else False,
            "location": self._location.is_alive if self._location else False,
        }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    print("🦊 CamoFox Keepalive — Feature Detection")
    print(f"  Platform:        {PLATFORM}")
    print(f"  Console module:  {'YES' if _HAS_CONSOLE else 'NO'}")
    print(f"  ObjC utilities:  {'YES' if _HAS_OBJC else 'NO'}")
    print(f"  Sound module:    {'YES' if _HAS_SOUND else 'NO'}")
    print(f"  Location module: {'YES' if _HAS_LOCATION else 'NO'}")
    print()

    # Show which strategies will be active
    print("  Strategies available:")
    print(f"    Self-ping:         YES (all platforms)")
    print(f"    Network activity:  YES (all platforms)")
    print(f"    File I/O activity: YES (all platforms)")
    print(f"    Idle timer:        {'YES' if _HAS_CONSOLE and _HAS_OBJC else 'NO (Pythonista only)'}")
    print(f"    Silent audio:      {'YES' if _HAS_SOUND else 'NO (Pythonista only)'}")
    print(f"    Location:          {'YES' if _HAS_LOCATION else 'NO (Pythonista only)'}")
    print()

    km = KeepaliveManager(use_audio=True, use_location=False)
    results = km.start()
    print("Keepalive started:")
    for k, v in results.items():
        print(f"  {k}: {'ACTIVE' if v else 'unavailable'}")
    print()
    print("Status:", km.status())
    print("\nPress Ctrl+C to stop...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        km.stop()
        print("Stopped.")
