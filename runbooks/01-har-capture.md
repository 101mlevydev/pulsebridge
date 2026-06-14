# HAR Capture — Step-by-Step

**You will do this once at setup, then again every 4–8 weeks when bio-bridge starts seeing 401s.**

Total time: 10–15 minutes.

---

## What you'll end up with

A file `~/capture.har` on your laptop containing your Zepp account's `apptoken`, `user_id`, and regional `host`. This is the credential bio-bridge uses to pull your data.

**The file contains live credentials. Don't share, commit, email, or paste it anywhere. Once `bio-bridge init` extracts the values, shred it.**

---

## What you need

- **macOS laptop** (these steps assume macOS — Linux is similar)
- **iPhone or Android phone** with the Zepp app installed and logged in to your account
- **Both on the same Wi-Fi network**
- **About 10 minutes of focused time**

---

## Step 1 — Install mitmproxy on your laptop (one-time)

mitmproxy is a free tool that lets you see HTTPS traffic flowing through your machine. It runs entirely on your laptop — nothing leaves your computer.

```bash
brew install mitmproxy
```

If you don't have Homebrew, get it first from https://brew.sh.

Verify the install:

```bash
mitmproxy --version
# should print: Mitmproxy: 11.x.x or similar
```

---

## Step 2 — Find your laptop's local IP

Your phone needs to know where to send traffic.

```bash
ipconfig getifaddr en0
# prints something like: 192.168.1.42
```

If that returns nothing, try `en1` instead. Write down the IP — you'll need it in step 4.

---

## Step 3 — Start mitmproxy

In a terminal window:

```bash
mitmproxy --listen-port 8080
```

You'll see a TUI (text interface) with three panes. Leave this terminal open — it has to keep running for the next 10 minutes.

To exit later: press `q` then `y`.

---

## Step 4 — Point your phone's Wi-Fi through mitmproxy

**On iPhone:**

1. **Settings → Wi-Fi**
2. Tap the **(i)** info icon next to your current network
3. Scroll down to **HTTP Proxy** → tap **Configure Proxy**
4. Choose **Manual**
5. **Server:** the IP from step 2 (e.g. `192.168.1.42`)
6. **Port:** `8080`
7. Leave **Authentication** off
8. Tap **Save** (top right)

**On Android:**

1. Settings → Wi-Fi → long-press your network → Modify Network → Advanced
2. Proxy: **Manual**
3. Hostname: your laptop's IP
4. Port: `8080`
5. Save

After this, your phone's normal web traffic will flow through mitmproxy. You'll see entries appear in the mitmproxy terminal as your phone makes requests.

---

## Step 5 — Install the mitmproxy CA certificate on your phone

This is the trickiest step. Without it, HTTPS-decrypting fails because your phone doesn't trust mitmproxy yet.

**On iPhone:**

1. Open **Safari** on the phone (must be Safari, not Chrome)
2. Go to **`mitm.it`** (no `https://`, just `mitm.it`)
3. You should see a page with iOS / Android / etc. logos. If you see "Tip: check the docs!" something is wrong — your proxy isn't working.
4. Tap **Apple** (the iOS logo)
5. Safari downloads a configuration profile. Tap **Allow**.
6. iOS pops a notification: "Profile Downloaded". Tap **Close**.
7. Open **Settings** (yes, leave Safari).
8. At the very top of Settings you'll now see **Profile Downloaded** (in blue). Tap it.
9. Tap **Install** (top right). Enter your iPhone passcode. Tap **Install** again to confirm.
10. **Now the critical step:** go to **Settings → General → About → Certificate Trust Settings**.
11. You'll see a switch for **mitmproxy** under "Enable Full Trust for Root Certificates". **Turn it on.** Confirm.

**That's the part most tutorials skip and it's why captures fail. The profile install isn't enough — you must enable Full Trust separately.**

**On Android:**

1. Open Chrome
2. Visit `mitm.it`
3. Tap Android → download the cert
4. Settings → Security → Encryption & credentials → Install a certificate → CA certificate → pick the downloaded file
5. (Android 7+: only apps that explicitly opt in to user CA certs will trust it — most apps including Zepp do, but if it fails, you may need a rooted phone or Frida)

---

## Step 6 — Generate Zepp traffic to capture

On your phone:

1. Open the **Zepp** app (the one synced to your Amazfit watch / Helio Strap)
2. Tap **Health** at the bottom (or whichever tab shows your daily metrics)
3. Pull down to refresh
4. Scroll through different cards — Heart Rate, Sleep, Readiness, etc. Tap into a few to load detail views.
5. Do this for 20–30 seconds

**While you're doing this, watch the mitmproxy terminal on your laptop.** You should see lines like:

```
GET   https://api-mifit-us3.zepp.com/users/.../heartRate?...
GET   https://api-mifit-us3.zepp.com/v2/watch/.../readiness/watch_score?...
GET   https://api-mifit-us3.zepp.com/users/.../bloodPressure?...
```

If you don't see those — see "Troubleshooting" below.

---

## Step 7 — Export the capture

In the mitmproxy terminal:

1. Type a forward slash `/` to open the filter prompt
2. Type `~d zepp.com` then press Enter → this filters to only Zepp traffic
3. Type a colon `:` to open the command prompt
4. Type: `export.file har @all ~/capture.har` then press Enter
5. You'll see "Saved to: ~/capture.har"
6. Press `q` then `y` to exit mitmproxy

Verify the file exists:

```bash
ls -lh ~/capture.har
# should show a file, typically 50KB to several MB
```

---

## Step 8 — Disable the proxy on your phone (important!)

Otherwise your phone keeps trying to talk through a proxy that's no longer running.

**iPhone:**

1. Settings → Wi-Fi → (i) next to your network → Configure Proxy → **Off**

**Then remove the mitmproxy certificate** (don't leave a dev cert installed on your phone):

1. Settings → General → VPN & Device Management
2. Tap **mitmproxy** profile → **Remove Profile** → enter passcode

**Android:** Wi-Fi settings → proxy: None. Remove the cert from Security → Trusted credentials → User → mitmproxy → Remove.

---

## Step 9 — Hand off the HAR to bio-bridge

```bash
cd /Users/michaellevy/projects/bio-bridge
.venv/bin/bio-bridge init ~/capture.har
```

This prints something like:

```
Extracted: app_token=AbCdEf..., user_id=1234567890, host=api-mifit-us3.zepp.com
Wrote config.json (chmod 600).
```

Then immediately:

```bash
shred -u ~/capture.har    # macOS: brew install coreutils for `gshred`, OR just rm
rm -P ~/capture.har        # macOS native secure delete
```

The credentials now live only in `config.json` (chmod 600, gitignored), or in the environment variables you set for a deployment.

---

## Troubleshooting

### "I don't see any traffic in mitmproxy"

- Your phone isn't actually proxying. Check Settings → Wi-Fi → (i) → HTTP Proxy is set to Manual with the right IP.
- Try opening Safari on the phone and visiting any website — you should see those requests in mitmproxy. If not, the proxy itself isn't working.

### "I see traffic but no zepp.com entries"

- The Zepp app on your phone refuses to send requests through the proxy. This usually means certificate trust isn't working.
- Double-check Settings → General → About → Certificate Trust Settings → mitmproxy is ON.

### "The Zepp app shows an error like 'Network error' or just blank screens"

- Zepp may have added TLS pinning since this runbook was written (worst-case scenario in §13 of the design doc). Try a Frida bypass or fall back to whatever endpoints still work unpinned.

### "I closed mitmproxy before exporting"

- Re-do steps 3, 6, 7. Don't worry about the cert install — it's still trusted from before.

### "The HAR file is tiny (under 5KB)"

- You probably didn't generate enough traffic in step 6. Open the Zepp app, scroll a lot, tap into Sleep and Heart Rate detail views, and try again.

---

## Security notes

- The HAR file contains your live `apptoken`. Anyone with that file can read your Zepp data until you log out of the Zepp app on your phone.
- Always disable the phone proxy after capture. Leaving it on means your phone tries to talk through a dead proxy → no internet.
- Always remove the mitmproxy profile after capture. Leaving a dev CA on your phone is a security risk — anyone who controls that cert can intercept your HTTPS traffic.
- Always shred/securely-delete the HAR after extraction. `rm` on macOS doesn't really delete the file's content — use `rm -P` or `shred -u`.
