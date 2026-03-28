#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# <swiftbar.title>Claude Usage</swiftbar.title>
# <swiftbar.version>1.0</swiftbar.version>
# <swiftbar.desc>Shows Claude plan session usage % in the menu bar</swiftbar.desc>

import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.config/claude-usage/config.json")
CACHE_PATH = os.path.expanduser("~/.cache/claude-usage/result.json")
FETCH_BINARY = os.path.expanduser("~/.config/claude-usage/fetch")
DEFAULT_CONFIG = {"session_key": "", "interval_s": 60, "alert_pct": 80}

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
    if not os.path.exists(path):
        return dict(DEFAULT_CONFIG)
    with open(path) as f:
        data = json.load(f)
    return {**DEFAULT_CONFIG, **data}


def save_config(config, path=CONFIG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


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
    if session_pct >= alert_pct:
        return f"Claude ⚠️ {session_pct}% | color=red"
    return f"Claude {session_pct}%"


def format_reset_time(reset_iso):
    if reset_iso is None:
        return "N/A"
    reset = datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
    now = datetime.now(reset.tzinfo)
    delta = reset - now
    total_seconds = delta.total_seconds()
    if total_seconds <= 0:
        return "soon"
    total_minutes = math.ceil(total_seconds / 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
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
        f'-- 🔑 Set Session Key... | bash="{script_path}" param1=set_session_key terminal=false refresh=true',
        f'-- ⏱ Refresh: {config["interval_s"]}s → change | bash="{script_path}" param1=set_interval terminal=false refresh=true',
        f'-- 🔔 Alert at: {config["alert_pct"]}% → change | bash="{script_path}" param1=set_threshold terminal=false refresh=true',
        "---",
        "↻ Refresh now | refresh=true",
    ]
    return "\n".join(lines)


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


def handle_set_session_key(config_path=CONFIG_PATH):
    value = run_osascript_dialog(
        "Paste your sessionKey from claude.ai cookies (starts with sk-ant-sid01-):",
        "sk-ant-sid01-..."
    )
    if value and value.strip().startswith("sk-"):
        config = load_config(config_path)
        config["session_key"] = value.strip()
        save_config(config, config_path)


def handle_set_interval(config_path=CONFIG_PATH):
    config = load_config(config_path)
    value = run_osascript_dialog(
        "Refresh interval in seconds (30–3600):",
        str(config["interval_s"])
    )
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
    value = run_osascript_dialog(
        "Alert when session usage reaches (1–100%):",
        str(config["alert_pct"])
    )
    if value:
        try:
            pct = int(value.strip())
            if 1 <= pct <= 100:
                config["alert_pct"] = pct
                save_config(config, config_path)
        except ValueError:
            pass


ACTIONS = {
    "set_session_key": handle_set_session_key,
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

    if not config.get("session_key"):
        print("Claude ⚙ setup")
        print("---")
        print(f'🔑 Set Session Key... | bash="{script_path}" param1=set_session_key terminal=false refresh=true')
        print("---")
        print("How to get your session key:")
        print("1. Open claude.ai in your browser")
        print("2. Open DevTools (F12) → Application → Cookies → claude.ai")
        print("3. Copy the value of the 'sessionKey' cookie")
        return

    cache = load_cache()
    stale_seconds = None
    data = None

    if cache and cache_age_seconds(cache) < config["interval_s"]:
        data = cache["data"]
    else:
        try:
            data = fetch_usage(config["session_key"])
            save_cache(data)
        except Exception:
            if cache:
                data = cache["data"]
                stale_seconds = cache_age_seconds(cache)

    if data is None:
        print("Claude ?")
        print("---")
        print("Could not fetch usage data")
        print(f'🔑 Set Session Key... | bash="{script_path}" param1=set_session_key terminal=false refresh=true')
        return

    print(format_menu_bar(data["session_pct"], config["alert_pct"]))
    print("---")
    print(format_dropdown(data, config, script_path, stale_seconds))


if __name__ == "__main__":
    main()
