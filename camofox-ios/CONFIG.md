# CamoFox iOS Configuration Guide

Complete setup guide for running the CamoFox SOCKS5 proxy on your
iPhone with Pythonista 3, connecting to the GL-iNet Opal router.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [First Run Configuration](#3-first-run-configuration)
4. [Connecting to GL-iNet Opal Router](#4-connecting-to-gl-inet-opal-router)
5. [Configuration Reference](#5-configuration-reference)
6. [Keepalive Configuration](#6-keepalive-configuration)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

### Required

| Item | Details |
|------|--------|
| **iPhone** | Any iPhone with iOS 14 or later |
| **Pythonista 3** | [$9.99 on App Store](https://apps.apple.com/app/pythonista-3/id1085978097) |
| **Cellular plan** | T-Mobile (or any carrier) with unlimited on-device data |
| **GL-iNet Opal** | GL-SFT1200 with firmware 4.3.25+ (already configured with camofox-router) |

### Optional but Recommended

| Item | Details |
|------|--------|
| **dnspython** | Better DNS resolution (install via StaSh) |
| **Lightning/USB-C cable** | Keep iPhone charging while proxying |
| **iOS Shortcuts** | Automate proxy launch |

### Install dnspython in Pythonista

Pythonista includes a package manager called **StaSh**:

1. Open Pythonista
2. Create a new script with this content and run it:
   ```python
   import requests as r; exec(r.get('https://bit.ly/get-stash').text)
   ```
3. After StaSh installs, run StaSh from the script library
4. In the StaSh terminal, type:
   ```
   pip install dnspython
   ```
5. Restart Pythonista

> If StaSh doesn't work, the proxy will fall back to system DNS.
> This is fine for most use cases.

---

## 2. Installation

### Method A: Copy via iCloud Drive (Recommended)

1. On your computer, copy the entire `camofox-ios/` folder
2. Place it in **iCloud Drive → Pythonista 3** folder
3. Also copy the `lib/` and `dns/` folders from the project root
   to the same Pythonista 3 iCloud folder
4. Open Pythonista → you should see the files in the script library

Your Pythonista file structure should look like:

```
Pythonista 3/
├── camofox-ios/
│   ├── camofox_start.py
│   ├── camofox_proxy.py
│   ├── camofox_status.py
│   ├── keepalive.py
│   ├── diagnostics.py
│   └── shortcuts/
│       ├── README.md
│       └── url_schemes.md
├── lib/
│   ├── __init__.py
│   ├── proxy_server.py
│   ├── socks5_server.py
│   ├── http_proxy_server.py
│   ├── status.py
│   └── ifaddrs.py
├── dns/
│   ├── __init__.py
│   ├── asyncresolver.py
│   └── ... (entire dns package)
└── socks5.py  (original, optional)
```

### Method B: Copy via USB (iTunes/Finder)

1. Connect iPhone to computer
2. Open Finder (macOS) or iTunes (Windows)
3. Select your iPhone → Files → Pythonista 3
4. Drag the folders into Pythonista's document area

### Method C: Working Copy (Git)

If you have [Working Copy](https://apps.apple.com/app/working-copy/id896694807):

1. Clone the repository in Working Copy
2. Use "Open In" to export files to Pythonista

---

## 3. First Run Configuration

### Step 1: Run Diagnostics

Before starting the proxy, verify your setup:

1. Open `camofox-ios/diagnostics.py` in Pythonista
2. Tap the ▶️ play button
3. Review the output — all checks should pass or show warnings

Expected output:
```
✅ Pythonista Environment
✅ Network Interfaces
✅ WiFi Connectivity
✅ Cellular Interface
✅ DNS Resolution
...
```

### Step 2: Start the Proxy

1. Open `camofox-ios/camofox_start.py`
2. Tap ▶️ play
3. You should see the status dashboard:
   ```
   ╔══════════════════════════════════════════════════╗
   ║           CamoFox SOCKS5/HTTP Proxy              ║
   ╚══════════════════════════════════════════════════╝
   Proxy host: 172.20.10.1 (WiFi en0)
   Connect IPv4: 10.x.x.x (pdp_ip0)
   SOCKS5:     172.20.10.1:9876
   HTTP Proxy: 172.20.10.1:9877
   ```

### Step 3: Verify from Another Device

1. On a laptop connected to the same WiFi:
   ```bash
   curl --socks5 172.20.10.1:9876 http://ifconfig.me
   ```
2. The output should show your phone's cellular IP

---

## 4. Connecting to GL-iNet Opal Router

### Network Architecture

```
[Laptop] ──WiFi──→ [Opal Router] ──WiFi──→ [iPhone]
                   192.168.8.1              172.20.10.1
                   redsocks ────SOCKS5────→ :9876
```

### Option A: iPhone Creates WiFi Network (Simplest)

1. On iPhone: enable **Personal Hotspot** (Settings → Personal Hotspot)
   - Note: we're using the WiFi network it creates, NOT the
     tethering data path — all traffic goes through the SOCKS proxy
2. On Opal Router:
   - Go to Internet → Repeater
   - Connect to iPhone's WiFi hotspot name
   - The router gets an IP like 172.20.10.x
3. Start CamoFox proxy on iPhone
4. Configure camofox-router plugin on Opal (see camofox-router docs)

### Option B: Router Creates WiFi Network

If the router creates an ad-hoc WiFi network:

1. On Opal: configure a WiFi network (default: GL-SFT1200-xxx)
2. On iPhone: connect to the router's WiFi
3. iPhone gets an IP like 192.168.8.x
4. Start CamoFox proxy — it auto-detects the WiFi interface
5. Configure camofox-router with iPhone's IP as SOCKS target

### Verify End-to-End

From a device connected to the Opal's LAN WiFi:

```bash
# Check your visible IP
curl http://ifconfig.me

# Should show iPhone's cellular IP, NOT a hotspot IP

# Check for DNS leaks
curl https://dnsleaktest.com/test/
```

---

## 5. Configuration Reference

Edit the `ProxyConfig` class in `camofox_proxy.py` or pass CLI arguments.

### Network Settings

| Parameter | Default | Description |
|-----------|---------|------------|
| `proxy_host` | auto-detect | IP the proxy advertises to clients |
| `listen_host` | `0.0.0.0` | Bind address for all listeners |
| `socks_port` | `9876` | SOCKS5 proxy port |
| `http_port` | `9877` | HTTP proxy port |
| `wpad_port` | `8088` | WPAD/PAC auto-config port |

### Connectivity Settings

| Parameter | Default | Description |
|-----------|---------|------------|
| `connect_host_ipv4` | auto-detect | Outbound IPv4 interface |
| `connect_host_ipv6` | auto-detect | Outbound IPv6 interface |
| `idle_timeout` | `1800` | Seconds before idle connection timeout |
| `use_phone_vpn` | `True` | Route through VPN interface if present |

### Reliability Settings

| Parameter | Default | Description |
|-----------|---------|------------|
| `auto_restart` | `True` | Auto-restart proxy on crash |
| `max_restart_attempts` | `10` | Max consecutive restart attempts |
| `restart_delay` | `2.0` | Initial delay between restarts (sec) |
| `restart_backoff` | `1.5` | Multiply delay after each failure |
| `restart_max_delay` | `60.0` | Maximum restart delay (sec) |

### CLI Arguments

```bash
python camofox_proxy.py --help

Options:
  --host HOST           Proxy host IP (auto-detected if omitted)
  --socks-port PORT     SOCKS5 port (default: 9876)
  --http-port PORT      HTTP proxy port (default: 9877)
  --no-restart          Disable auto-restart on crash
  --no-keepalive        Disable iOS keepalive strategies
  --verbose, -v         Enable verbose logging
```

---

## 6. Keepalive Configuration

The proxy uses multiple strategies to prevent iOS from killing Pythonista:

### Strategies

| Strategy | Default | Battery Impact | Effectiveness |
|----------|---------|---------------|---------------|
| Idle timer disable | ON | None | High — prevents screen lock |
| Silent audio | ON | Very low | Medium — keeps audio session |
| Self-ping | ON | Negligible | Low — generates activity |
| Location services | OFF | Medium-High | High — but shows GPS icon |

### Tuning Keepalive

In `camofox_start.py`, adjust the config:

```python
config = ProxyConfig(
    enable_keepalive=True,
    keepalive_audio=True,       # Toggle silent audio
    keepalive_location=False,   # Toggle GPS keepalive
    keepalive_ping_interval=30, # Seconds between self-pings
)
```

### When to Enable Location Keepalive

Enable location services keepalive (`keepalive_location=True`) if:
- The proxy keeps getting killed despite other strategies
- You're running for extended periods (hours)
- The iPhone is plugged in (mitigates battery drain)

---

## 7. Troubleshooting

### Pythonista Gets Killed by iOS

**Symptoms**: Proxy stops, router loses internet, dashboard disappears.

**Solutions** (in order of effectiveness):

1. **Keep Pythonista in foreground** — don't switch to other apps
2. **Enable Guided Access** — locks Pythonista as the only app:
   - Settings → Accessibility → Guided Access → ON
   - Open Pythonista → triple-click side button → Start
3. **Keep device charging** — iOS is less aggressive when plugged in
4. **Reduce screen brightness** — saves battery, extends runtime
5. **Enable location keepalive** — last resort, uses more battery:
   ```python
   config = ProxyConfig(keepalive_location=True)
   ```
6. **Use iOS Shortcuts automation** to relaunch if killed
   (see `shortcuts/README.md`)

### WiFi Disconnects

**Symptoms**: Proxy shows "no WiFi detected", router can't connect.

**Solutions**:

1. Check iPhone's WiFi is enabled and connected
2. Disable "Auto-Join" for other nearby WiFi networks
3. Forget other saved networks to prevent switching
4. If using Personal Hotspot: ensure "Allow Others to Join" is ON
5. Restart proxy — it re-detects interfaces on each start

### Connection Drops Under Load

**Symptoms**: Intermittent failures, slow speeds, timeout errors.

**Solutions**:

1. Reduce concurrent connections on client devices
2. Increase `idle_timeout` in config
3. Check cellular signal strength
4. Move closer to cell tower / change location
5. Check data cap hasn't been reached (Settings → Cellular → Usage)

### DNS Resolution Failures

**Symptoms**: Websites don't load, "host not found" errors.

**Solutions**:

1. Install dnspython via StaSh (see Prerequisites)
2. Ensure DNS-over-HTTPS is configured on the router
3. Test DNS: run `diagnostics.py` → check DNS Resolution
4. Try different DNS resolvers in config:
   ```python
   config = ProxyConfig(
       custom_resolvers=["9.9.9.9", "149.112.112.112"],
   )
   ```

### Proxy Port Already in Use

**Symptoms**: "Address already in use" error on startup.

**Solutions**:

1. Another instance may be running — restart Pythonista completely
   (swipe up from app switcher)
2. Wait 30 seconds for the port to be released
3. Use different ports:
   ```python
   config = ProxyConfig(socks_port=1080, http_port=8080)
   ```
   (Remember to update the router's redsocks config too!)

### Router Can't Reach Proxy

**Symptoms**: Router shows proxy as unreachable, no internet.

**Solutions**:

1. Verify iPhone and router are on the same WiFi network
2. Check proxy is listening: run diagnostics on iPhone
3. Check router's redsocks config points to correct iPhone IP
4. Verify firewall isn't blocking connections (unlikely on iPhone)
5. Try pinging iPhone IP from router:
   ```bash
   ssh root@192.168.8.1 "ping -c 3 172.20.10.1"
   ```

### Slow Speeds

**Symptoms**: Internet works but is much slower than expected.

**Causes & Solutions**:

| Cause | Fix |
|-------|-----|
| Weak cellular signal | Move to better coverage area |
| CPU-bound Pythonista | Reduce logging: `log_level=logging.ERROR` |
| Too many connections | Limit client devices or connections |
| DNS delays | Install dnspython or use DoH on router |
| IPv6 fallback issues | Disable IPv6: `connect_host_ipv6=None` |

---

## Quick Start Checklist

- [ ] Pythonista 3 installed
- [ ] CamoFox files copied to Pythonista
- [ ] lib/ and dns/ folders copied to Pythonista
- [ ] Diagnostics pass (`diagnostics.py`)
- [ ] Proxy starts successfully (`camofox_start.py`)
- [ ] Router connected to iPhone WiFi
- [ ] Router camofox plugin configured
- [ ] End-to-end test passes (curl ifconfig.me from LAN device)
- [ ] iOS Shortcut created for quick launch (optional)
- [ ] Keepalive strategies configured (optional)
