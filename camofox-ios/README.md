# 🦊 CamoFox iOS — SOCKS5 Proxy for Tethering Bypass

CamoFox iOS runs a SOCKS5/HTTP proxy on your iPhone using Pythonista 3,
enabling the GL-iNet Opal travel router to tunnel all connected device
traffic through the phone's native cellular connection — making it
indistinguishable from normal on-device usage.

---

## How It Works

```
[Laptop/Tablet]          [GL-iNet Opal]           [iPhone]
     │                        │                       │
     │── WiFi ──────────→ LAN │── WiFi ──→ SOCKS5 ──→ │── Cellular ──→ Internet
     │                        │   redsocks     :9876   │
     │                        │                        │
     │   No config needed     │   Transparent proxy    │   T-Mobile sees:
     │   Any OS works         │   TTL mangling         │   Normal iPhone traffic
     │                        │   DNS-over-HTTPS       │   TTL=64, iOS fingerprint
     │                        │   Kill switch          │   Primary data APN
```

### Why This Works

T-Mobile detects tethering primarily through the **APN** (Access Point
Name) that iPhone uses for hotspot traffic.  When Personal Hotspot is
active, iOS routes tethered data through a special "dun" APN that the
carrier monitors.

CamoFox bypasses this entirely:
- The SOCKS proxy runs directly on the iPhone
- It creates **new TCP connections** from the phone's own TCP/IP stack
- These connections use the phone's **primary data APN** (not hotspot)
- The carrier sees: TTL=64, iOS TCP fingerprint, normal traffic
- No hotspot indicator is triggered at the network level

---

## File Listing

| File | Description |
|------|------------|
| **`camofox_start.py`** | 🚀 One-tap launch script — add to Pythonista home screen |
| **`camofox_proxy.py`** | Core enhanced SOCKS5/HTTP proxy with auto-restart |
| **`camofox_status.py`** | Real-time status dashboard (connections, speeds, uptime) |
| **`keepalive.py`** | iOS suspension prevention (idle timer, audio, ping, GPS) |
| **`diagnostics.py`** | Network diagnostic tool — verify setup before use |
| **`CONFIG.md`** | Comprehensive setup and configuration guide |
| **`shortcuts/README.md`** | iOS Shortcuts integration guide |
| **`shortcuts/url_schemes.md`** | Pythonista URL scheme reference |

---

## Quick Start

### 1. Install Pythonista 3

Download [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097)
from the App Store ($9.99).

### 2. Copy Files

Copy these folders to Pythonista's document directory (via iCloud, USB,
or Working Copy):

```
camofox-ios/    ← this folder
lib/            ← proxy server library
dns/            ← DNS resolver library
```

See [CONFIG.md](CONFIG.md) for detailed installation instructions.

### 3. Run Diagnostics

Open `camofox-ios/diagnostics.py` in Pythonista and tap ▶️.  All checks
should pass.

### 4. Start the Proxy

Open `camofox-ios/camofox_start.py` and tap ▶️.  You'll see:

```
╔══════════════════════════════════════════════════╗
║           CamoFox SOCKS5/HTTP Proxy              ║
╚══════════════════════════════════════════════════╝
Proxy host: 172.20.10.1 (WiFi en0)
SOCKS5:     172.20.10.1:9876
HTTP Proxy: 172.20.10.1:9877
```

### 5. Connect the Router

The GL-iNet Opal connects to the iPhone's WiFi and routes all traffic
through the SOCKS proxy via `redsocks`.  See the `camofox-router`
package for router-side setup.

---

## Architecture

### Component Overview

```
camofox_start.py          Entry point — one-tap launcher
       │
       ▼
camofox_proxy.py          Core proxy orchestrator
       │
       ├──→ lib/proxy_server.py      Async TCP proxy base
       ├──→ lib/socks5_server.py     SOCKS5 protocol handler
       ├──→ lib/http_proxy_server.py HTTP CONNECT proxy
       ├──→ lib/status.py            Traffic stats & display
       ├──→ lib/ifaddrs.py           iOS network interface detection
       ├──→ dns/asyncresolver.py     DNS resolution
       │
       ├──→ keepalive.py             iOS suspension prevention
       │    ├── Idle timer disable
       │    ├── Silent audio loop
       │    ├── Self-ping loopback
       │    └── Location services (opt)
       │
       └──→ WPAD server              Auto-configuration for clients
```

### Network Flow

```
Client Device (any OS)
    │
    │ TCP connection (any port)
    ▼
GL-iNet Opal Router
    │
    │ iptables REDIRECT → redsocks (port 12345)
    │ redsocks wraps in SOCKS5 → iPhone:9876
    ▼
iPhone SOCKS5 Proxy (CamoFox)
    │
    │ Creates NEW TCP connection
    │ Source: iPhone cellular interface (pdp_ip0)
    │ Uses primary data APN
    ▼
T-Mobile Network
    │
    │ Sees: Normal iPhone traffic
    │ TTL=64, iOS TCP fingerprint
    │ No hotspot indicator
    ▼
Internet
```

---

## Features

### Enhanced Proxy (`camofox_proxy.py`)
- 🔍 **Auto-detect interfaces** — finds WiFi/cellular/VPN automatically
- 🔄 **Auto-restart** — recovers from crashes with exponential backoff
- 📊 **Live statistics** — throughput, connections, uptime, errors
- ⚙️ **Configurable** — ports, timeouts, DNS, all via dataclass config
- 🌐 **WPAD server** — auto-proxy configuration for clients
- 🔌 **Dual protocol** — SOCKS5 (port 9876) + HTTP proxy (port 9877)
- 📡 **IPv4 + IPv6** — happy eyeballs for optimal connectivity
- 🔐 **Custom DNS** — configurable resolvers, dnspython integration

### Keepalive System (`keepalive.py`)
- 🖥️ **Idle timer disable** — prevents screen dimming/lock
- 🔇 **Silent audio** — keeps audio session active
- 🏓 **Self-ping** — periodic loopback activity
- 📍 **Location services** — optional GPS-based keepalive
- 🔌 **Pluggable** — enable/disable strategies independently

### Status Dashboard (`camofox_status.py`)
- 📈 Real-time speed display (Mbps up/down)
- 🔢 Active connection count
- ⏱️ Uptime counter
- 📊 Total data transferred
- 🚦 Connection quality indicator
- 📝 Recent log messages

### Diagnostics (`diagnostics.py`)
- ✅ 13-point check suite
- 📋 Formatted report output
- 🔧 JSON output for scripting
- 🌐 Tests WiFi, cellular, DNS, ports, proxy, internet

---

## Limitations & Known Issues

### iOS Constraints
- **Pythonista must stay in foreground** — iOS aggressively suspends
  background apps.  Keepalive strategies help but don't guarantee
  indefinite runtime.
- **No UDP forwarding** — SOCKS5 is TCP-only.  UDP traffic (gaming,
  VoIP) won't work through the proxy.  DNS is handled via DoH on
  the router.
- **Network changes kill connections** — if WiFi reconnects or the
  phone switches between WiFi and cellular, active connections drop.
  The auto-restart feature handles this.
- **Single-threaded GIL** — Python's GIL limits true parallelism.
  In practice this is fine — cellular bandwidth is the bottleneck,
  not CPU.

### Security Notes
- The proxy does **not** encrypt traffic between router and iPhone.
  This is fine because they're on a local WiFi network.
- Traffic between iPhone and the internet uses standard TLS/HTTPS
  as initiated by the client application.
- The proxy is open (no authentication).  Only devices on the local
  WiFi network can reach it.

### Performance
- Expect **80-90%** of raw cellular speed through the proxy
- Latency adds **1-5ms** per connection (proxy hop)
- Works well for web browsing, streaming, downloads
- Not ideal for competitive gaming (UDP + latency sensitive)

---

## Dependencies

### Required (bundled in project)
- `lib/` — Proxy server implementations (from iOS-SOCKS-Server)
- `lib/ifaddrs.py` — iOS network interface detection via ctypes

### Required (Pythonista built-in)
- `asyncio` — Async I/O for proxy connections
- `socket` — Low-level networking
- `threading` — WPAD server and keepalive threads
- `console` — Pythonista screen control
- `objc_util` — iOS Objective-C bridge

### Optional
- `dns/` (dnspython) — Enhanced DNS resolution
- `sound` — Silent audio keepalive
- `location` — GPS-based keepalive

---

## Companion: camofox-router

The router-side component (`camofox-router/`) installs and configures:
- `redsocks` — Transparent SOCKS5 redirect
- `iptables` — Traffic interception and TTL mangling
- `https-dns-proxy` — DNS-over-HTTPS
- Health monitoring and kill switch
- Auto-reconnect on proxy failover

See `camofox-router/README.md` for setup.

---

## Credits

Built on top of [iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server)
by @nneonneo, with IPv6 support by @philrosenthal.

Tethering bypass techniques researched from:
- [iOS-SOCKS-Server Issue #1](https://github.com/nneonneo/iOS-SOCKS-Server/issues/1)
- GL-iNet community forums
- GrapheneOS community
- Reddit r/tmobile, r/GlInet, r/NoContract

---

## License

Same license as the upstream iOS-SOCKS-Server project.
