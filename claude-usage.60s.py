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
DEFAULT_CONFIG = {"session_key": "", "interval_s": 60, "alert_pct": 80}


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


ORGS_URL = "https://claude.ai/api/organizations"


def _make_request(url, session_key):
    req = urllib.request.Request(url)
    req.add_header("Cookie", f"sessionKey={session_key}")
    req.add_header("anthropic-client-platform", "web_claude_ai")
    return req


def fetch_usage(session_key):
    # Step 1: get org UUID
    with urllib.request.urlopen(_make_request(ORGS_URL, session_key), timeout=10) as resp:
        orgs = json.loads(resp.read())
    org_id = orgs[0]["uuid"]

    # Step 2: get usage
    usage_url = f"https://claude.ai/api/organizations/{org_id}/usage"
    with urllib.request.urlopen(_make_request(usage_url, session_key), timeout=10) as resp:
        raw = json.loads(resp.read())

    five_hour = raw.get("five_hour") or {}
    seven_day = raw.get("seven_day") or {}
    return {
        "session_pct": int(five_hour.get("utilization", 0)),
        "session_reset_at": five_hour.get("resets_at"),
        "weekly_pct": int(seven_day.get("utilization", 0)),
        "weekly_reset_at": seven_day.get("resets_at"),
    }


if __name__ == "__main__":
    pass
