"""Command line: ``python -m benchmark {run,pull,site,readme}``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from benchmark.api import DEFAULT_TARGET, ApiClient, ConfigError
from benchmark.claims import target_host
from benchmark.console import Console, use_color
from benchmark.domains import DomainError, discover, load_pull, write_references
from benchmark.paths import DIST_DIR, DOMAINS_DIR, ENV_FILE, README_PATH, RESULTS_DIR
from benchmark.readme import ReadmeError, update
from benchmark.results import (
    JSON_FILE,
    ResultsError,
    document,
    exit_code,
    run_domain,
    write_results,
)
from benchmark.schema import SchemaError, load_charts
from benchmark.site import SiteError, build
from benchmark.spec import SpecError, drift, live_spec

USAGE_ERROR = 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        code: int = args.handler(args)
    except (
        ConfigError,
        DomainError,
        ReadmeError,
        ResultsError,
        SchemaError,
        SiteError,
        SpecError,
    ) as e:
        print(f"error: {e}", file=sys.stderr)
        return USAGE_ERROR
    return code


def run(args: argparse.Namespace) -> int:
    loaded = discover(load_charts(), DOMAINS_DIR)
    if args.domain:
        unknown = set(args.domain) - {d.domain.id for d in loaded}
        if unknown:
            raise DomainError(f"unknown domain {', '.join(sorted(unknown))}")
        loaded = [d for d in loaded if d.domain.id in args.domain]
    if not loaded:
        raise DomainError(f"no domain found under {DOMAINS_DIR.name}/")
    api = ApiClient.from_env(args.target, args.env_file)
    problems = drift((e for d in loaded for e in d.domain.endpoints), live_spec())
    if problems:
        raise SpecError(f"declared endpoints missing from the live spec: {'; '.join(problems)}")
    console = Console(sys.stdout, use_color(sys.stdout))
    console.header(target_host(args.target), args.date)
    width = max(len(d.domain.title) for d in loaded)
    results = []
    for d in loaded:
        console.start(d.domain.title)
        results.append(run_domain(d, api))
        console.domain(results[-1], width)
    doc = document(args.date, args.target, results)
    json_path, csv_path = write_results(args.out, doc)
    console.scorecard(results, doc)
    print(
        f"wrote {json_path.name} and {csv_path.name} to {os.path.relpath(args.out)}",
        file=sys.stderr,
    )
    return exit_code(results)


def pull(args: argparse.Namespace) -> int:
    folder = DOMAINS_DIR / args.domain
    if not folder.is_dir():
        raise DomainError(f"unknown domain {args.domain}")
    path = write_references(folder, load_pull(folder)(), load_charts())
    print(f"wrote {path.relative_to(DOMAINS_DIR.parent)}", file=sys.stderr)
    return 0


def site(args: argparse.Namespace) -> int:
    path = build(args.results, out_dir=args.out)
    print(f"wrote {path}", file=sys.stderr)
    return 0


def readme(args: argparse.Namespace) -> int:
    changed = update(args.readme, args.results, check=args.check)
    name = args.readme.name
    if args.check:
        if changed:
            print(f"{name} is stale: run python -m benchmark readme and commit it", file=sys.stderr)
            return 1
        print(f"{name} is current", file=sys.stderr)
        return 0
    print(f"{'rewrote' if changed else 'unchanged'} {name}", file=sys.stderr)
    return 0


def _run_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m benchmark", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("run", help="check every domain against the target API")
    p.add_argument("--target", default=DEFAULT_TARGET, help="API base URL")
    p.add_argument("--domain", action="append", help="run only this domain id (repeatable)")
    p.add_argument("--out", type=Path, default=RESULTS_DIR, help="results directory")
    p.add_argument("--env-file", type=Path, default=ENV_FILE, help="KEY=VALUE file")
    p.add_argument(
        "--date",
        type=_run_date,
        default=datetime.now(UTC).date().isoformat(),
        help="run date stamped on the results (default today, UTC)",
    )
    p.set_defaults(handler=run)

    p = commands.add_parser("pull", help="regenerate one domain references.json from its source")
    p.add_argument("domain", help="domain id, the folder name under domains/")
    p.set_defaults(handler=pull)

    p = commands.add_parser("site", help="build the report page from the committed results")
    p.add_argument("--results", type=Path, default=RESULTS_DIR / JSON_FILE, help="results file")
    p.add_argument("--out", type=Path, default=DIST_DIR, help="output directory")
    p.set_defaults(handler=site)

    p = commands.add_parser("readme", help="rewrite the generated README blocks from the results")
    p.add_argument("--results", type=Path, default=RESULTS_DIR / JSON_FILE, help="results file")
    p.add_argument("--readme", type=Path, default=README_PATH, help="README to rewrite")
    p.add_argument(
        "--check", action="store_true", help="exit 1 when the blocks are stale, write nothing"
    )
    p.set_defaults(handler=readme)
    return parser


if __name__ == "__main__":
    sys.exit(main())
