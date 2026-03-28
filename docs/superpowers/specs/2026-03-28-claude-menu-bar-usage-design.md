# Claude Plan Usage — macOS Menu Bar Widget

**Date:** 2026-03-28
**Status:** Approved

---

## Overview

A lightweight macOS menu bar widget that displays Claude plan session usage (%) in real time. Built on SwiftBar — a free menu bar host that runs a script on an interval and renders its stdout output. No persistent process, minimal CPU and memory footprint.

---

## Goals

- Always-visible session usage % in the menu bar
- Click to see session + weekly detail and change settings
- Visual alert (color change) when usage crosses a configurable threshold
- Very low resource footprint: no persistent process, no dependencies beyond Python stdlib

---

## Non-Goals

- macOS notifications (visual alert only)
- Multiple account support
- Usage history or charting

---

## Components

| Component | Location | Purpose |
|-----------|----------|---------|
| SwiftBar | Installed via Homebrew or direct download | Menu bar host, runs the plugin script on a schedule |
| `claude-usage.60s.py` | `~/Library/Application Support/SwiftBar/Plugins/` | Single script: fetches data, formats output, prints to stdout |
| `config.json` | `~/.config/claude-usage/config.json` | User settings: API key, refresh interval, alert threshold |
| `result.json` | `~/.cache/claude-usage/result.json` | Cached API response with timestamp |

---

## Data Flow

```
SwiftBar runs claude-usage.60s.py every 60s
  │
  ├── config.json missing or no API key?
  │     └── print "Claude ⚙ setup" + dropdown with "Set API Key..."
  │
  ├── result.json fresh (age < config.interval_s)?
  │     └── skip API call, render cached data
  │
  └── result.json stale or missing?
        ├── call Anthropic usage API with API key
        ├── success → write result.json, render fresh data
        └── failure → render stale data + "⚠ last updated Xm ago"
```

---

## API

The widget calls the Anthropic usage endpoint authenticated with an API key (`Authorization: Bearer sk-...`).

**Open prerequisite:** Confirm the exact endpoint and response schema. If no public endpoint exists, discover it via one-time network inspection of the Claude desktop app (e.g., Charles Proxy or mitmproxy). This must be resolved before implementation begins.

Expected response fields needed:
- Session usage % and reset time
- Weekly usage % and reset time

---

## Menu Bar Display

**Normal state:**
```
Claude 39%
```

**At or above alert threshold:**
```
Claude ⚠️ 85%   ← orange/red text via SwiftBar color= parameter
```

**No API key configured:**
```
Claude ⚙ setup
```

---

## Dropdown Layout

```
Claude 39%
---
Session: 39%  (resets in 1h 48m)
Weekly:  15%  (resets Fri 9:59 AM)
Last updated: 30s ago
---
⚙ Settings
-- 🔑 Set API Key...
-- ⏱ Refresh interval: 60s  →  click to change
-- 🔔 Alert threshold: 80%   →  click to change
---
↻ Refresh now
```

Each settings item triggers an `osascript` dialog to collect the new value, validates it, writes to `config.json`, and triggers an immediate SwiftBar refresh.

---

## Config Schema

```json
{
  "api_key": "sk-ant-...",
  "interval_s": 60,
  "alert_pct": 80
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `api_key` | — | Anthropic API key (required) |
| `interval_s` | `60` | Seconds between API calls (SwiftBar always runs every 60s; script skips the API call if cache is fresh) |
| `alert_pct` | `80` | Session usage % at which menu bar text turns orange/red |

---

## File Layout

```
~/Library/Application Support/SwiftBar/Plugins/
  claude-usage.60s.py

~/.config/claude-usage/
  config.json

~/.cache/claude-usage/
  result.json
```

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| No config / no API key | Menu bar shows "Claude ⚙ setup"; dropdown prompts to set API key |
| API call fails | Show stale cached data with staleness age indicator |
| Cache missing + API fails | Menu bar shows "Claude ?" |
| Invalid config value entered | Dialog re-prompts or shows error, does not write bad value |

---

## Dependencies

- **SwiftBar** — free, installed once by the user
- **Python 3** — pre-installed on macOS
- **No pip packages** — stdlib only (`urllib`, `json`, `os`, `datetime`)

---

## Open Questions

1. **API endpoint** — confirm URL and response schema before implementation (see API section above)
