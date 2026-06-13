# Claude Plan Usage — tmux Status Bar Segment

**Date:** 2026-06-13
**Status:** Approved

---

## Overview

A new, independent script that displays Claude plan session usage (%) as a segment in the tmux status bar — the tmux analog of the existing `claude-usage.60s.py` SwiftBar menu bar widget. It is fully independent of the SwiftBar plugin (separate config, cache, session key, and compiled fetch binary), but shares the small piece of code that works around Cloudflare's TLS-fingerprint blocking of `urllib`/`curl`.

---

## Goals

- A tmux status bar segment showing `Claude <session_pct>%`, color-highlighted at a configurable alert threshold
- Fully independent from the SwiftBar plugin: own config file, own cache, own session key, own compiled fetch binary
- Plain script + manual `.tmux.conf` wiring (no TPM plugin structure, no plugin manager)
- Reuse the Cloudflare TLS workaround (compiled Swift fetch binary) without duplicating ~50 lines of Swift source and its compile logic

---

## Non-Goals

- No click-to-detail popup, dropdown, or `display-popup` integration
- No weekly usage %, reset times, or ETA-to-100% in the tmux segment
- No interactive setup flow (`tmux command-prompt`, `osascript` dialogs, etc.) — config is a hand-edited JSON file
- No syncing or config sharing with the SwiftBar plugin (not even a one-time copy of the session key)
- No TPM (Tmux Plugin Manager) packaging

---

## Architecture

### New shared module: `claude_fetch.py`

Extracted from `claude-usage.60s.py` verbatim (no behavior change):

- `SWIFT_SOURCE` — the embedded Swift program that calls `claude.ai/api/organizations` and `.../usage` via `URLSession` (Safari's TLS stack, which Cloudflare doesn't block)
- `_ensure_fetch_binary(binary_path)` — compiles `SWIFT_SOURCE` via `swiftc` to `binary_path` if it doesn't exist yet
- `fetch_usage(session_key, binary_path)` — runs the compiled binary with `SESSION_KEY` in the environment, returns the normalized JSON dict (`session_pct`, `weekly_pct`, `session_reset_at`, `weekly_reset_at`)

Both `claude-usage.60s.py` and `claude-usage-tmux.py` import this module and pass **their own** `binary_path`. Each compiles and keeps its own binary at its own path — there is no shared runtime state, only shared code.

### Refactored: `claude-usage.60s.py`

- Removes its local `SWIFT_SOURCE`, `_ensure_fetch_binary`, and `fetch_usage` definitions
- Adds `from claude_fetch import fetch_usage`
- No other changes — cache, config, history, ETA, and dropdown logic are unaffected (the tmux script needs none of this)

### New: `claude-usage-tmux.py`

A small, self-contained script (aside from the `claude_fetch` import) with its own runtime paths:

| Constant | Path |
|---|---|
| `CONFIG_PATH` | `~/.config/claude-usage-tmux/config.json` |
| `CACHE_PATH` | `~/.cache/claude-usage-tmux/result.json` |
| `FETCH_BINARY` | `~/.config/claude-usage-tmux/fetch` |

No history file, no ETA calculation — out of scope per Non-Goals.

`load_config`, `save_config`, `load_cache`, `save_cache`, and `cache_age_seconds` are reimplemented locally (each ~5 lines, parameterized by path). They are small enough that duplicating them keeps this script readable on its own, rather than pulling cache/config helpers into the shared module too.

---

## Data Flow

```
tmux runs `#(python3 claude-usage-tmux.py)` every status-interval seconds
  │
  ├── config.json missing or no session_key?
  │     └── print "Claude ⚙ setup"
  │
  ├── result.json fresh (age < config.interval_s)?
  │     └── skip fetch, use cached data
  │
  └── result.json stale or missing?
        ├── fetch_usage(session_key, FETCH_BINARY) via claude_fetch
        ├── success → write result.json, use fresh data
        └── failure → fall back to cached data if present
              └── still nothing? → print "Claude ?"

Render: format_status(session_pct, alert_pct)
```

---

## Display Format

tmux re-parses `#[...]` style directives found in `#()` command-substitution output, so the script can color itself directly:

| State | Output |
|---|---|
| Normal | `Claude 39%` |
| `session_pct >= alert_pct` | `#[fg=red]Claude ⚠️ 85%#[default]` |
| No session key configured | `Claude ⚙ setup` |
| Fetch fails, stale cache available | Render the stale `session_pct` normally (same rules as above) — no "last updated Xm ago" text; there's no room and no popup to put it in |
| Fetch fails, no cache at all | `Claude ?` |

---

## Config Schema

`~/.config/claude-usage-tmux/config.json` — created and edited by hand:

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
| `interval_s` | `60` | Minimum seconds between actual API calls (independent of tmux's `status-interval`) |
| `alert_pct` | `80` | Session usage % at which the segment turns red |

If the file is missing or `session_key` is empty, the script prints `Claude ⚙ setup` and exits. Setup instructions (how to get the session key, where to put this file) live in `CLAUDE.md`.

---

## `.tmux.conf` Wiring

```tmux
set -g status-right '#(python3 /absolute/path/to/repo/claude-usage-tmux.py)'
set -g status-interval 30
```

`status-interval` controls how often tmux re-runs the script (display refresh); `interval_s` in the config controls how often it actually hits the network (gated by the cache). A `status-interval` of 30s with the default `interval_s` of 60 means roughly every other tick is a cache hit.

---

## File Layout

```
<repo>/
  claude-usage.60s.py        (refactored: imports claude_fetch)
  claude_fetch.py             (new, shared)
  claude-usage-tmux.py        (new)
  Makefile                     (install also copies claude_fetch.py)
  tests/
    test_claude_usage.py       (3 fetch_usage tests updated to patch claude_fetch)
    test_claude_fetch.py        (new)
    test_claude_usage_tmux.py    (new)

Runtime (tmux, independent of SwiftBar paths):
~/.config/claude-usage-tmux/config.json
~/.config/claude-usage-tmux/fetch        (compiled binary, separate copy)
~/.cache/claude-usage-tmux/result.json
```

---

## Error Handling

| Condition | Behavior |
|---|---|
| No config / no session key | `Claude ⚙ setup` |
| Fetch fails, cache exists | Use stale cached `session_pct`, formatted normally |
| Fetch fails, no cache | `Claude ?` |
| `session_pct >= alert_pct` | Red via `#[fg=red]...#[default]` |

---

## Testing

- `tests/test_claude_fetch.py` — `_ensure_fetch_binary` and `fetch_usage` (moved from `test_claude_usage.py`), mocking `subprocess.run`
- `tests/test_claude_usage.py` — the 3 existing `fetch_usage`-related tests updated to patch `claude_fetch._ensure_fetch_binary` instead of the SwiftBar module's (now-removed) local copy; everything else unchanged
- `tests/test_claude_usage_tmux.py` — loaded via `importlib` (dashes in filename, same pattern as the existing test file):
  - `load_config` / `save_config` / `load_cache` / `save_cache` / `cache_age_seconds` round-trips
  - `format_status` for normal, alert-threshold, setup, and unknown (`?`) states
  - `main()` flow with `fetch_usage` mocked (success, failure-with-cache, failure-without-cache)

---

## Dependencies

- **tmux** with support for `#[...]` style directives in `#()` command-substitution output (standard in any reasonably recent tmux — the same technique used by common status-bar plugins like tmux-battery) — already required by the user
- **Python 3** — pre-installed on macOS
- **swiftc** — already required by the existing SwiftBar plugin for the same Cloudflare workaround
- No pip packages — stdlib only
