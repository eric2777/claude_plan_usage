# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two independent scripts display Claude plan session usage (%) in real time:

- `claude-usage.60s.py` — a SwiftBar macOS menu bar plugin. SwiftBar runs it every 60 seconds (interval encoded in filename) and renders its stdout as a menu bar item.
- `claude-usage-tmux.py` — a tmux status bar segment, invoked via `#()` command substitution from `.tmux.conf`.

Both scripts share `claude_fetch.py` (the Cloudflare TLS workaround for calling claude.ai's API) but otherwise have completely separate config, cache, and session keys.

## Commands

```bash
make test      # run pytest
make run       # run the plugin script directly (prints SwiftBar-formatted stdout)
make install   # copy plugin to ~/swiftbar plugins/
```

Run a single test:
```bash
python3 -m pytest tests/test_claude_usage.py::test_format_menu_bar_normal
```

## Architecture

### Shared: `claude_fetch.py`

Both scripts import `fetch_usage(session_key, binary_path)` from this module. It holds `SWIFT_SOURCE` (an embedded Swift program using `URLSession` — Cloudflare blocks Python `urllib`/`curl` via TLS fingerprinting, but not Safari's TLS stack) and `_ensure_fetch_binary(binary_path)`, which compiles it via `swiftc` on first use. Each caller passes its own `binary_path` and ends up with its own compiled copy — no shared runtime state.

### `claude-usage.60s.py` (SwiftBar menu bar plugin)

No dependencies beyond the Python stdlib (plus `claude_fetch`).

**Runtime paths:**
- Config: `~/.config/claude-usage/config.json` — session key, refresh interval, alert threshold
- Cache: `~/.cache/claude-usage/result.json` — last API response with timestamp
- History: `~/.cache/claude-usage/history.json` — rolling window of `session_pct` readings used to compute ETA
- Fetch binary: `~/.config/claude-usage/fetch` — compiled on first run via `claude_fetch._ensure_fetch_binary`

**Data flow:**
1. SwiftBar executes the script every 60s
2. If cache is fresh (age < `interval_s`), render cached data — no network call
3. If stale, call `claude_fetch.fetch_usage()` (which calls `claude.ai/api/organizations` then `.../usage`) and write new cache + append to history
4. On fetch failure, render stale cache with a "last updated Xm ago" warning
5. Print line 1 as the menu bar title; everything after `---` becomes the dropdown

**Key functions:**
- `calc_eta_minutes()` — linear rate from the 15-minute history window to estimate time to 100%
- `format_eta_line()` — suppresses ETA if it would land after the session reset time
- `format_dropdown()` — builds the full SwiftBar dropdown text including settings menu items
- `handle_set_*()` — action handlers dispatched from SwiftBar menu items via `sys.argv[1]`

**Tests** import the module dynamically from its `.py` filename path (`importlib.util.spec_from_file_location`) since it contains a dot in the name. Tests use `tempfile.TemporaryDirectory` for isolation and `unittest.mock.patch` for `subprocess.run` and `run_osascript_dialog`.

### `claude-usage-tmux.py` (tmux status bar segment)

Fully independent of the SwiftBar plugin — separate config, cache, session key, and compiled fetch binary. No history/ETA tracking; prints a single status line, no dropdown.

**Runtime paths:**
- Config: `~/.config/claude-usage-tmux/config.json` — session key, refresh interval, alert threshold (same schema as the SwiftBar config, but a separate file — edit by hand, no setup dialog)
- Cache: `~/.cache/claude-usage-tmux/result.json`
- Fetch binary: `~/.config/claude-usage-tmux/fetch`

**Output:**

| State | Output |
|---|---|
| Normal | `Claude 39%` |
| `session_pct >= alert_pct` | `#[fg=red]Claude ⚠️ 85%#[default]` (tmux re-parses `#[...]` in `#()` output) |
| No session key configured | `Claude ⚙ setup` |
| Fetch fails, no cache | `Claude ?` |

**Setup:**
1. Get your session key the same way as for the SwiftBar plugin: open claude.ai → DevTools → Application → Cookies → claude.ai → copy `sessionKey`
2. Create `~/.config/claude-usage-tmux/config.json`:
   ```json
   {
     "session_key": "sk-ant-sid01-...",
     "interval_s": 60,
     "alert_pct": 80
   }
   ```
3. Add to `.tmux.conf`:
   ```tmux
   set -g status-right '#(python3 /absolute/path/to/repo/claude-usage-tmux.py)'
   set -g status-interval 30
   ```

Note: `claude-usage-tmux.py` is run **in-place from the repo directory** (not installed by `make install`). Because tmux invokes it via an absolute path, `claude_fetch.py` is automatically co-located — no install step needed.

**Tests** use the same `importlib` dynamic-loading pattern as `claude-usage.60s.py` (dashes in the filename).
