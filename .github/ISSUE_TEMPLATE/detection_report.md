---
name: Detection Report
about: Report a carrier detection event — T-Mobile (or other carrier) detected tethering or changed detection methods
title: '[DETECTION] '
labels: detection, high-priority
assignees: ''
---

## ⚠️ Detection Event Summary

Brief description of what happened (throttled, warning message, service change, etc.).

## Carrier & Plan

| Detail | Value |
|--------|-------|
| **Carrier** | e.g. T-Mobile |
| **Plan** | e.g. Magenta Max, Go5G Plus |
| **Account Type** | Prepaid / Postpaid |
| **Region** | e.g. US West Coast |

## What Happened

- [ ] Speed throttled (describe: from ____ Mbps to ____ Mbps)
- [ ] Warning message / notification from carrier
- [ ] Hotspot data cap applied despite using CamoFox
- [ ] Service suspended or restricted
- [ ] T-Mobile account shows hotspot usage
- [ ] Other: ____

## Date & Timeline

| Detail | Value |
|--------|-------|
| **Date first noticed** | YYYY-MM-DD |
| **Duration of issue** | Ongoing / Resolved after ____ |
| **Working before?** | Yes, since ____ / No |

## CamoFox Configuration

### Bypass Layers Active

- [ ] 🔴 SOCKS5 proxy on iPhone
- [ ] 🟠 TTL set to 65
- [ ] 🟡 DNS-over-HTTPS
- [ ] 🟢 Kill switch enabled
- [ ] Custom modifications: ____

### Router Config

<details>
<summary>Output of: cat /etc/config/camofox</summary>

```
Paste here
```
</details>

<details>
<summary>Output of: camofox status</summary>

```
Paste here
```
</details>

## Hardware & Software

| Component | Value |
|-----------|-------|
| **Router Model** | GL-iNet Opal (GL-SFT1200) / Other: ____ |
| **Router Firmware** | e.g. 4.3.11 |
| **iPhone Model** | e.g. iPhone 14 Pro |
| **iOS Version** | e.g. 17.4 |
| **Pythonista Version** | e.g. 3.4 |
| **CamoFox Version** | e.g. v1.0.0 |

## Network Evidence

If you have any of the following, please share:

- [ ] Speed test results (before/after)
- [ ] T-Mobile app screenshots showing hotspot usage
- [ ] `camofox test` output
- [ ] Packet captures or network logs

<details>
<summary>Evidence / Screenshots</summary>

Attach or paste here.
</details>

## What You've Tried

Describe any troubleshooting steps you took:

1. ...
2. ...

## Additional Context

Any other information that might help diagnose the detection method.

---

> **Note to maintainers:** Detection reports are high-priority. If confirmed, this may require new bypass techniques or updates to existing layers.
