# GL-iNet Opal (GL-SFT1200) Technical Research Document

> Compiled: 2026-04-27 | Sources: Official GL-iNet docs, OpenWrt forums, GL-iNet forums, GitHub repos, community research

---

## Table of Contents

1. [Hardware Specifications](#1-hardware-specifications)
2. [OpenWrt Version & Firmware](#2-openwrt-version--firmware)
3. [USB Tethering (iPhone)](#3-usb-tethering-iphone)
4. [Available Packages & Software](#4-available-packages--software)
5. [Plugin/Package Development](#5-pluginpackage-development)
6. [Firewall Capabilities](#6-firewall-capabilities)
7. [Storage Limitations](#7-storage-limitations)
8. [GL-iNet Admin API](#8-gl-inet-admin-api)
9. [Tethering Detection Bypass Techniques](#9-tethering-detection-bypass-techniques)
10. [iOS SOCKS Proxy Approach](#10-ios-socks-proxy-approach)
11. [Key Findings & Recommendations](#11-key-findings--recommendations)

---

## 1. Hardware Specifications

| Component | Specification |
|---|---|
| Model | GL-SFT1200 (Opal) |
| CPU | SiFlower SF19A28, Dual-Core ARM @1GHz |
| RAM | 128MB DDR3 |
| Flash Storage | 128MB SPI NAND Flash |
| WiFi Chipset | Integrated in SF19A28 SoC |
| WiFi Standards | IEEE 802.11a/b/g/n/ac |
| WiFi 2.4GHz | 300 Mbps (802.11n) |
| WiFi 5GHz | 867 Mbps (802.11ac) |
| Combined Speed | 1167 Mbps (AC1200 class) |
| Antennas | 2x undetachable external WiFi antennas |
| WAN Port | 1x 10/100/1000 Mbps Ethernet |
| LAN Ports | 2x 10/100/1000 Mbps Ethernet |
| USB | 1x USB 2.0 Type-A |
| Power Input | USB Type-C, 5V/3A |
| Mode Switch | Physical toggle switch (VPN on/off) |
| Reset Button | 1x recessed |
| Dimensions | 118 x 85 x 30 mm |
| Weight | 145g |
| Operating Temp | 0°C to 40°C (32°F to 104°F) |
| Storage Temp | -20°C to 70°C (-4°F to 158°F) |

### Key Hardware Notes

- The SF19A28 SoC is manufactured by SiFlower, a Chinese fabless semiconductor company
- The SoC uses a MIPS or ARM architecture (SiFlower-specific); Linux kernel support is limited to kernel 4.14
- The SoC is NOT supported by mainline OpenWrt — only SiFlower's vendor SDK provides support
- USB 2.0 port supports iPhone tethering, USB storage, and USB cellular modems
- Can be powered from a USB power bank (5V/3A via Type-C)
- Gigabit Ethernet on all 3 ports (WAN + 2 LAN)

---

## 2. OpenWrt Version & Firmware

### Current Firmware Status

| Property | Value |
|---|---|
| Latest Stable Firmware | 4.3.25 |
| Latest Beta Firmware | 4.7.2 |
| Base OpenWrt Version | 18.06 (SiFlower SDK fork) |
| Linux Kernel | 4.14.x |
| Firewall Framework | fw3 (iptables-based) on 4.3.x |
| Support Status | Active (no EOL date announced) |
| LuCI Version | openwrt-18.06 branch |

### Firmware Version History (Recent)

- **4.3.25** — Latest stable release
- **4.3.24** — Previous stable (Feb 2025)
- **4.3.11** — Had USB tethering regression bugs
- **4.7.2 beta** — Newer GL-iNet software layer, still OpenWrt 18.06 kernel
  - Added: Camouflage, Lock BSSID, TTL/HL/MTU GUI settings, AstroWarp
  - Removed: TOR support
  - Regressions: TX power reduced ~30dB, lost 5GHz DFS channel support

### OpenWrt Version Implications

- OpenWrt 18.06 is **extremely outdated** (released 2018, EOL upstream)
- Uses **iptables/fw3** (NOT nftables/fw4 which is in OpenWrt 22.03+)
- Upstream OpenWrt does NOT support the SiFlower SF19A28 SoC
- SiFlower is working on OpenWrt SNAPSHOT with kernel 6.6 support, but this is not yet available for the Opal
- The GL-iNet 4.x firmware layer adds significant functionality on top of the base OpenWrt
- Security patches depend on GL-iNet's maintenance, not upstream OpenWrt

### Firmware Download

- Official download center: `https://dl.gl-inet.com/router/sft1200/`
- Stable firmware: `https://dl.gl-inet.com/router/sft1200/stable`
- Beta/testing firmware: `https://dl.gl-inet.com/release/router/testing/sft1200/`

---

## 3. USB Tethering (iPhone)

### Native Support

The GL-SFT1200 supports iPhone USB tethering **natively** in the firmware. No additional packages need to be installed.

### Setup Process

1. Connect iPhone to the router's USB 2.0 port via Lightning-to-USB-A (or USB-C-to-USB-A for newer iPhones)
2. On iPhone: Tap "Trust" when prompted about the connected device
3. On iPhone: Go to **Settings → Personal Hotspot → Allow Others to Join** (enable)
4. On router web panel: Navigate to **INTERNET → Tethering → Connect**
5. Optional: Click **Advanced** to customize TTL, HL, and MTU settings before connecting
6. Green dot appears in the Tethering section when connected

### Required Kernel Modules (Pre-installed)

- `kmod-usb-net` — USB networking support
- `kmod-usb-net-ipheth` — iPhone USB Ethernet driver (Apple iPhone tethering protocol)
- `usbmuxd` / `libusbmuxd` — USB multiplexing daemon for Apple devices
- `libimobiledevice` — Library for communicating with iOS devices
- `libplist` — Apple Property List library

### Known Issues

- **Firmware 4.3.11**: USB tethering broken after update (fixed in later versions)
- **iPhone recognition failures**: Some users report the Opal not recognizing iPhones via USB, requiring cable swap or reconnection
- **Lightning cables**: Must use Apple-certified or MFi cables; some third-party cables don't work
- **USB-C iPhones (iPhone 15+)**: Require USB-C-to-USB-A adapter/cable
- **iPhone must remain unlocked** during initial connection; screen lock can interrupt tethering on some iOS versions

### Important: iPhone Tethering Detection

When using iPhone's Personal Hotspot for USB tethering, **iOS creates a separate APN context** for tethered traffic. This means:

- T-Mobile (and other carriers) can detect hotspot data **independently of TTL values**
- The carrier sees tethered data on a separate APN, counted toward hotspot data allowance
- TTL mangling alone does NOT prevent detection on iPhone tethering
- A VPN tunnel combined with TTL mangling is more effective
- The iOS SOCKS proxy approach (Section 10) avoids this entirely by not using Personal Hotspot

---

## 4. Available Packages & Software

### Package Manager

- **opkg** — the standard OpenWrt package manager
- Repository: GL-iNet maintains custom package repositories for the SiFlower platform
- Base URL: `http://download.gl-inet.com/releases/packages-siflower/`

### Pre-installed VPN Support

| VPN Protocol | Status | Notes |
|---|---|---|
| WireGuard | Built-in | Client and Server support |
| OpenVPN | Built-in | Client and Server support |
| TOR | Removed in 4.7.x | Was available via plugin in earlier versions |

### Key Available Packages

#### Networking
- `wireguard-tools` — WireGuard userspace tools
- `openvpn-openssl` — OpenVPN with OpenSSL
- `iptables` — Firewall rules (fw3)
- `iptables-mod-ipopt` — IP options module (includes TTL target)
- `iptables-mod-nat-extra` — Extra NAT targets
- `ip-full` — iproute2 full suite
- `tcpdump` — Packet capture
- `mwan3` — Multi-WAN load balancing/failover

#### USB/Tethering
- `kmod-usb-net-ipheth` — iPhone tethering driver
- `usbmuxd` — Apple USB multiplexer
- `libimobiledevice` — iOS device communication

#### System
- `luci` — OpenWrt web interface (pre-installed)
- `openssh-sftp-server` — SFTP support
- `curl` / `wget` — HTTP clients
- `nano` / `vim` — Text editors

### Package Installation

~~~bash
# Update package lists
opkg update

# List available packages
opkg list

# Install a package
opkg install <package_name>

# List installed packages
opkg list-installed

# Check available space
df -h
~~~

### Custom Package Repositories

Custom opkg feeds can be added via:
- **GUI**: GL-iNet Admin Panel → Applications → Plug-ins → Add Custom Software Source
- **SSH**: Edit `/etc/opkg/customfeeds.conf`

---

## 5. Plugin/Package Development

### GL-iNet SDK

GL-iNet provides a pre-compiled SDK for creating custom packages without compiling the entire OpenWrt build environment.

#### SDK Repository
- GitHub: `https://github.com/gl-inet/sdk`
- Target for Opal: **`siflower-1806`** (covers SF1200 and SFT1200)

#### Build Process

~~~bash
# 1. Clone the SDK repository
git clone https://github.com/gl-inet/sdk.git
cd sdk

# 2. Download the SiFlower SDK
./download.sh siflower-1806

# 3. Place custom package in the packages directory
# sdk/<version>/siflower-1806/package/your_package/

# 4. Create Makefile following OpenWrt package structure
# See: https://openwrt.org/docs/guide-developer/packages

# 5. Compile the package
cd sdk/<version>/siflower-1806/
make package/your_package/compile V=s

# 6. Find the .ipk output
# Located in bin/targets/<target>/<subtarget>/packages/

# 7. Transfer to router and install
scp your_package.ipk root@192.168.8.1:/tmp/
ssh root@192.168.8.1 "opkg install /tmp/your_package.ipk"
~~~

#### Alternative: Builder Script

~~~bash
./builder.sh -d /path/to/packages -t siflower-1806
~~~

#### Package Structure (Standard OpenWrt)

~~~
your_package/
├── Makefile              # Build instructions
├── files/
│   ├── etc/
│   │   ├── config/       # UCI config files
│   │   └── init.d/       # Init scripts
│   └── usr/
│       └── bin/          # Executables
└── src/                  # Source code (if C/C++)
~~~

#### Package Makefile Template

~~~makefile
include $(TOPDIR)/rules.mk

PKG_NAME:=your-package
PKG_VERSION:=1.0.0
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define Package/your-package
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Your Package Description
  DEPENDS:=+iptables +kmod-ipt-ipopt
endef

define Package/your-package/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/usr/bin/your-script $(1)/usr/bin/
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/etc/init.d/your-service $(1)/etc/init.d/
endef

$(eval $(call BuildPackage,your-package))
~~~

### Important SDK Notes

- Must build as normal user (not root/sudo)
- No spaces in directory paths
- Linux x86_64 required (Ubuntu recommended)
- WSL supported but must clone to Linux filesystem
- Dependencies resolved via: `./scripts/feeds update -f && ./scripts/feeds install <dep>`
- Example packages: `https://github.com/mwarning/openwrt-examples`

---

## 6. Firewall Capabilities

### Firewall Framework

| Firmware Version | Firewall | Backend |
|---|---|---|
| 4.3.x (stable) | fw3 | iptables |
| 4.7.x (beta) | fw3 | iptables (still OpenWrt 18.06) |
| OpenWrt 22.03+ (other routers) | fw4 | nftables |

Since the Opal is stuck on OpenWrt 18.06, it uses **iptables (fw3)**, NOT nftables.

### iptables Capabilities

#### TTL Mangling (CRITICAL for tethering bypass)

~~~bash
# Set outgoing TTL to 65 on all interfaces
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65

# Set IPv6 Hop Limit to 65
ip6tables -t mangle -A POSTROUTING -j HL --hl-set 65

# More targeted: only modify non-ICMP packets (preserve traceroute)
iptables -t mangle -A POSTROUTING -p icmp -j ACCEPT
iptables -t mangle -A POSTROUTING -m ttl --ttl-lt 10 -j ACCEPT
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65
~~~

#### Required iptables Modules

~~~bash
# TTL target (for --ttl-set)
opkg install iptables-mod-ipopt
# Provides: -j TTL --ttl-set, --ttl-inc, --ttl-dec
# Provides: -m ttl --ttl-eq, --ttl-lt, --ttl-gt

# NAT/MASQUERADE
# Pre-installed with fw3
iptables -t nat -A POSTROUTING -o <wan_iface> -j MASQUERADE

# Conntrack
opkg install iptables-mod-conntrack-extra
~~~

#### MASQUERADE Support

Fully supported. The router uses MASQUERADE by default for NAT:

~~~bash
# Verify current NAT rules
iptables -t nat -L POSTROUTING -v -n

# Standard WAN masquerade (usually pre-configured)
iptables -t nat -A POSTROUTING -o eth0.2 -j MASQUERADE

# WireGuard masquerade
iptables -t nat -A POSTROUTING -o wg0 -j MASQUERADE
~~~

### Persistent Firewall Rules

#### Method 1: Custom Firewall Rules via LuCI

Navigate to **LuCI → Network → Firewall → Custom Rules** and add iptables commands.

#### Method 2: Local Startup Script

Add commands to `/etc/rc.local` (before `exit 0`):

~~~bash
# /etc/rc.local
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65
ip6tables -t mangle -A POSTROUTING -j HL --hl-set 65
exit 0
~~~

#### Method 3: Firewall Include

Create `/etc/firewall.user` and reference it in `/etc/config/firewall`:

~~~bash
# /etc/firewall.user
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65
ip6tables -t mangle -A POSTROUTING -j HL --hl-set 65
~~~

### GL-iNet GUI TTL Settings

- **Firmware 4.3.x**: TTL/HL settings available in tethering "Advanced" options
- **Firmware 4.7.x beta**: Additional TTL/HL/MTU settings in main GUI
- GUI sets TTL on all traffic (including ICMP), which can break traceroute
- Custom iptables rules provide more granular control

---

## 7. Storage Limitations

### Total Flash Storage

- **128MB SPI NAND Flash** total
- Firmware image consumes approximately 30-50MB
- Overlay filesystem (for user packages/config): approximately 70-90MB available
- Actual free space varies by firmware version and installed packages

### Checking Available Space

~~~bash
# Check flash usage
df -h

# Check overlay (writable) space
df -h /overlay

# Check /tmp (RAM-based tmpfs)
df -h /tmp
~~~

### Typical Space Availability

| Partition | Typical Size | Notes |
|---|---|---|
| /rom | ~30-50MB | Read-only firmware base |
| /overlay | ~70-90MB | Writable overlay (packages, config) |
| /tmp | ~60MB | RAM-based tmpfs (volatile) |

### Space Optimization Strategies

1. **Remove unnecessary packages**: `opkg remove <package>` to free overlay space
2. **Use extroot**: Mount USB storage as overlay (limited by USB 2.0 speed)
3. **Compile minimal packages**: Strip debug symbols, minimize dependencies
4. **Use /tmp for temporary files**: 60MB RAM-based storage, lost on reboot
5. **Prefer shell scripts over compiled binaries**: Smaller footprint

### Package Size Estimates

| Package | Approximate Size |
|---|---|
| wireguard-tools | ~60KB |
| openvpn-openssl | ~300KB |
| iptables-mod-ipopt | ~15KB |
| python3 (full) | ~10-15MB (too large!) |
| python3-light | ~3-5MB |
| tcpdump | ~400KB |
| curl | ~200KB |

---

## 8. GL-iNet Admin API

### API Architecture

| Property | Value |
|---|---|
| Protocol | JSON-RPC (firmware 4.x) |
| Previous Protocol | REST API (firmware 3.x) |
| Default Port | 80 (HTTP) / 443 (HTTPS) |
| Authentication | Challenge-response with password hash |
| Session Management | Token-based with keep-alive |

### API Access

#### Direct JSON-RPC Requests

~~~bash
# Step 1: Get challenge (salt and nonce)
curl -s http://192.168.8.1/rpc -d '{
  "jsonrpc": "2.0",
  "method": "challenge",
  "params": {"username": "root"},
  "id": 1
}'

# Step 2: Login with hashed password
# Password must be hashed with the salt and nonce from challenge
curl -s http://192.168.8.1/rpc -d '{
  "jsonrpc": "2.0",
  "method": "login",
  "params": {"username": "root", "hash": "<computed_hash>"},
  "id": 2
}'

# Step 3: Make API calls with session token
curl -s http://192.168.8.1/rpc -d '{
  "jsonrpc": "2.0",
  "method": "call",
  "params": ["<session_token>", "system", "board"],
  "id": 3
}'
~~~

#### Python Library (python-glinet)

~~~bash
pip install python-glinet
~~~

~~~python
from pyglinet import GlInet

# Connect to router
gl = GlInet(base_url="http://192.168.8.1")
gl.login()  # Will prompt for password

# Get API client with all available methods
api = gl.get_api_client()

# Example: Get system info
result = gl.request("call", ["system", "board"])
print(result)

# Example: List available API methods
for method in dir(api):
    print(method)
~~~

### Available API Categories (Firmware 4.x)

- **system** — System information, reboot, firmware
- **network** — WAN, LAN, WiFi configuration
- **firewall** — Firewall rules, zones, forwards
- **vpn** — WireGuard/OpenVPN client/server management
- **tethering** — USB tethering configuration
- **wifi** — Wireless settings, SSID, security
- **clients** — Connected client management
- **dns** — DNS settings, custom DNS
- **repeater** — WiFi repeater/extender mode

### LuCI Web Interface

- Accessible via: `http://192.168.8.1/cgi-bin/luci`
- Username: `root`
- Password: Same as GL-iNet admin panel
- Provides full OpenWrt configuration access
- More granular control than the GL-iNet admin panel

### SSH Access

~~~bash
ssh root@192.168.8.1
# Password: Same as GL-iNet admin panel
# Shell: /bin/ash (BusyBox)
~~~

### UCI Configuration System

~~~bash
# View all network config
uci show network

# View firewall config
uci show firewall

# View wireless config
uci show wireless

# Make changes
uci set network.wan.proto='dhcp'
uci commit network
/etc/init.d/network restart
~~~

---

## 9. Tethering Detection Bypass Techniques

### How Carriers Detect Tethering

| Method | Description | Effectiveness |
|---|---|---|
| TTL Analysis | Tethered packets have TTL decremented by 1 extra hop | Easily bypassed with TTL mangling |
| Separate APN | iPhone creates separate APN context for hotspot | Cannot be bypassed by TTL alone |
| Deep Packet Inspection (DPI) | Analyzing traffic patterns, HTTP headers, OS fingerprints | Bypassed by VPN encryption |
| IMEI Checking | Carrier checks device IMEI against known router devices | Bypassed by IMEI spoofing |
| MAC Address Analysis | Upstream sees multiple MAC addresses | Bypassed by NAT/masquerade |
| DHCP Client Name | Router sends identifiable DHCP hostname | Bypassed by camouflage mode |

### Bypass Technique Matrix

| Technique | What It Bypasses | GL-iNet Support |
|---|---|---|
| TTL set to 65 | TTL hop detection | GUI + iptables |
| HL set to 65 | IPv6 hop detection | GUI + ip6tables |
| VPN tunnel (WireGuard/OpenVPN) | DPI, traffic analysis | Built-in |
| MAC Cloning | MAC-based detection | Built-in GUI |
| Camouflage Mode | Device fingerprinting | Firmware 4.7+ |
| DHCP Client Name | Hostname detection | Via camouflage |
| IMEI Spoofing | IMEI-based detection | Not applicable (USB tethering) |
| iOS SOCKS Proxy | ALL detection methods | External (Pythonista app) |

### Recommended Multi-Layer Bypass Stack

1. **Layer 1 — TTL/HL Mangling**: Set outgoing TTL to 65, HL to 65
2. **Layer 2 — VPN Tunnel**: Route all traffic through WireGuard or OpenVPN
3. **Layer 3 — Camouflage**: Enable camouflage mode (firmware 4.7+)
4. **Layer 4 — MAC Clone**: Clone the tethering phone's MAC address
5. **Layer 5 — Custom Firewall**: Targeted iptables rules for edge cases

### Why VPN Is Essential

- TTL mangling alone is insufficient for iPhone tethering on T-Mobile
- iPhone creates a separate APN context when Personal Hotspot is enabled
- Carrier sees tethered data on this separate APN regardless of TTL
- VPN encrypts all traffic, preventing DPI from analyzing content
- VPN makes all traffic appear as a single encrypted stream from the phone
- Combined TTL + VPN has been confirmed effective on multiple carriers

---

## 10. iOS SOCKS Proxy Approach

### Overview

The iOS-SOCKS-Server project (`https://github.com/nneonneo/iOS-SOCKS-Server`) provides an alternative approach that completely avoids the Personal Hotspot feature, making all traffic appear to originate from the phone itself.

### How It Works

1. A SOCKS5/HTTP proxy runs on the iPhone via the **Pythonista** app
2. The router connects to the iPhone over WiFi (NOT USB tethering)
3. All router traffic is routed through the SOCKS proxy on the iPhone
4. The iPhone makes all outbound connections on behalf of the router
5. Carrier sees ONLY normal phone traffic — no tethering APN, no TTL decrement

### Architecture

~~~
[Client Devices] → [GL-iNet Router] → WiFi → [iPhone SOCKS Proxy] → [Carrier Network] → [Internet]
                                                    ↑
                                          All connections originate
                                          from the phone itself
~~~

### Key Advantages

- **Completely avoids Personal Hotspot** — no separate APN context created
- **No TTL decrement** — connections originate from the phone
- **No DPI concerns** — traffic appears as normal phone usage
- **Works even when carriers ban tethering entirely**
- **Bypasses speed limits** on tethered connections
- **No VPN needed** for basic tethering bypass

### Key Limitations

- **TCP only** — UDP traffic is not proxied (problematic for DNS, gaming, VoIP)
- **Requires Pythonista app** ($9.99 paid app on App Store)
- **WiFi connection only** — cannot use USB tethering (the proxy runs over WiFi)
- **Performance overhead** — proxy adds latency and CPU usage on iPhone
- **iPhone screen must stay active** or Pythonista must run in background
- **Ad-hoc network complexity** — requires creating a WiFi network for the connection

### Integration with GL-iNet Router

The SOCKS proxy approach requires the router to be configured to route all traffic through the proxy. This can be done via:

1. **redsocks** — Transparent SOCKS proxy redirector (redirect all TCP via iptables)
2. **tun2socks** — Create a TUN interface that routes through SOCKS
3. **WireGuard over SOCKS** — Tunnel WireGuard through the SOCKS proxy for UDP support

---

## 11. Key Findings & Recommendations

### Hardware Suitability: GOOD

- Adequate CPU (dual-core 1GHz) for VPN + routing
- 128MB RAM is sufficient for WireGuard (lightweight protocol)
- 128MB flash provides reasonable space for additional packages
- USB 2.0 supports iPhone tethering natively
- Gigabit Ethernet for wired clients
- Compact and power-bank friendly

### Software Suitability: MODERATE (with caveats)

- OpenWrt 18.06 is very old but functional
- iptables (fw3) fully supports TTL mangling and MASQUERADE
- WireGuard and OpenVPN are built-in
- opkg package manager works for installing additional tools
- GL-iNet SDK available for custom package compilation
- JSON-RPC API enables programmatic configuration

### Recommended Approach for This Project

1. **Primary Method: VPN + TTL Mangling via USB Tethering**
   - Use iPhone USB tethering (native support)
   - Set TTL to 65 via iptables
   - Route all traffic through WireGuard VPN
   - Enable camouflage mode (firmware 4.7+)
   - This is the simplest and most reliable approach

2. **Advanced Method: SOCKS Proxy (No Personal Hotspot)**
   - Run SOCKS5 proxy on iPhone via Pythonista
   - Connect router to iPhone via WiFi
   - Use redsocks/tun2socks on router for transparent proxying
   - Completely invisible to carrier
   - More complex setup, TCP-only limitation

3. **Plugin Architecture**
   - Create an OpenWrt .ipk package using the GL-iNet SDK (target: siflower-1806)
   - Package should contain:
     - Firewall rules (TTL/HL mangling)
     - WireGuard auto-configuration
     - Tethering auto-detection and setup
     - Status monitoring
   - Install via opkg on the router
   - Configure via UCI or the JSON-RPC API

### Critical Configuration Paths

| Configuration | Path / Command |
|---|---|
| Network config | `/etc/config/network` |
| Firewall config | `/etc/config/firewall` |
| Wireless config | `/etc/config/wireless` |
| Custom firewall rules | `/etc/firewall.user` |
| Startup script | `/etc/rc.local` |
| Package feeds | `/etc/opkg/customfeeds.conf` |
| WireGuard config | `/etc/config/network` (interface section) |
| UCI commands | `uci show/set/commit` |
| Web admin | `http://192.168.8.1` |
| LuCI admin | `http://192.168.8.1/cgi-bin/luci` |
| SSH access | `ssh root@192.168.8.1` |
| API endpoint | `http://192.168.8.1/rpc` (JSON-RPC) |

---

## Sources

1. GL-iNet Official Documentation: https://docs.gl-inet.com/router/en/4/user_guide/gl-sft1200/
2. GL-iNet Specification Page: https://docs.gl-inet.com/router/en/3/specification/gl-sft1200/
3. GL-iNet Firmware Versions: https://www.gl-inet.com/support/firmware-versions/
4. GL-iNet Tethering Guide: https://docs.gl-inet.com/router/en/4/interface_guide/internet_tethering/
5. GL-iNet SDK: https://github.com/gl-inet/sdk
6. GL-iNet Forum — TTL Mangling: https://forum.gl-inet.com/t/changing-ttl-in-openwrt-22-03/30838
7. GL-iNet Forum — TTL Dead?: https://forum.gl-inet.com/t/ttl-mangeling-basically-dead/64088
8. GL-iNet Forum — Beryl AX iPhone TTL: https://forum.gl-inet.com/t/beryl-ax-usb-iphone-tethering-mangling-ttl-doesnt-avoid-hotspot-data/56191
9. GL-iNet Forum — Beta Firmware 4.7: https://forum.gl-inet.com/t/gl-sft1200-opal-new-beta-firmware/52565
10. GL-iNet Forum — Camouflage: https://forum.gl-inet.com/t/i-got-confused-with-new-features/48429
11. iOS-SOCKS-Server: https://github.com/nneonneo/iOS-SOCKS-Server
12. python-glinet: https://github.com/tomtana/python-glinet
13. OpenWrt Package Development: https://openwrt.org/docs/guide-developer/packages
14. TTL Bypass (nftables): https://github.com/xiv3r/ttl-bypass
