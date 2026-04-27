# Pythonista URL Schemes for CamoFox

Complete reference for automating CamoFox via Pythonista's URL schemes.

---

## Basic URL Scheme

Pythonista 3 registers the `pythonista3://` URL scheme.  Use it to
run scripts directly from iOS Shortcuts, Safari, or other apps.

### Syntax

```
pythonista3://<path-to-script>?action=run
```

- `<path-to-script>` — Relative path from Pythonista's script library root
- `?action=run` — Execute the script immediately upon opening

---

## CamoFox Script URLs

### Start Proxy

```
pythonista3://camofox-ios/camofox_start.py?action=run
```

Launches the full CamoFox proxy with default settings (SOCKS5 on
port 9876, HTTP on 9877, WPAD on 8088, all keepalive strategies).

### Run Diagnostics

```
pythonista3://camofox-ios/diagnostics.py?action=run
```

Runs the network diagnostic suite and displays results in the console.

### Keepalive Test

```
pythonista3://camofox-ios/keepalive.py?action=run
```

Tests which keepalive strategies are available on the current device.

### Status Dashboard (standalone)

```
pythonista3://camofox-ios/camofox_status.py?action=run
```

Opens the status dashboard in test/standalone mode.

---

## x-callback-url Scheme

Pythonista supports the [x-callback-url](http://x-callback-url.com/)
standard for inter-app communication with success/error callbacks.

### Syntax

```
pythonista3://x-callback-url/run?argv=<path>&x-success=<url>&x-error=<url>&x-cancel=<url>
```

| Parameter | Description |
|-----------|-------------|
| `argv` | Path to the script (required) |
| `x-success` | URL to open on successful completion |
| `x-error` | URL to open if the script raises an error |
| `x-cancel` | URL to open if the user cancels |

### Examples

#### Run proxy, return to Shortcuts on success

```
pythonista3://x-callback-url/run?argv=camofox-ios/camofox_start.py&x-success=shortcuts://
```

#### Run diagnostics, return to Shortcuts on success or error

```
pythonista3://x-callback-url/run?argv=camofox-ios/diagnostics.py&x-success=shortcuts://&x-error=shortcuts://
```

#### Chain with another shortcut

```
pythonista3://x-callback-url/run?argv=camofox-ios/camofox_start.py&x-success=shortcuts://run-shortcut?name=CamoFox%20Status
```

---

## Passing Arguments

You can pass command-line arguments to scripts using the `argv` parameter
with space-separated values:

```
pythonista3://x-callback-url/run?argv=camofox-ios/camofox_proxy.py --host 192.168.2.1 --socks-port 1080
```

> Note: Spaces in the URL may need percent-encoding (`%20`) depending
> on the source app.

---

## Opening Scripts Without Running

To open a script in the editor without running it:

```
pythonista3://camofox-ios/camofox_proxy.py
```

(Omit the `?action=run` parameter.)

---

## Integration with iOS Shortcuts App

### "Open URLs" Action

The simplest way to call Pythonista from Shortcuts:

1. Add action: **Open URLs**
2. Paste the URL from above
3. That's it — the action opens Pythonista and runs the script

### "Run Script Over SSH" (Advanced)

If you have SSH access to Pythonista (via a-Shell or similar):

1. Add action: **Run Script Over SSH**
2. Host: `localhost`
3. Script: `cd ~/Documents && python3 camofox-ios/camofox_start.py`

This approach runs in the background but requires additional setup.

---

## URL Scheme Security Notes

- Any app can call `pythonista3://` URLs — there is no built-in
  authentication mechanism
- The proxy does not expose any sensitive data through URL schemes
- Script arguments are visible in the URL — do not pass secrets
- Consider using Guided Access to prevent other apps from
  interfering with the proxy

---

## Quick Reference Table

| Action | URL |
|--------|-----|
| Start proxy | `pythonista3://camofox-ios/camofox_start.py?action=run` |
| Run diagnostics | `pythonista3://camofox-ios/diagnostics.py?action=run` |
| Test keepalive | `pythonista3://camofox-ios/keepalive.py?action=run` |
| View status | `pythonista3://camofox-ios/camofox_status.py?action=run` |
| Open proxy config | `pythonista3://camofox-ios/camofox_proxy.py` |
| Custom SOCKS port | `pythonista3://x-callback-url/run?argv=camofox-ios/camofox_proxy.py --socks-port 1080` |
