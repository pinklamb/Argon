"""Command line entry point for inspecting AST counters locally."""

from __future__ import annotations

import argparse
import sys
from time import perf_counter
from pathlib import Path

from argon.engine.ast_counters import find_branch_nodes
from argon.engine.languages import SUPPORTED_EXTENSIONS, parse_source


def _source_files(paths: list[Path]) -> list[tuple[Path, str]]:
    files = []
    for path in paths:
        if path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append((path, path.name))
            continue
        if path.is_dir():
            files.extend(
                (candidate, candidate.relative_to(path).as_posix())
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS
            )
    return sorted(files, key=lambda item: item[1])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print JavaScript/TypeScript/Python AST branch nodes for verification."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="source files or folders to scan")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="print per-file counts without listing every branch node",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="print total file read, parse, and analysis time",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    files = _source_files(args.paths)
    if not files:
        extensions = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        print(
            f"error: no supported source files found; expected one of: {extensions}",
            file=sys.stderr,
        )
        return 2

    started = perf_counter()
    for path, display_name in files:
        tree = parse_source(display_name, path.read_bytes())
        if tree.has_error:
            print(f"WARN {display_name}: syntax errors, scored anyway", file=sys.stderr)
        branches = find_branch_nodes(tree)
        if not args.summary_only:
            for branch in branches:
                operator = f" operator={branch.operator}" if branch.operator else ""
                print(
                    f"FOUND branch node {branch.node_type}{operator} "
                    f"at {display_name}:{branch.line}"
                )
        print(f"{display_name}: {len(branches)} cyclomatic branches")
    if args.timing:
        print(f"Analysis time: {perf_counter() - started:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
