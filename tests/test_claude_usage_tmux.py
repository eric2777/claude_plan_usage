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
