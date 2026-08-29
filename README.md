# 🦊 CamoFox — Hide iPhone Tethering from T-Mobile

[![CI](https://github.com/ilovekyrinathemost-maker/CamoFox/actions/workflows/ci.yml/badge.svg)](https://github.com/ilovekyrinathemost-maker/CamoFox/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


> **Tunnel your internet through your iPhone without T-Mobile ever knowing.**

CamoFox is a two-part system that makes your iPhone's cellular data available to all your devices through a GL-iNet Opal travel router — while making all traffic appear as normal on-device phone usage.

---

## 🧠 How It Works

Instead of using iPhone's **Personal Hotspot** (which T-Mobile detects via a special tethering APN), CamoFox runs a **SOCKS5 proxy directly on the iPhone** using [Pythonista](https://apps.apple.com/us/app/pythonista-3/id1085978097). The GL-iNet Opal router connects to the iPhone's WiFi and transparently routes all connected devices' traffic through this proxy.

**Why this works:** Every packet originates from the iPhone's own TCP/IP stack on its primary data APN. T-Mobile literally cannot tell the difference between your laptop's traffic and the phone's own traffic.

### Architecture

```
┌─────────────┐     WiFi      ┌──────────────┐    WiFi/USB    ┌──────────────┐
│   Laptop    │ ◄──────────► │  GL-iNet     │ ◄────────────► │   iPhone     │
│   Tablet    │   LAN        │  Opal        │   Client       │              │
│   Smart TV  │              │              │                │  Pythonista  │
│   Any WiFi  │              │  • redsocks  │                │  SOCKS5      │
│   Device    │              │  • TTL=65    │                │  Proxy       │
│             │              │  • DoH DNS   │                │              │
│             │              │  • Kill Sw.  │                │  ↕ Cellular  │
└─────────────┘              └──────────────┘                └──────┬───────┘
                                                                    │
                                                              T-Mobile sees:
                                                              Normal phone
                                                              traffic only ✓
```

### Multi-Layer Bypass

| Layer | Technique | What It Defeats |
|-------|-----------|----------------|
| 🔴 **Primary** | SOCKS5 proxy on iPhone | APN detection (the #1 method) |
| 🟠 **Secondary** | TTL set to 65 | TTL/Hop limit analysis |
| 🟡 **Tertiary** | DNS-over-HTTPS | DNS pattern analysis |
| 🟢 **Safety** | Kill switch | Prevents unproxied leaks |
| 🔵 **Defense** | Traffic originates from iOS | TCP/IP fingerprinting, DPI |

---

## 📦 What's Included

```
```
camofox/
├── camofox-router/          # GL-iNet Opal plugin (OpenWrt)
│   ├── scripts/install.sh   # One-click installer
│   ├── scripts/setup-wizard.sh
│   ├── files/               # All config files, firewall rules, services
│   └── README.md            # Router-specific documentation
│
├── camofox-mac/             # MacBook direct-connect mode (NEW!)
│   ├── camofox-mac.sh       # Main CLI (start/stop/status/test/find)
│   ├── discover.sh          # Auto-find iPhone on network
│   ├── dns-setup.sh         # DNS leak prevention
│   ├── proxy_helper.py      # Transparent proxy for force mode
│   ├── pfctl-rules.conf     # Packet filter rules
│   ├── install.sh           # macOS installer
│   └── README.md            # Mac-specific documentation
│
├── camofox-ios/             # iPhone proxy app (Pythonista)
│   ├── camofox_start.py     # One-tap launcher
│   ├── camofox_proxy.py     # Enhanced SOCKS5/HTTP proxy
│   ├── keepalive.py         # Prevent iOS from killing Pythonista
│   ├── diagnostics.py       # Network diagnostic tool
│   ├── shortcuts/           # iOS Shortcuts integration guide
│   ├── CONFIG.md            # Detailed setup guide
│   └── README.md            # iOS-specific documentation
│
├── docs/                    # Research & specifications
│   ├── RESEARCH_SPEC.md     # Complete technical research (917 lines)
│   ├── opal_hardware_research.md
│   └── vpn_comparison_research.md
│
├── lib/                     # Proxy server library (from iOS-SOCKS-Server)
├── dns/                     # Bundled dnspython
└── socks5.py                # Original iOS-SOCKS-Server script
```

---

## 🚀 Quick Start

### Prerequisites

| Item | Requirement |
|------|------------|
| **iPhone** | Any model with cellular data |
| **Pythonista 3** | $9.99 from [App Store](https://apps.apple.com/us/app/pythonista-3/id1085978097) |
| **GL-iNet Opal** | GL-SFT1200 travel router ([buy](https://www.gl-inet.com/products/gl-sft1200/)) |
| **T-Mobile plan** | Any plan with cellular data |

### Step 1: Set Up iPhone (5 minutes)

1. Install **Pythonista 3** from the App Store
2. Download the `camofox-ios/` folder to Pythonista's iCloud directory
3. Also copy the `lib/` and `dns/` folders (needed for proxy)
4. Open `camofox_start.py` in Pythonista and tap **Run** ▶️
5. Note the displayed IP address and ports

### Step 2: Set Up Router (10 minutes)

1. Connect to your Opal router via SSH:
   ```bash
   ssh root@192.168.8.1
   ```
2. Copy the `camofox-router/` folder to the router:
   ```bash
   scp -r camofox-router/ root@192.168.8.1:/tmp/
   ```
3. Run the installer:
   ```bash
   cd /tmp/camofox-router
   sh scripts/install.sh
   ```
4. Run the setup wizard:
   ```bash
   camofox setup
   ```

### 🍎 Option B: MacBook Direct Connect (No Router Needed)

If you don't have the GL-iNet Opal with you, your MacBook can connect directly:

1. Connect both your MacBook and iPhone to the **same WiFi network**
2. Run `camofox_start.py` in Pythonista on the iPhone
3. On your MacBook:
   ```bash
   cd camofox-mac
   sh install.sh
   camofox-mac start
   ```
4. CamoFox auto-discovers the iPhone and routes all traffic through it

**Two modes:**
- **Simple mode** (default): Sets macOS system proxy — works for most apps
- **Force mode**: Uses `pfctl` to capture ALL traffic — nothing leaks



### Step 3: Connect & Verify

1. Connect your devices to the Opal's WiFi network
2. Check status: `camofox status`
3. Run tests: `camofox test`
4. Browse the internet — all traffic goes through your iPhone's data
5. Check your T-Mobile account — data should show as on-device, not hotspot

---

## 🛡️ How T-Mobile Detects Tethering (And How We Beat It)

| Detection Method | How T-Mobile Does It | How CamoFox Defeats It |
|-----------------|---------------------|----------------------|
| **APN Detection** | iPhone uses hotspot APN when Personal Hotspot is on | We never use Personal Hotspot — SOCKS proxy uses primary APN |
| **TTL Analysis** | Tethered packets have TTL=63 instead of 64 | Router sets TTL to 65, arrives at carrier as 64 |
| **TCP Fingerprinting** | Windows/Mac TCP stack differs from iOS | All connections made BY the iPhone — iOS fingerprint always |
| **Deep Packet Inspection** | HTTP headers reveal desktop browsers | Proxy rewrites nothing — carrier sees iPhone-originated TCP |
| **DNS Patterns** | Desktop DNS queries for Windows Update, etc. | DNS-over-HTTPS tunneled through the proxy |
| **MAC/DHCP** | Device hostnames reveal laptops | Kill switch + proxy = carrier never sees LAN devices |

---

## ⚙️ Configuration

### Router (`/etc/config/camofox`)

| Setting | Default | Description |
|---------|---------|------------|
| `proxy_ip` | `172.20.10.1` | iPhone's IP address |
| `proxy_port` | `9876` | SOCKS5 proxy port |
| `ttl_value` | `65` | TTL to set on outgoing packets |
| `kill_switch` | `1` | Block traffic if proxy unavailable |
| `doh_enabled` | `1` | Use DNS-over-HTTPS |
| `health_interval` | `30` | Health check frequency (seconds) |
| `auto_detect` | `1` | Auto-detect iPhone IP |

### iPhone (`camofox_proxy.py`)

Edit the `ProxyConfig` at the top of the file, or pass CLI arguments.

---

## 🔧 Management Commands

```bash
camofox start      # Start all services
camofox stop       # Stop all services
camofox restart    # Restart everything
camofox status     # Show component status
camofox test       # Run connectivity & leak tests
camofox setup      # Interactive configuration wizard
camofox logs       # View logs
```

---

## ⚠️ Known Limitations

1. **TCP only** — SOCKS5 proxies only handle TCP. UDP-based apps (some games, VoIP) may not work through the proxy.
2. **Pythonista can be killed** — iOS may suspend Pythonista if it runs too long in the background. The keepalive module mitigates this but can't fully prevent it.
3. **Speed limited by cellular** — Max speed is your iPhone's cellular connection speed.
4. **Requires Pythonista** — $9.99 paid app, but well worth it.
5. **Cat and mouse** — T-Mobile may update their detection. Our multi-layer approach provides resilience.

---

## 📊 Project Stats

| Component | Files | Lines | Purpose |
|-----------|-------|-------|---------|
| **Research** | 3 | 2,229 | Technical specification & analysis |
| **Router Plugin** | 12 | 2,863 | OpenWrt package for GL-iNet Opal |
| **Mac Direct Connect** | 10 | 3,452 | MacBook-to-iPhone tunnel |
| **iOS App** | 9 | 2,925 | Enhanced proxy & automation |
| **Total** | **34+** | **11,469+** | Complete multi-platform bypass system |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

Originally based on [iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server) by @nneonneo.

Copyright (c) 2026 My LiLPWNY

---

## 🤝 Contributing

Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) before submitting a PR.

- 🐛 [Report a Bug](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=bug_report.md)
- ✨ [Request a Feature](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=feature_request.md)
- ⚠️ [Report a Detection Change](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=detection_report.md)

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## 🔒 Security

If you discover a security vulnerability, please follow our [Security Policy](SECURITY.md). **Do not** open a public issue for security vulnerabilities.

---

1. Run SOCKS proxy on iPhone via Pythonista
2. **With router**: Opal tunnels all WiFi devices through proxy
3. **Without router**: MacBook connects directly via `camofox-mac`
4. T-Mobile sees normal iPhone traffic — no hotspot APN, no TTL anomalies, no DPI flags
5. Enjoy unlimited, unthrottled internet on all your devices
