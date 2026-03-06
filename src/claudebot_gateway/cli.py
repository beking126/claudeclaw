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
    return f"gateway:{state} workers={snapshot['worker_count']} errors={snapshot['unhandled_errors']}"


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

    return 2
