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


if __name__ == "__main__":
    pass
