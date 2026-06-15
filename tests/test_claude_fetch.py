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
