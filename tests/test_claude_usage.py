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
        with patch.object(m, "run_osascript_dialog", return_value="sk-ant-sid01-abc123"):
            m.handle_set_session_key(path)
        config = m.load_config(path)
        assert config["session_key"] == "sk-ant-sid01-abc123"

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
