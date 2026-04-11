import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from claudebot_gateway.config import GatewayConfig, load_gateway_config
from claudebot_gateway.runtime import GatewayApp, GatewayRuntime

_LOGGER = logging.getLogger("claudebot_gateway.cli")


def status_text(data: GatewayRuntime | dict[str, object]) -> str:
    if isinstance(data, GatewayRuntime):
        data = {
            "runtime": data.health_snapshot(),
            "signals": {},
        }
    runtime_snapshot = data.get("runtime")
    snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else data
    state = "running" if snapshot.get("running") else "stopped"
    maybe_signals = data.get("signals")
    signals = maybe_signals if isinstance(maybe_signals, dict) else {}
    inbound_raw = signals.get("inbound_queue_depth", 0)
    outbound_raw = signals.get("outbound_queue_depth", 0)
    due_raw = signals.get("due_cron_jobs", 0)
    inbound_depth = int(inbound_raw) if isinstance(inbound_raw, int | str) else 0
    outbound_depth = int(outbound_raw) if isinstance(outbound_raw, int | str) else 0
    due_cron = int(due_raw) if isinstance(due_raw, int | str) else 0
    channels_parts: list[str] = []
    channels_raw = signals.get("channels")
    if isinstance(channels_raw, dict):
        for name, chan_status in channels_raw.items():
            if not isinstance(chan_status, dict):
                continue
            chan_state = chan_status.get("state", "unknown")
            last_error = chan_status.get("last_error")
            error_suffix = f" err={last_error}" if last_error else ""
            channels_parts.append(f"{name}:{chan_state}{error_suffix}")
    channels_str = " ".join(channels_parts) if channels_parts else "none"
    return (
        f"gateway:{state} workers={snapshot.get('worker_count', 0)} errors={snapshot.get('unhandled_errors', 0)} "
        f"in={inbound_depth} out={outbound_depth} due_cron={due_cron} channels=[{channels_str}]"
    )


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )


def _fetch_live_status(host: str, port: int) -> dict[str, object] | None:
    url = f"http://{host}:{port}/health"
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=2) as resp:
            if resp.status != 200:
                return None
            body = resp.read()
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, dict):
                return data
    except (URLError, OSError, json.JSONDecodeError):
        return None
    return None


def _fetch_status(config: GatewayConfig) -> dict[str, object]:
    live = _fetch_live_status(config.health_http.host, config.health_http.port)
    if live is not None:
        _LOGGER.info("status_source=live host=%s port=%s", config.health_http.host, config.health_http.port)
        return live
    _LOGGER.info("status_source=fallback gateway_not_reachable")
    return {
        "runtime": {"started": False, "running": False, "stopped": False, "worker_count": 0, "unhandled_errors": 0},
        "signals": {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claudebot-gateway")
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gateway = subparsers.add_parser("gateway")
    gateway.add_argument("--workspace-root", default=None)
    gateway.add_argument("--db-path", default=None)
    gateway.add_argument("--once", action="store_true")
    gateway.add_argument("--demo-text", default="")

    status = subparsers.add_parser("status")
    status.add_argument("--workspace-root", default=None)
    status.add_argument("--db-path", default=None)

    agent = subparsers.add_parser("agent")
    agent.add_argument("--prompt", required=True)
    agent.add_argument("--workspace-root", default=None)
    agent.add_argument("--workspace", default="main")
    agent.add_argument("--db-path", default=None)

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    _LOGGER.debug("verbose_mode_enabled=true")
    if args.command == "status":
        config = load_gateway_config(
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
            sqlite_path=Path(args.db_path) if args.db_path else None,
        )
        snapshot = _fetch_status(config)
        print(status_text(snapshot))
        return 0

    if args.command == "gateway":
        config = load_gateway_config(
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
            sqlite_path=Path(args.db_path) if args.db_path else None,
        )
        workspace_root = config.workspace_root
        sqlite_path = config.sqlite_path
        app = GatewayApp(
            config=config
        )
        _LOGGER.info(
            "key_paths workspace_root=%s sqlite_path=%s",
            workspace_root.resolve(),
            sqlite_path.resolve(),
        )
        if args.once:
            asyncio.run(app.run_once(demo_text=args.demo_text))
            return 0
        try:
            asyncio.run(app.run_forever())
        except KeyboardInterrupt:
            return 0
        return 0

    if args.command == "agent":
        config = load_gateway_config(
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
            sqlite_path=Path(args.db_path) if args.db_path else None,
        )
        workspace_root = config.workspace_root
        sqlite_path = config.sqlite_path
        selected_workspace = (workspace_root / args.workspace).resolve()
        if not selected_workspace.is_relative_to(workspace_root.resolve()):
            print(f"error: workspace '{args.workspace}' escapes workspace root", file=sys.stderr)
            return 1
        app = GatewayApp(
            config=config
        )
        _LOGGER.info(
            "key_paths workspace_root=%s selected_workspace=%s sqlite_path=%s",
            workspace_root.resolve(),
            selected_workspace.resolve(),
            sqlite_path.resolve(),
        )
        _LOGGER.info("agent_runtime provider=%s", config.agent_runtime.provider)
        try:
            response = asyncio.run(app.execute_prompt(prompt=args.prompt, workspace=selected_workspace))
        except KeyboardInterrupt:
            return 130
        except Exception:
            _LOGGER.exception("agent_command_failed")
            return 1
        print(response)
        return 0

    return 2
