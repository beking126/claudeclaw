from claudebot_gateway.runtime import GatewayRuntime


def status_text(runtime: GatewayRuntime) -> str:
    snapshot = runtime.health_snapshot()
    state = "running" if snapshot["running"] else "stopped"
    return f"gateway:{state} workers={snapshot['worker_count']} errors={snapshot['unhandled_errors']}"


def main() -> int:
    return 0
