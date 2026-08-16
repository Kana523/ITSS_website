import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.sde.errors import SdeError
from app.sde.importer import import_sde


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import manufacturing and reaction data from an EVE SDE JSONL "
            "directory or ZIP archive."
        )
    )
    parser.add_argument("source", type=Path, help="Extracted SDE directory or ZIP")
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=2_000,
        help="Rows per database batch (default: 2000)",
    )
    parser.add_argument(
        "--allow-large-deletions",
        action="store_true",
        help=(
            "Allow an update that reduces a core dataset by more than 5%%; "
            "use only after verifying the source"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = import_sde(
            args.source,
            batch_size=args.batch_size,
            allow_large_deletions=args.allow_large_deletions,
        )
    except (SdeError, SQLAlchemyError, ValueError) as exc:
        print(f"SDE import failed: {exc}", file=sys.stderr)
        return 1

    status = "already imported" if result.already_imported else "imported"
    print(
        f"SDE build {result.build_number} {status} "
        f"(SHA-256 {result.source_checksum})"
    )
    print(json.dumps(result.row_counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
