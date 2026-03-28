import importlib.util
import json
import os
import tempfile

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
