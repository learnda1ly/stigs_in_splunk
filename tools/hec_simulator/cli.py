from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tools.hec_simulator import hec_client, simulator


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cmd_run(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    hosts = Path(args.hosts)
    if not manifest.is_file():
        print(f"manifest not found: {manifest}", file=sys.stderr)
        return 1
    if not hosts.is_file():
        print(f"hosts config not found: {hosts}", file=sys.stderr)
        return 1

    collection_id = (args.collection_id or simulator.default_collection_id()).strip()
    if not collection_id:
        print("STIG_COLLECTION_ID or --collection-id is required", file=sys.stderr)
        return 1

    settings = hec_client.hec_settings_from_env()
    if args.dry_run:
        settings["hec_token"] = settings["hec_token"] or "dry-run"

    def one_cycle() -> None:
        events = simulator.simulate_all_hosts(
            manifest_path=manifest,
            hosts_path=hosts,
            collection_id=collection_id,
            collection_name=args.collection_name or "",
            baseline_key_override=args.baseline_key,
        )
        print(f"Built {len(events)} finding events for collection {collection_id}")
        if args.dry_run:
            if events:
                sample = events[0]
                print(
                    "Sample keys:",
                    sorted(k for k in sample.keys() if k not in ("rule", "stig", "asset")),
                )
            return
        sent = hec_client.post_hec(
            settings["hec_url"],
            settings["hec_token"],
            events,
            index=settings["ingest_index"],
            sourcetype=settings["ingest_sourcetype"],
            source=settings["source"],
        )
        print(f"Posted {sent} events to HEC index={settings['ingest_index']}")

    if args.once or not args.interval:
        one_cycle()
        return 0

    interval = max(1, int(args.interval))
    print(f"Running every {interval}s (Ctrl+C to stop)")
    while True:
        one_cycle()
        time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    root = _repo_root()
    default_manifest = root / "tests" / "fixtures" / "baselines" / "manifest.yaml"
    default_hosts = Path(__file__).resolve().parent / "hosts.yaml"

    parser = argparse.ArgumentParser(prog="hec_simulator", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Simulate findings and POST to Splunk HEC")
    run.add_argument("--manifest", type=Path, default=default_manifest)
    run.add_argument("--hosts", type=Path, default=default_hosts)
    run.add_argument("--collection-id", default="", help="Overrides STIG_COLLECTION_ID")
    run.add_argument("--collection-name", default="")
    run.add_argument(
        "--baseline-key",
        default="",
        help="Force all hosts to use this manifest baseline key (e.g. minimal for smoke)",
    )
    run.add_argument("--once", action="store_true", help="Run a single simulation cycle")
    run.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Seconds between cycles (omit with --once for one shot)",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Build events only; do not POST to HEC",
    )
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run" and not args.once and not args.interval:
        args.once = True
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
