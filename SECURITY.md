# Security Policy

## About This Project

CamoFox is a network privacy tool that routes traffic through an iPhone's cellular connection via a SOCKS5 proxy. Because this project handles live network traffic, security is a critical concern.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ Yes    |
| < 1.0   | ❌ No     |

## Reporting a Vulnerability

**⚠️ Please do NOT open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in CamoFox, please report it responsibly:

1. **Email**: Send a detailed report to the repository maintainers via [GitHub private vulnerability reporting](https://github.com/ilovekyrinathemost-maker/CamoFox/security/advisories/new)
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if you have one)
3. **Response time**: We aim to acknowledge reports within 48 hours and provide a fix timeline within 7 days

## Scope

### In Scope

- **Proxy security**: Vulnerabilities in the SOCKS5/HTTP proxy (`camofox-ios/`, `lib/`, `socks5.py`)
- **Traffic leaks**: Scenarios where unproxied traffic could escape the kill switch
- **Router configuration**: Firewall rule bypasses, redsocks vulnerabilities, TTL manipulation failures
- **Credential exposure**: Proxy credentials or configuration data leaked in logs, error messages, or network traffic
- **Denial of service**: Attacks that could crash the proxy or router services
- **Injection attacks**: Command injection via the setup wizard, CLI tool, or configuration files

### Out of Scope

- **Carrier detection methods**: T-Mobile changing their detection techniques is not a security vulnerability — use the [Detection Report](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=detection_report.md) issue template instead
- **Pythonista app sandbox**: Issues inherent to the iOS Pythonista runtime environment
- **Third-party libraries**: Vulnerabilities in the bundled `dns/` (dnspython) library — report those upstream
- **Physical access attacks**: Scenarios requiring physical access to the router or iPhone
- **Social engineering**: Attacks targeting users rather than the software

## Security Best Practices for Users

### Router

- **Change default passwords**: Always change the GL-iNet admin and SSH passwords
- **Keep firmware updated**: Apply GL-iNet firmware updates regularly
- **Use the kill switch**: Always keep `kill_switch` enabled in `/etc/config/camofox` to prevent traffic leaks
- **Restrict SSH access**: Limit SSH access to the LAN interface only

### iPhone

- **Keep iOS updated**: Apply iOS updates for the latest security patches
- **Bind to local only**: The proxy should only bind to the local WiFi interface, not `0.0.0.0`
- **Monitor Pythonista**: Ensure Pythonista is running and the proxy is active before routing traffic

### General

- **Do not commit credentials**: Never push proxy passwords, WiFi passwords, or carrier account info to version control
- **Review configurations**: Inspect configuration files before deploying to production hardware
- **Use DNS-over-HTTPS**: Keep DoH enabled to prevent DNS-based tracking and manipulation

## Security Design Principles

CamoFox follows these security principles:

1. **Fail closed**: The kill switch blocks all traffic if the proxy is unavailable — no silent fallback to direct routing
2. **Minimal attack surface**: The router runs only essential services (redsocks, dnsmasq, firewall)
3. **No external dependencies at runtime**: All required libraries are bundled; no network calls needed for operation
4. **Transparent operation**: All network rules are visible via standard OpenWrt tools (`iptables`, `uci`)
5. **Least privilege**: Scripts run with minimum required permissions where possible

## Acknowledgments

We appreciate security researchers who help keep CamoFox and its users safe. Contributors who report valid vulnerabilities will be acknowledged here (with permission).

---

Thank you for helping keep CamoFox secure! 🔒🦊
