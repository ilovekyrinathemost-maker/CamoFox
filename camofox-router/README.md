# 🦊 CamoFox Router Plugin

**Transparent tethering bypass for GL-iNet routers + iPhone**

CamoFox tunnels all connected device traffic through a SOCKS5 proxy running on your iPhone, making tethered traffic indistinguishable from normal phone usage. T-Mobile (and other carriers) cannot detect tethering because the traffic genuinely originates from the phone's native TCP/IP stack.

---

## How It Works

```
[Laptop/Tablet/TV]  ──WiFi──▶  [GL-iNet Opal Router]  ──USB/WiFi──▶  [iPhone]
       │                              │                                  │
       │                     redsocks intercepts              SOCKS5 proxy creates
       │                     TCP, redirects to                NEW connections via
       │                     iPhone's SOCKS5 proxy            phone's cellular data
       │                              │                                  │
       │                     TTL set to 65                    Carrier sees:
       │                     DNS via DoH (encrypted)          - TTL=64 (normal iOS)
       │                     Kill switch if proxy down        - iOS TCP fingerprint
       │                                                      - Primary data APN
       │                                                      - NO hotspot indicator
       ▼
  Normal internet access
  with zero configuration
  on client devices
```

### Why SOCKS5 Proxy?

Unlike VPN or TTL-only approaches, the SOCKS5 proxy method is the **only** technique that defeats T-Mobile's primary detection mechanism: **APN-based detection**.

| Detection Method | TTL Only | TTL+VPN | **SOCKS5 Proxy** |
|---|---|---|---|
| APN-based (hotspot flag) | ❌ | ❌ | ✅ |
| TTL analysis | ✅ | ✅ | ✅ |
| TCP/IP fingerprinting | ❌ | ✅ | ✅ |
| Deep packet inspection | ❌ | ✅ | ✅ |
| **Overall effectiveness** | **2/10** | **6/10** | **9/10** |

---

## Requirements

### Router
- **GL-iNet Opal (GL-SFT1200)** or compatible GL-iNet router
- Firmware **4.3.25** (stable) recommended
- SSH access enabled

### iPhone
- iOS 14+
- **Pythonista 3** app ($9.99 on App Store)
- **iOS-SOCKS-Server** script from [nneonneo/iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server)
- Active T-Mobile plan with unlimited on-device data

### Connection
- USB Lightning/USB-C cable (recommended) **OR**
- iPhone Personal Hotspot WiFi

---

## Quick Start

### 1. Set Up iPhone SOCKS5 Proxy

1. Install **Pythonista 3** from the App Store
2. Download [iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server)
3. Open `socks5.py` in Pythonista and run it
4. The proxy starts on port **1080** (SOCKS5) and **1081** (HTTP)
5. Keep Pythonista in the foreground

### 2. Connect iPhone to Router

**USB Tethering (recommended):**
1. Connect iPhone to router's USB port with a cable
2. On iPhone: tap "Trust This Computer" if prompted
3. Enable Personal Hotspot (Settings → Personal Hotspot)
4. The router auto-detects the iPhone

**WiFi Client Mode:**
1. Enable Personal Hotspot on iPhone
2. On router admin panel: Internet → Connect to iPhone's WiFi

### 3. Install CamoFox on Router

SSH into your router and run:

```bash
# Copy camofox-router directory to the router, then:
cd /tmp/camofox-router
sh scripts/install.sh
```

The installer will:
- Check platform compatibility
- Install dependencies (`redsocks`, `iptables-mod-ipopt`, `https-dns-proxy`)
- Copy all configuration files
- Enable the service for boot startup

### 4. Configure and Start

**Interactive setup (recommended for first time):**
```bash
camofox setup
```

**Or start with defaults:**
```bash
camofox start
```

### 5. Verify

```bash
camofox test
```

This runs a full diagnostic checking proxy connectivity, firewall rules, DNS configuration, and external connectivity.

---

## Usage

### Management Commands

```bash
camofox start     # Start all services
camofox stop      # Stop all services, remove firewall rules
camofox restart   # Restart everything
camofox status    # Show detailed status of all components
camofox test      # Run connectivity and leak diagnostics
camofox logs      # Show CamoFox-related logs
camofox setup     # Run interactive setup wizard
camofox enable    # Enable auto-start at boot
camofox disable   # Disable auto-start at boot
camofox version   # Show version
```

### Configuration

CamoFox uses UCI (Unified Configuration Interface), the standard OpenWrt config system:

```bash
# View current configuration
uci show camofox

# Change proxy IP
uci set camofox.main.proxy_ip='172.20.10.1'

# Change proxy port
uci set camofox.main.proxy_port='1080'

# Toggle kill switch
uci set camofox.main.kill_switch='1'

# Apply changes
uci commit camofox
camofox restart
```

### Configuration Options

| Option | Default | Description |
|---|---|---|
| `enabled` | `1` | Master enable/disable |
| `proxy_ip` | `172.20.10.1` | iPhone's IP address |
| `proxy_port` | `1080` | SOCKS5 proxy port |
| `proxy_type` | `socks5` | `socks5` or `http` |
| `connection_mode` | `usb` | `usb` or `wifi` |
| `auto_detect` | `1` | Auto-detect iPhone IP |
| `ttl_value` | `65` | TTL to set on packets |
| `ttl_enabled` | `1` | Enable TTL mangling |
| `kill_switch` | `1` | Block traffic if proxy down |
| `doh_enabled` | `1` | DNS-over-HTTPS |
| `doh_resolver` | Cloudflare | DoH resolver URL |
| `health_interval` | `30` | Health check interval (seconds) |
| `health_fail_threshold` | `3` | Failures before kill switch |
| `redsocks_port` | `12345` | Local redsocks port |
| `lan_iface` | `br-lan` | LAN interface name |
| `log_level` | `1` | 0=quiet, 1=normal, 2=verbose |

---

## Architecture

### File Layout

```
/etc/config/camofox              # UCI configuration
/etc/camofox/
├── redsocks.conf.template       # Template for redsocks config
├── firewall.rules               # iptables rules script
└── health_check.sh              # Health monitor daemon
/etc/init.d/camofox              # OpenWrt procd init script
/etc/hotplug.d/iface/99-camofox  # Auto-detect iPhone on connect
/usr/bin/camofox                 # CLI management tool
```

### Traffic Flow

1. **LAN device** sends TCP traffic to the internet
2. **iptables PREROUTING** on `br-lan` catches the packet
3. **REDSOCKS chain** checks if destination is local/private → if so, passes through normally
4. **REDIRECT** sends non-local TCP to redsocks on port 12345
5. **redsocks** wraps the connection in SOCKS5 protocol and sends to iPhone
6. **iPhone's SOCKS5 proxy** creates a NEW TCP connection using the phone's cellular data
7. **T-Mobile sees**: TTL=64, iOS fingerprint, primary data APN — normal phone traffic

### DNS Flow

1. LAN device sends DNS query (UDP:53) to router
2. dnsmasq forwards to https-dns-proxy (127.0.0.1:5053)
3. https-dns-proxy converts to HTTPS request (TCP:443)
4. TCP request is caught by iptables → redsocks → SOCKS5 → iPhone
5. DNS queries are encrypted and routed through the proxy
6. Direct UDP:53 to internet is blocked (DNS leak prevention)

### Kill Switch

When enabled, the kill switch prevents any traffic from leaking if the proxy goes down:

- Health monitor checks proxy every 30 seconds
- After 3 consecutive failures, `CAMOFOX_KILLSW` chain is set to DROP
- All FORWARD traffic from br-lan is blocked
- When proxy returns, kill switch deactivates automatically
- Router management (SSH, web UI) remains accessible

---

## Troubleshooting

### Proxy Not Reachable

```bash
# Check if iPhone is connected
ip route  # Look for 172.20.10.x route

# Test proxy directly
nc -w 3 172.20.10.1 1080 && echo "OK" || echo "FAIL"

# Check Pythonista is running on iPhone
# iOS kills background apps — keep Pythonista in foreground
```

### No Internet After Starting

```bash
# Check redsocks is running
pidof redsocks

# Check firewall rules
iptables -t nat -L REDSOCKS -n -v

# Check kill switch isn't engaged
iptables -L CAMOFOX_KILLSW -n -v

# Check logs
camofox logs

# Emergency: stop everything and restore normal routing
camofox stop
```

### DNS Not Working

```bash
# Check https-dns-proxy
pidof https-dns-proxy

# Test DNS resolution
nslookup google.com 127.0.0.1

# Check if UDP:53 is blocked
iptables -L FORWARD -n -v | grep 53
```

### High Latency

- Use USB tethering instead of WiFi (lower latency)
- Use 5GHz WiFi if using WiFi client mode
- Check iPhone signal strength
- The SOCKS proxy adds ~5-15ms overhead

### iPhone Disconnects

- Keep Pythonista in foreground (iOS kills background apps)
- Use iOS Shortcuts to auto-relaunch Pythonista
- Connect iPhone to power (battery drain causes shutdowns)
- The health monitor will detect disconnection and engage kill switch

---

## Uninstallation

```bash
# Full removal
sh /tmp/camofox-router/scripts/uninstall.sh

# Keep configuration for reinstall
sh /tmp/camofox-router/scripts/uninstall.sh --keep-config

# Also remove dependencies
sh /tmp/camofox-router/scripts/uninstall.sh --remove-deps
```

---

## Security Considerations

- **T-Mobile TOS**: Using tethering bypass may violate your carrier's Terms of Service. Use at your own risk.
- **Traffic Privacy**: Traffic between LAN devices and the router is unencrypted on the local network. The SOCKS5 proxy does not add encryption — it tunnels TCP connections.
- **DNS Privacy**: With DoH enabled, DNS queries are encrypted via HTTPS through the SOCKS proxy.
- **Router Security**: OpenWrt 18.06 is outdated. The router should not be exposed to untrusted networks.

---

## Building as OpenWrt Package

To build a `.ipk` package using the OpenWrt SDK:

```bash
# Clone the OpenWrt SDK for your router
git clone https://github.com/gl-inet/sdk.git
cd sdk

# Copy CamoFox to packages directory
cp -r /path/to/camofox-router package/camofox

# Build
make package/camofox/compile V=s

# Find the .ipk
find bin/ -name 'camofox*.ipk'

# Install on router
scp bin/.../camofox_1.0.0-1_all.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 'opkg install /tmp/camofox_1.0.0-1_all.ipk'
```

---

## Credits

- [iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server) by nneonneo — SOCKS5 proxy for iPhone
- [redsocks](https://github.com/darkk/redsocks) — Transparent TCP-to-SOCKS redirector
- [softmoth's redsocks gist](https://gist.github.com/softmoth/039e2879198f298a41f0924f9fd357c2) — Setup reference
- GL-iNet and OpenWrt communities for extensive documentation

---

## License

MIT License. See individual component licenses for dependencies.
