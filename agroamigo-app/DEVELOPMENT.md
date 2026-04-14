# AgroAmigo App - Development Guide

## Prerequisites

- Node.js 18+
- [Expo Go](https://expo.dev/go) installed on your phone (Android or iOS)
- `.env` file in `agroamigo-app/` with `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_KEY`

## Quick Start (Same Wi-Fi Network)

If your phone and computer are on the same Wi-Fi network:

```bash
cd agroamigo-app
npx expo start
```

Scan the QR code with Expo Go (Android) or the Camera app (iOS).

## Remote Access (Different Network / Tunnel)

If your phone is on a different network (e.g. mobile data, different Wi-Fi), use a Cloudflare tunnel. This requires **two terminal windows**.

> **Why not ngrok?** The `--tunnel` flag in Expo uses ngrok, which may be blocked by corporate Device Guard policies. Cloudflare tunnels are a free alternative that works without an account.

### Step 1: Start the Cloudflare Tunnel

Open **Terminal 1** (PowerShell) and run:

```powershell
cd agroamigo-app
npx cloudflared tunnel --url http://localhost:8085
```

Wait for output like:

```
Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):
https://some-random-words.trycloudflare.com
```

**Copy this URL** - you'll need it in the next step. The URL changes every time you restart the tunnel.

### Step 2: Start Expo with the Tunnel URL

Open **Terminal 2** (PowerShell) and run:

```powershell
cd agroamigo-app
$env:EXPO_PACKAGER_PROXY_URL="https://some-random-words.trycloudflare.com"; npx expo start --port 8085
```

Replace `some-random-words.trycloudflare.com` with the actual URL from Step 1.

> **Bash/Git Bash alternative:**
> ```bash
> EXPO_PACKAGER_PROXY_URL=https://some-random-words.trycloudflare.com npx expo start --port 8085
> ```

### Step 3: Open on Your Phone

Open the tunnel URL in your phone's browser:

```
https://some-random-words.trycloudflare.com
```

This should prompt to open in Expo Go. If it doesn't, open Expo Go manually and enter the URL in "Enter URL manually":

```
exp://some-random-words.trycloudflare.com:443
```

## Running on Android Emulator

If you have Android Studio with an AVD configured:

```bash
cd agroamigo-app
npx expo start --port 8085
```

Then press `a` in the terminal to open on the Android emulator, or scan the QR code in Expo Go on the emulator.

## Troubleshooting

### Port already in use

Find and kill the process using the port:

```powershell
netstat -ano | findstr :8085
taskkill /PID <pid> /F
```

### Tunnel shows 502 Bad Gateway

Expo must be running **before** traffic hits the tunnel. Make sure Step 2 (Expo) is fully started before opening the URL on your phone.

### `EXPO_PACKAGER_PROXY_URL` not recognized

You're likely in PowerShell. Use the `$env:` syntax:

```powershell
$env:EXPO_PACKAGER_PROXY_URL="https://your-url.trycloudflare.com"; npx expo start --port 8085
```

### Manifest URLs still show localhost or LAN IP

The `EXPO_PACKAGER_PROXY_URL` env var must be set **before** starting Expo. If you set it after, restart Expo.
