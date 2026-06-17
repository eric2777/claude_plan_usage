# Claude Plan Usage Tracker

Displays your Claude Pro plan session usage (%) in real time — as a macOS menu bar item via [SwiftBar](https://github.com/swiftbar/SwiftBar) and/or as a tmux status bar segment.

```
Claude 42%          ← tmux status bar (normal)
Claude ⚠️ 85%       ← tmux status bar (alert threshold reached, shown in red)
```

---

## Requirements

- macOS
- Python 3 (pre-installed on macOS)
- `swiftc` (Xcode Command Line Tools): `xcode-select --install`
- [SwiftBar](https://github.com/swiftbar/SwiftBar) — for the menu bar plugin only
- tmux — for the status bar segment only

---

## How It Works

The scripts call `claude.ai`'s internal usage API. Because Cloudflare blocks Python's `urllib` and `curl` via TLS fingerprinting, a small Swift binary is compiled on first run and used instead — it uses `URLSession` (Safari's TLS stack), which Cloudflare doesn't block. The binary is compiled once and cached; subsequent runs use the cached binary.

Both scripts share `claude_fetch.py` (the fetch + compilation logic) but are otherwise fully independent: separate config files, caches, session keys, and compiled binaries.

---

## Getting Your Session Key

1. Open [claude.ai](https://claude.ai) in your browser and log in
2. Open DevTools (`Cmd+Option+I`)
3. Go to **Application** → **Cookies** → `claude.ai`
4. Find the `sessionKey` cookie and copy its value (starts with `sk-ant-sid`)

---

## SwiftBar Menu Bar Plugin

### Install SwiftBar

Download from [swiftbar.app](https://swiftbar.app) or via Homebrew:

```bash
brew install --cask swiftbar
```

Set your SwiftBar plugins directory when prompted (e.g. `~/swiftbar plugins`).

### Install the Plugin

```bash
make install
```

This copies `claude-usage.60s.py` and `claude_fetch.py` to your SwiftBar plugins directory (`~/swiftbar plugins` by default — edit `Makefile` if yours differs).

SwiftBar picks up the script automatically. The `60s` in the filename tells SwiftBar to refresh every 60 seconds.

### Configure

On first run, click the menu bar item → **Settings** → **Set session key** and paste your session key. You can also set the alert threshold and refresh interval from the same menu.

Config is stored at `~/.config/claude-usage/config.json`:

```json
{
  "session_key": "sk-ant-sid01-...",
  "interval_s": 60,
  "alert_pct": 80
}
```

### What It Shows

Click the menu bar item to expand:

```
Claude 42%                     ← menu bar title
---
Session:  42%  → 100% in ~3h (est.)
Weekly:   15%
Resets:   session in 3h 12m
          weekly  in 6d 14h
---
Settings
  Set session key
  Set refresh interval
  Set alert threshold
About
```

When usage reaches the alert threshold, the title turns red: `Claude ⚠️ 85%`.

---

## tmux Status Bar Segment

### Install

The tmux script runs directly from the repo — no `make install` needed. Copy the two required files to a permanent location:

```bash
mkdir -p ~/.config/tmux/scripts
cp claude-usage-tmux.py claude_fetch.py ~/.config/tmux/scripts/
```

### Configure

Create `~/.config/claude-usage-tmux/config.json`:

```json
{
  "session_key": "sk-ant-sid01-...",
  "interval_s": 60,
  "alert_pct": 80
}
```

| Field | Default | Description |
|---|---|---|
| `session_key` | `""` | Cookie value from claude.ai (required) |
| `interval_s` | `60` | Minimum seconds between API calls (network gate, independent of tmux's `status-interval`) |
| `alert_pct` | `80` | Usage % at which the segment turns red |

### Wire into `.tmux.conf`

Append to (or replace) your `status-right`. Example that prepends Claude usage before the default date/time:

```tmux
set -g status-right '   #(python3 ~/.config/tmux/scripts/claude-usage-tmux.py) #{?window_bigger,[#{window_offset_x}#,#{window_offset_y}] ,}"#{=21:pane_title}" %H:%M %d-%b-%y'
set -g status-interval 30
```

Then reload:

```bash
tmux source ~/.tmux.conf
```

### What It Shows

| State | Output |
|---|---|
| Normal | `Claude 42%` |
| At/above alert threshold | `Claude ⚠️ 85%` (red) |
| No session key configured | `Claude ⚙ setup` |
| Fetch failed, no cache | `Claude ?` |

When a fetch fails but a previous result is cached, the cached value is shown silently (no error indicator — status bars have no room for it).

---

## Runtime Files

### SwiftBar plugin

| Path | Purpose |
|---|---|
| `~/.config/claude-usage/config.json` | Session key, interval, alert threshold |
| `~/.cache/claude-usage/result.json` | Last API response (cache) |
| `~/.cache/claude-usage/history.json` | Rolling 15-min window for ETA calculation |
| `~/.config/claude-usage/fetch` | Compiled Swift binary (auto-created on first run) |

### tmux segment

| Path | Purpose |
|---|---|
| `~/.config/claude-usage-tmux/config.json` | Session key, interval, alert threshold |
| `~/.cache/claude-usage-tmux/result.json` | Last API response (cache) |
| `~/.config/claude-usage-tmux/fetch` | Compiled Swift binary (auto-created on first run) |

---

## Development

```bash
make test      # run all tests (pytest)
make run       # run the SwiftBar plugin directly and print its output
make install   # copy SwiftBar plugin files to ~/swiftbar plugins/
```

Run a single test:

```bash
python3 -m pytest tests/test_claude_usage.py::test_format_menu_bar_normal -v
```

### Project Structure

```
claude-usage.60s.py      SwiftBar menu bar plugin
claude-usage-tmux.py     tmux status bar segment
claude_fetch.py          Shared fetch module (Cloudflare TLS workaround)
tests/
  test_claude_usage.py
  test_claude_fetch.py
  test_claude_usage_tmux.py
```

### Session Key Expiry

Session keys expire periodically. When the menu bar item shows `Claude ⚠️ auth` or the tmux segment shows `Claude ?`, re-copy your `sessionKey` cookie from the browser and update both config files.
