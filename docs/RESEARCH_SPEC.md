# CamoFox Tethering Bypass: Comprehensive Technical Research Specification

> **Project**: Hide iPhone tethering from T-Mobile using GL-iNet Opal travel router
> **Date**: 2026-04-27
> **Status**: Research Complete — Ready for Implementation
> **Sources**: GL-iNet Forums, XDA Forums, GrapheneOS Community, Reddit (r/tmobile, r/GlInet, r/NoContract), GitHub repos, GL-iNet official docs, OpenWrt wiki

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [T-Mobile Tethering Detection Methods](#2-t-mobile-tethering-detection-methods)
3. [Known Bypass Techniques — Rated by Effectiveness](#3-known-bypass-techniques--rated-by-effectiveness)
4. [Recommended Multi-Layer Architecture](#4-recommended-multi-layer-architecture)
5. [GL-iNet Opal (GL-SFT1200) Capabilities & Limitations](#5-gl-inet-opal-gl-sft1200-capabilities--limitations)
6. [WireGuard vs OpenVPN Comparison](#6-wireguard-vs-openvpn-comparison)
7. [Technical Requirements](#7-technical-requirements)
8. [Architecture Diagram & Traffic Flow](#8-architecture-diagram--traffic-flow)
9. [Implementation Roadmap](#9-implementation-roadmap)
10. [Risk Assessment](#10-risk-assessment)
11. [References](#11-references)

---

## 1. Executive Summary

### The Problem
T-Mobile detects and throttles/caps tethered (hotspot) data separately from on-device data. Users with "unlimited" plans are limited to 5-50GB of hotspot data, after which speeds are throttled to 600kbps. T-Mobile uses **multiple detection methods** that make simple TTL mangling insufficient.

### The Solution
A **multi-layer bypass system** running on a GL-iNet Opal travel router that tunnels all connected device traffic through a SOCKS5 proxy running on the iPhone itself. Because the proxy runs on the phone, all outbound traffic originates from the phone's native TCP/IP stack using the phone's primary data APN — making it indistinguishable from normal phone usage.

### Key Insight
**The SOCKS5 proxy approach is fundamentally different from VPN/TTL approaches.** When using USB tethering or Personal Hotspot, the iPhone creates a separate network interface with a dedicated APN (the "dun" APN type). T-Mobile monitors this APN for tethered traffic. A SOCKS proxy running on the phone via Pythonista creates NEW TCP connections from the phone's main data socket — the hotspot APN is never activated.

### Confidence Level
- **SOCKS proxy approach**: HIGH confidence (traffic genuinely originates from phone)
- **TTL + VPN combo**: MEDIUM confidence (works on Visible, unconfirmed on T-Mobile)
- **TTL alone**: LOW confidence (confirmed NOT working on T-Mobile by multiple sources)

---

## 2. T-Mobile Tethering Detection Methods

T-Mobile employs a **layered detection strategy** that makes single-technique bypasses unreliable. The following methods are confirmed through community research:

### 2.1 APN-Based Detection (PRIMARY)

**Severity: CRITICAL** — This is the most important detection vector for iPhone.

- When iPhone's "Personal Hotspot" is enabled, iOS uses a **hardcoded separate APN** (the "dun" APN type) for all tethered traffic
- This APN is different from the phone's normal data APN (`fast.tmobile.com`)
- T-Mobile can trivially distinguish hotspot traffic because it arrives on a different APN at the network level
- On iPhone, this APN **cannot be modified** without a jailbreak — iOS hardcodes it
- On Android, GrapheneOS removes the `dun` APN type by default, which is their primary bypass mechanism
- **Implication**: Any approach that uses iPhone's Personal Hotspot (including USB tethering mode) triggers the hotspot APN

### 2.2 TTL/Hop Limit Analysis (SECONDARY)

**Severity: HIGH** — Easy to detect, easy to bypass.

- Packets from a phone have TTL=64 (iOS/Android default)
- When the phone routes tethered traffic, the TTL is decremented by 1 to 63
- T-Mobile flags packets with TTL < 64 as tethered
- **Bypass**: Set TTL to 65 on the router so after decrement it appears as 64
- **Limitation**: TTL mangling alone is confirmed NOT sufficient for T-Mobile (multiple sources confirm)
- IPv6 uses Hop Limit (HL) — same principle, same bypass needed

### 2.3 TCP/IP Stack Fingerprinting (SECONDARY)

**Severity: HIGH** — Harder to bypass, requires encryption or stack modification.

- Different operating systems have distinct TCP/IP stack signatures:
  - **TCP Window Size Scale**: iOS=16, Windows=256, Linux varies
  - **TCP Timestamp patterns**: Clock frequency and boot time variance differ per OS
  - **Initial TTL values**: Windows=128, Linux/Android=64, iOS=64
  - **TCP options ordering**: SYN packet option layout differs per OS
  - **MSS values**: Vary by OS and MTU configuration
- T-Mobile performs DPI to identify the source OS of traffic
- If traffic with a Windows or macOS TCP fingerprint comes from an iPhone line, it's flagged as tethering
- **Note**: Linux fingerprints are very similar to Android (both use Linux kernel), so Linux tethering is harder to detect via fingerprinting alone
- **Bypass**: Encrypt all traffic (VPN/tunnel) so DPI cannot see TCP headers, OR modify TCP stack parameters to mimic iOS

### 2.4 Deep Packet Inspection — DPI (SECONDARY)

**Severity: MEDIUM-HIGH** — Requires encrypted tunnel to bypass.

- T-Mobile inspects packet payloads for:
  - HTTP User-Agent strings (e.g., "Windows NT 10.0" from a phone line)
  - DNS query patterns (desktop services like Windows Update, macOS iCloud sync)
  - TLS SNI (Server Name Indication) revealing desktop-specific domains
  - Application-layer protocol signatures
- **Bypass**: Any form of encryption (VPN, SSH tunnel, SOCKS over TLS) prevents payload inspection
- **Note**: The SOCKS5 proxy approach inherently avoids this because the phone makes the connections itself

### 2.5 MAC Address & DHCP Analysis (TERTIARY)

**Severity: LOW-MEDIUM** — Detectable at the local network level.

- Carriers can see MAC address OUI (manufacturer prefix) patterns
- DHCP client hostnames can reveal device types (e.g., "DESKTOP-ABC123", "Johns-MacBook")
- Multiple different device fingerprints from one phone line indicate tethering
- **Bypass**: GL-iNet routers support MAC cloning and DHCP client name manipulation
  - Camouflage mode (firmware 4.7+) sets MAC upper portion to disguise device
  - MAC cloning sets DHCP client name to "*"

### 2.6 Traffic Pattern Analysis (TERTIARY)

**Severity: LOW** — Statistical analysis, harder to implement per-user.

- Simultaneous connections to many different servers (typical of multiple devices)
- Traffic volume patterns inconsistent with single-device usage
- Concurrent streaming sessions from different services
- **Bypass**: Difficult to fully mask, but SOCKS proxy approach naturally consolidates connections through phone

### 2.7 Detection Method Summary Matrix

| Detection Method | Severity | TTL Fix? | VPN Fix? | SOCKS Fix? | Notes |
|---|---|---|---|---|---|
| APN-based (dun type) | CRITICAL | NO | NO | YES | iPhone hardcoded; SOCKS avoids hotspot entirely |
| TTL/HL analysis | HIGH | YES | PARTIAL | YES | Must set TTL=65 on router |
| TCP/IP fingerprinting | HIGH | NO | YES | YES | VPN encrypts headers; SOCKS uses phone's stack |
| Deep packet inspection | MEDIUM-HIGH | NO | YES | YES | Encryption prevents payload analysis |
| MAC/DHCP analysis | LOW-MEDIUM | NO | NO | YES | GL-iNet camouflage helps; SOCKS avoids entirely |
| Traffic patterns | LOW | NO | NO | PARTIAL | Statistical; hard to detect per-user |

---

## 3. Known Bypass Techniques — Rated by Effectiveness

### 3.1 SOCKS5 Proxy via Pythonista (Effectiveness: 9/10)

**Status: RECOMMENDED — Primary approach**

The iOS-SOCKS-Server project runs a SOCKS5/HTTP proxy directly on the iPhone using Pythonista. This is the most effective approach because:

- Traffic originates from the phone's own TCP/IP stack
- Uses the phone's primary data APN (NOT the hotspot APN)
- Phone creates new outbound TCP connections for each proxied request
- Carrier sees: TTL=64, iOS TCP fingerprint, normal traffic patterns
- No hotspot indicator is triggered at the network level

**How it works:**
1. iPhone runs SOCKS5 proxy server on its WiFi interface (e.g., port 1080)
2. Router connects to iPhone via WiFi or processes USB tethered data
3. Router runs `redsocks` to transparently redirect all LAN TCP traffic to the SOCKS5 proxy
4. All outbound internet traffic goes: LAN device → Router → redsocks → iPhone SOCKS5 → Internet
5. iPhone makes the actual TCP connections using its cellular data

**Limitations:**
- TCP only — UDP is not supported by standard SOCKS5 (DNS must use DoH/DoT)
- Requires Pythonista ($9.99) or similar Python runtime on iPhone
- Pythonista must remain running in foreground (iOS background limitations)
- Slight latency increase due to proxy hop
- Single point of failure (if Pythonista crashes, internet drops)

**Mitigations:**
- DNS handled via DNS-over-HTTPS (DoH) on router — TCP-based, goes through SOCKS
- Use iOS Shortcuts automation to relaunch Pythonista if killed
- Consider SOCKS5 with UDP ASSOCIATE extension for limited UDP support

### 3.2 TTL Mangling + VPN Tunnel (Effectiveness: 6/10)

**Status: FALLBACK — Partially effective**

Combining TTL modification with a VPN tunnel addresses multiple detection vectors:

- TTL set to 65 defeats TTL analysis
- VPN encryption defeats DPI and TCP fingerprinting
- **BUT**: Still uses the hotspot APN (iPhone Personal Hotspot must be active)
- T-Mobile may still detect tethering via APN monitoring
- Confirmed working on **Visible** (Verizon MVNO) but **unconfirmed on T-Mobile**

**Setup:**
~~~
iptables -t mangle -A POSTROUTING -o eth0 -j TTL --ttl-set 65
ip6tables -t mangle -A POSTROUTING -o eth0 -j HL --hl-set 65
~~~
Plus WireGuard/OpenVPN client to external VPN server.

**Why it may not work for T-Mobile:**
- T-Mobile's APN-based detection is at the network infrastructure level
- VPN encrypts content but doesn't change which APN the traffic traverses
- The iPhone's cellular modem reports hotspot data usage to T-Mobile's billing system

### 3.3 TTL Mangling Only (Effectiveness: 2/10)

**Status: INSUFFICIENT — Do not rely on**

Multiple sources confirm TTL mangling alone does NOT prevent T-Mobile from detecting tethering:

- GL-iNet forum: Beryl AX user confirmed TTL=65 did not prevent hotspot data counting on T-Mobile
- GrapheneOS forum: macOS and Windows TTL changes did not prevent detection
- Reddit r/GlInet: Multiple reports of TTL being insufficient for T-Mobile
- Only works for carriers that ONLY check TTL (some smaller MVNOs)

### 3.4 APN Modification (Effectiveness: 4/10 — Android only)

**Status: NOT APPLICABLE for iPhone**

- On Android, removing the "dun" APN type routes tethering through the normal data APN
- GrapheneOS does this by default, which is their primary bypass
- On rooted Android, creating a custom APN with `dun,default,mms,supl` can work
- **iPhone**: APN for Personal Hotspot is hardcoded in iOS carrier bundles; cannot be modified without jailbreak
- Even on Android, this approach can break when changing cell towers

### 3.5 PDANet / USB Tethering Apps (Effectiveness: 5/10)

**Status: ALTERNATIVE — Platform dependent**

- PDANet creates a VPN tunnel for tethered traffic
- Available for Android; iOS version limited
- Requires app running on both phone and connected device
- Not suitable for router-based solution (designed for direct phone-to-PC)
- WiFi sharing from PC adds latency and complexity

### 3.6 Custom APN + TTL (T-Mobile Android) (Effectiveness: 5/10)

**Status: Android only, unreliable**

- XDA method: Create APN with `fast.tmobile.net`, MVNO type GIO, APN type `dun,default,mms,supl`
- Combined with TTL=65
- Reported working by some users but breaks when changing towers
- Only works on rooted Android devices
- Not applicable to iPhone

### 3.7 Anti-DPI Tools (Effectiveness: 7/10 — as supplement)

**Status: SUPPLEMENTAL — For defense in depth**

- Projects like `felikcat/unlimited-hotspot` modify TCP/IP stack parameters:
  - TCP window size
  - TCP timestamp behavior
  - MSS clamping
  - IPv6 flow label randomization
- Must run on the tethered device (not the phone)
- Useful as additional layer but requires per-device configuration
- Can be applied at router level via iptables for all connected devices

### Technique Effectiveness Summary

| Technique | Rating | iPhone? | T-Mobile? | Complexity | Notes |
|---|---|---|---|---|---|
| SOCKS5 Proxy (Pythonista) | 9/10 | YES | YES | Medium | Primary recommendation |
| Anti-DPI + TTL + VPN | 7/10 | Partial | Maybe | High | Defense in depth |
| TTL + VPN | 6/10 | YES | Unconfirmed | Medium | Works on Visible |
| PDANet | 5/10 | Limited | Maybe | Low | Not router-compatible |
| Custom APN + TTL | 5/10 | NO | Partial | Medium | Android only |
| APN Modification | 4/10 | NO | Partial | Low | Android only |
| TTL Only | 2/10 | YES | NO | Low | Confirmed insufficient |

---

## 4. Recommended Multi-Layer Architecture

### 4.1 Primary: SOCKS5 Proxy Tunneling

The core bypass mechanism uses the iOS-SOCKS-Server running on Pythonista:

1. **iPhone** runs SOCKS5 proxy server on its WiFi interface
2. **GL-iNet Opal** connects to iPhone's WiFi hotspot (or USB tethering for control plane only)
3. **redsocks** on the router transparently redirects all LAN TCP traffic to iPhone's SOCKS5 proxy
4. **DNS-over-HTTPS** (DoH) on the router converts DNS queries to TCP/HTTPS (avoidings UDP leak)
5. **iptables** rules ensure no traffic bypasses the SOCKS tunnel

### 4.2 Defense in Depth: TTL Mangling

Even with the SOCKS proxy, apply TTL mangling as additional insurance:

~~~bash
# IPv4 TTL
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65

# IPv6 Hop Limit
ip6tables -t mangle -A POSTROUTING -j HL --hl-set 65
~~~

### 4.3 Defense in Depth: Device Camouflage

Use GL-iNet's built-in features (firmware 4.7+):

- **Camouflage mode**: Disguises router's MAC address OUI
- **DHCP client name**: Set to "*" or iPhone-like name
- **MAC cloning**: Clone iPhone's MAC address for WAN interface

### 4.4 Defense in Depth: DNS Leak Prevention

- All DNS queries must go through DoH (DNS-over-HTTPS) via TCP
- Standard UDP DNS queries would bypass the SOCKS proxy and leak to carrier
- Use `https-dns-proxy` package on OpenWrt or configure stubby
- Block all UDP port 53 traffic from LAN to prevent DNS leaks

### 4.5 Kill Switch

- If SOCKS proxy becomes unavailable, block all internet traffic rather than leaking
- iptables rules should DROP all non-SOCKS TCP and all UDP (except DoH) if proxy is down
- Health check script monitors SOCKS proxy availability

---

## 5. GL-iNet Opal (GL-SFT1200) Capabilities & Limitations

### 5.1 Hardware Specifications

| Component | Specification |
|---|---|
| Model | GL-SFT1200 (Opal) |
| CPU | SiFlower SF19A28, Dual-Core ARM @1GHz |
| RAM | 128MB DDR3 |
| Flash | 128MB SPI NAND |
| WiFi | Dual-band AC1200 (300+867 Mbps) |
| Ethernet | 1x WAN + 2x LAN (all Gigabit) |
| USB | 1x USB 2.0 Type-A |
| Power | USB-C, 5V/3A (power bank compatible) |
| Size/Weight | 118x85x30mm, 145g |

### 5.2 Software Platform

| Property | Value |
|---|---|
| Base OS | OpenWrt 18.06 (SiFlower SDK fork) |
| Kernel | Linux 4.14.x |
| Firewall | fw3 / iptables (NOT nftables) |
| Package Manager | opkg |
| Latest Stable | Firmware 4.3.25 |
| Latest Beta | Firmware 4.7.2 |
| Admin GUI | GL-iNet custom + LuCI |
| API | JSON-RPC (port 80/443) |

### 5.3 Key Capabilities for This Project

| Capability | Status | Notes |
|---|---|---|
| iPhone USB Tethering | Built-in | kmod-usb-net-ipheth, usbmuxd pre-installed |
| WiFi Client Mode | Built-in | Can connect to iPhone's hotspot |
| iptables TTL mangling | Supported | Requires iptables-mod-ipopt |
| IPv6 HL mangling | Supported | Via ip6tables |
| MASQUERADE | Supported | Standard NAT |
| WireGuard | Built-in | Client + server, ~55 Mbps throughput |
| OpenVPN | Built-in | Client + server, ~11-15 Mbps throughput |
| redsocks | Available | Via opkg install |
| DNS-over-HTTPS | Available | https-dns-proxy package |
| Custom firewall rules | Supported | /etc/firewall.user |
| Camouflage mode | 4.7+ only | MAC/DHCP disguise |
| SSH access | Built-in | Full root shell |

### 5.4 Limitations & Constraints

| Limitation | Impact | Mitigation |
|---|---|---|
| OpenWrt 18.06 (very outdated) | Security concerns, limited packages | GL-iNet maintains own patches |
| SiFlower SoC not in mainline OpenWrt | Cannot flash standard OpenWrt | Must use GL-iNet firmware |
| 128MB RAM | Limits concurrent connections | SOCKS proxy is lightweight |
| 128MB flash (~70-90MB available) | Package space limited | Shell scripts preferred over Python |
| USB 2.0 (not 3.0) | Max ~35 MBps throughput | Sufficient for cellular speeds |
| No Python3-full (too large) | Can't run complex Python on router | Proxy runs on iPhone, not router |
| WiFi limitations (AC1200) | Max ~867 Mbps on 5GHz | Far exceeds cellular speeds |

### 5.5 Firmware Recommendation

For this project, **Firmware 4.3.25 (latest stable)** is recommended:
- Stable iptables support
- Built-in WireGuard and OpenVPN
- USB tethering works reliably
- LuCI access for advanced configuration

Firmware 4.7.2 beta adds camouflage mode but has regressions:
- TX power reduced ~30dB (significant WiFi range reduction)
- Lost 5GHz DFS channel support
- Beta stability concerns

---

## 6. WireGuard vs OpenVPN Comparison

### 6.1 Performance on GL-iNet Opal

| Metric | WireGuard | OpenVPN |
|---|---|---|
| Throughput | ~55 Mbps | ~11-15 Mbps |
| CPU Usage | 5-8% | 38-45% |
| RAM Usage | 2-5 MB | 20-40 MB |
| Latency Overhead | ~1-3 ms | ~5-15 ms |
| iPhone Battery (4hr) | ~22% | ~31% |
| Kernel/Userspace | Kernel module | Userspace daemon |
| Protocol | UDP only | TCP or UDP |
| Encryption | ChaCha20-Poly1305 | AES-256-GCM (configurable) |

### 6.2 DPI Detection Characteristics

| Factor | WireGuard | OpenVPN |
|---|---|---|
| Protocol Fingerprint | Easily identifiable | Easily identifiable |
| DPI Detectable | YES | YES |
| Obfuscation Support | None built-in | stunnel/obfsproxy wrapping |
| Can mimic HTTPS | NO | YES (TCP 443 + stunnel) |
| Packet Size Patterns | Fixed header format | More variable |
| MTU Signature | 1420 (distinctive) | 1380-1400 (distinctive) |

### 6.3 Suitability for Tethering Bypass

**Neither WireGuard nor OpenVPN alone solves the tethering detection problem.**

The fundamental issue: VPNs encrypt the payload, but the transport-layer connection between the router and iPhone's tethering interface still uses the hotspot APN. T-Mobile detects tethering at the APN level before the VPN tunnel is even established.

VPNs are useful as a supplementary layer:
- Encrypt traffic to prevent DPI (if traffic somehow reaches carrier inspection)
- Can be used for external VPN server connection for additional privacy
- WireGuard is strongly preferred on Opal hardware due to 4x performance advantage

### 6.4 Local Tunnel Feasibility

For a local tunnel between iPhone and router (no external server):

| Factor | WireGuard | OpenVPN |
|---|---|---|
| Local tunnel possible | YES | YES |
| Practical benefit | Minimal | Minimal |
| Reason | Doesn't change APN | Doesn't change APN |
| Better alternative | SOCKS5 proxy | SOCKS5 proxy |

### 6.5 Recommendation

**For this project: SOCKS5 proxy is superior to any VPN approach.**

If a VPN is needed (e.g., external VPN server for privacy), use WireGuard:
- 4x faster on Opal hardware
- Lower battery impact on iPhone
- Simpler configuration
- Built into GL-iNet firmware

---

## 7. Technical Requirements

### 7.1 iPhone Requirements

| Requirement | Details |
|---|---|
| iOS Version | 14+ (Pythonista compatibility) |
| App: Pythonista 3 | $9.99 on App Store — runs Python on iOS |
| iOS-SOCKS-Server | Python script from nneonneo/iOS-SOCKS-Server |
| WiFi | Must be on same network as router OR create ad-hoc |
| Cellular Data | Active T-Mobile plan with unlimited on-device data |
| Personal Hotspot | May need to be ON for WiFi AP mode, OR use USB |
| Storage | Minimal (<50MB for Pythonista + scripts) |

### 7.2 Router Requirements

| Requirement | Details |
|---|---|
| Hardware | GL-iNet Opal GL-SFT1200 |
| Firmware | 4.3.25 (stable) recommended |
| Additional Packages | redsocks, https-dns-proxy, iptables-mod-ipopt |
| Configuration | Custom firewall rules, redsocks config, DoH setup |
| Network Mode | WiFi client (to iPhone) + WiFi AP (to LAN devices) |

### 7.3 Network Configuration Requirements

| Component | Configuration |
|---|---|
| Router WAN | WiFi client connected to iPhone's WiFi OR USB tethering |
| Router LAN | WiFi AP on separate band/channel for client devices |
| SOCKS5 Proxy | Running on iPhone, accessible from router |
| redsocks | Transparently redirect TCP to SOCKS5 proxy |
| DNS | DoH (DNS-over-HTTPS) for all DNS resolution |
| Firewall | Block non-proxied traffic (kill switch) |
| TTL | Set to 65 for all outbound packets |

### 7.4 Software Components to Develop/Configure

| Component | Platform | Description |
|---|---|---|
| SOCKS5 Proxy Server | iPhone (Pythonista) | Already exists in iOS-SOCKS-Server |
| Router Plugin | OpenWrt (Opal) | Auto-configure redsocks, iptables, DoH |
| Health Monitor | OpenWrt (Opal) | Check SOCKS proxy availability, trigger kill switch |
| Auto-Setup Script | OpenWrt (Opal) | One-command installation of all components |
| Connection Manager | OpenWrt (Opal) | Manage WiFi client connection to iPhone |

---

## 8. Architecture Diagram & Traffic Flow

### 8.1 Network Topology

~~~
                                    ┌─────────────────────────────┐
                                    │        T-MOBILE NETWORK      │
                                    │                               │
                                    │  Sees: Normal iPhone traffic  │
                                    │  TTL=64, iOS TCP fingerprint  │
                                    │  Primary data APN             │
                                    │  NO hotspot indicator         │
                                    └───────────────┬───────────────┘
                                                    │
                                                    │ Cellular (LTE/5G)
                                                    │
                                    ┌───────────────┴───────────────┐
                                    │         iPHONE                 │
                                    │                                │
                                    │  ┌──────────────────────┐     │
                                    │  │  Pythonista App       │     │
                                    │  │  ┌──────────────────┐ │     │
                                    │  │  │ SOCKS5 Proxy     │ │     │
                                    │  │  │ Port 1080        │ │     │
                                    │  │  │                  │ │     │
                                    │  │  │ Creates NEW TCP  │ │     │
                                    │  │  │ connections via  │ │     │
                                    │  │  │ phone's cellular │ │     │
                                    │  │  │ data socket      │ │     │
                                    │  │  └──────────────────┘ │     │
                                    │  └──────────────────────┘     │
                                    │                                │
                                    │  WiFi AP: 192.168.2.1         │
                                    │  (Personal Hotspot or ad-hoc) │
                                    └───────────────┬───────────────┘
                                                    │
                                                    │ WiFi (5GHz preferred)
                                                    │
                                    ┌───────────────┴───────────────┐
                                    │     GL-iNet OPAL ROUTER       │
                                    │                                │
                                    │  WAN: WiFi Client → iPhone    │
                                    │  IP: 192.168.2.x (from iPhone)│
                                    │                                │
                                    │  ┌──────────────────────┐     │
                                    │  │ redsocks             │     │
                                    │  │ Transparent SOCKS5   │     │
                                    │  │ redirector           │     │
                                    │  │ Local port: 12345    │     │
                                    │  │ Remote: 192.168.2.1  │     │
                                    │  │         :1080        │     │
                                    │  └──────────────────────┘     │
                                    │                                │
                                    │  ┌──────────────────────┐     │
                                    │  │ iptables             │     │
                                    │  │ - TTL=65 (mangle)    │     │
                                    │  │ - REDIRECT TCP to    │     │
                                    │  │   redsocks (NAT)     │     │
                                    │  │ - Block UDP except   │     │
                                    │  │   DoH (kill switch)  │     │
                                    │  └──────────────────────┘     │
                                    │                                │
                                    │  ┌──────────────────────┐     │
                                    │  │ https-dns-proxy      │     │
                                    │  │ DNS-over-HTTPS       │     │
                                    │  │ (Cloudflare/Google)  │     │
                                    │  └──────────────────────┘     │
                                    │                                │
                                    │  LAN: WiFi AP 192.168.8.1     │
                                    │  (2.4GHz or 5GHz, separate)   │
                                    └───────────────┬───────────────┘
                                                    │
                                                    │ WiFi / Ethernet
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            │                       │                       │
                    ┌───────┴───────┐       ┌───────┴───────┐       ┌───────┴───────┐
                    │   Laptop      │       │   Tablet      │       │   Smart TV    │
                    │   Any OS      │       │   Any OS      │       │   Any OS      │
                    │   No config   │       │   No config   │       │   No config   │
                    │   needed      │       │   needed      │       │   needed      │
                    └───────────────┘       └───────────────┘       └───────────────┘
~~~

### 8.2 Detailed Traffic Flow (TCP)

~~~
Step 1: Laptop sends HTTP request to example.com
        Laptop → [TCP SYN, TTL=128 (Windows)] → Router LAN interface

Step 2: Router iptables intercepts on br-lan
        iptables -t nat -A PREROUTING -i br-lan -p tcp -j REDSOCKS
        → Redirects to local redsocks port 12345

Step 3: redsocks wraps in SOCKS5 protocol
        redsocks → [SOCKS5 CONNECT example.com:80] → iPhone:1080
        (via Router WAN WiFi interface to iPhone WiFi)

Step 4: iPhone SOCKS5 proxy creates NEW connection
        iPhone → [TCP SYN, TTL=64, iOS fingerprint] → T-Mobile → example.com
        *** This is the key: T-Mobile sees iPhone's native TCP stack ***

Step 5: Response flows back
        example.com → T-Mobile → iPhone → SOCKS5 → redsocks → Router → Laptop

Step 6: Router applies TTL mangling (defense in depth)
        iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65
~~~

### 8.3 DNS Traffic Flow

~~~
Step 1: Laptop sends DNS query for example.com
        Laptop → [UDP:53 DNS query] → Router (192.168.8.1)

Step 2: Router's https-dns-proxy intercepts
        Local DNS server (dnsmasq) forwards to https-dns-proxy
        https-dns-proxy converts to HTTPS request:
        → [TCP:443 HTTPS POST] → https://cloudflare-dns.com/dns-query

Step 3: TCP HTTPS request is captured by iptables/redsocks
        → Redirected through SOCKS5 proxy on iPhone
        → iPhone makes HTTPS request to Cloudflare DNS

Step 4: DNS response flows back through same path
        Cloudflare → iPhone → SOCKS5 → redsocks → https-dns-proxy → dnsmasq → Laptop

Result: DNS queries are encrypted AND routed through SOCKS proxy
        T-Mobile cannot see DNS queries or destinations
~~~

---

## 9. Implementation Roadmap

### Phase 1: Core SOCKS Infrastructure

1. **Validate iOS-SOCKS-Server** on iPhone via Pythonista
   - Test SOCKS5 proxy connectivity from a laptop
   - Measure throughput and latency
   - Test stability (how long before Pythonista is killed by iOS)

2. **Configure GL-iNet Opal**
   - Update to firmware 4.3.25
   - Install packages: `redsocks`, `iptables-mod-ipopt`, `https-dns-proxy`
   - Connect to iPhone's WiFi hotspot as WAN
   - Configure redsocks to point to iPhone's SOCKS5 proxy
   - Set up iptables transparent redirect rules
   - Configure DNS-over-HTTPS

3. **Test end-to-end**
   - Connect a laptop to Opal's WiFi
   - Verify all TCP traffic goes through SOCKS proxy
   - Verify DNS goes through DoH
   - Check for IP/DNS leaks
   - Monitor T-Mobile data usage (should show as on-device, not hotspot)

### Phase 2: Reliability & Automation

4. **Create router plugin package**
   - Auto-install and configure all required packages
   - Generate redsocks config based on iPhone's IP
   - Set up iptables rules that persist across reboots
   - Health monitoring script (check SOCKS proxy, reconnect if needed)
   - Kill switch (block traffic if proxy unavailable)

5. **iPhone auto-configuration**
   - Pythonista script that auto-starts SOCKS proxy
   - iOS Shortcuts integration for auto-launch
   - Status indicator/notification

### Phase 3: Defense in Depth

6. **Apply additional camouflage**
   - TTL mangling (65 for IPv4, 65 for IPv6 HL)
   - MAC address cloning
   - DHCP client name spoofing
   - Consider firmware 4.7.x for built-in camouflage features

7. **Optional: External VPN**
   - WireGuard to external VPN server for additional privacy
   - Routes through SOCKS proxy like all other traffic
   - Provides IP address change beyond carrier tunnel

### Phase 4: Polish & Packaging

8. **Create installable OpenWrt package (.ipk)**
   - Standard opkg-installable package
   - Web UI integration (LuCI app or GL-iNet plugin)
   - Configuration wizard
   - Status dashboard
   - One-click enable/disable

---

## 10. Risk Assessment

### 10.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Pythonista killed by iOS | HIGH | Internet drops | Kill switch + auto-restart + Shortcuts |
| iPhone WiFi hotspot power drain | MEDIUM | Battery dies | USB power + optimize proxy code |
| T-Mobile updates detection | LOW | Bypass stops working | Multi-layer approach provides redundancy |
| redsocks performance bottleneck | LOW | Slow speeds | redsocks is lightweight; cellular is bottleneck |
| DNS leaks via UDP | MEDIUM | Tethering detected | Block all UDP port 53; enforce DoH |
| OpenWrt 18.06 security | MEDIUM | Vulnerabilities | Limit exposure; router is behind iPhone |
| SOCKS5 TCP-only limitation | MEDIUM | Some apps break | Most modern apps use TCP; gaming may suffer |

### 10.2 Legal/Policy Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| T-Mobile TOS violation | HIGH | Account suspension/termination | Use within reason; avoid excessive data |
| Throttling rather than termination | HIGH | Reduced speeds | Monitor data patterns |
| Plan changes by T-Mobile | LOW | Feature removed | Have backup plan/carrier |

### 10.3 Operational Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Complex setup deters users | MEDIUM | Low adoption | Auto-setup script + documentation |
| iPhone must stay running | HIGH | Single point of failure | Power management + monitoring |
| WiFi interference | LOW | Connection drops | Use 5GHz; short distance |
| Router overheating | LOW | Performance degradation | Good ventilation; portable design |

---

## 11. References

### Primary Sources

1. **iOS-SOCKS-Server** — nneonneo/iOS-SOCKS-Server
   - https://github.com/nneonneo/iOS-SOCKS-Server
   - SOCKS5/HTTP proxy for iPhone via Pythonista

2. **redsocks Transparent Proxy** — darkk/redsocks
   - https://github.com/darkk/redsocks
   - TCP-to-SOCKS transparent redirector

3. **redsocks Tethering Bypass Gist** — softmoth
   - https://gist.github.com/softmoth/039e2879198f298a41f0924f9fd357c2
   - Complete setup guide for OpenWrt + redsocks + SOCKS5 tethering bypass

4. **tether-throttle-bypass** — fqlx
   - https://github.com/fqlx/tether-throttle-bypass
   - TTL-based bypass for GL-iNet routers (insufficient alone for T-Mobile)

5. **GL-iNet Opal Documentation**
   - https://docs.gl-inet.com/router/en/4/interface_guide/internet_tethering/
   - Official tethering documentation

### Community Research Sources

6. **GL-iNet Forum: iPhone Tethering on T-Mobile**
   - https://forum.gl-inet.com/t/iphone-tethering-on-t-mobile-and-throttling-issues/23482

7. **GL-iNet Forum: Beryl AX TTL Doesn't Avoid Hotspot Data**
   - https://forum.gl-inet.com/t/beryl-ax-usb-iphone-tethering-mangling-ttl-doesnt-avoid-hotspot-data/56191
   - Confirms TTL alone insufficient for T-Mobile

8. **GrapheneOS: Tethering Detected by T-Mobile**
   - https://discuss.grapheneos.org/d/5683-tethering-is-being-detected-by-t-mobile
   - Detailed analysis of T-Mobile detection methods

9. **XDA Forums: Enabling Full Speed Hotspot/Tethering**
   - https://xdaforums.com/t/guide-enabling-full-speed-hotspot-tethering-throttle-bypasses.3905948/
   - Comprehensive guide with multiple techniques

10. **XDA Forums: T-Mobile Hotspot Tethering Bypass**
    - https://xdaforums.com/t/t-mobile-hotspot-tethering-bypass.4151227/

11. **XDA Forums: Bypass Hotspot Detection**
    - https://xdaforums.com/t/bypass-hotspot-detection.4658123/
    - Mentions Tetrd for USB cable approach

12. **Reddit r/NoContract: Bypassing Hotspot Throttle MVNO**
    - https://www.reddit.com/r/NoContract/comments/1cszmsq/bypassing_hotspot_throttle_mvno/
    - APN is primary detection; DPI secondary

13. **Reddit r/GlInet: TTL to Avoid Hotspot Data**
    - https://www.reddit.com/r/GlInet/comments/1ocwwzz/setting_ttl_to_avoid_hotspot_data_usage_via_usb/

14. **Reddit r/GlInet: Change TTL on Router**
    - https://www.reddit.com/r/GlInet/comments/1cgrcgp/just_wondering_if_anybody_knows_how_to_change_ttl/

15. **Juraj Bednar: Bypassing Hotspot Restrictions**
    - https://juraj.bednar.io/en/blog-en/2025/03/07/bypassing-hotspot-restrictions-for-data/

16. **GroovyPost: Hide Data Usage T-Mobile**
    - https://www.groovypost.com/howto/hide-data-usage-get-truly-unlimited-tethering-tmobile-one/

### Technical References

17. **OpenWrt iptables TTL documentation**
    - https://openwrt.org/docs/guide-user/firewall/firewall_configuration

18. **GL-iNet SDK (GitHub)**
    - https://github.com/gl-inet/sdk
    - For custom package development

19. **GL-iNet Firmware Downloads**
    - https://dl.gl-inet.com/router/sft1200/

20. **https-dns-proxy for OpenWrt**
    - DNS-over-HTTPS proxy package for OpenWrt

---

## Appendix A: Key Configuration Files

### A.1 redsocks.conf

~~~conf
base {
    log_debug = off;
    log_info = on;
    log = "syslog:daemon";
    daemon = on;
    redirector = iptables;
}

redsocks {
    local_ip = 0.0.0.0;
    local_port = 12345;
    ip = 192.168.2.1;      // iPhone's WiFi IP
    port = 1080;            // SOCKS5 proxy port
    type = socks5;
}
~~~

### A.2 iptables Rules (Transparent Redirect)

~~~bash
#!/bin/sh
# /etc/firewall.user

# Create REDSOCKS chain
iptables -t nat -N REDSOCKS 2>/dev/null || iptables -t nat -F REDSOCKS

# Exclude local/private addresses
iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 224.0.0.0/4 -j RETURN
iptables -t nat -A REDSOCKS -d 240.0.0.0/4 -j RETURN

# Redirect all remaining TCP to redsocks
iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345

# Apply to LAN traffic
iptables -t nat -A PREROUTING -i br-lan -p tcp -j REDSOCKS

# TTL mangling (defense in depth)
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65
ip6tables -t mangle -A POSTROUTING -j HL --hl-set 65

# Kill switch: block UDP except established and DoH
iptables -A FORWARD -i br-lan -p udp --dport 53 -j DROP
~~~

### A.3 DNS-over-HTTPS Configuration

~~~conf
# /etc/config/https-dns-proxy
config https-dns-proxy
    option bootstrap_dns '1.1.1.1,8.8.8.8'
    option resolver_url 'https://cloudflare-dns.com/dns-query'
    option listen_addr '127.0.0.1'
    option listen_port '5053'
~~~

### A.4 Package Installation Commands

~~~bash
# Install required packages on GL-iNet Opal
opkg update
opkg install redsocks
opkg install iptables-mod-ipopt     # For TTL mangling
opkg install https-dns-proxy        # For DNS-over-HTTPS
opkg install luci-app-https-dns-proxy  # Optional: LuCI UI
~~~

---

## Appendix B: Alternative Architecture (USB Tethering Mode)

If WiFi client mode is unreliable or introduces too much latency, an alternative uses USB:

~~~
[LAN Devices] ←WiFi→ [GL-iNet Opal] ←USB Cable→ [iPhone]
                       │                            │
                       │ redsocks redirects TCP     │ SOCKS5 proxy
                       │ to iPhone via USB network  │ on WiFi interface
                       │                            │
                       └── USB tethering creates ───┘
                           172.20.10.x network
~~~

In USB mode:
- iPhone creates a network interface on 172.20.10.0/28
- Router gets IP 172.20.10.x via DHCP
- iPhone is at 172.20.10.1
- redsocks connects to 172.20.10.1:1080
- **Caveat**: USB tethering STILL activates the hotspot APN on iPhone
- The SOCKS proxy must be running and traffic must go through it, NOT through the USB tethering IP routing
- This requires careful iptables rules to ensure all traffic goes through SOCKS, not the default USB route

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| APN | Access Point Name — gateway between carrier network and internet |
| DPI | Deep Packet Inspection — analyzing packet contents beyond headers |
| DoH | DNS-over-HTTPS — encrypted DNS using HTTPS protocol |
| DUN | Dial-Up Networking — APN type used for tethered/hotspot traffic |
| HL | Hop Limit — IPv6 equivalent of TTL |
| MASQUERADE | iptables NAT target that rewrites source IP to outgoing interface IP |
| MVNO | Mobile Virtual Network Operator — resells major carrier service |
| NAT | Network Address Translation — maps private IPs to public IPs |
| OUI | Organizationally Unique Identifier — first 3 bytes of MAC address |
| redsocks | Transparent TCP-to-proxy redirector daemon |
| SNI | Server Name Indication — TLS extension revealing destination hostname |
| SOCKS5 | Socket Secure v5 — proxy protocol for routing TCP connections |
| TTL | Time To Live — IP header field decremented at each router hop |

---

*Document generated by Deep Research Agent — 2026-04-27*
*For implementation details, see individual research files in /docs/*
