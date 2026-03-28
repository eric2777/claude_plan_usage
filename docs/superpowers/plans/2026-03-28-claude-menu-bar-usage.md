# Claude Menu Bar Usage Widget — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A SwiftBar Python plugin that displays Claude plan session usage % in the macOS menu bar with a clickable dropdown for details and settings.

**Architecture:** A single Python script (`claude-usage.60s.py`) placed in the SwiftBar plugins directory. SwiftBar runs it every 60 seconds; the script reads a config file, checks a local cache, optionally calls the Anthropic usage API, then prints formatted text to stdout which SwiftBar renders as the menu bar item and dropdown.

**Tech Stack:** Python 3 (stdlib only: `urllib`, `json`, `os`, `subprocess`, `datetime`), SwiftBar, macOS `osascript` for settings dialogs.

---

## File Map

| File | Purpose |
|------|---------|
| `claude-usage.60s.py` | Single SwiftBar plugin script — all logic lives here |
| `tests/test_claude_usage.py` | Unit tests for all pure functions |
| `~/.config/claude-usage/config.json` | Runtime config (API key, interval, threshold) |
| `~/.cache/claude-usage/result.json` | Cached API response with timestamp |

---

## ⚠️ Task 1: Discover the API Endpoint (Manual — Do First)

> **This is a prerequisite. Do not write any API fetch code until this is resolved.**

The Claude desktop app's Settings > Usage screen shows plan consumption data. The widget needs to call the same endpoint. It is **not certain** this endpoint is accessible via a public Anthropic API key (`sk-ant-...`) — it may require a claude.ai session token instead.

### Investigation steps

- [ ] **Step 1: Check Anthropic's public API docs**

  Visit `https://docs.anthropic.com` and search for "usage", "plan", "limits". Look for any endpoint returning session or weekly consumption percentages. If found, note the URL, required headers, and response schema — then skip to Step 4.

- [ ] **Step 2: Open Claude desktop app DevTools**

  In the Claude desktop app, try: `Help > Toggle Developer Tools` or `Cmd+Option+I`. If DevTools opens, go to the **Network** tab, then navigate to **Settings > Usage** in the app. Look for an XHR/fetch request returning usage percentages. Note the URL and request headers.

- [ ] **Step 3: If DevTools unavailable — use a proxy**

  Install mitmproxy: `brew install mitmproxy`

  Run it:
  ```bash
  mitmweb --listen-port 8080
  ```

  In System Settings > Network > your connection > Proxies, set HTTP and HTTPS proxy to `127.0.0.1:8080`. Trust the mitmproxy cert when prompted. Open the Claude desktop app, go to Settings > Usage, and capture the request in the mitmweb browser at `http://127.0.0.1:8081`.

- [ ] **Step 4: Record findings**

  Fill in the blanks:
  ```
  Endpoint URL:    _________________________________
  Auth header:     _________________________________
  Auth value:      _________________________________  (API key / session token / cookie)
  Response schema: see sample below
  ```

  Sample response to capture:
  ```json
  {
    "session_pct": 39,
    "session_reset_at": "2026-03-28T14:00:00Z",
    "weekly_pct": 15,
    "weekly_reset_at": "2026-03-29T09:59:00Z"
  }
  ```
  (Field names may differ — note the actual field names from the real response.)

- [ ] **Step 5: Update constants in Task 4**

  Once discovered, replace the placeholder `API_ENDPOINT` and `fetch_usage()` auth headers in Task 4 with the real values.

---

## Task 2: Project Scaffold and Config Management

**Files:**
- Create: `claude-usage.60s.py`
- Create: `tests/test_claude_usage.py`

- [ ] **Step 1: Write failing tests for config management**

  Create `tests/test_claude_usage.py`:

  ```python
  import importlib.util
  import json
  import os
  import sys
  import tempfile

  def load_module():
      script_path = os.path.join(os.path.dirname(__file__), "..", "claude-usage.60s.py")
      spec = importlib.util.spec_from_file_location("claude_usage", os.path.abspath(script_path))
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      return module

  m = load_module()

  def test_load_config_defaults_when_missing():
      with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as f:
          path = f.name
      # file does not exist
      config = m.load_config(path)
      assert config["interval_s"] == 60
      assert config["alert_pct"] == 80
      assert config["api_key"] == ""

  def test_load_config_merges_with_defaults():
      with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
          json.dump({"api_key": "sk-test", "alert_pct": 90}, f)
          path = f.name
      config = m.load_config(path)
      assert config["api_key"] == "sk-test"
      assert config["alert_pct"] == 90
      assert config["interval_s"] == 60  # default preserved
      os.unlink(path)

  def test_save_and_reload_config():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          m.save_config({"api_key": "sk-abc", "interval_s": 120, "alert_pct": 75}, path)
          config = m.load_config(path)
          assert config["api_key"] == "sk-abc"
          assert config["interval_s"] == 120
          assert config["alert_pct"] == 75
  ```

- [ ] **Step 2: Run tests — verify they fail (module not found)**

  ```bash
  cd "/Users/user/Anloreric Dropbox/Eric Perraudeau/SeldonIA/code/claude plan usage tracker"
  python3 -m pytest tests/test_claude_usage.py -v 2>&1 | head -20
  ```

  Expected: error loading module (file doesn't exist yet).

- [ ] **Step 3: Create the plugin script with config functions**

  Create `claude-usage.60s.py`:

  ```python
  #!/usr/bin/env python3
  # -*- coding: utf-8 -*-
  # <swiftbar.title>Claude Usage</swiftbar.title>
  # <swiftbar.version>1.0</swiftbar.version>
  # <swiftbar.desc>Shows Claude plan session usage % in the menu bar</swiftbar.desc>

  import json
  import os
  import subprocess
  import sys
  import urllib.request
  import urllib.error
  from datetime import datetime

  CONFIG_PATH = os.path.expanduser("~/.config/claude-usage/config.json")
  CACHE_PATH = os.path.expanduser("~/.cache/claude-usage/result.json")
  DEFAULT_CONFIG = {"api_key": "", "interval_s": 60, "alert_pct": 80}


  def load_config(path=CONFIG_PATH):
      if not os.path.exists(path):
          return dict(DEFAULT_CONFIG)
      with open(path) as f:
          data = json.load(f)
      return {**DEFAULT_CONFIG, **data}


  def save_config(config, path=CONFIG_PATH):
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path, "w") as f:
          json.dump(config, f, indent=2)


  if __name__ == "__main__":
      pass
  ```

- [ ] **Step 4: Run tests — verify they pass**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -v
  ```

  Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git init
  git add "claude-usage.60s.py" "tests/test_claude_usage.py"
  git commit -m "feat: scaffold plugin with config load/save"
  ```

---

## Task 3: Cache Management

**Files:**
- Modify: `claude-usage.60s.py`
- Modify: `tests/test_claude_usage.py`

- [ ] **Step 1: Write failing tests for cache**

  Append to `tests/test_claude_usage.py`:

  ```python
  import time

  def test_load_cache_returns_none_when_missing():
      with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as f:
          path = f.name
      assert m.load_cache(path) is None

  def test_save_and_load_cache():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "result.json")
          data = {"session_pct": 39, "weekly_pct": 15,
                  "session_reset_at": "2026-03-28T14:00:00",
                  "weekly_reset_at": "2026-03-29T09:59:00"}
          m.save_cache(data, path)
          cache = m.load_cache(path)
          assert cache["data"]["session_pct"] == 39
          assert "timestamp" in cache

  def test_cache_age_seconds():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "result.json")
          data = {"session_pct": 50, "weekly_pct": 10,
                  "session_reset_at": "2026-03-28T14:00:00",
                  "weekly_reset_at": "2026-03-29T09:59:00"}
          m.save_cache(data, path)
          cache = m.load_cache(path)
          age = m.cache_age_seconds(cache)
          assert 0 <= age < 2  # written just now
  ```

- [ ] **Step 2: Run tests — verify new tests fail**

  ```bash
  python3 -m pytest tests/test_claude_usage.py::test_load_cache_returns_none_when_missing -v
  ```

  Expected: FAIL (function not defined).

- [ ] **Step 3: Add cache functions to plugin**

  Add after `save_config` in `claude-usage.60s.py`:

  ```python
  def load_cache(path=CACHE_PATH):
      if not os.path.exists(path):
          return None
      with open(path) as f:
          return json.load(f)


  def save_cache(data, path=CACHE_PATH):
      os.makedirs(os.path.dirname(path), exist_ok=True)
      entry = {"timestamp": datetime.now().isoformat(), "data": data}
      with open(path, "w") as f:
          json.dump(entry, f, indent=2)


  def cache_age_seconds(cache):
      ts = datetime.fromisoformat(cache["timestamp"])
      return (datetime.now() - ts).total_seconds()
  ```

- [ ] **Step 4: Run tests — verify all pass**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -v
  ```

  Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add "claude-usage.60s.py" "tests/test_claude_usage.py"
  git commit -m "feat: add cache load/save with age check"
  ```

---

## Task 4: API Fetch

> **Prerequisite: Task 1 must be complete.** Replace `API_ENDPOINT` and auth headers below with the values discovered in Task 1.

**Files:**
- Modify: `claude-usage.60s.py`
- Modify: `tests/test_claude_usage.py`

- [ ] **Step 1: Write failing tests for fetch_usage**

  Append to `tests/test_claude_usage.py`:

  ```python
  from unittest.mock import patch, MagicMock
  import urllib.error

  def test_fetch_usage_returns_parsed_data():
      fake_response = json.dumps({
          "session_pct": 39,
          "session_reset_at": "2026-03-28T14:00:00Z",
          "weekly_pct": 15,
          "weekly_reset_at": "2026-03-29T09:59:00Z"
      }).encode()

      mock_resp = MagicMock()
      mock_resp.read.return_value = fake_response
      mock_resp.__enter__ = lambda s: s
      mock_resp.__exit__ = MagicMock(return_value=False)

      with patch("urllib.request.urlopen", return_value=mock_resp):
          data = m.fetch_usage("sk-test", "https://fake.endpoint/usage")

      assert data["session_pct"] == 39
      assert data["weekly_pct"] == 15

  def test_fetch_usage_raises_on_http_error():
      with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
          url=None, code=401, msg="Unauthorized", hdrs=None, fp=None
      )):
          try:
              m.fetch_usage("sk-bad", "https://fake.endpoint/usage")
              assert False, "should have raised"
          except urllib.error.HTTPError as e:
              assert e.code == 401
  ```

- [ ] **Step 2: Run tests — verify new tests fail**

  ```bash
  python3 -m pytest tests/test_claude_usage.py::test_fetch_usage_returns_parsed_data -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Add API fetch function**

  Add after `cache_age_seconds` in `claude-usage.60s.py`.

  Replace `API_ENDPOINT` with the URL discovered in Task 1. Replace the auth header if session token auth is required.

  ```python
  # ── Replace with values from Task 1 ──────────────────────────────────────────
  API_ENDPOINT = "https://api.anthropic.com/v1/usage/plan"  # UPDATE THIS
  # If session token auth is needed instead of API key, adjust fetch_usage() below.
  # ─────────────────────────────────────────────────────────────────────────────


  def fetch_usage(api_key, endpoint=API_ENDPOINT):
      req = urllib.request.Request(endpoint)
      req.add_header("Authorization", f"Bearer {api_key}")
      req.add_header("anthropic-version", "2023-06-01")
      with urllib.request.urlopen(req, timeout=10) as resp:
          return json.loads(resp.read())
  ```

  **If Task 1 revealed session-token auth**, replace the function body with:
  ```python
  def fetch_usage(api_key, endpoint=API_ENDPOINT):
      req = urllib.request.Request(endpoint)
      req.add_header("Cookie", f"sessionKey={api_key}")  # api_key field stores session token
      with urllib.request.urlopen(req, timeout=10) as resp:
          return json.loads(resp.read())
  ```
  And update the config field name from `api_key` to `session_token` in `DEFAULT_CONFIG` and all references.

- [ ] **Step 4: Run tests — verify all pass**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -v
  ```

  Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add "claude-usage.60s.py" "tests/test_claude_usage.py"
  git commit -m "feat: add API fetch with mock tests"
  ```

---

## Task 5: Output Formatting

**Files:**
- Modify: `claude-usage.60s.py`
- Modify: `tests/test_claude_usage.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_claude_usage.py`:

  ```python
  def test_format_menu_bar_normal():
      result = m.format_menu_bar(39, 80)
      assert result == "Claude 39%"

  def test_format_menu_bar_at_threshold():
      result = m.format_menu_bar(80, 80)
      assert "⚠️" in result
      assert "80%" in result
      assert "color=red" in result

  def test_format_menu_bar_above_threshold():
      result = m.format_menu_bar(95, 80)
      assert "⚠️" in result
      assert "color=red" in result

  def test_format_reset_time_hours():
      from datetime import timedelta
      future = (datetime.now() + timedelta(hours=1, minutes=48)).isoformat()
      result = m.format_reset_time(future)
      assert "h" in result and "m" in result

  def test_format_reset_time_minutes_only():
      from datetime import timedelta
      future = (datetime.now() + timedelta(minutes=23)).isoformat()
      result = m.format_reset_time(future)
      assert result == "in 23m"

  def test_format_dropdown_contains_key_info():
      data = {
          "session_pct": 39,
          "weekly_pct": 15,
          "session_reset_at": (datetime.now() + __import__("datetime").timedelta(hours=1, minutes=48)).isoformat(),
          "weekly_reset_at": (datetime.now() + __import__("datetime").timedelta(days=1)).isoformat(),
      }
      config = {"interval_s": 60, "alert_pct": 80, "api_key": "sk-test"}
      result = m.format_dropdown(data, config, "/path/to/script.py")
      assert "Session: 39%" in result
      assert "Weekly:  15%" in result
      assert "Set API Key" in result
      assert "Refresh: 60s" in result
      assert "Alert at: 80%" in result

  def test_format_dropdown_shows_staleness():
      data = {
          "session_pct": 50,
          "weekly_pct": 20,
          "session_reset_at": (datetime.now() + __import__("datetime").timedelta(hours=1)).isoformat(),
          "weekly_reset_at": (datetime.now() + __import__("datetime").timedelta(days=1)).isoformat(),
      }
      config = {"interval_s": 60, "alert_pct": 80, "api_key": "sk-test"}
      result = m.format_dropdown(data, config, "/path/to/script.py", stale_seconds=180)
      assert "last updated 3m ago" in result
  ```

- [ ] **Step 2: Run tests — verify new tests fail**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -k "format" -v
  ```

  Expected: all format tests FAIL.

- [ ] **Step 3: Add formatting functions to plugin**

  Add after `fetch_usage` in `claude-usage.60s.py`:

  ```python
  def format_menu_bar(session_pct, alert_pct):
      if session_pct >= alert_pct:
          return f"Claude ⚠️ {session_pct}% | color=red"
      return f"Claude {session_pct}%"


  def format_reset_time(reset_iso):
      reset = datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
      # Compare naive to naive
      now = datetime.now(reset.tzinfo)
      delta = reset - now
      total_seconds = int(delta.total_seconds())
      if total_seconds <= 0:
          return "soon"
      hours = total_seconds // 3600
      minutes = (total_seconds % 3600) // 60
      if hours > 0:
          return f"in {hours}h {minutes}m"
      return f"in {minutes}m"


  def format_dropdown(data, config, script_path, stale_seconds=None):
      session_reset = format_reset_time(data["session_reset_at"])
      weekly_reset = format_reset_time(data["weekly_reset_at"])

      lines = [
          f"Session: {data['session_pct']}%  (resets {session_reset})",
          f"Weekly:  {data['weekly_pct']}%  (resets {weekly_reset})",
      ]
      if stale_seconds is not None:
          lines.append(f"⚠ last updated {int(stale_seconds // 60)}m ago")
      else:
          lines.append("Last updated: just now")
      lines += [
          "---",
          "⚙ Settings",
          f"-- 🔑 Set API Key... | bash={script_path} param1=set_api_key terminal=false refresh=true",
          f"-- ⏱ Refresh: {config['interval_s']}s → change | bash={script_path} param1=set_interval terminal=false refresh=true",
          f"-- 🔔 Alert at: {config['alert_pct']}% → change | bash={script_path} param1=set_threshold terminal=false refresh=true",
          "---",
          "↻ Refresh now | refresh=true",
      ]
      return "\n".join(lines)
  ```

- [ ] **Step 4: Run all tests**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -v
  ```

  Expected: all tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add "claude-usage.60s.py" "tests/test_claude_usage.py"
  git commit -m "feat: add menu bar and dropdown formatting"
  ```

---

## Task 6: Settings Dialogs

**Files:**
- Modify: `claude-usage.60s.py`
- Modify: `tests/test_claude_usage.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_claude_usage.py`:

  ```python
  def test_handle_set_api_key_saves_valid_key():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          with patch.object(m, "run_osascript_dialog", return_value="sk-ant-abc123"):
              m.handle_set_api_key(path)
          config = m.load_config(path)
          assert config["api_key"] == "sk-ant-abc123"

  def test_handle_set_api_key_ignores_invalid_key():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          with patch.object(m, "run_osascript_dialog", return_value="not-a-key"):
              m.handle_set_api_key(path)
          # config file should not have been written
          assert not os.path.exists(path)

  def test_handle_set_api_key_ignores_cancel():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          with patch.object(m, "run_osascript_dialog", return_value=None):
              m.handle_set_api_key(path)
          assert not os.path.exists(path)

  def test_handle_set_interval_saves_valid_value():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          m.save_config({"api_key": "sk-x", "interval_s": 60, "alert_pct": 80}, path)
          with patch.object(m, "run_osascript_dialog", return_value="120"):
              m.handle_set_interval(path)
          assert m.load_config(path)["interval_s"] == 120

  def test_handle_set_interval_rejects_out_of_range():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          m.save_config({"api_key": "sk-x", "interval_s": 60, "alert_pct": 80}, path)
          with patch.object(m, "run_osascript_dialog", return_value="5"):  # below 30
              m.handle_set_interval(path)
          assert m.load_config(path)["interval_s"] == 60  # unchanged

  def test_handle_set_threshold_saves_valid_value():
      with tempfile.TemporaryDirectory() as d:
          path = os.path.join(d, "config.json")
          m.save_config({"api_key": "sk-x", "interval_s": 60, "alert_pct": 80}, path)
          with patch.object(m, "run_osascript_dialog", return_value="90"):
              m.handle_set_threshold(path)
          assert m.load_config(path)["alert_pct"] == 90
  ```

- [ ] **Step 2: Run tests — verify new tests fail**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -k "handle_set" -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Add settings dialog functions to plugin**

  Add after `format_dropdown` in `claude-usage.60s.py`:

  ```python
  def run_osascript_dialog(prompt, default=""):
      script = (
          f'display dialog "{prompt}" '
          f'default answer "{default}" '
          f'with title "Claude Usage" '
          f'buttons {{"Cancel", "OK"}} default button "OK"'
      )
      result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
      if result.returncode != 0:
          return None
      for part in result.stdout.strip().split(", "):
          if part.startswith("text returned:"):
              return part[len("text returned:"):]
      return None


  def handle_set_api_key(config_path=CONFIG_PATH):
      value = run_osascript_dialog("Enter your Anthropic API key (starts with sk-):", "sk-ant-...")
      if value and value.strip().startswith("sk-"):
          config = load_config(config_path)
          config["api_key"] = value.strip()
          save_config(config, config_path)


  def handle_set_interval(config_path=CONFIG_PATH):
      config = load_config(config_path)
      value = run_osascript_dialog("Refresh interval in seconds (30–3600):", str(config["interval_s"]))
      if value:
          try:
              seconds = int(value.strip())
              if 30 <= seconds <= 3600:
                  config["interval_s"] = seconds
                  save_config(config, config_path)
          except ValueError:
              pass


  def handle_set_threshold(config_path=CONFIG_PATH):
      config = load_config(config_path)
      value = run_osascript_dialog("Alert when session reaches (1–100%):", str(config["alert_pct"]))
      if value:
          try:
              pct = int(value.strip())
              if 1 <= pct <= 100:
                  config["alert_pct"] = pct
                  save_config(config, config_path)
          except ValueError:
              pass
  ```

- [ ] **Step 4: Run all tests**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -v
  ```

  Expected: all tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add "claude-usage.60s.py" "tests/test_claude_usage.py"
  git commit -m "feat: add settings dialogs with validation"
  ```

---

## Task 7: Main Entry Point

**Files:**
- Modify: `claude-usage.60s.py`

No new unit tests here — this is I/O wiring. Verify by running the script directly.

- [ ] **Step 1: Add the main function**

  Replace `if __name__ == "__main__": pass` at the bottom of `claude-usage.60s.py` with:

  ```python
  ACTIONS = {
      "set_api_key": handle_set_api_key,
      "set_interval": handle_set_interval,
      "set_threshold": handle_set_threshold,
  }


  def main():
      script_path = os.path.abspath(sys.argv[0])

      # Handle settings actions dispatched from SwiftBar menu items
      if len(sys.argv) > 1 and sys.argv[1] in ACTIONS:
          ACTIONS[sys.argv[1]]()
          return

      config = load_config()

      if not config.get("api_key"):
          print("Claude ⚙ setup")
          print("---")
          print(f"🔑 Set API Key... | bash={script_path} param1=set_api_key terminal=false refresh=true")
          return

      cache = load_cache()
      stale_seconds = None
      data = None

      if cache and cache_age_seconds(cache) < config["interval_s"]:
          data = cache["data"]
      else:
          try:
              data = fetch_usage(config["api_key"])
              save_cache(data)
          except Exception:
              if cache:
                  data = cache["data"]
                  stale_seconds = cache_age_seconds(cache)

      if data is None:
          print("Claude ?")
          print("---")
          print("Could not fetch usage data")
          print(f"🔑 Set API Key... | bash={script_path} param1=set_api_key terminal=false refresh=true")
          return

      print(format_menu_bar(data["session_pct"], config["alert_pct"]))
      print("---")
      print(format_dropdown(data, config, script_path, stale_seconds))


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Run all tests to ensure nothing broke**

  ```bash
  python3 -m pytest tests/test_claude_usage.py -v
  ```

  Expected: all tests PASS.

- [ ] **Step 3: Smoke test — no API key state**

  ```bash
  python3 "claude-usage.60s.py"
  ```

  Expected output:
  ```
  Claude ⚙ setup
  ---
  🔑 Set API Key... | bash=.../claude-usage.60s.py param1=set_api_key terminal=false refresh=true
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add "claude-usage.60s.py"
  git commit -m "feat: wire main entry point with full data flow"
  ```

---

## Task 8: Install Into SwiftBar

- [ ] **Step 1: Install SwiftBar**

  ```bash
  brew install --cask swiftbar
  ```

  Launch SwiftBar. When prompted to choose a plugins folder, select or create:
  `~/Library/Application Support/SwiftBar/Plugins/`

- [ ] **Step 2: Copy and make executable**

  ```bash
  PLUGINS_DIR="$HOME/Library/Application Support/SwiftBar/Plugins"
  mkdir -p "$PLUGINS_DIR"
  cp "claude-usage.60s.py" "$PLUGINS_DIR/"
  chmod +x "$PLUGINS_DIR/claude-usage.60s.py"
  ```

- [ ] **Step 3: Verify Python shebang works**

  SwiftBar runs the script with the shebang line. Verify:
  ```bash
  /usr/bin/env python3 --version
  ```

  Expected: Python 3.x.x (any version ≥ 3.8).

- [ ] **Step 4: Refresh SwiftBar**

  In SwiftBar's menu bar icon, click **Refresh All**. The `Claude ⚙ setup` item should appear in your menu bar.

- [ ] **Step 5: Set your API key via the widget**

  Click `Claude ⚙ setup` > `🔑 Set API Key...`, enter your key. SwiftBar will refresh and the widget should show usage data (once the API endpoint from Task 1 is confirmed working).

- [ ] **Step 6: Final commit**

  ```bash
  git add -A
  git commit -m "feat: complete claude menu bar usage widget"
  ```

---

## Self-Review Notes

- **Spec coverage:** All spec requirements covered — session % in menu bar, weekly in dropdown, alert threshold (color), settings via osascript, cache layer, error states (no config, stale, total failure).
- **Open item:** Task 1 (API endpoint) must be completed before Task 4 produces working code. The script is fully functional for all other states (no-key, stale cache) without it.
- **No placeholders** beyond the intentional `API_ENDPOINT` constant clearly marked for update in Task 4.
- **Type consistency:** `session_pct`, `weekly_pct`, `session_reset_at`, `weekly_reset_at` used consistently across all tasks.
