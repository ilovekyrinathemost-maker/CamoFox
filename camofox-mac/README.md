# CamoFox Mac

> **Route your MacBook's traffic through your iPhone's SOCKS5 proxy, bypassing T-Mobile tethering detection — no router required.**

CamoFox Mac is a macOS companion tool for the [CamoFox](https://github.com/nneonneo/iOS-SOCKS-Server) tethering bypass system. It lets a MacBook connect directly to the iPhone's SOCKS5 proxy tunnel, eliminating the need for the GL-iNet Opal travel router.

## How It Works

```
┌──────────┐        Wi-Fi        ┌─────────────────────┐      Cellular      ┌──────────┐
│          │◄───────────────────►│  iPhone              │◄──────────────────►│          │
│  MacBook │   Same network      │  CamoFox iOS proxy   │    T-Mobile sees   │ Internet │
│          │   (not hotspot!)    │  SOCKS5 :9876         │    normal phone    │          │
└──────────┘                     └─────────────────────┘    traffic           └──────────┘
```

**Key insight:** We do NOT use iPhone's Personal Hotspot (that triggers the tethering APN and gets throttled). Instead:

1. Both the iPhone and MacBook join the **same Wi-Fi network** (home router, café, etc.)
2. The iPhone runs CamoFox iOS proxy (via Pythonista), listening on the Wi-Fi interface
3. Traffic flows: **MacBook → Wi-Fi → iPhone SOCKS proxy → iPhone cellular → Internet**
4. T-Mobile sees normal phone data usage — no tethering flags, no throttling

## Router vs Mac Approach

| Feature | CamoFox Router | CamoFox Mac |
|---------|---------------|-------------|
| Hardware needed | GL-iNet Opal router | Just your MacBook |
| TTL manipulation | ✅ via iptables | ❌ Not needed (same network) |
| Covers all devices | ✅ Entire LAN | ❌ MacBook only |
| Transparent proxying | ✅ redsocks | ✅ pfctl + Python helper |
| DNS leak prevention | ✅ https-dns-proxy | ✅ dnscrypt-proxy/cloudflared |
| Kill switch | ✅ iptables | ✅ pfctl (force mode) |
| Portable | ✅ Travel router | ✅ Laptop-only |
| Setup complexity | Medium | Simple |

## Prerequisites

- **macOS 10.14+** (Mojave or later)
- **Python 3** (ships with Xcode Command Line Tools: `xcode-select --install`)
- **iPhone** on the same Wi-Fi, running CamoFox iOS proxy
- **Admin password** (for force mode only)

### Optional (Recommended)

```bash
# Best DNS privacy — DNS-over-HTTPS
brew install dnscrypt-proxy

# Alternative DoH proxy
brew install cloudflared
```

## Installation

```bash
# Clone or download CamoFox Mac
cd camofox-mac/

# Run the installer
./install.sh
```

The installer will:
- Check macOS compatibility and prerequisites
- Copy scripts to `/usr/local/share/camofox-mac/`
- Create the `camofox-mac` command in your PATH
- Set up the config directory at `~/.camofox/`
- Optionally install a LaunchAgent for auto-start

## Quick Start

```bash
# 1. Start CamoFox iOS proxy on your iPhone (via Pythonista)
# 2. Connect both devices to the same Wi-Fi network

# 3. Start CamoFox Mac
camofox-mac start

# 4. Verify everything works
camofox-mac test

# 5. When done
camofox-mac stop
```

## Commands

| Command | Description |
|---------|-------------|
| `camofox-mac start` | Discover iPhone, configure proxy, DNS, and health monitor |
| `camofox-mac stop` | Disable everything and restore original settings |
| `camofox-mac status` | Show detailed status of all components |
| `camofox-mac test` | Run connectivity, DNS leak, and speed diagnostics |
| `camofox-mac find` | Scan local network for iPhone SOCKS5 proxy |
| `camofox-mac version` | Show version information |

## Operation Modes

### Simple Mode (Default)

Sets macOS system-wide proxy settings. Works for **most** applications (browsers, curl, etc.).

```bash
# Edit config (optional)
vim ~/.camofox/config
# Set: MODE=simple

camofox-mac start
```

**What it does:**
- Sets SOCKS5 proxy via `networksetup`
- Sets HTTP/HTTPS proxy via `networksetup`
- Configures DNS leak prevention
- Starts background health monitor

**Limitations:** Some apps ignore system proxy settings (e.g., some games, VPN clients, CLI tools without proxy env vars).

### Force Mode (Catches ALL Traffic)

Uses macOS packet filter (`pfctl`) to redirect ALL TCP traffic through the proxy. No app can bypass it.

```bash
# Edit config
vim ~/.camofox/config
# Set: MODE=force

# Force mode requires root
sudo camofox-mac start
```

**What it does:**
- Everything in simple mode, PLUS:
- Starts a local transparent proxy (`proxy_helper.py`)
- Loads `pfctl` rules that redirect all outbound TCP to the local proxy
- The local proxy forwards everything through the iPhone's SOCKS5 proxy
- Blocks direct DNS (UDP 53) to prevent leaks

**Requires:** `sudo` (root access) for pfctl

## DNS Leak Prevention

CamoFox Mac prevents DNS queries from leaking to your ISP/network:

| DNS Mode | How It Works | Privacy Level |
|----------|-------------|---------------|
| `doh` (default) | DNS-over-HTTPS via dnscrypt-proxy or cloudflared | 🟢 Excellent |
| `proxy` | DNS tunneled through SOCKS5 proxy | 🟢 Excellent |
| `system` | No changes (not recommended) | 🔴 Poor |

```bash
# In ~/.camofox/config
DNS_MODE=doh
```

## Configuration

Edit `~/.camofox/config`:

```bash
# iPhone proxy (auto-detect or manual IP)
PROXY_IP=auto
SOCKS_PORT=9876
HTTP_PORT=9877

# Operation mode
MODE=simple          # simple or force

# DNS leak prevention
DNS_MODE=doh         # doh, proxy, or system

# Kill switch (block traffic if proxy dies)
KILL_SWITCH=true

# macOS network service name
NETWORK_SERVICE=Wi-Fi
```

See `config.example` for all available options.

## Network Setup Options

### Option A: Shared Wi-Fi (Recommended)

Both devices join the same existing Wi-Fi network:

```
[Wi-Fi Router]
     ├── MacBook (192.168.1.100)
     └── iPhone  (192.168.1.105) ← runs SOCKS proxy
```

1. Connect both devices to the same Wi-Fi
2. Start CamoFox iOS on the iPhone
3. Run `camofox-mac start` on the MacBook

### Option B: Mac Creates Ad-Hoc Network

Create a direct Wi-Fi link between Mac and iPhone:

1. On Mac: **System Preferences → Sharing → Internet Sharing**
   - Or create via terminal:
     ```bash
     # Create ad-hoc network (Mac acts as access point)
     networksetup -createnetworkservice "CamoFox" Wi-Fi
     ```
2. On iPhone: Join the Mac's network
3. Start CamoFox iOS on the iPhone
4. Run `camofox-mac start` — it will auto-discover the iPhone

### Option C: iPhone USB (Direct Connection)

Connect iPhone via USB and use its network interface:

1. Connect iPhone via Lightning/USB-C cable
2. On iPhone: **Settings → Personal Hotspot** (just to enable the USB interface)
3. On Mac, a new network interface appears
4. Set `PROXY_IP=172.20.10.1` in config (iPhone USB default)
5. Run `camofox-mac start`

> ⚠️ USB hotspot may still be flagged by T-Mobile. Prefer Wi-Fi methods.

## Troubleshooting

### iPhone proxy not found

```bash
# Run discovery with verbose output
camofox-mac find

# Or scan manually
nc -z -G 2 <iphone-ip> 9876
```

**Checklist:**
- Is Pythonista running CamoFox proxy on the iPhone?
- Are both devices on the same Wi-Fi network?
- Is iOS firewall allowing incoming connections?
- Try setting `PROXY_IP` manually in `~/.camofox/config`

### Apps not using proxy (simple mode)

Some apps ignore macOS system proxy. Solutions:

1. Switch to **force mode**: `MODE=force` + `sudo camofox-mac start`
2. Set env variables for CLI tools:
   ```bash
   export ALL_PROXY=socks5://192.168.1.5:9876
   export http_proxy=http://192.168.1.5:9877
   export https_proxy=http://192.168.1.5:9877
   ```

### DNS leaking

```bash
# Check current DNS
camofox-mac test

# Install proper DoH proxy
brew install dnscrypt-proxy

# Or use proxy DNS mode
# In ~/.camofox/config:
DNS_MODE=proxy
```

### Force mode not working

```bash
# Must run as root
sudo camofox-mac start

# Check pfctl status
sudo pfctl -s rules
sudo pfctl -a com.camofox -s rules

# Check transparent proxy
ps aux | grep proxy_helper
```

### Connection slow

- Check iPhone signal strength
- Ensure iPhone is on LTE/5G (not Wi-Fi for outbound)
- Reduce DNS resolution overhead: use `DNS_MODE=doh`
- Check for background iPhone apps consuming bandwidth

### Restoring settings after crash

If CamoFox Mac crashes or your Mac restarts unexpectedly:

```bash
# This restores ALL settings to defaults
camofox-mac stop

# Nuclear option: manual cleanup
networksetup -setsocksfirewallproxystate Wi-Fi off
networksetup -setwebproxystate Wi-Fi off
networksetup -setsecurewebproxystate Wi-Fi off
networksetup -setdnsservers Wi-Fi empty
```

## File Structure

```
camofox-mac/
├── camofox-mac.sh      # Main CLI control script
├── discover.sh         # iPhone auto-discovery
├── dns-setup.sh        # DNS leak prevention
├── proxy_helper.py     # Transparent proxy (force mode)
├── pfctl-rules.conf    # PF anchor rules template
├── com.camofox.mac.plist  # LaunchAgent for auto-start
├── install.sh          # Installer
├── uninstall.sh        # Uninstaller
├── config.example      # Example configuration
└── README.md           # This file

~/.camofox/             # Runtime state (created on first run)
├── config              # Your configuration
├── camofox.log         # Log file
├── dns_backup          # Original DNS settings
├── proxy_backup        # Original proxy settings
├── proxy_state         # Current proxy health (up/down)
└── *.pid               # PID files for background processes
```

## Uninstall

```bash
# Interactive
./uninstall.sh

# Non-interactive (removes everything)
./uninstall.sh --force

# Or via installer
./install.sh --uninstall
```

## Security Notes

- **No encryption between Mac and iPhone** — traffic on the local Wi-Fi is unencrypted before reaching the SOCKS proxy. Use HTTPS for sensitive traffic (which you should be doing anyway).
- **Admin password** is only needed for force mode (pfctl).
- **Kill switch** prevents data leaks if the proxy goes down unexpectedly.
- The proxy runs **without authentication** — only use on trusted networks.

## License

MIT — See [LICENSE](../LICENSE)

## Credits

- Based on [iOS-SOCKS-Server](https://github.com/nneonneo/iOS-SOCKS-Server) by nneonneo
- Tethering bypass techniques from the [community discussion](https://github.com/nneonneo/iOS-SOCKS-Server/issues/1#issuecomment-583989079)
