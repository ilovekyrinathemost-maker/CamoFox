# CamoFox iOS Shortcuts Integration

iOS Shortcuts can automate launching, monitoring, and recovering the
CamoFox proxy on your iPhone.  This guide walks through creating
Shortcuts that work with Pythonista 3.

---

## Prerequisites

- iPhone with iOS 14+
- [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) installed
- CamoFox files copied to Pythonista (see `CONFIG.md`)
- iOS Shortcuts app (built into iOS)

---

## Shortcut 1: Launch CamoFox Proxy

This shortcut opens Pythonista and runs the proxy script with one tap.

### Steps to Create

1. Open the **Shortcuts** app on your iPhone
2. Tap **+** to create a new shortcut
3. Tap **Add Action**
4. Search for **"Open URLs"**
5. Set the URL to:
   ```
   pythonista3://camofox-ios/camofox_start.py?action=run
   ```
6. Tap the shortcut name at the top → rename to **"CamoFox Start"**
7. Tap the icon → choose a fox emoji 🦊 or an orange color
8. Tap **Done**

### Add to Home Screen

1. Long-press the shortcut → **Details**
2. Tap **Add to Home Screen**
3. Now you have a one-tap launcher!

### Alternative: Using x-callback-url

For more control, use the x-callback-url scheme:

```
pythonista3://x-callback-url/run?argv=camofox-ios/camofox_start.py
```

This variant supports callbacks on success/failure:

```
pythonista3://x-callback-url/run?argv=camofox-ios/camofox_start.py&x-success=shortcuts://&x-error=shortcuts://
```

---

## Shortcut 2: Run Diagnostics

Quickly check if your proxy setup is healthy.

### Steps to Create

1. Create a new shortcut
2. Add **Open URLs** action with:
   ```
   pythonista3://camofox-ios/diagnostics.py?action=run
   ```
3. Name it **"CamoFox Diagnostics"**

---

## Shortcut 3: Auto-Launch on WiFi Connection

This automation starts CamoFox whenever your iPhone connects to a
specific WiFi network (e.g., the one from your GL-iNet Opal).

### Steps to Create

1. Open **Shortcuts** → **Automation** tab
2. Tap **+** → **Create Personal Automation**
3. Select **"WiFi"**
4. Tap **Network** → choose your router's WiFi name
   (e.g., "GL-SFT1200-xxx" or your custom SSID)
5. Select **"Connects"** (not Disconnects)
6. Tap **Next**
7. Add action: **Open URLs**
8. Set URL to:
   ```
   pythonista3://camofox-ios/camofox_start.py?action=run
   ```
9. **Important**: Toggle OFF "Ask Before Running"
10. Tap **Done**

### Behavior

- When iPhone connects to the specified WiFi → Pythonista opens and
  starts the proxy automatically
- If Pythonista is already running the proxy, it will just bring it
  to the foreground (the proxy handles being re-started gracefully)

---

## Shortcut 4: Recovery Shortcut

If iOS kills Pythonista (memory pressure, etc.), this shortcut
can be triggered manually or via automation to restart it.

### Steps to Create

1. Create a new shortcut
2. Add **Wait** action → set to 2 seconds
3. Add **Open URLs** action with:
   ```
   pythonista3://camofox-ios/camofox_start.py?action=run
   ```
4. Name it **"CamoFox Recovery"**

### Automation Trigger (Optional)

You can set this up as an automation that triggers:
- When you open a specific app (Settings, Safari, etc.)
- At a specific time of day
- When connecting to WiFi

Note: iOS 15+ limits background automation — it may still show
a notification asking you to confirm.

---

## Shortcut 5: Stop Proxy

To gracefully stop the proxy (useful before switching networks).

### Steps to Create

1. Create a new shortcut
2. Add **Open URLs** action with:
   ```
   pythonista3://camofox-ios/camofox_start.py?action=run&argv=-stop
   ```
3. Name it **"CamoFox Stop"**

> Note: In practice, you can just swipe Pythonista closed from the
> app switcher.  The proxy will stop automatically.

---

## Tips & Tricks

### Keep Pythonista in the Foreground

The #1 reason the proxy stops is iOS suspending Pythonista.
To minimise this:

- **Don't switch away** from Pythonista when using the proxy heavily
- **Use Picture-in-Picture** from another app if you need to multitask
- **Enable Guided Access** (Settings → Accessibility → Guided Access)
  to lock Pythonista in the foreground
- **Keep the device plugged in** — iOS is less aggressive about killing
  apps when charging

### Siri Integration

Any shortcut can be triggered by Siri:

1. Open the shortcut → tap the **ℹ️** button
2. Tap **Add to Siri**
3. Record a phrase like "Start CamoFox"

Now say: **"Hey Siri, Start CamoFox"** → proxy launches!

### Focus Mode Integration (iOS 15+)

1. Go to Settings → Focus
2. Create a "Travel" or "Tethering" focus mode
3. Under Automation → add "Turn on CamoFox" shortcut
4. When you activate this Focus mode, the proxy starts automatically

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Shortcut shows "not allowed" | Enable Shortcuts access in Settings → Pythonista 3 |
| Pythonista doesn't open | Ensure the URL scheme is exactly right (no extra spaces) |
| Proxy doesn't start | Run diagnostics shortcut to identify the issue |
| Automation asks for confirmation | iOS limitation — toggle "Ask Before Running" off |
| Proxy stops when switching apps | Enable keepalive features (see CONFIG.md) |

---

## URL Scheme Reference

See [url_schemes.md](url_schemes.md) for the complete URL scheme reference.
