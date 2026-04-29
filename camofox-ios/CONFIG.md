# CamoFox iOS Configuration Guide

Complete setup guide for running the CamoFox SOCKS5 proxy on your
iPhone, connecting to the GL-iNet Opal router.

**Works with multiple FREE iOS Python apps — Pythonista is NOT required!**

---

## Table of Contents

1. [Choose Your Platform](#1-choose-your-platform)
2. [Platform Setup Guides](#2-platform-setup-guides)
3. [First Run Configuration](#3-first-run-configuration)
4. [Connecting to GL-iNet Opal Router](#4-connecting-to-gl-inet-opal-router)
5. [Configuration Reference](#5-configuration-reference)
6. [Keepalive Configuration](#6-keepalive-configuration)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Choose Your Platform

| Platform | Cost | Install | Background | Best For |
|----------|------|---------|------------|----------|
| **a-Shell** | **FREE** | App Store | Fair | ⭐ Recommended free option |
| **iSH** | **FREE** | App Store | **Best** | Long running sessions |
| **Pyto** | **FREE** | App Store | Fair | GUI + terminal |
| **Pythonista** | $9.99 | App Store | Poor* | Premium iOS integration |

\* Pythonista has poor background persistence but offers unique iOS features
(silent audio keepalive, screen lock prevention, GPS keepalive) that partially compensate.

### Quick Recommendation

- **Just want it to work for free?** → Use **a-Shell**
- **Need it running for hours?** → Use **iSH** (enable Location Services)
- **Already own Pythonista?** → Use **Pythonista** (most features)
- **Want a GUI?** → Use **Pyto**

---

## 2. Platform Setup Guides

### a-Shell Setup (FREE — Recommended)

[Install a-Shell](https://apps.apple.com/us/app/a-shell/id1473805438) from the App Store.

#### Step 1: Install a-Shell

1. Open the App Store on your iPhone
2. Search for "a-Shell" (by Nicolas Holzschuch)
3. Install the free app

#### Step 2: Copy Files

Option A — Using iCloud Drive:
1. On your computer, copy these folders to iCloud Drive:
   - `camofox-ios/`
   - `lib/`
   - `dns/` (optional, for enhanced DNS)
2. In a-Shell, access them via: `cd ~/Documents`

Option B — Using the Files app:
1. Open the Files app on your iPhone
2. Navigate to the a-Shell folder
3. Copy the project folders there

#### Step 3: Install Optional Dependencies

```bash
# In a-Shell (optional — proxy works without this)
pip install dnspython
```

#### Step 4: Run

```bash
cd ~/Documents   # or wherever you put the files
python3 camofox-ios/camofox_start.py
```

#### a-Shell Tips

- a-Shell has built-in Python 3 with full socket support
- Use `lg` (lg = "large") window for better status display
- Keep the app in foreground for best results
- a-Shell persists better than Pythonista in background

---

### iSH Setup (FREE — Best Background Persistence)

[Install iSH](https://apps.apple.com/us/app/ish-shell/id1436902243) from the App Store.

#### Step 1: Install iSH

1. Open the App Store
2. Search for "iSH Shell"
3. Install the free app

#### Step 2: Install Python

```bash
# In iSH (runs Alpine Linux)
apk update
apk add python3 py3-pip
```

#### Step 3: Copy Files

Option A — Git clone (if git is installed):
```bash
apk add git
git clone <your-repo-url> camofox
cd camofox
```

Option B — Manual copy:
1. Use the Files app to copy folders into iSH's file system
2. iSH's files are at: `/root/` or wherever you place them

#### Step 4: Install Optional Dependencies

```bash
pip3 install dnspython
```

#### Step 5: Run

```bash
python3 camofox-ios/camofox_start.py
```

#### iSH Tips — IMPORTANT

**Enable Location Services for iSH:**
1. Go to iOS Settings → Privacy → Location Services
2. Find iSH → Set to "Always"
3. This keeps iSH alive **indefinitely** in the background!
4. This is the #1 most effective keepalive on any iOS Python app

Other tips:
- Install `tmux` for session management: `apk add tmux`
- iSH uses x86 emulation — adds ~1-2ms latency (negligible)
- iSH has the BEST background persistence of all iOS Python apps

---

### Pyto Setup (FREE)

[Install Pyto](https://apps.apple.com/us/app/pyto-python-3/id1436650069) from the App Store.

#### Step 1: Install Pyto

1. Open the App Store
2. Search for "Pyto - Python 3" 
3. Install the free app

#### Step 2: Copy Files

1. Copy `camofox-ios/`, `lib/`, and `dns/` to Pyto's documents folder
2. Use iCloud Drive, Files app, or AirDrop

#### Step 3: Run

1. Open `camofox-ios/camofox_start.py` in Pyto
2. Tap the Run button (▶️)

#### Pyto Tips

- Pyto has both GUI and terminal modes
- Use the terminal/console view for the status dashboard
- Keep Pyto in foreground for best persistence
- Pyto supports pip for installing packages

---

### Pythonista Setup ($9.99)

[Install Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) from the App Store.

#### Step 1: Install Pythonista 3

1. Purchase and install from the App Store ($9.99)

#### Step 2: Copy Files

Copy via iCloud Drive (recommended):
1. Copy `camofox-ios/`, `lib/`, and `dns/` to iCloud Drive → Pythonista 3
2. Files appear in Pythonista's script library

Your Pythonista file structure should look like:

```
Pythonista 3/
├── camofox-ios/
│   ├── camofox_start.py
│   ├── camofox_proxy.py
│   ├── camofox_status.py
│   ├── keepalive.py
│   ├── diagnostics.py
│   └── platform_detect.py
├── lib/
│   ├── proxy_server.py
│   ├── socks5_server.py
│   ├── http_proxy_server.py
│   ├── status.py
│   └── ifaddrs.py
└── dns/       (optional)
    └── ...
```

#### Step 3: Install dnspython (Optional)

Pythonista uses StaSh package manager:
1. Create a new script with this content and run it:
   ```python
   import requests as r; exec(r.get('https://bit.ly/get-stash').text)
   ```
2. After StaSh installs, run StaSh
3. In StaSh terminal: `pip install dnspython`
4. Restart Pythonista

#### Step 4: Run

1. Open `camofox-ios/camofox_start.py`
2. Tap the ▶️ play button

#### Pythonista Bonus Features

Pythonista gets these extra features that aren't available on free platforms:
- **Screen lock prevention** — Keeps screen on while proxy runs
- **Silent audio keepalive** — Plays inaudible sound to prevent suspension
- **GPS keepalive** — Uses location services for background persistence
- **iOS Shortcuts integration** — Launch via URL scheme
- **Home screen shortcut** — One-tap launch

---

## 3. First Run Configuration

### Step 1: Run Diagnostics

Before starting the proxy, verify your setup:

```bash
# All platforms:
python3 camofox-ios/diagnostics.py
```

Expected output:
```
✔ Platform & Environment
     Python 3.x on a-Shell (FREE)
✔ Python Version
✔ Network Interfaces
✔ WiFi Connectivity
✔ DNS Resolution
...
```

### Step 2: Start the Proxy

```bash
python3 camofox-ios/camofox_start.py
```

You should see:
```
╔══════════════════════════════════════════════════╗
║           CamoFox SOCKS5/HTTP Proxy              ║
╚══════════════════════════════════════════════════╝
Platform:   ashell
Proxy host: 172.20.10.1 (WiFi en0)
SOCKS5:     172.20.10.1:9876
HTTP Proxy: 172.20.10.1:9877
```

### Step 3: Verify from Another Device

```bash
# From a laptop on the same WiFi:
curl --socks5 172.20.10.1:9876 http://ifconfig.me
# Should show your phone's cellular IP
```

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
   - Note: we use the WiFi network it creates, NOT the tethering data path
   - All traffic goes through the SOCKS proxy on the primary data APN
2. On Opal Router:
   - Go to Internet → Repeater
   - Connect to iPhone's WiFi hotspot name
   - Router gets an IP like 172.20.10.x
3. Start CamoFox proxy on iPhone
4. Configure camofox-router plugin on Opal (see camofox-router docs)

### Option B: Router Creates WiFi Network

1. On Opal: configure a WiFi network (default: GL-SFT1200-xxx)
2. On iPhone: connect to the router's WiFi
3. iPhone gets an IP like 192.168.8.x
4. Start CamoFox proxy — it auto-detects the WiFi interface
5. Configure camofox-router with iPhone's IP as SOCKS target

### Verify End-to-End

```bash
# From a device connected to the Opal's WiFi:
curl http://ifconfig.me
# Should show iPhone's cellular IP, NOT a hotspot IP
```

---

## 5. Configuration Reference

Edit the `ProxyConfig` class in `camofox_proxy.py` or pass CLI arguments.

### Network Settings

| Parameter | Default | Description |
|-----------|---------|------------|
| `proxy_host` | auto-detect | IP the proxy advertises |
| `listen_host` | `0.0.0.0` | Bind address |
| `socks_port` | `9876` | SOCKS5 proxy port |
| `http_port` | `9877` | HTTP proxy port |
| `wpad_port` | `8088` | WPAD/PAC auto-config port |

### Reliability Settings

| Parameter | Default | Description |
|-----------|---------|------------|
| `auto_restart` | `True` | Auto-restart on crash |
| `max_restart_attempts` | `10` | Max consecutive restarts |
| `restart_delay` | `2.0` | Initial restart delay (sec) |

### CLI Arguments

```bash
python3 camofox_proxy.py --help

Options:
  --host HOST           Proxy host IP (auto-detected if omitted)
  --socks-port PORT     SOCKS5 port (default: 9876)
  --http-port PORT      HTTP proxy port (default: 9877)
  --no-restart          Disable auto-restart
  --no-keepalive        Disable keepalive strategies
  --verbose, -v         Enable verbose logging
  --platform            Show detected platform and exit
```

---

## 6. Keepalive Configuration

The proxy uses multiple strategies to prevent iOS from killing the app.
Strategies are automatically selected based on your platform.

### Universal Strategies (ALL platforms)

| Strategy | Default | Description |
|----------|---------|------------|
| Self-ping | ON | Loopback TCP to proxy port |
| Network activity | ON | Small HTTP connections |
| File heartbeat | ON | Periodic disk writes |

### Pythonista-Only Strategies

| Strategy | Default | Battery | Description |
|----------|---------|---------|------------|
| Idle timer disable | ON | None | Prevents screen lock |
| Silent audio | ON | Very low | Keeps audio session |
| Location services | OFF | Medium-High | GPS keepalive |

### Platform-Specific Keepalive Tips

**iSH (BEST option):**
- Enable Location Services in iOS Settings → iSH → "Always"
- iSH stays alive indefinitely with location enabled
- No code changes needed — this is handled by iOS itself

**a-Shell:**
- Keep the app in foreground
- Network + file activity keepalive runs automatically
- Tap the screen periodically for long sessions

**Pyto:**
- Keep the app in foreground
- Use terminal mode (not GUI) for the proxy

**Pythonista:**
- Enable Guided Access for long sessions
- Keep device charging
- Enable location keepalive if proxy keeps dying:
  ```python
  config = ProxyConfig(keepalive_location=True)
  ```

---

## 7. Troubleshooting

### App Gets Killed by iOS

**Solutions by platform:**

| Platform | Solution |
|----------|----------|
| iSH | Enable Location Services (Settings → iSH → Always) |
| a-Shell | Keep in foreground, keep device charging |
| Pyto | Keep in foreground, use terminal mode |
| Pythonista | Enable Guided Access, use audio + location keepalive |
| All | Keep device charging — iOS is less aggressive when plugged in |

### WiFi Disconnects

1. Check iPhone's WiFi is enabled and connected
2. Disable "Auto-Join" for other nearby WiFi networks
3. Restart proxy — it re-detects interfaces on each start

### DNS Resolution Failures

Install dnspython:

| Platform | Command |
|----------|--------|
| a-Shell | `pip install dnspython` |
| iSH | `pip3 install dnspython` |
| Pyto | Use built-in package manager |
| Pythonista | StaSh: `pip install dnspython` |

Or use DNS-over-HTTPS on the router (recommended regardless).

### Proxy Port Already in Use

1. Wait 30 seconds for the port to be released
2. Close and reopen the Python app
3. Use different ports:
   ```bash
   python3 camofox_proxy.py --socks-port 1080 --http-port 8080
   ```

### Slow Speeds

| Cause | Fix |
|-------|-----|
| Weak cellular signal | Move to better coverage |
| Too many connections | Limit client devices |
| DNS delays | Install dnspython or use DoH on router |
| iSH emulation overhead | Minimal (~1-2ms), usually not the bottleneck |

---

## Quick Start Checklist

- [ ] iOS Python app installed (a-Shell, iSH, Pyto, or Pythonista)
- [ ] CamoFox files copied to the app
- [ ] lib/ folder copied (required)
- [ ] dns/ folder copied (optional, for better DNS)
- [ ] Diagnostics pass (`python3 diagnostics.py`)
- [ ] Proxy starts successfully (`python3 camofox_start.py`)
- [ ] Router connected to iPhone WiFi
- [ ] Router camofox plugin configured
- [ ] End-to-end test passes (curl ifconfig.me from LAN device)
- [ ] Keepalive configured for your platform
