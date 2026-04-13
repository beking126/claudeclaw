import time
from pathlib import Path

from claudebot_gateway.config import GatewayConfig, reload_gateway_config


def test_reload_returns_false_when_no_source_path(tmp_path: Path):
    config = GatewayConfig(workspace_root=tmp_path)
    assert reload_gateway_config(config) is False


def test_reload_returns_false_when_file_not_changed(tmp_path: Path, monkeypatch):
    config_path = tmp_path / ".claudebot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"rate_limit":{"max_requests_per_sender":5}}', encoding="utf-8")

    from claudebot_gateway.config import load_gateway_config
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    assert config.rate_limit_max_requests_per_sender == 5
    # No file change — reload should return False
    assert reload_gateway_config(config) is False


def test_reload_applies_rate_limit_changes(tmp_path: Path, monkeypatch):
    config_path = tmp_path / ".claudebot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"rate_limit":{"max_requests_per_sender":5}}', encoding="utf-8")

    from claudebot_gateway.config import load_gateway_config
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    assert config.rate_limit_max_requests_per_sender == 5

    # Modify config file (ensure mtime changes)
    time.sleep(0.1)
    config_path.write_text('{"rate_limit":{"max_requests_per_sender":10,"window_seconds":120}}', encoding="utf-8")

    reloaded = reload_gateway_config(config)
    assert reloaded is True
    assert config.rate_limit_max_requests_per_sender == 10
    assert config.rate_limit_window_seconds == 120.0


def test_reload_applies_allowed_senders(tmp_path: Path, monkeypatch):
    config_path = tmp_path / ".claudebot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"channels":{"telegram":{"enabled":true,"allowed_senders":["user1"]}}}', encoding="utf-8")

    from claudebot_gateway.config import load_gateway_config
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    assert config.channels.telegram.allowed_senders == ["user1"]

    # Update senders (ensure mtime changes)
    time.sleep(0.1)
    config_path.write_text('{"channels":{"telegram":{"enabled":true,"allowed_senders":["user1","user2"]}}}', encoding="utf-8")

    reloaded = reload_gateway_config(config)
    assert reloaded is True
    assert "user2" in config.channels.telegram.allowed_senders


def test_reload_returns_false_on_invalid_json(tmp_path: Path, monkeypatch):
    config_path = tmp_path / ".claudebot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"rate_limit":{"max_requests_per_sender":5}}', encoding="utf-8")

    from claudebot_gateway.config import load_gateway_config
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()

    # Corrupt the file
    time.sleep(0.1)
    config_path.write_text("not valid json{{{", encoding="utf-8")
    reloaded = reload_gateway_config(config)
    assert reloaded is False
    # Config should remain unchanged
    assert config.rate_limit_max_requests_per_sender == 5


def test_rate_limiter_update_limits():
    from claudebot_gateway.rate_limiter import SlidingWindowRateLimiter
    import time

    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    assert limiter.is_allowed("key1", now=time.monotonic()) is True
    assert limiter.is_allowed("key1", now=time.monotonic()) is True
    assert limiter.is_allowed("key1", now=time.monotonic()) is False

    limiter.update_limits(max_requests=5, window_seconds=60.0)
    # Buckets cleared, should be allowed again
    assert limiter.is_allowed("key1", now=time.monotonic()) is True


def test_agent_runner_update_allowed_senders(tmp_path: Path):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.agent_runtime.types import AgentExecutionRequest, AgentExecutionResult

    class FakeRuntime:
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            return AgentExecutionResult(text="ok", provider="test")

    runner = AgentRunner(runtime=FakeRuntime(), default_workspace=tmp_path)
    assert runner._is_sender_allowed(channel="telegram", sender="unknown")

    runner.update_allowed_senders({"telegram": {"user1", "user2"}})
    assert runner._is_sender_allowed(channel="telegram", sender="user1")
    assert not runner._is_sender_allowed(channel="telegram", sender="user3")
