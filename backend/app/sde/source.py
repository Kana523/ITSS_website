from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from io import TextIOWrapper
from pathlib import Path, PurePosixPath
from typing import BinaryIO, TextIO
from zipfile import BadZipFile, ZipFile, is_zipfile

from app.sde.errors import SdeSourceError


DATASET_FILENAMES = {
    "manifest": "_sde.jsonl",
    "categories": "categories.jsonl",
    "groups": "groups.jsonl",
    "types": "types.jsonl",
    "activity_types": "industryActivities.jsonl",
    "blueprints": "blueprints.jsonl",
}


class SdeSource:
    """Read the required JSONL datasets from a directory or official ZIP."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()
        self._is_zip = self.path.is_file() and is_zipfile(self.path)

        if self.path.is_dir():
            self._locations = self._find_directory_files()
        elif self._is_zip:
            self._locations = self._find_zip_members()
        elif self.path.exists():
            raise SdeSourceError(
                f"SDE source must be a directory or ZIP archive: {self.path}"
            )
        else:
            raise SdeSourceError(f"SDE source does not exist: {self.path}")

    def _find_directory_files(self) -> dict[str, Path | str]:
        matches_by_name: dict[str, list[Path]] = {
            filename: [] for filename in DATASET_FILENAMES.values()
        }
        for candidate in self.path.rglob("*.jsonl"):
            if candidate.name in matches_by_name:
                matches_by_name[candidate.name].append(candidate)

        return self._validate_matches(matches_by_name)

    def _find_zip_members(self) -> dict[str, Path | str]:
        matches_by_name: dict[str, list[str]] = {
            filename: [] for filename in DATASET_FILENAMES.values()
        }
        try:
            with ZipFile(self.path) as archive:
                for member in archive.namelist():
                    filename = PurePosixPath(member).name
                    if filename in matches_by_name:
                        matches_by_name[filename].append(member)
        except BadZipFile as exc:
            raise SdeSourceError(f"Invalid SDE ZIP archive: {self.path}") from exc

        return self._validate_matches(matches_by_name)

    @staticmethod
    def _validate_matches(
        matches_by_name: dict[str, list[Path] | list[str]],
    ) -> dict[str, Path | str]:
        locations: dict[str, Path | str] = {}
        for dataset, filename in DATASET_FILENAMES.items():
            matches = matches_by_name[filename]
            if not matches:
                raise SdeSourceError(f"Required SDE file is missing: {filename}")
            if len(matches) > 1:
                raise SdeSourceError(
                    f"Multiple SDE files named {filename} were found"
                )
            locations[dataset] = matches[0]
        return locations

    @contextmanager
    def open_binary(self, dataset: str) -> Iterator[BinaryIO]:
        try:
            location = self._locations[dataset]
        except KeyError as exc:
            raise SdeSourceError(f"Unknown SDE dataset: {dataset}") from exc

        if self._is_zip:
            try:
                with ZipFile(self.path) as archive:
                    with archive.open(str(location), "r") as stream:
                        yield stream
            except (BadZipFile, KeyError, OSError) as exc:
                raise SdeSourceError(
                    f"Could not read {location} from {self.path}"
                ) from exc
            return

        try:
            with Path(location).open("rb") as stream:
                yield stream
        except OSError as exc:
            raise SdeSourceError(
                f"Could not read {location} from {self.path}"
            ) from exc

    @contextmanager
    def open_text(self, dataset: str) -> Iterator[TextIO]:
        with self.open_binary(dataset) as binary_stream:
            with TextIOWrapper(binary_stream, encoding="utf-8-sig") as text_stream:
                yield text_stream

    def calculate_checksum(self) -> str:
        """Hash the exact source bytes used by this importer."""
        digest = sha256()
        for dataset, filename in DATASET_FILENAMES.items():
            digest.update(filename.encode("utf-8"))
            digest.update(b"\0")
            with self.open_binary(dataset) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        return digest.hexdigest()
