import argparse
import asyncio
import logging
from pathlib import Path

from claudebot_gateway.config import GatewayConfig
from claudebot_gateway.runtime import GatewayApp, GatewayRuntime

_LOGGER = logging.getLogger("claudebot_gateway.cli")


def status_text(runtime: GatewayRuntime | dict[str, object]) -> str:
    if isinstance(runtime, dict):
        snapshot = runtime
    else:
        snapshot = runtime.health_snapshot()
    runtime_snapshot = snapshot.get("runtime")
    if isinstance(runtime_snapshot, dict):
        snapshot = runtime_snapshot
    state = "running" if snapshot["running"] else "stopped"
    signals: dict[str, object] = {}
    if isinstance(runtime, dict):
        maybe_signals = runtime.get("signals")
        if isinstance(maybe_signals, dict):
            signals = maybe_signals
    inbound_raw = signals.get("inbound_queue_depth", 0)
    outbound_raw = signals.get("outbound_queue_depth", 0)
    due_raw = signals.get("due_cron_jobs", 0)
    inbound_depth = int(inbound_raw) if isinstance(inbound_raw, int | str) else 0
    outbound_depth = int(outbound_raw) if isinstance(outbound_raw, int | str) else 0
    due_cron = int(due_raw) if isinstance(due_raw, int | str) else 0
    return (
        f"gateway:{state} workers={snapshot['worker_count']} errors={snapshot['unhandled_errors']} "
        f"in={inbound_depth} out={outbound_depth} due_cron={due_cron}"
    )


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claudebot-gateway")
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gateway = subparsers.add_parser("gateway")
    gateway.add_argument("--workspace-root", default="workspaces")
    gateway.add_argument("--db-path", default="state/gateway.db")
    gateway.add_argument("--once", action="store_true")
    gateway.add_argument("--demo-text", default="")

    status = subparsers.add_parser("status")
    status.add_argument("--workspace-root", default="workspaces")
    status.add_argument("--db-path", default="state/gateway.db")

    agent = subparsers.add_parser("agent")
    agent.add_argument("--prompt", required=True)
    agent.add_argument("--workspace-root", default="workspaces")
    agent.add_argument("--workspace", default="main")
    agent.add_argument("--db-path", default="state/gateway.db")

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    _LOGGER.debug("verbose_mode_enabled=true")
    if args.command == "status":
        workspace_root = Path(args.workspace_root)
        sqlite_path = Path(args.db_path)
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=workspace_root,
                sqlite_path=sqlite_path,
            )
        )
        _LOGGER.info(
            "key_paths workspace_root=%s sqlite_path=%s",
            workspace_root.resolve(),
            sqlite_path.resolve(),
        )
        print(status_text(app.status()))
        return 0

    if args.command == "gateway":
        workspace_root = Path(args.workspace_root)
        sqlite_path = Path(args.db_path)
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=workspace_root,
                sqlite_path=sqlite_path,
            )
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
        workspace_root = Path(args.workspace_root)
        sqlite_path = Path(args.db_path)
        selected_workspace = workspace_root / args.workspace
        config = GatewayConfig(
            workspace_root=workspace_root,
            sqlite_path=sqlite_path,
        )
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
