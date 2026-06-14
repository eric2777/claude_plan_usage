# tmux Status Bar Segment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fully-independent tmux status bar segment (`claude-usage-tmux.py`) that shows `Claude <session_pct>%`, color-highlighted at an alert threshold, sharing only the Cloudflare TLS-workaround fetch code with the existing SwiftBar plugin.

**Architecture:** Extract `SWIFT_SOURCE`, `_ensure_fetch_binary`, and `fetch_usage` from `claude-usage.60s.py` into a new shared module `claude_fetch.py`. Build `claude-usage-tmux.py` as a small standalone script with its own config/cache/binary paths under `~/.config/claude-usage-tmux/` and `~/.cache/claude-usage-tmux/`, importing only `fetch_usage` from `claude_fetch`.

**Tech Stack:** Python 3 stdlib only, pytest, `importlib`-based test loading for dash-named files.

**Spec:** `docs/superpowers/specs/2026-06-13-tmux-status-bar-design.md`

---

## Task 1: Extract `claude_fetch.py` shared module

**Files:**
- Create: `claude_fetch.py`
- Create: `tests/test_claude_fetch.py`
- Modify: `claude-usage.60s.py`
- Modify: `tests/test_claude_usage.py`

- [ ] **Step 1: Create `claude_fetch.py`**

```python
import json
import os
import subprocess
import tempfile

SWIFT_SOURCE = r"""import Foundation

guard let sessionKey = ProcessInfo.processInfo.environment["SESSION_KEY"] else {
    fputs("SESSION_KEY not set\n", stderr); exit(1)
}

func makeReq(_ urlStr: String) -> URLRequest {
    var req = URLRequest(url: URL(string: urlStr)!, timeoutInterval: 15)
    req.setValue("sessionKey=\(sessionKey)", forHTTPHeaderField: "Cookie")
    req.setValue("web_claude_ai", forHTTPHeaderField: "anthropic-client-platform")
    req.setValue("application/json", forHTTPHeaderField: "Accept")
    return req
}

func orNull(_ v: Any?) -> Any { return v ?? NSNull() }

let group = DispatchGroup()
group.enter()
URLSession.shared.dataTask(with: makeReq("https://claude.ai/api/organizations")) { d, resp, _ in
    guard let data = d,
          (resp as? HTTPURLResponse)?.statusCode == 200,
          let orgs = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
          let orgId = orgs.first?["uuid"] as? String else {
        fputs("Failed to fetch org\n", stderr); exit(1)
    }
    URLSession.shared.dataTask(with: makeReq("https://claude.ai/api/organizations/\(orgId)/usage")) { d2, resp2, _ in
        guard let data2 = d2,
              (resp2 as? HTTPURLResponse)?.statusCode == 200,
              let usage = try? JSONSerialization.jsonObject(with: data2) as? [String: Any] else {
            fputs("Failed to fetch usage\n", stderr); exit(1)
        }
        let fiveHour = usage["five_hour"] as? [String: Any] ?? [:]
        let sevenDay = usage["seven_day"] as? [String: Any] ?? [:]
        let out: [String: Any] = [
            "session_pct": Int((fiveHour["utilization"] as? Double) ?? 0),
            "weekly_pct": Int((sevenDay["utilization"] as? Double) ?? 0),
            "session_reset_at": orNull(fiveHour["resets_at"]),
            "weekly_reset_at": orNull(sevenDay["resets_at"]),
        ]
        guard let jsonData = try? JSONSerialization.data(withJSONObject: out),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            fputs("Failed to encode output\n", stderr); exit(1)
        }
        print(jsonStr)
        group.leave()
    }.resume()
}.resume()
group.wait()
"""


def _ensure_fetch_binary(binary_path):
    if os.path.exists(binary_path):
        return
    os.makedirs(os.path.dirname(binary_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
        f.write(SWIFT_SOURCE)
        src_path = f.name
    try:
        subprocess.run(["swiftc", src_path, "-o", binary_path], check=True, capture_output=True)
    finally:
        os.unlink(src_path)


def fetch_usage(session_key, binary_path):
    _ensure_fetch_binary(binary_path)
    result = subprocess.run(
        [binary_path],
        env={**os.environ, "SESSION_KEY": session_key},
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fetch binary failed: {result.stderr.strip()}")
    return json.loads(result.stdout)
```

- [ ] **Step 2: Create `tests/test_claude_fetch.py`**

```python
import json
from unittest.mock import patch, MagicMock

import claude_fetch as cf


def test_fetch_usage_returns_normalized_data():
    expected = {
        "session_pct": 39,
        "weekly_pct": 15,
        "session_reset_at": "2026-03-28T14:00:00Z",
        "weekly_reset_at": "2026-03-29T09:59:00Z",
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(expected)
    with patch.object(cf, "_ensure_fetch_binary"), \
         patch("subprocess.run", return_value=mock_result):
        data = cf.fetch_usage("sk-ant-sid01-test", "/tmp/fake-fetch")
    assert data["session_pct"] == 39
    assert data["weekly_pct"] == 15
    assert data["session_reset_at"] == "2026-03-28T14:00:00Z"
    assert data["weekly_reset_at"] == "2026-03-29T09:59:00Z"


def test_fetch_usage_raises_on_binary_failure():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Failed to fetch org"
    with patch.object(cf, "_ensure_fetch_binary"), \
         patch("subprocess.run", return_value=mock_result):
        try:
            cf.fetch_usage("sk-ant-sid01-bad", "/tmp/fake-fetch")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "fetch binary failed" in str(e)


def test_fetch_usage_handles_null_weekly():
    expected = {
        "session_pct": 10,
        "weekly_pct": 0,
        "session_reset_at": "2026-03-28T14:00:00Z",
        "weekly_reset_at": None,
    }
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(expected)
    with patch.object(cf, "_ensure_fetch_binary"), \
         patch("subprocess.run", return_value=mock_result):
        data = cf.fetch_usage("sk-ant-sid01-test", "/tmp/fake-fetch")
    assert data["session_pct"] == 10
    assert data["weekly_pct"] == 0
    assert data["weekly_reset_at"] is None


def test_ensure_fetch_binary_compiles_when_missing(tmp_path):
    binary_path = str(tmp_path / "fetch")
    with patch("subprocess.run") as mock_run:
        cf._ensure_fetch_binary(binary_path)
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "swiftc"
    assert "-o" in args
    assert binary_path in args


def test_ensure_fetch_binary_skips_when_present(tmp_path):
    binary_path = tmp_path / "fetch"
    binary_path.write_text("")
    with patch("subprocess.run") as mock_run:
        cf._ensure_fetch_binary(str(binary_path))
    mock_run.assert_not_called()
```

- [ ] **Step 3: Run the new tests**

Run: `python3 -m pytest tests/test_claude_fetch.py -v`
Expected: 5 passed

- [ ] **Step 4: Remove the extracted code from `claude-usage.60s.py`**

Edit the import block — old:

```python
import json
import math
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timedelta
```

new:

```python
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta

from claude_fetch import fetch_usage
```

Remove the `SWIFT_SOURCE` block — old:

```python
HISTORY_MAX_AGE_MIN = 30

SWIFT_SOURCE = r"""import Foundation

guard let sessionKey = ProcessInfo.processInfo.environment["SESSION_KEY"] else {
    fputs("SESSION_KEY not set\n", stderr); exit(1)
}

func makeReq(_ urlStr: String) -> URLRequest {
    var req = URLRequest(url: URL(string: urlStr)!, timeoutInterval: 15)
    req.setValue("sessionKey=\(sessionKey)", forHTTPHeaderField: "Cookie")
    req.setValue("web_claude_ai", forHTTPHeaderField: "anthropic-client-platform")
    req.setValue("application/json", forHTTPHeaderField: "Accept")
    return req
}

func orNull(_ v: Any?) -> Any { return v ?? NSNull() }

let group = DispatchGroup()
group.enter()
URLSession.shared.dataTask(with: makeReq("https://claude.ai/api/organizations")) { d, resp, _ in
    guard let data = d,
          (resp as? HTTPURLResponse)?.statusCode == 200,
          let orgs = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
          let orgId = orgs.first?["uuid"] as? String else {
        fputs("Failed to fetch org\n", stderr); exit(1)
    }
    URLSession.shared.dataTask(with: makeReq("https://claude.ai/api/organizations/\(orgId)/usage")) { d2, resp2, _ in
        guard let data2 = d2,
              (resp2 as? HTTPURLResponse)?.statusCode == 200,
              let usage = try? JSONSerialization.jsonObject(with: data2) as? [String: Any] else {
            fputs("Failed to fetch usage\n", stderr); exit(1)
        }
        let fiveHour = usage["five_hour"] as? [String: Any] ?? [:]
        let sevenDay = usage["seven_day"] as? [String: Any] ?? [:]
        let out: [String: Any] = [
            "session_pct": Int((fiveHour["utilization"] as? Double) ?? 0),
            "weekly_pct": Int((sevenDay["utilization"] as? Double) ?? 0),
            "session_reset_at": orNull(fiveHour["resets_at"]),
            "weekly_reset_at": orNull(sevenDay["resets_at"]),
        ]
        guard let jsonData = try? JSONSerialization.data(withJSONObject: out),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            fputs("Failed to encode output\n", stderr); exit(1)
        }
        print(jsonStr)
        group.leave()
    }.resume()
}.resume()
group.wait()
"""


def load_config(path=CONFIG_PATH):
```

new:

```python
HISTORY_MAX_AGE_MIN = 30


def load_config(path=CONFIG_PATH):
```

Remove `_ensure_fetch_binary` and `fetch_usage` — old:

```python
    return f"→ 100% in ~{hours}h {mins}m (est.)"


def _ensure_fetch_binary(binary_path=FETCH_BINARY):
    if os.path.exists(binary_path):
        return
    os.makedirs(os.path.dirname(binary_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
        f.write(SWIFT_SOURCE)
        src_path = f.name
    try:
        subprocess.run(["swiftc", src_path, "-o", binary_path], check=True, capture_output=True)
    finally:
        os.unlink(src_path)


def fetch_usage(session_key, binary_path=FETCH_BINARY):
    _ensure_fetch_binary(binary_path)
    result = subprocess.run(
        [binary_path],
        env={**os.environ, "SESSION_KEY": session_key},
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fetch binary failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def format_menu_bar(session_pct, alert_pct):
```

new:

```python
    return f"→ 100% in ~{hours}h {mins}m (est.)"


def format_menu_bar(session_pct, alert_pct):
```

- [ ] **Step 5: Update the `fetch_usage` call site to pass `FETCH_BINARY`**

old:

```python
    else:
        try:
            data = fetch_usage(config["session_key"])
            save_cache(data)
```

new:

```python
    else:
        try:
            data = fetch_usage(config["session_key"], FETCH_BINARY)
            save_cache(data)
```

- [ ] **Step 6: Remove the now-redundant `fetch_usage` tests from `tests/test_claude_usage.py`**

Delete these three test functions (now covered by `tests/test_claude_fetch.py`):
- `test_fetch_usage_returns_normalized_data`
- `test_fetch_usage_raises_on_binary_failure`
- `test_fetch_usage_handles_null_weekly`

`MagicMock` was only used by those three tests — update the import line:

old:

```python
from unittest.mock import patch, MagicMock
```

new:

```python
from unittest.mock import patch
```

(`patch` is still used by the `test_handle_set_*` tests later in the file.)

- [ ] **Step 7: Run the full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass (20 in `test_claude_usage.py`, 5 in `test_claude_fetch.py`)

- [ ] **Step 8: Commit**

```bash
git add claude_fetch.py claude-usage.60s.py tests/test_claude_fetch.py tests/test_claude_usage.py
git commit -m "refactor: extract Cloudflare fetch workaround into claude_fetch module"
```

---

## Task 2: Update Makefile to install `claude_fetch.py` alongside the SwiftBar plugin

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add `claude_fetch.py` to the `install` target**

old:

```makefile
install:
	cp claude-usage.60s.py "$(PLUGIN_DIR)/claude-usage.60s.py"
```

new:

```makefile
install:
	cp claude-usage.60s.py "$(PLUGIN_DIR)/claude-usage.60s.py"
	cp claude_fetch.py "$(PLUGIN_DIR)/claude_fetch.py"
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "build: install claude_fetch.py alongside the SwiftBar plugin"
```

---

## Task 3: Create `claude-usage-tmux.py` — config, cache, and status formatting

**Files:**
- Create: `claude-usage-tmux.py`
- Create: `tests/test_claude_usage_tmux.py`

- [ ] **Step 1: Write failing tests for config/cache helpers and `format_status`**

```python
import importlib.util
import json
import os
import tempfile


def load_module():
    script_path = os.path.join(os.path.dirname(__file__), "..", "claude-usage-tmux.py")
    spec = importlib.util.spec_from_file_location("claude_usage_tmux", os.path.abspath(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load_module()


def test_load_config_defaults_when_missing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nonexistent.json")
        config = m.load_config(path)
        assert config["interval_s"] == 60
        assert config["alert_pct"] == 80
        assert config["session_key"] == ""


def test_load_config_merges_with_defaults():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"session_key": "sk-ant-sid01-test", "alert_pct": 90}, f)
        path = f.name
    try:
        config = m.load_config(path)
        assert config["session_key"] == "sk-ant-sid01-test"
        assert config["alert_pct"] == 90
        assert config["interval_s"] == 60
    finally:
        os.unlink(path)


def test_load_cache_returns_none_when_missing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nonexistent.json")
        assert m.load_cache(path) is None


def test_save_and_load_cache():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "result.json")
        data = {
            "session_pct": 39, "weekly_pct": 15,
            "session_reset_at": "2026-03-28T14:00:00Z",
            "weekly_reset_at": "2026-03-29T09:59:00Z",
        }
        m.save_cache(data, path)
        cache = m.load_cache(path)
        assert cache["data"]["session_pct"] == 39
        assert "timestamp" in cache


def test_cache_age_seconds():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "result.json")
        data = {
            "session_pct": 50, "weekly_pct": 10,
            "session_reset_at": "2026-03-28T14:00:00Z",
            "weekly_reset_at": "2026-03-29T09:59:00Z",
        }
        m.save_cache(data, path)
        cache = m.load_cache(path)
        age = m.cache_age_seconds(cache)
        assert 0 <= age < 2


def test_format_status_normal():
    assert m.format_status(39, 80) == "Claude 39%"


def test_format_status_at_threshold():
    result = m.format_status(80, 80)
    assert result == "#[fg=red]Claude ⚠️ 80%#[default]"


def test_format_status_above_threshold():
    result = m.format_status(95, 80)
    assert "95%" in result
    assert result.startswith("#[fg=red]")
    assert result.endswith("#[default]")
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python3 -m pytest tests/test_claude_usage_tmux.py -v`
Expected: ERROR — `claude-usage-tmux.py` does not exist yet (collection error / `FileNotFoundError`)

- [ ] **Step 3: Create `claude-usage-tmux.py` with config/cache helpers and `format_status`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.config/claude-usage-tmux/config.json")
CACHE_PATH = os.path.expanduser("~/.cache/claude-usage-tmux/result.json")
DEFAULT_CONFIG = {"session_key": "", "interval_s": 60, "alert_pct": 80}


def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return dict(DEFAULT_CONFIG)
    with open(path) as f:
        data = json.load(f)
    return {**DEFAULT_CONFIG, **data}


def load_cache(path=CACHE_PATH):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def save_cache(data, path=CACHE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(), "data": data}
    with open(path, "w") as f:
        json.dump(entry, f, indent=2)


def cache_age_seconds(cache):
    ts = datetime.fromisoformat(cache["timestamp"])
    return (datetime.now() - ts).total_seconds()


def format_status(session_pct, alert_pct):
    if session_pct >= alert_pct:
        return f"#[fg=red]Claude ⚠️ {session_pct}%#[default]"
    return f"Claude {session_pct}%"
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python3 -m pytest tests/test_claude_usage_tmux.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add claude-usage-tmux.py tests/test_claude_usage_tmux.py
git commit -m "feat: add config/cache helpers and status formatting for tmux segment"
```

---

## Task 4: Implement `main()` for `claude-usage-tmux.py`

**Files:**
- Modify: `claude-usage-tmux.py`
- Modify: `tests/test_claude_usage_tmux.py`

- [ ] **Step 1: Write failing tests for `main()`**

Add to `tests/test_claude_usage_tmux.py` (add `from datetime import timedelta` and `from unittest.mock import patch` to the imports at the top):

```python
from datetime import timedelta
from unittest.mock import patch
```

Append these tests:

```python
def test_main_prints_setup_when_no_session_key(capsys):
    config = {"session_key": "", "interval_s": 60, "alert_pct": 80}
    with patch.object(m, "load_config", return_value=config):
        m.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "Claude ⚙ setup"


def test_main_uses_fresh_cache_without_fetching(capsys):
    config = {"session_key": "sk-ant-sid01-test", "interval_s": 60, "alert_pct": 80}
    cache = {
        "timestamp": datetime.now().isoformat(),
        "data": {"session_pct": 42, "weekly_pct": 10,
                  "session_reset_at": None, "weekly_reset_at": None},
    }
    with patch.object(m, "load_config", return_value=config), \
         patch.object(m, "load_cache", return_value=cache), \
         patch.object(m, "fetch_usage") as mock_fetch:
        m.main()
    mock_fetch.assert_not_called()
    captured = capsys.readouterr()
    assert captured.out.strip() == "Claude 42%"


def test_main_fetches_when_cache_stale(capsys):
    config = {"session_key": "sk-ant-sid01-test", "interval_s": 60, "alert_pct": 80}
    stale_cache = {
        "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
        "data": {"session_pct": 30, "weekly_pct": 5,
                  "session_reset_at": None, "weekly_reset_at": None},
    }
    fresh_data = {"session_pct": 55, "weekly_pct": 12,
                   "session_reset_at": None, "weekly_reset_at": None}
    with patch.object(m, "load_config", return_value=config), \
         patch.object(m, "load_cache", return_value=stale_cache), \
         patch.object(m, "fetch_usage", return_value=fresh_data) as mock_fetch, \
         patch.object(m, "save_cache") as mock_save:
        m.main()
    mock_fetch.assert_called_once_with("sk-ant-sid01-test", m.FETCH_BINARY)
    mock_save.assert_called_once_with(fresh_data)
    captured = capsys.readouterr()
    assert captured.out.strip() == "Claude 55%"


def test_main_falls_back_to_stale_cache_on_fetch_failure(capsys):
    config = {"session_key": "sk-ant-sid01-test", "interval_s": 60, "alert_pct": 80}
    stale_cache = {
        "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
        "data": {"session_pct": 30, "weekly_pct": 5,
                  "session_reset_at": None, "weekly_reset_at": None},
    }
    with patch.object(m, "load_config", return_value=config), \
         patch.object(m, "load_cache", return_value=stale_cache), \
         patch.object(m, "fetch_usage", side_effect=RuntimeError("boom")):
        m.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "Claude 30%"


def test_main_prints_unknown_when_fetch_fails_and_no_cache(capsys):
    config = {"session_key": "sk-ant-sid01-test", "interval_s": 60, "alert_pct": 80}
    with patch.object(m, "load_config", return_value=config), \
         patch.object(m, "load_cache", return_value=None), \
         patch.object(m, "fetch_usage", side_effect=RuntimeError("boom")):
        m.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "Claude ?"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python3 -m pytest tests/test_claude_usage_tmux.py -v`
Expected: FAIL — `AttributeError: module 'claude_usage_tmux' has no attribute 'main'` (and `'fetch_usage'`, `'FETCH_BINARY'`)

- [ ] **Step 3: Add `fetch_usage` import, `FETCH_BINARY`, and `main()`**

Add to the top of `claude-usage-tmux.py`, after the existing imports:

```python
from claude_fetch import fetch_usage
```

Add alongside the other path constants:

```python
FETCH_BINARY = os.path.expanduser("~/.config/claude-usage-tmux/fetch")
```

Append at the end of the file:

```python
def main():
    config = load_config()
    if not config.get("session_key"):
        print("Claude ⚙ setup")
        return

    cache = load_cache()
    data = None

    if cache and cache_age_seconds(cache) < config["interval_s"]:
        data = cache["data"]
    else:
        try:
            data = fetch_usage(config["session_key"], FETCH_BINARY)
            save_cache(data)
        except Exception:
            if cache:
                data = cache["data"]

    if data is None:
        print("Claude ?")
        return

    print(format_status(data["session_pct"], config["alert_pct"]))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python3 -m pytest tests/test_claude_usage_tmux.py -v`
Expected: 13 passed

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass (20 in `test_claude_usage.py`, 5 in `test_claude_fetch.py`, 13 in `test_claude_usage_tmux.py`)

- [ ] **Step 6: Commit**

```bash
git add claude-usage-tmux.py tests/test_claude_usage_tmux.py
git commit -m "feat: implement main() for tmux status bar segment"
```

---

## Task 5: Document the tmux segment and the `claude_fetch` refactor in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Project Overview section**

old:

```markdown
## Project Overview

A SwiftBar macOS menu bar plugin that displays Claude plan session usage (%) in real time. SwiftBar runs `claude-usage.60s.py` every 60 seconds (interval encoded in filename) and renders its stdout as a menu bar item.
```

new:

```markdown
## Project Overview

Two independent scripts display Claude plan session usage (%) in real time:

- `claude-usage.60s.py` — a SwiftBar macOS menu bar plugin. SwiftBar runs it every 60 seconds (interval encoded in filename) and renders its stdout as a menu bar item.
- `claude-usage-tmux.py` — a tmux status bar segment, invoked via `#()` command substitution from `.tmux.conf`.

Both scripts share `claude_fetch.py` (the Cloudflare TLS workaround for calling claude.ai's API) but otherwise have completely separate config, cache, and session keys.
```

- [ ] **Step 2: Replace the Architecture section**

old:

```markdown
## Architecture

Everything lives in one file: `claude-usage.60s.py`. No dependencies beyond the Python stdlib.

**Runtime paths:**
- Config: `~/.config/claude-usage/config.json` — session key, refresh interval, alert threshold
- Cache: `~/.cache/claude-usage/result.json` — last API response with timestamp
- History: `~/.cache/claude-usage/history.json` — rolling window of `session_pct` readings used to compute ETA
- Fetch binary: `~/.config/claude-usage/fetch` — compiled on first run from the embedded `SWIFT_SOURCE` string via `swiftc`

**Data flow:**
1. SwiftBar executes the script every 60s
2. If cache is fresh (age < `interval_s`), render cached data — no network call
3. If stale, run the compiled Swift binary (which calls `claude.ai/api/organizations` then `.../usage`) and write new cache + append to history
4. On fetch failure, render stale cache with a "last updated Xm ago" warning
5. Print line 1 as the menu bar title; everything after `---` becomes the dropdown

**Key functions:**
- `fetch_usage()` — shells out to the compiled Swift binary with `SESSION_KEY` env var
- `_ensure_fetch_binary()` — compiles `SWIFT_SOURCE` via `swiftc` on first run if binary is missing
- `calc_eta_minutes()` — linear rate from the 15-minute history window to estimate time to 100%
- `format_eta_line()` — suppresses ETA if it would land after the session reset time
- `format_dropdown()` — builds the full SwiftBar dropdown text including settings menu items
- `handle_set_*()` — action handlers dispatched from SwiftBar menu items via `sys.argv[1]`

**Tests** import the module dynamically from its `.py` filename path (`importlib.util.spec_from_file_location`) since it contains a dot in the name. Tests use `tempfile.TemporaryDirectory` for isolation and `unittest.mock.patch` for `subprocess.run` and `run_osascript_dialog`.
```

new:

```markdown
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

**Tests** use the same `importlib` dynamic-loading pattern as `claude-usage.60s.py` (dashes in the filename).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document claude_fetch module and tmux status bar segment"
```
