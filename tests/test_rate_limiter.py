from pathlib import Path

from claudebot_gateway.rate_limiter import SlidingWindowRateLimiter


def test_allows_requests_within_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0)
    assert limiter.is_allowed("user-1", now=0.0) is True
    assert limiter.is_allowed("user-1", now=0.0) is True
    assert limiter.is_allowed("user-1", now=0.0) is True


def test_denies_requests_exceeding_limit():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    limiter.is_allowed("user-1", now=0.0)
    limiter.is_allowed("user-1", now=0.0)
    assert limiter.is_allowed("user-1", now=0.0) is False


def test_window_reset_allows_again():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    limiter.is_allowed("user-1", now=0.0)
    limiter.is_allowed("user-1", now=0.0)
    assert limiter.is_allowed("user-1", now=0.0) is False
    assert limiter.is_allowed("user-1", now=60.0) is True


def test_different_keys_tracked_independently():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
    assert limiter.is_allowed("user-1", now=0.0) is True
    assert limiter.is_allowed("user-2", now=0.0) is True
    assert limiter.is_allowed("user-1", now=0.0) is False
    assert limiter.is_allowed("user-2", now=0.0) is False


def test_zero_max_requests_means_unlimited():
    limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
    for _ in range(100):
        assert limiter.is_allowed("user-1", now=0.0) is True


def test_rate_limit_config_parsing(tmp_path: Path, monkeypatch):
    import json

    from claudebot_gateway.config import load_gateway_config

    config_dir = tmp_path / ".claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps({"rate_limit": {"max_requests_per_sender": 10, "window_seconds": 30}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    assert config.rate_limit_max_requests_per_sender == 10
    assert config.rate_limit_window_seconds == 30.0
