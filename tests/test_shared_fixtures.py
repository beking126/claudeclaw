from pathlib import Path


def test_shared_runtime_and_adapter_fixtures(
    collecting_adapter,
    echo_runtime,
    gateway_app_factory,
    tmp_path: Path,
):
    app = gateway_app_factory(tmp_path)
    assert hasattr(collecting_adapter, "sent")
    assert hasattr(echo_runtime, "execute")
    assert app.status() is not None
