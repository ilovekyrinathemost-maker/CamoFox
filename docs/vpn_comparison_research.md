# VPN Protocol Comparison Research: Hiding Tethering on GL-iNet Opal

**Research Date**: 2026-04-27  
**Purpose**: Determine optimal protocol for tunneling data from GL-iNet Opal router through iPhone without T-Mobile detecting hotspot usage  
**Target Hardware**: GL-iNet Opal (GL-SFT1200) — 128MB RAM, MIPS architecture, OpenWrt-based firmware

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How T-Mobile Detects Tethering](#how-t-mobile-detects-tethering)
3. [WireGuard Analysis](#wireguard-analysis)
4. [OpenVPN Analysis](#openvpn-analysis)
5. [Alternative Tunneling Approaches](#alternative-tunneling-approaches)
6. [Head-to-Head Comparison](#head-to-head-comparison)
7. [The Critical Architecture Question](#the-critical-architecture-question)
8. [Recommended Architecture](#recommended-architecture)
9. [References](#references)

---

## 1. Executive Summary

For hiding tethering traffic from T-Mobile using a GL-iNet Opal travel router connected to an iPhone, **neither WireGuard nor OpenVPN alone is the optimal solution**. The most effective approach is a **SOCKS5 proxy running on the iPhone** with **redsocks transparent proxy on the router**, optionally wrapped in a local VPN tunnel for encryption.

Key findings:
- T-Mobile primarily detects tethering via **TTL decrement** (64→63) and **TCP/IP stack fingerprinting**
- The SOCKS proxy approach defeats ALL detection methods because traffic originates from the phone's own IP stack
- WireGuard is vastly superior on the Opal hardware (~55 Mbps vs ~12 Mbps for OpenVPN)
- WireGuard is detectable by DPI but this is **irrelevant for local tunnels** — T-Mobile isn't blocking VPNs, they're detecting tethering
- A hybrid approach (SOCKS proxy + optional WireGuard wrapper) provides the best balance

---

## 2. How T-Mobile Detects Tethering

### 2.1 Primary Method: TTL Analysis

T-Mobile's primary detection mechanism inspects the **Time-To-Live (TTL)** field in IP packet headers.

- **Normal phone traffic**: Packets originate with TTL=64 (iOS/Android default)
- **Tethered traffic**: Packets from connected devices (laptop, router) start with TTL=64 but the phone decrements to TTL=63 when routing
- **Detection**: T-Mobile flags any packets with TTL < 64 as hotspot/tethered traffic
- **Action**: Flagged traffic is throttled or counted against hotspot data cap

**Source**: T-Mobile throttle defeat project (GitHub: niski84/t-mobile-throttle-defeat); multiple Reddit/XDA confirmations

### 2.2 Secondary Method: TCP/IP Stack Fingerprinting

Based on academic research (Yi-Chao Chen et al., IMC 2014 — "OS Fingerprinting and Tethering Detection in Mobile Networks"), carriers can use multiple TCP/IP header features:

| Feature | How It Detects Tethering | Accuracy |
|---------|-------------------------|----------|
| **TTL values** | Multiple distinct TTLs from one IP = tethering | 92-96% precision |
| **TCP Timestamp Monotonicity** | Non-monotonic timestamps = multiple devices | ~95% coverage |
| **TCP Window Size Scale** | iOS=16, Android=64, Windows=256; mixed values = tethering | Deterministic for iOS |
| **Clock Frequency Std Dev** | High variance = multiple device clocks | Threshold-based |
| **Boot Time Std Dev** | Different boot times from TCP timestamps = multiple devices | Threshold-based |
| **IP ID Monotonicity** | Different IP ID sequences = multiple devices | OS-dependent |

**Critical insight**: These methods analyze TCP/IP header metadata, NOT packet contents. A VPN encrypts content but the encrypted packets still carry the tethered device's TCP/IP fingerprint characteristics UNLESS the connection is re-originated from the phone itself.

### 2.3 Tertiary Methods (Less Common)

- **HTTP User-Agent sniffing**: Browser UA strings reveal OS (Windows/macOS vs iOS) — defeated by HTTPS encryption
- **DNS query patterns**: Desktop apps query different domains than mobile apps
- **MTU analysis**: VPN tunnels reduce MTU (WireGuard=1420, OpenVPN=1380 vs standard 1500)
- **IMEI/TAC fingerprinting**: Device type identification via hardware identifiers

### 2.4 What T-Mobile Is NOT Doing

T-Mobile is **not** performing deep packet inspection to block VPN protocols. They are not China's Great Firewall. Their goal is to identify tethered traffic for throttling/metering, not to block encrypted tunnels. This distinction is critical for protocol selection.

---

## 3. WireGuard Analysis

### 3.1 Protocol Characteristics

- **Protocol type**: UDP-only, kernel-level implementation
- **Codebase**: ~4,000 lines of code (extremely lean)
- **Encryption**: ChaCha20, Poly1305, Curve25519, BLAKE2s
- **Connection time**: ~100ms cold start, ~50ms reconnect
- **Overhead**: Minimal — runs in kernel space

### 3.2 DPI Detectability

WireGuard is **officially acknowledged as detectable by DPI**:

> "WireGuard does not focus on obfuscation. Obfuscation, rather, should happen at a layer above WireGuard."
> — wireguard.com/known-limitations/

**Detection vectors**:
- Fixed packet structure patterns (handshake initiation = 148 bytes, response = 92 bytes)
- `mac1` field computed over responder's public key (can be trial-hashed)
- UDP-only traffic on consistent port
- Distinctive packet length distribution
- MTU of 1420 (detectable via PMTUD)

**DPI detection status globally** (dpi.watch):
- Actively detected/blocked in: China (GFW), Russia, Iran, Jordan, some Middle Eastern countries
- Machine learning classifiers can identify WireGuard with high confidence from traffic patterns

**Relevance to our use case**: LOW. T-Mobile is not blocking VPN protocols. They're detecting tethering via TTL/fingerprinting. WireGuard's DPI visibility is irrelevant for this application.

### 3.3 Performance on GL-iNet Opal (GL-SFT1200)

| Metric | WireGuard | Notes |
|--------|-----------|-------|
| **Throughput** | ~55 Mbps | Via Ethernet, per GL-iNet forum |
| **CPU Impact** | Low (kernel module) | 5-8% CPU usage |
| **RAM Usage** | Minimal (~2-5 MB) | Kernel module, no userspace daemon |
| **Official Support** | Yes | Built into GL-iNet firmware |
| **Max Advertised** | 65 Mbps | Per GL-iNet spec sheet |

### 3.4 iPhone Integration

- **Native iOS app**: WireGuard app available on App Store (free)
- **Configuration**: Simple QR code or config file import
- **Battery impact**: 22% over 4 hours (vs 18% baseline) — minimal drain
- **Wake-ups/hour**: 15 (very efficient)
- **Connection stability**: Excellent roaming support, survives network switches
- **Can run as server on iPhone**: NO — iOS does not allow running WireGuard server. Can only be a client.

### 3.5 Local Tunnel Feasibility

**Router as WireGuard server, iPhone as client**: YES — The Opal can run WireGuard server. The iPhone connects as a WireGuard client to the router. Traffic from the internet flows: Internet → T-Mobile → iPhone → WireGuard tunnel → Router → LAN devices.

**Problem**: In this configuration, the iPhone still uses its native tethering/hotspot to provide connectivity to the router. The WireGuard tunnel runs OVER the tethered connection. T-Mobile still sees the outer packets with decremented TTL. The VPN wraps the content but doesn't change the transport-layer fingerprint.

**iPhone as WireGuard server, Router as client**: NOT POSSIBLE on stock iOS. iOS doesn't allow running a WireGuard server.

### 3.6 OpenWrt Kernel Module Availability

- **OpenWrt 19.07+**: WireGuard available as `kmod-wireguard` package
- **OpenWrt 21.02+**: WireGuard in mainline Linux kernel (5.6+), native support
- **GL-iNet firmware**: Ships with WireGuard support pre-installed
- **Kernel version**: GL-iNet Opal runs Linux 4.14 (OpenWrt 19.07 base), uses backported `kmod-wireguard`

### 3.7 Obfuscation Options for WireGuard

| Method | Description | Feasibility on Opal |
|--------|-------------|---------------------|
| **AmneziaWG** | WireGuard fork with built-in obfuscation | NOT supported on Opal (only Brume 3, Flint 2/3, Beryl AX with firmware 4.9+) |
| **udp2raw** | Wraps UDP in fake TCP/ICMP headers | Possible but adds overhead, complex setup |
| **wstunnel** | Tunnels WireGuard over WebSocket/HTTPS | Heavy for 128MB RAM, complex |
| **Shadowsocks wrapping** | Encrypt WireGuard UDP in Shadowsocks | Possible but convoluted |

---

## 4. OpenVPN Analysis

### 4.1 Protocol Characteristics

- **Protocol type**: UDP or TCP, userspace implementation
- **Codebase**: ~100,000+ lines of code
- **Encryption**: OpenSSL library (AES-256-GCM, etc.)
- **Connection time**: 8-10 seconds cold start, 2-3 seconds reconnect
- **Overhead**: High — runs entirely in userspace, TLS handshake

### 4.2 DPI Detectability

OpenVPN is **highly detectable by DPI** even with basic obfuscation:

- TCP mode has distinctive TLS handshake patterns
- UDP mode has recognizable opcode bytes in packet headers
- Even on TCP port 443, DPI can distinguish OpenVPN from regular HTTPS
- China's GFW, Russia's TSPU, and other censorship systems actively block OpenVPN

**Obfuscation options**:
- **TCP port 443**: Simplest but still detectable by advanced DPI
- **stunnel wrapping**: Wraps OpenVPN in genuine TLS — effective against basic DPI
- **obfsproxy/obfs4**: Tor pluggable transports — effective but resource-heavy
- **Shapeshifter Dispatcher**: Designed for DPI evasion — moderate resource usage
- **XOR patch (--scramble)**: Weak obfuscation, easily detected by modern DPI

### 4.3 Performance on GL-iNet Opal (GL-SFT1200)

| Metric | OpenVPN | Notes |
|--------|---------|-------|
| **Throughput** | ~11-15 Mbps | Per GL-iNet forum benchmarks |
| **CPU Impact** | Very High (38-45%) | Single-threaded userspace process |
| **RAM Usage** | ~20-40 MB | OpenSSL + daemon overhead |
| **Official Support** | Yes | Built into GL-iNet firmware |
| **Max Advertised** | 12 Mbps | Per GL-iNet spec sheet |

**OpenVPN is severely bottlenecked on the Opal's MIPS CPU.** The Opal lacks AES hardware acceleration, making OpenVPN's AES encryption extremely expensive. This is the single biggest disadvantage.

### 4.4 iPhone Integration

- **Native app**: OpenVPN Connect on App Store (free)
- **Configuration**: .ovpn config file import
- **Battery impact**: 31% over 4 hours (vs 18% baseline) — significant drain
- **Wake-ups/hour**: 45 (3x more than WireGuard)
- **Connection stability**: Slower reconnection, TCP retransmission issues on mobile
- **Can run as server on iPhone**: NO — iOS doesn't allow running OpenVPN server

### 4.5 Local Tunnel Feasibility

Same limitations as WireGuard — iOS cannot run a VPN server. The router can run an OpenVPN server, but the iPhone connecting as a client still uses native tethering to reach the router.

### 4.6 Stunnel Wrapping on GL-iNet

GL-iNet forum confirms stunnel can be installed via LuCI on OpenWrt:
- Install `stunnel` package via `opkg`
- Configure stunnel to wrap OpenVPN TCP traffic in TLS
- Routes: OpenVPN → stunnel → TLS tunnel to router
- **Performance impact**: Additional TLS overhead on already slow OpenVPN = likely 5-8 Mbps
- **RAM impact**: stunnel adds ~5-10 MB RAM usage

---

## 5. Alternative Tunneling Approaches

### 5.1 SSH Tunneling (SOCKS Proxy over SSH)

**How it works**: Run an SSH server on the phone, create a SOCKS proxy via `ssh -D`.

| Aspect | Details |
|--------|----------|
| **DPI resistance** | SSH traffic on port 22 is common and rarely blocked |
| **Performance** | Moderate — userspace, single-threaded |
| **iPhone support** | Requires jailbreak or special SSH server app |
| **Setup complexity** | Moderate — SSH + SOCKS proxy config on router |
| **Battery impact** | Moderate |

**Limitation**: Requires running an SSH server on iOS, which is not natively supported without jailbreak.

### 5.2 Shadowsocks

**How it works**: Lightweight encrypted SOCKS5 proxy protocol designed for DPI evasion.

| Aspect | Details |
|--------|----------|
| **DPI resistance** | Good — designed specifically for censorship circumvention |
| **Performance** | Very good — lightweight encryption (chacha20-ietf-poly1305) |
| **OpenWrt support** | Yes — `shadowsocks-libev` in OpenWrt repos (up to 23.05) |
| **RAM usage** | ~5-10 MB |
| **iPhone support** | Client apps available (Shadowrocket, Potatso Lite) |
| **Setup complexity** | Moderate |

**For local tunnel use**: Could run Shadowsocks server on the router, client on iPhone. Traffic flows through the phone's network but is encrypted. However, this DOESN'T solve the TTL problem — packets still traverse the tethering interface with decremented TTL.

### 5.3 V2Ray / VLESS / VMess

**How it works**: Advanced proxy protocols with sophisticated traffic obfuscation.

| Aspect | Details |
|--------|----------|
| **DPI resistance** | Excellent — VLESS+XTLS can mimic genuine TLS traffic |
| **Performance** | Good with VLESS, moderate with VMess |
| **OpenWrt support** | Available via passwall/ShadowSocksR packages |
| **RAM usage** | ~30-50 MB (heavy for 128MB Opal) |
| **iPhone support** | Client apps (Shadowrocket, V2Box) |
| **Setup complexity** | High |

**Verdict**: Overkill for this use case. Designed to evade nation-state censorship (China's GFW), not carrier tethering detection. Too resource-heavy for the Opal.

### 5.4 SOCKS5 Proxy on iPhone (iOS-SOCKS-Server Approach)

**How it works**: Run a SOCKS5/HTTP proxy server directly on the iPhone using Pythonista. The router connects to the phone's hotspot and routes ALL traffic through the SOCKS proxy. The phone creates NEW TCP connections with its own IP stack.

| Aspect | Details |
|--------|----------|
| **Tethering detection bypass** | COMPLETE — all traffic originates from phone's IP stack |
| **TTL issue** | SOLVED — phone creates packets with TTL=64 |
| **TCP fingerprint** | SOLVED — phone's own TCP/IP stack used for all connections |
| **Performance** | Near-native — minimal proxy overhead |
| **iPhone support** | Yes — Pythonista app (no jailbreak needed) |
| **Encryption** | NONE (plain SOCKS5) — content visible to carrier |
| **Router support** | redsocks transparent proxy on OpenWrt |
| **Setup complexity** | Moderate |

**This is the approach from the iOS-SOCKS-Server project referenced in our project repository.**

### 5.5 Redsocks (Transparent SOCKS Redirector on Router)

**How it works**: Installed on OpenWrt, intercepts all outgoing TCP traffic via iptables and redirects through a SOCKS5 proxy.

**Architecture**:
```
[LAN Devices] → [Router (redsocks + iptables)] → [iPhone Hotspot] → [SOCKS5 proxy on iPhone] → [Internet]
```

**iptables rules** (proven working from community):
```bash
# Create REDSOCKS chain
iptables -t nat -N REDSOCKS
# Exclude local/private traffic
iptables -t nat -A REDSOCKS -d 0.0.0.0/8 -j RETURN
iptables -t nat -A REDSOCKS -d 127.0.0.0/8 -j RETURN
iptables -t nat -A REDSOCKS -d 10.0.0.0/8 -j RETURN
iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 224.0.0.0/4 -j RETURN
iptables -t nat -A REDSOCKS -d 240.0.0.0/4 -j RETURN
# Redirect TCP to redsocks port
iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
# Apply to LAN traffic
iptables -t nat -A PREROUTING -i br-lan -p tcp -j REDSOCKS
```

**redsocks.conf**:
```
base {
    redirector = iptables;
}
redsocks {
    local_ip = 0.0.0.0;
    local_port = 12345;
    ip = 172.20.10.1;    // iPhone hotspot IP
    port = 9876;          // SOCKS5 proxy port on iPhone
    type = socks5;
}
```

---

## 6. Head-to-Head Comparison

### 6.1 Performance Comparison on GL-iNet Opal

| Metric | WireGuard | OpenVPN UDP | OpenVPN TCP | Shadowsocks | SOCKS5 Proxy |
|--------|-----------|-------------|-------------|-------------|---------------|
| **Throughput** | ~55 Mbps | ~15 Mbps | ~11 Mbps | ~30-40 Mbps* | ~50+ Mbps |
| **CPU Usage** | 5-8% | 38-45% | 40-50% | 10-20% | 5-10% |
| **RAM Usage** | 2-5 MB | 20-40 MB | 20-40 MB | 5-10 MB | 2-5 MB |
| **Latency Overhead** | +1.2 ms | +8.3 ms | +15-25 ms | +2-5 ms | +1-3 ms |
| **Connection Time** | 100 ms | 8-10 sec | 8-10 sec | 500 ms | Instant |

*Estimated based on protocol efficiency on similar MIPS hardware

### 6.2 Tethering Detection Evasion

| Detection Method | WireGuard | OpenVPN | Shadowsocks | SOCKS5 Proxy | TTL Fix Only |
|-----------------|-----------|---------|-------------|--------------|-------------|
| **TTL Analysis** | ❌ Fails | ❌ Fails | ❌ Fails | ✅ Bypassed | ✅ Bypassed |
| **TCP Fingerprint** | ❌ Fails* | ❌ Fails* | ❌ Fails* | ✅ Bypassed | ❌ Fails |
| **TCP Timestamp** | ❌ Fails* | ❌ Fails* | ❌ Fails* | ✅ Bypassed | ❌ Fails |
| **Window Size Scale** | ❌ Fails* | ❌ Fails* | ❌ Fails* | ✅ Bypassed | ❌ Fails |
| **Clock Frequency** | ❌ Fails* | ❌ Fails* | ❌ Fails* | ✅ Bypassed | ❌ Fails |
| **HTTP User-Agent** | ✅ Encrypted | ✅ Encrypted | ✅ Encrypted | ✅ Bypassed | ❌ Fails |
| **DNS Patterns** | ✅ If tunnel DNS | ✅ If tunnel DNS | ✅ If tunnel DNS | ✅ Bypassed | ❌ Fails |
| **MTU Detection** | ⚠️ 1420 visible | ⚠️ 1380 visible | N/A | ✅ Normal MTU | ✅ Normal MTU |

*VPN encrypts content but outer packet headers still carry router's TCP/IP stack fingerprint on the tethering interface

**Key insight**: VPNs (WireGuard, OpenVPN) encrypt the PAYLOAD but the TRANSPORT packets between the router and the phone's tethering interface still carry the router's TCP/IP characteristics. T-Mobile inspects these transport-level headers, not the encrypted content.

The SOCKS5 proxy approach is fundamentally different: the phone CREATES NEW CONNECTIONS using its own TCP/IP stack. The carrier only sees the phone's native traffic characteristics.

### 6.3 iPhone Battery Impact

| Protocol | 4-Hour Battery Drain | Wake-ups/Hour | Connection Stability |
|----------|---------------------|---------------|---------------------|
| **No VPN (baseline)** | 18% | N/A | N/A |
| **WireGuard** | 22% (+4%) | 15 | Excellent |
| **OpenVPN** | 31% (+13%) | 45 | Moderate |
| **SOCKS5 Proxy (Pythonista)** | ~20-25%* | ~10* | Good |

*Estimated — Pythonista proxy is lightweight but iOS may throttle background apps

### 6.4 Ease of Auto-Configuration

| Protocol | Router Config | iPhone Config | Auto-Setup Feasibility |
|----------|---------------|---------------|------------------------|
| **WireGuard** | Simple (GL-iNet GUI) | QR code scan | HIGH |
| **OpenVPN** | Moderate (GL-iNet GUI) | Config file import | MODERATE |
| **SOCKS5 Proxy** | Moderate (redsocks + iptables) | Run Pythonista script | MODERATE |
| **SSH Tunnel** | Complex (autossh setup) | Requires jailbreak | LOW |
| **Shadowsocks** | Moderate (opkg install) | Third-party app | MODERATE |

---

## 7. The Critical Architecture Question

### 7.1 Why a "Local VPN Tunnel" Alone Doesn't Work

For a VPN tunnel between the iPhone and router (no external server), the architecture would be:

```
[Internet] → [T-Mobile Network] → [iPhone] → [Hotspot/Tethering] → [Router] → [VPN Tunnel to iPhone] → [iPhone] → ...
```

This creates a **circular routing problem**: The router needs internet access from the iPhone's hotspot, but the VPN tunnel also goes back to the iPhone. The router would be sending VPN packets through the tethering interface — which T-Mobile can still fingerprint.

More critically, a local VPN between router and phone doesn't change the fundamental problem: **packets leaving the phone to T-Mobile's network still originate from the phone's tethering interface with tethered device characteristics** unless the traffic is re-originated by a proxy.

### 7.2 Why SOCKS Proxy IS the Solution

The SOCKS proxy approach fundamentally changes the traffic flow:

```
[LAN Device] → [Router] → [Hotspot WiFi] → [iPhone receives on hotspot interface]
                                                        ↓
                                            [SOCKS proxy on iPhone]
                                                        ↓
                                            [iPhone creates NEW TCP connection]
                                                        ↓
                                            [T-Mobile sees phone-native traffic (TTL=64, iOS TCP stack)]
                                                        ↓
                                                    [Internet]
```

The proxy server on the iPhone receives the request, then creates a BRAND NEW connection using the phone's own network stack. The carrier sees:
- TTL = 64 (phone's default)
- iOS TCP/IP fingerprint
- iOS TCP window size scale (16)
- iOS TCP timestamps with proper monotonicity
- Normal iOS clock frequency patterns

**ALL detection methods are defeated** because the traffic literally IS phone-native traffic.

### 7.3 The Encryption Gap

The main drawback of the plain SOCKS5 proxy approach: **traffic between the router and the iPhone's proxy is unencrypted**. On the hotspot WiFi link, this means:
- WPA2 encryption on the WiFi layer (standard hotspot security)
- No additional encryption layer
- Anyone on the same hotspot WiFi could sniff traffic

For a personal hotspot with only the router connected, this is acceptable — the WiFi encryption is sufficient. But if additional security is desired, a VPN tunnel can be added ON TOP of the SOCKS proxy.

---

## 8. Recommended Architecture

### 8.1 Primary Recommendation: SOCKS5 Proxy (Simple, Maximum Effectiveness)

```
[LAN Devices] ←WiFi→ [GL-iNet Opal (redsocks)] ←Hotspot WiFi→ [iPhone (SOCKS5 proxy via Pythonista)]
                                                                            ↓
                                                              [T-Mobile Network (sees phone traffic)]
                                                                            ↓
                                                                        [Internet]
```

**Components**:
1. **iPhone**: Runs iOS-SOCKS-Server via Pythonista app (SOCKS5 + HTTP proxy)
2. **Router**: Runs redsocks + iptables to transparently redirect all LAN TCP traffic
3. **LAN Devices**: Connect normally to router WiFi — zero configuration needed

**Pros**:
- Defeats ALL tethering detection methods
- Near-native performance (~50+ Mbps)
- Minimal resource usage on both devices
- No jailbreak required
- Battle-tested approach (iOS-SOCKS-Server project)

**Cons**:
- SOCKS5 only handles TCP (not UDP) — affects some gaming, VoIP
- No additional encryption beyond WiFi WPA2
- Pythonista must stay running in foreground on iPhone
- DNS queries need separate handling (or use HTTP proxy mode)

### 8.2 Enhanced Recommendation: SOCKS5 + WireGuard Wrapper

For additional encryption and UDP support:

```
[LAN Devices] ←WiFi→ [Opal (WG client + redsocks)] ←WG tunnel over Hotspot→ [iPhone (WG server* + SOCKS5)]
```

**Note**: Since iOS can't run a WireGuard server, this would require:
- A modified approach using the WireGuard iOS app in a non-standard configuration, OR
- Using a lightweight VPN alternative that CAN run as server on iOS (limited options)

**Practical alternative**: Just use the SOCKS5 proxy approach (8.1) with TTL fix as a fallback:

### 8.3 Fallback: TTL Fix on Router

If the SOCKS proxy approach isn't feasible, a simple TTL modification on the router provides partial protection:

```bash
# On GL-iNet Opal (OpenWrt)
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 65
```

This sets outgoing TTL to 65, so after the phone decrements it to 64, T-Mobile sees the expected value.

**Pros**: Simple one-line fix
**Cons**: Only defeats TTL detection — TCP fingerprinting, timestamps, window size, etc. can still reveal tethering if T-Mobile uses advanced detection

### 8.4 Protocol Selection Summary

| Scenario | Recommended Protocol | Reason |
|----------|---------------------|--------|
| **Maximum stealth** | SOCKS5 proxy (iOS-SOCKS-Server) | Defeats all detection methods |
| **Quick partial fix** | TTL=65 on router (iptables mangle) | Defeats primary detection only |
| **If VPN needed for other reasons** | WireGuard | 4x faster than OpenVPN on Opal |
| **If DPI evasion also needed** | OpenVPN + stunnel on TCP 443 | Only if connecting to external VPN server |
| **Maximum DPI evasion** | Shadowsocks or V2Ray/VLESS | For nation-state censorship, not T-Mobile |

---

## 9. References

### Academic Papers
1. Yi-Chao Chen et al., "OS Fingerprinting and Tethering Detection in Mobile Networks," ACM IMC 2014. https://conferences.sigcomm.org/imc/2014/papers/p173.pdf

### Official Documentation
2. WireGuard Known Limitations — https://www.wireguard.com/known-limitations/
3. GL-iNet Opal (GL-SFT1200) Specifications — https://www.gl-inet.com/products/gl-sft1200/
4. GL-iNet VPN Obfuscation (AmneziaWG) — https://docs.gl-inet.com/router/en/4/tutorials/vpn_obfuscation/
5. GL-iNet WireGuard Server Docs — https://docs.gl-inet.com/router/en/4/interface_guide/wireguard_server/
6. OpenWrt Shadowsocks — https://openwrt.org/docs/guide-user/services/proxy/shadowsocks

### Community Sources
7. GL-iNet Forum: SFT1200 VPN Performance — https://forum.gl-inet.com/t/sf1200-very-slow-with-wireguard-or-openvpn/24411
8. GL-iNet Forum: Detecting WG Tunneling — https://forum.gl-inet.com/t/detecting-wg-tunnelling/48809
9. GL-iNet Forum: Stunnel + OpenVPN — https://forum.gl-inet.com/t/route-openvpn-through-stunnel/22942
10. GitHub: T-Mobile Throttle Defeat — https://github.com/niski84/t-mobile-throttle-defeat
11. GitHub: iOS-SOCKS-Server — https://github.com/nneonneo/iOS-SOCKS-Server
12. GitHub: socks5-ios — https://github.com/nneonneo/socks5-ios
13. Gist: Proxy tether throttling bypass with router — https://gist.github.com/softmoth/039e2879198f298a41f0924f9fd357c2
14. Juraj Bednar: Bypassing Hotspot Restrictions — https://juraj.bednar.io/en/blog-en/2025/03/07/bypassing-hotspot-restrictions-for-data/

### Performance Benchmarks
15. WireGuard vs OpenVPN Benchmarks — https://www.goodservers.net/blog/wireguard-vs-openvpn-benchmarks
16. Cisco Tethering Detection — https://www.cisco.com/c/en/us/td/docs/wireless/asr_5000/21-28/ecs-admin/21-28-ecs-admin/m_tethering-detection.pdf
17. F5 Tethering Detection (DTOS) — https://techdocs.f5.com/en-us/bigip-14-1-0/big-ip-policy-enforcement-manager-implementations-14-1-0/detecting-tethering-device-operation-system-and-type.html

### DPI and Censorship
18. DPI.Watch — Global DPI Monitoring — https://www.dpi.watch/
19. Advancing Obfuscation Strategies (arXiv) — https://arxiv.org/html/2503.02018v1
20. V2Ray vs Shadowsocks Comparison — https://edgevpn.tech/en/compare/v2ray-vs-shadowsocks-protocols
21. OpenVPN Traffic Obfuscation Wiki — https://community.openvpn.net/Pages/TrafficObfuscation
22. Obfuscating OpenVPN with Pluggable Transports — https://www.pluggabletransports.info/implement/openvpn/

---

## Appendix A: Quick Decision Matrix

```
Q: Do you need to hide tethering from T-Mobile?
├── YES → Use SOCKS5 proxy on iPhone + redsocks on router
│         (Defeats ALL detection methods)
│
├── PARTIALLY (just TTL) → iptables TTL=65 on router
│         (Quick fix, may not survive advanced fingerprinting)
│
Q: Do you also need VPN for privacy/external server?
├── YES → WireGuard (4x faster on Opal hardware)
│
Q: Are you in a country that blocks VPN protocols?
├── YES → OpenVPN + stunnel, or Shadowsocks
│         (But this is not the T-Mobile use case)
│
Q: Do you need UDP support (gaming, VoIP)?
├── YES → SOCKS5 proxy handles TCP only
│         Consider TTL fix + SOCKS proxy hybrid
│         Or WireGuard tunnel + TTL fix
```

## Appendix B: GL-iNet Opal Hardware Constraints Summary

| Resource | Value | Impact |
|----------|-------|--------|
| **RAM** | 128 MB DDR3 | OpenVPN + stunnel may consume 40-60 MB, leaving little for routing |
| **CPU** | SF19A2890 dual-core MIPS @1.0 GHz | No AES-NI, OpenVPN extremely slow |
| **Flash** | 16 MB NOR | Limited space for additional packages |
| **WiFi** | AC1200 (2.4GHz + 5GHz) | One radio for hotspot uplink, one for LAN clients |
| **Ethernet** | 2x 100Mbps | VPN throughput won't bottleneck Ethernet on Opal |
| **USB** | 1x USB 2.0 | Could be used for USB tethering instead of WiFi hotspot |
| **OpenWrt** | Based on 19.07 (kernel 4.14) | WireGuard via kmod, Shadowsocks available, redsocks available |
