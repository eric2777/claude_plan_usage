import importlib.util
import json
import os
import tempfile
from datetime import datetime

def load_module():
    script_path = os.path.join(os.path.dirname(__file__), "..", "claude-usage.60s.py")
    spec = importlib.util.spec_from_file_location("claude_usage", os.path.abspath(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

m = load_module()

def test_load_config_defaults_when_missing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nonexistent.json")
        # file is never created — load_config should return defaults
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
        assert config["interval_s"] == 60  # default preserved
    finally:
        os.unlink(path)

def test_save_and_reload_config():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        m.save_config({"session_key": "sk-ant-sid01-abc", "interval_s": 120, "alert_pct": 75}, path)
        config = m.load_config(path)
        assert config["session_key"] == "sk-ant-sid01-abc"
        assert config["interval_s"] == 120
        assert config["alert_pct"] == 75

def test_load_cache_returns_none_when_missing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nonexistent.json")
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


from unittest.mock import patch, MagicMock
import urllib.error

def _make_mock_response(body_dict):
    body = json.dumps(body_dict).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp

def test_fetch_usage_returns_normalized_data():
    orgs_resp = _make_mock_response([{"uuid": "org-123", "name": "Test"}])
    usage_resp = _make_mock_response({
        "five_hour": {"utilization": 39.0, "resets_at": "2026-03-28T14:00:00Z"},
        "seven_day": {"utilization": 15.0, "resets_at": "2026-03-29T09:59:00Z"},
        "seven_day_sonnet": None,
    })
    with patch("urllib.request.urlopen", side_effect=[orgs_resp, usage_resp]):
        data = m.fetch_usage("sk-ant-sid01-test")
    assert data["session_pct"] == 39
    assert data["weekly_pct"] == 15
    assert data["session_reset_at"] == "2026-03-28T14:00:00Z"
    assert data["weekly_reset_at"] == "2026-03-29T09:59:00Z"

def test_fetch_usage_raises_on_http_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        url=None, code=403, msg="Forbidden", hdrs=None, fp=None
    )):
        try:
            m.fetch_usage("sk-ant-sid01-bad")
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 403

def test_fetch_usage_handles_null_weekly():
    """seven_day can be null when weekly limit is not yet reached"""
    orgs_resp = _make_mock_response([{"uuid": "org-123"}])
    usage_resp = _make_mock_response({
        "five_hour": {"utilization": 10.0, "resets_at": "2026-03-28T14:00:00Z"},
        "seven_day": None,
    })
    with patch("urllib.request.urlopen", side_effect=[orgs_resp, usage_resp]):
        data = m.fetch_usage("sk-ant-sid01-test")
    assert data["session_pct"] == 10
    assert data["weekly_pct"] == 0
    assert data["weekly_reset_at"] is None


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
    assert "1h" in result and "48m" in result

def test_format_reset_time_minutes_only():
    from datetime import timedelta
    future = (datetime.now() + timedelta(minutes=23)).isoformat()
    result = m.format_reset_time(future)
    assert result == "in 23m"

def test_format_reset_time_none():
    result = m.format_reset_time(None)
    assert result == "N/A"

def test_format_dropdown_contains_key_info():
    from datetime import timedelta
    data = {
        "session_pct": 39,
        "weekly_pct": 15,
        "session_reset_at": (datetime.now() + timedelta(hours=1, minutes=48)).isoformat(),
        "weekly_reset_at": (datetime.now() + timedelta(days=1)).isoformat(),
    }
    config = {"interval_s": 60, "alert_pct": 80, "session_key": "sk-ant-sid01-test"}
    result = m.format_dropdown(data, config, "/path/to/script.py")
    assert "Session: 39%" in result
    assert "Weekly:  15%" in result
    assert "Set Session Key" in result
    assert "Refresh: 60s" in result
    assert "Alert at: 80%" in result

def test_format_dropdown_shows_staleness():
    from datetime import timedelta
    data = {
        "session_pct": 50,
        "weekly_pct": 20,
        "session_reset_at": (datetime.now() + timedelta(hours=1)).isoformat(),
        "weekly_reset_at": (datetime.now() + timedelta(days=1)).isoformat(),
    }
    config = {"interval_s": 60, "alert_pct": 80, "session_key": "sk-ant-sid01-test"}
    result = m.format_dropdown(data, config, "/path/to/script.py", stale_seconds=180)
    assert "last updated 3m ago" in result


def test_handle_set_session_key_saves_valid_key():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        with patch.object(m, "run_osascript_dialog", return_value="sk-ant-sid01-abc123") as mock_dialog:
            m.handle_set_session_key(path)
        config = m.load_config(path)
        assert config["session_key"] == "sk-ant-sid01-abc123"
        # Verify width_chars is passed to make the field wide enough
        _, kwargs = mock_dialog.call_args
        assert kwargs.get("width_chars", 0) >= 100

def test_handle_set_session_key_ignores_invalid_key():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        with patch.object(m, "run_osascript_dialog", return_value="not-a-valid-key"):
            m.handle_set_session_key(path)
        assert not os.path.exists(path)

def test_handle_set_session_key_ignores_cancel():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        with patch.object(m, "run_osascript_dialog", return_value=None):
            m.handle_set_session_key(path)
        assert not os.path.exists(path)

def test_handle_set_interval_saves_valid_value():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        m.save_config({"session_key": "sk-ant-sid01-x", "interval_s": 60, "alert_pct": 80}, path)
        with patch.object(m, "run_osascript_dialog", return_value="120"):
            m.handle_set_interval(path)
        assert m.load_config(path)["interval_s"] == 120

def test_handle_set_interval_rejects_out_of_range():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        m.save_config({"session_key": "sk-ant-sid01-x", "interval_s": 60, "alert_pct": 80}, path)
        with patch.object(m, "run_osascript_dialog", return_value="5"):  # below 30
            m.handle_set_interval(path)
        assert m.load_config(path)["interval_s"] == 60  # unchanged

def test_handle_set_threshold_saves_valid_value():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        m.save_config({"session_key": "sk-ant-sid01-x", "interval_s": 60, "alert_pct": 80}, path)
        with patch.object(m, "run_osascript_dialog", return_value="90"):
            m.handle_set_threshold(path)
        assert m.load_config(path)["alert_pct"] == 90


# --- History tests ---

def test_load_history_returns_empty_when_missing():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "history.json")
        assert m.load_history(path) == []

def test_load_history_returns_empty_on_corrupt_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not json{{{")
        path = f.name
    try:
        assert m.load_history(path) == []
    finally:
        os.unlink(path)

def test_save_and_load_history():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "history.json")
        entries = [{"timestamp": datetime.now().isoformat(), "session_pct": 40}]
        m.save_history(entries, path)
        loaded = m.load_history(path)
        assert len(loaded) == 1
        assert loaded[0]["session_pct"] == 40

def test_append_history_adds_entry():
    history = []
    result = m.append_history(30, history)
    assert len(result) == 1
    assert result[0]["session_pct"] == 30
    assert "timestamp" in result[0]

def test_append_history_prunes_old_entries():
    from datetime import timedelta
    old_ts = (datetime.now() - timedelta(minutes=35)).isoformat()
    recent_ts = (datetime.now() - timedelta(minutes=5)).isoformat()
    history = [
        {"timestamp": old_ts, "session_pct": 10},
        {"timestamp": recent_ts, "session_pct": 20},
    ]
    result = m.append_history(25, history, max_age_min=30)
    assert len(result) == 2  # old entry pruned, recent kept, new added
    assert result[0]["session_pct"] == 20
    assert result[1]["session_pct"] == 25

def test_append_history_keeps_recent_entries():
    from datetime import timedelta
    history = [
        {"timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(), "session_pct": 15},
    ]
    result = m.append_history(20, history, max_age_min=30)
    assert len(result) == 2


# --- calc_eta_minutes tests ---

def test_calc_eta_returns_none_insufficient_data():
    history = [{"timestamp": datetime.now().isoformat(), "session_pct": 30}]
    assert m.calc_eta_minutes(history, 30) is None

def test_calc_eta_returns_none_empty_history():
    assert m.calc_eta_minutes([], 50) is None

def test_calc_eta_returns_none_when_rate_zero():
    from datetime import timedelta
    history = [
        {"timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(), "session_pct": 30},
        {"timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(), "session_pct": 30},
    ]
    assert m.calc_eta_minutes(history, 30) is None

def test_calc_eta_returns_none_when_rate_negative():
    from datetime import timedelta
    history = [
        {"timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(), "session_pct": 40},
        {"timestamp": (datetime.now() - timedelta(minutes=2)).isoformat(), "session_pct": 35},
    ]
    assert m.calc_eta_minutes(history, 35) is None

def test_calc_eta_calculates_correctly():
    from datetime import timedelta
    # 10 pct increase over 10 minutes = 1 pct/min; 50 pct remaining → 50 min ETA
    history = [
        {"timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(), "session_pct": 40},
        {"timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(), "session_pct": 45},
    ]
    eta = m.calc_eta_minutes(history, 50)
    assert eta is not None
    assert 45 <= eta <= 55  # ~50 min, allow small timing variance

def test_calc_eta_returns_none_at_100pct():
    from datetime import timedelta
    history = [
        {"timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(), "session_pct": 90},
        {"timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(), "session_pct": 95},
    ]
    assert m.calc_eta_minutes(history, 100) is None

def test_calc_eta_ignores_entries_outside_window():
    from datetime import timedelta
    # Entry at -20min is outside the 15-min window → only 1 entry in window → None
    history = [
        {"timestamp": (datetime.now() - timedelta(minutes=20)).isoformat(), "session_pct": 10},
        {"timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(), "session_pct": 20},
    ]
    # window_min=15: the first entry (-20min) is excluded, only second entry remains → < 2 entries
    assert m.calc_eta_minutes(history, 20, window_min=15) is None


# --- format_eta_line tests ---

def test_format_eta_line_minutes():
    result = m.format_eta_line(23.0, None)
    assert result == "→ 100% in ~23m (est.)"

def test_format_eta_line_hours_and_minutes():
    result = m.format_eta_line(90.0, None)
    assert result == "→ 100% in ~1h 30m (est.)"

def test_format_eta_line_returns_none_if_after_reset():
    from datetime import timedelta
    # Reset is in 10 min, but ETA is 30 min away → None
    reset_time = (datetime.now(tz=__import__("datetime").timezone.utc) + timedelta(minutes=10)).isoformat()
    result = m.format_eta_line(30.0, reset_time)
    assert result is None

def test_format_eta_line_shows_when_before_reset():
    from datetime import timedelta
    # Reset is in 60 min, ETA is 30 min → show ETA
    reset_time = (datetime.now(tz=__import__("datetime").timezone.utc) + timedelta(minutes=60)).isoformat()
    result = m.format_eta_line(30.0, reset_time)
    assert result == "→ 100% in ~30m (est.)"


# --- format_dropdown with eta_line tests ---

def test_format_dropdown_shows_eta_line():
    from datetime import timedelta
    data = {
        "session_pct": 50,
        "weekly_pct": 20,
        "session_reset_at": (datetime.now() + timedelta(hours=1)).isoformat(),
        "weekly_reset_at": (datetime.now() + timedelta(days=1)).isoformat(),
    }
    config = {"interval_s": 60, "alert_pct": 80, "session_key": "sk-ant-sid01-test"}
    result = m.format_dropdown(data, config, "/path/to/script.py", eta_line="→ 100% in ~25m (est.)")
    assert "→ 100% in ~25m (est.)" in result
    # ETA line should appear after Session line
    session_pos = result.index("Session:")
    eta_pos = result.index("→ 100%")
    weekly_pos = result.index("Weekly:")
    assert session_pos < eta_pos < weekly_pos

def test_format_dropdown_no_eta_when_none():
    from datetime import timedelta
    data = {
        "session_pct": 50,
        "weekly_pct": 20,
        "session_reset_at": (datetime.now() + timedelta(hours=1)).isoformat(),
        "weekly_reset_at": (datetime.now() + timedelta(days=1)).isoformat(),
    }
    config = {"interval_s": 60, "alert_pct": 80, "session_key": "sk-ant-sid01-test"}
    result = m.format_dropdown(data, config, "/path/to/script.py")
    assert "→ 100%" not in result
