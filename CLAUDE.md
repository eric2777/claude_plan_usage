# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A macOS menu bar widget (SwiftBar plugin) that displays Claude plan session and weekly usage % in real time. A single Python script (`claude-usage.60s.py`) is installed into SwiftBar's plugins directory — SwiftBar runs it every 60 seconds and renders its stdout as the menu bar item and dropdown.

## Commands

```bash
# Run all tests
python3 -m pytest tests/

# Run a single test
python3 -m pytest tests/test_claude_usage.py::test_fetch_usage_returns_normalized_data -v

# Run the plugin locally (renders menu bar output to stdout)
python3 claude-usage.60s.py

# Install the plugin to SwiftBar
cp claude-usage.60s.py ~/Library/Application\ Support/SwiftBar/Plugins/claude-usage.60s.py

# Force-recompile the Swift fetch binary (delete it so _ensure_fetch_binary() rebuilds)
rm -f ~/.config/claude-usage/fetch
```

## Architecture

**Single-file plugin:** All logic lives in `claude-usage.60s.py`. The filename encodes the SwiftBar refresh interval (`60s`). There is no package, no build step, no pip dependencies — stdlib only.

**Swift binary for HTTP:** Cloudflare blocks Python `urllib` and `curl` to `claude.ai` (TLS fingerprinting). The plugin compiles a Swift binary (`~/.config/claude-usage/fetch`) on first run using `swiftc`. `_ensure_fetch_binary()` writes the embedded `SWIFT_SOURCE` to a temp file, compiles it, then deletes the source. The binary reads `SESSION_KEY` from the environment, calls the claude.ai API using `URLSession` (Safari's TLS stack), and outputs normalized JSON to stdout.

**API flow (inside the Swift binary):**
1. `GET https://claude.ai/api/organizations` → get org UUID (cookie auth: `sessionKey=...`)
2. `GET https://claude.ai/api/organizations/{orgId}/usage` → `five_hour.utilization`, `five_hour.resets_at`, `seven_day.utilization`, `seven_day.resets_at`

**Cache:** `~/.cache/claude-usage/result.json` stores the last successful API response with a timestamp. The plugin skips the API call if cache age < `config.interval_s`. On API failure it falls back to stale cache.

**Settings dispatch:** SwiftBar menu items use `bash="{script_path}" param1=<action>` to re-invoke the script with an action name. `main()` checks `sys.argv[1]` against `ACTIONS` dict and calls the matching handler, which opens an `osascript` dialog, validates input, and writes to `config.json`.

**Runtime files:**

| Path | Purpose |
|------|---------|
| `~/.config/claude-usage/config.json` | `session_key`, `interval_s` (default 60), `alert_pct` (default 80) |
| `~/.cache/claude-usage/result.json` | Cached API response + timestamp |
| `~/.config/claude-usage/fetch` | Compiled Swift binary (auto-built on first run) |

## Tests

`tests/test_claude_usage.py` loads the plugin via `importlib.util` (needed because the filename contains dots). All 23 tests use only stdlib + pytest — no external dependencies. Fetch tests mock `subprocess.run` and `_ensure_fetch_binary` — do not mock `urllib`.
