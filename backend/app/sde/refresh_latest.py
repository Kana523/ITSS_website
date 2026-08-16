import argparse
import logging
import tempfile
from pathlib import Path

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.sde.errors import SdeError
from app.sde.importer import import_sde


logger = logging.getLogger(__name__)
_CHUNK_SIZE = 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download CCP's latest JSONL SDE and atomically import it."
    )
    parser.add_argument(
        "--allow-large-deletions",
        action="store_true",
        help="Allow the importer's protected datasets to shrink by more than 5%%.",
    )
    return parser


def _download_latest_sde(
    destination: Path,
    *,
    url: str,
    user_agent: str,
    maximum_bytes: int,
) -> int:
    written = 0
    with httpx.Client(
        timeout=httpx.Timeout(120.0, connect=15.0),
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    advertised = int(content_length)
                except ValueError:
                    advertised = None
                if advertised is not None and advertised > maximum_bytes:
                    raise ValueError(
                        "Latest SDE exceeds the configured download size limit"
                    )
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(_CHUNK_SIZE):
                    written += len(chunk)
                    if written > maximum_bytes:
                        raise ValueError(
                            "Latest SDE exceeds the configured download size limit"
                        )
                    handle.write(chunk)
    if written == 0:
        raise ValueError("Latest SDE download was empty")
    return written


def refresh_latest_sde(*, allow_large_deletions: bool = False):
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="itss-sde-") as temporary_directory:
        archive = Path(temporary_directory) / "latest-sde.zip"
        byte_count = _download_latest_sde(
            archive,
            url=settings.sde_latest_url,
            user_agent=settings.esi_user_agent,
            maximum_bytes=settings.sde_download_max_bytes,
        )
        logger.info("Downloaded latest EVE SDE (%d bytes)", byte_count)
        return import_sde(
            archive,
            allow_large_deletions=allow_large_deletions,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = refresh_latest_sde(
            allow_large_deletions=args.allow_large_deletions,
        )
    except (httpx.HTTPError, SdeError, SQLAlchemyError, ValueError) as exc:
        logger.exception("Automatic SDE refresh failed")
        print(f"SDE refresh failed: {exc}")
        return 1

    status = "already current" if result.already_imported else "updated"
    print(
        f"SDE {status}: build {result.build_number} "
        f"({result.source_checksum})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
