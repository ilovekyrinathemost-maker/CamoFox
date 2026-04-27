#!python3
"""CamoFox Keepalive Helper — Prevent iOS from suspending Pythonista.

This module provides multiple strategies to keep Pythonista alive in the
foreground on iOS.  Each approach has trade-offs; the KeepaliveManager
class automatically selects the best available method.

Strategies (in order of effectiveness):
  1. Idle-timer disable  — Prevents screen dimming / auto-lock.
  2. Silent audio loop    — Plays inaudible audio to signal "active media".
  3. Periodic self-ping   — Lightweight network activity on loopback.
  4. Location services    — Requests GPS updates (high battery cost).

Limitations:
  • None of these prevent iOS from killing Pythonista when the user
    explicitly swipes it away in the app switcher.
  • If iOS is under extreme memory pressure it *will* terminate
    background apps regardless.
  • Silent audio only works when the device is not in Silent Mode on
    some iOS versions.
  • Location services requires user permission on first run.

Usage:
    from keepalive import KeepaliveManager
    km = KeepaliveManager()
    km.start()   # call once at proxy startup
    ...
    km.stop()    # call on clean shutdown
"""

import threading
import time
import logging

logger = logging.getLogger("camofox.keepalive")

# ---------------------------------------------------------------------------
# Feature detection — import Pythonista-only modules safely
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
# Strategy 1: Disable idle timer (screen-off prevention)
# ---------------------------------------------------------------------------
def disable_idle_timer() -> bool:
    """Prevent iOS from dimming / locking the screen.

    Uses ``console.set_idle_timer_disabled(True)`` dispatched on the
    main thread via ``objc_util.on_main_thread``.

    Returns True if successfully applied.
    """
    if _HAS_CONSOLE and _HAS_OBJC:
        try:
            on_main_thread(console.set_idle_timer_disabled)(True)
            logger.info("Idle timer disabled — screen will stay on")
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
# Strategy 2: Silent audio loop
# ---------------------------------------------------------------------------
class SilentAudioLoop:
    """Play a short silent WAV in a loop to keep the audio session active.

    iOS treats apps with an active audio session as higher priority and is
    less likely to suspend them.  We generate a 1-second silent WAV in
    memory and replay it every few seconds.

    NOTE: This works best when the device is *not* in Silent Mode.
    """

    def __init__(self, interval: float = 10.0):
        self._interval = interval
        self._thread: threading.Thread | None = None
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
        logger.info("Silent audio keepalive started (interval=%ss)", self._interval)
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        """Background loop that plays a near-silent beep."""
        while not self._stop_event.is_set():
            try:
                # Pythonista's sound module can play built-in effects.
                # 'ui:click1' is a very short, quiet system sound.
                # We set volume to minimum to be effectively inaudible.
                sound.play_effect("ui:click1", volume=0.01)
            except Exception:
                pass
            self._stop_event.wait(self._interval)


# ---------------------------------------------------------------------------
# Strategy 3: Periodic self-ping (loopback TCP)
# ---------------------------------------------------------------------------
class SelfPingLoop:
    """Periodically connect to localhost to create network activity.

    This is the most lightweight strategy and works on all platforms.
    It generates minimal CPU / battery load.
    """

    def __init__(self, interval: float = 30.0):
        self._interval = interval
        self._thread: threading.Thread | None = None
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

    def _loop(self) -> None:
        import socket
        while not self._stop_event.is_set():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                # Connect to a likely-open port (our own proxy) or just
                # attempt a connection that will be refused — either way
                # it counts as network activity.
                try:
                    sock.connect(("127.0.0.1", 9876))
                except (ConnectionRefusedError, OSError):
                    pass
                finally:
                    sock.close()
            except Exception:
                pass
            self._stop_event.wait(self._interval)


# ---------------------------------------------------------------------------
# Strategy 4: Location services keepalive
# ---------------------------------------------------------------------------
class LocationKeepalive:
    """Request low-accuracy location updates to keep the app alive.

    iOS grants apps that are actively using location services additional
    background execution time.  We request "significant change" updates
    which use minimal battery.

    WARNING: This requires the user to grant location permission when
    prompted.  It also shows the location indicator in the status bar.
    Use only as a last resort.
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
            logger.info("Location keepalive started (shows location icon)")
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


# ---------------------------------------------------------------------------
# Combined KeepaliveManager
# ---------------------------------------------------------------------------
class KeepaliveManager:
    """Orchestrate multiple keepalive strategies.

    By default enables:
      - Idle timer disable (always)
      - Self-ping (always)
      - Silent audio (if available, optional)
      - Location (disabled by default — high battery cost)

    Args:
        use_audio: Enable silent audio loop.  Default True.
        use_location: Enable location keepalive.  Default False.
        ping_interval: Seconds between self-pings.  Default 30.
        audio_interval: Seconds between audio pings.  Default 10.
    """

    def __init__(
        self,
        use_audio: bool = True,
        use_location: bool = False,
        ping_interval: float = 30.0,
        audio_interval: float = 10.0,
    ):
        self._idle_disabled = False
        self._audio = SilentAudioLoop(interval=audio_interval) if use_audio else None
        self._ping = SelfPingLoop(interval=ping_interval)
        self._location = LocationKeepalive() if use_location else None
        self._started = False

    def start(self) -> dict:
        """Start all configured keepalive strategies.

        Returns a dict of strategy names → whether they were activated.
        """
        if self._started:
            return {"already_running": True}

        results = {}

        # Always try to disable idle timer
        self._idle_disabled = disable_idle_timer()
        results["idle_timer_disabled"] = self._idle_disabled

        # Always start self-ping
        results["self_ping"] = self._ping.start()

        # Optional: silent audio
        if self._audio and self._audio.available:
            results["silent_audio"] = self._audio.start()
        else:
            results["silent_audio"] = False

        # Optional: location
        if self._location and self._location.available:
            results["location"] = self._location.start()
        else:
            results["location"] = False

        self._started = True
        active = [k for k, v in results.items() if v]
        logger.info("Keepalive active strategies: %s", ", ".join(active) or "none")
        return results

    def stop(self) -> None:
        """Stop all keepalive strategies and restore idle timer."""
        if not self._started:
            return

        self._ping.stop()
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
            "idle_timer_disabled": self._idle_disabled,
            "self_ping": self._ping._thread is not None
            and self._ping._thread.is_alive()
            if self._ping._thread
            else False,
            "silent_audio": (
                self._audio._thread is not None and self._audio._thread.is_alive()
                if self._audio and self._audio._thread
                else False
            ),
            "location": (
                self._location._active if self._location else False
            ),
        }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    print("CamoFox Keepalive — Feature Detection")
    print(f"  Console module:  {'YES' if _HAS_CONSOLE else 'NO'}")
    print(f"  ObjC utilities:  {'YES' if _HAS_OBJC else 'NO'}")
    print(f"  Sound module:    {'YES' if _HAS_SOUND else 'NO'}")
    print(f"  Location module: {'YES' if _HAS_LOCATION else 'NO'}")
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
