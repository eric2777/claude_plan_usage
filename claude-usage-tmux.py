#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime

from claude_fetch import fetch_usage

CONFIG_PATH = os.path.expanduser("~/.config/claude-usage-tmux/config.json")
CACHE_PATH = os.path.expanduser("~/.cache/claude-usage-tmux/result.json")
FETCH_BINARY = os.path.expanduser("~/.config/claude-usage-tmux/fetch")
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
