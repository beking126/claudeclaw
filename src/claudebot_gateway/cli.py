import argparse
import asyncio
import json
import logging
import sys
import uuid
import time
from datetime import datetime, timezone
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


def _cron_schedule_label(job: dict[str, object]) -> str:
    kind = str(job.get("schedule_kind", ""))
    value = str(job.get("schedule_value", ""))
    if kind == "every":
        return f"every {value}s"
    if kind == "at":
        ts = float(value) if value else 0.0
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return f"at {dt.strftime('%Y-%m-%d %H:%M UTC')}"
    if kind == "cron":
        return f"cron {value}"
    return kind


def _parse_at_time(raw: str) -> float:
    """Parse --at value as either an ISO datetime or an epoch float."""
    try:
        return float(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse --at time: {raw!r}. Use epoch float or ISO format like '2026-04-12T15:30'")


def _cron_job_line(job: dict[str, object]) -> str:
    job_id = str(job.get("job_id", ""))
    channel = str(job.get("channel", ""))
    destination = str(job.get("destination", ""))
    schedule = _cron_schedule_label(job)
    next_run_raw = job.get("next_run_epoch_seconds", 0)
    next_ts = float(next_run_raw) if isinstance(next_run_raw, (int, float)) else 0.0
    dt = datetime.fromtimestamp(next_ts, tz=timezone.utc)
    return f"{job_id}  {schedule}  {channel}/{destination}  next={dt.strftime('%Y-%m-%d %H:%M UTC')}"


def _handle_cron_add(args: argparse.Namespace) -> int:
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    schedule_count = sum(1 for flag in (args.every, args.at, args.cron) if flag is not None)
    if schedule_count == 0:
        print("error: one of --every, --at, or --cron is required", file=sys.stderr)
        return 1
    if schedule_count > 1:
        print("error: only one of --every, --at, or --cron can be specified", file=sys.stderr)
        return 1
    config = load_gateway_config(
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        sqlite_path=Path(args.db_path) if args.db_path else None,
    )
    job_id = args.job_id or f"cron_{uuid.uuid4().hex[:8]}"
    store = SqliteStore(db_path=config.sqlite_path)

    now = time.time()
    if args.every is not None:
        interval = int(args.every)
        if interval < 1:
            print("error: --every must be at least 1 second", file=sys.stderr)
            return 1
        store.upsert_cron_job(
            job_id=job_id,
            prompt=args.prompt,
            channel=args.channel,
            destination=args.destination,
            interval_seconds=interval,
            schedule_kind="every",
            schedule_value=str(interval),
            next_run_epoch_seconds=now,
        )
    elif args.at is not None:
        try:
            run_at = _parse_at_time(args.at)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        store.upsert_cron_job(
            job_id=job_id,
            prompt=args.prompt,
            channel=args.channel,
            destination=args.destination,
            interval_seconds=0,
            schedule_kind="at",
            schedule_value=str(run_at),
            next_run_epoch_seconds=run_at,
        )
    elif args.cron is not None:
        store.upsert_cron_job(
            job_id=job_id,
            prompt=args.prompt,
            channel=args.channel,
            destination=args.destination,
            interval_seconds=0,
            schedule_kind="cron",
            schedule_value=args.cron,
            next_run_epoch_seconds=now,
        )
    print(f"scheduled {job_id}")
    return 0


def _handle_cron_list(args: argparse.Namespace) -> int:
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    config = load_gateway_config(
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        sqlite_path=Path(args.db_path) if args.db_path else None,
    )
    store = SqliteStore(db_path=config.sqlite_path)
    jobs = store.list_all_cron_jobs()
    for job in jobs:
        print(_cron_job_line(job))
    return 0


def _handle_cron_remove(args: argparse.Namespace) -> int:
    from claudebot_gateway.cron_service import CronService

    config = load_gateway_config(
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        sqlite_path=Path(args.db_path) if args.db_path else None,
    )
    service = CronService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
    removed = service.remove_job(job_id=args.job_id)
    if not removed:
        print(f"error: job '{args.job_id}' not found", file=sys.stderr)
        return 1
    print(f"removed {args.job_id}")
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    errors: list[str] = []
    config_path = Path(".claudebot/config.json")
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                errors.append(f"config file is not a JSON object: {config_path}")
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"config file parse error: {exc}")
    try:
        config = load_gateway_config(
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
            sqlite_path=Path(args.db_path) if args.db_path else None,
        )
    except Exception as exc:
        errors.append(f"config load error: {exc}")
        config = None
    if config is None:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    workspace_root = config.workspace_root
    sqlite_path = config.sqlite_path
    try:
        workspace_root.mkdir(parents=True, exist_ok=True)
        test_file = workspace_root / ".validate_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
    except OSError as exc:
        errors.append(f"workspace_root not writable: {workspace_root}: {exc}")
    try:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"sqlite_path parent not writable: {sqlite_path.parent}: {exc}")
    provider = config.agent_runtime.provider.strip().lower()
    if provider != "claude":
        errors.append(f"unsupported agent_runtime.provider: {config.agent_runtime.provider}")
    if config.channels.telegram.enabled and not config.channels.telegram.bot_token:
        errors.append("telegram enabled but bot_token is not set")
    if config.channels.feishu.enabled and not config.channels.feishu.app_id:
        errors.append("feishu enabled but app_id is not set")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"ok provider={provider} "
        f"workspace={workspace_root.resolve()} "
        f"sqlite={sqlite_path.resolve()} "
        f"channels={','.join(k for k in ('cli', 'telegram', 'discord', 'feishu', 'whatsapp', 'slack') if getattr(config.channels, k).enabled)}"
    )
    return 0


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

    cron = subparsers.add_parser("cron")
    cron_sub = cron.add_subparsers(dest="cron_action", required=True)

    cron_add = cron_sub.add_parser("add")
    cron_add.add_argument("--prompt", required=True)
    cron_add.add_argument("--channel", required=True)
    cron_add.add_argument("--destination", required=True)
    cron_add.add_argument("--every", type=int, default=None)
    cron_add.add_argument("--at", type=str, default=None)
    cron_add.add_argument("--cron", default=None)
    cron_add.add_argument("--job-id", default=None)
    cron_add.add_argument("--workspace-root", default=None)
    cron_add.add_argument("--db-path", default=None)

    cron_list = cron_sub.add_parser("list")
    cron_list.add_argument("--workspace-root", default=None)
    cron_list.add_argument("--db-path", default=None)

    cron_remove = cron_sub.add_parser("remove")
    cron_remove.add_argument("--job-id", required=True)
    cron_remove.add_argument("--workspace-root", default=None)
    cron_remove.add_argument("--db-path", default=None)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--workspace-root", default=None)
    validate.add_argument("--db-path", default=None)

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
            print(f'error: workspace "{args.workspace}" escapes workspace root', file=sys.stderr)
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

    if args.command == "cron":
        if args.cron_action == "add":
            return _handle_cron_add(args)
        if args.cron_action == "list":
            return _handle_cron_list(args)
        if args.cron_action == "remove":
            return _handle_cron_remove(args)

    if args.command == "validate":
        return _handle_validate(args)

    return 2
