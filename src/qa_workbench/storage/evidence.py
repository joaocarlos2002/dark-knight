"""Evidence registration and integrity (NFR-008).

Evidence files are kept apart from the Markdown records. Registering a file
copies it (the original is never touched or moved), computes its SHA-256, and
writes an immutable ``EVD`` record with the hash, size, origin, step, and a
description. An annotated version is a separate file and record that points
back to the original. :meth:`EvidenceStore.verify` re-checks file and record
at any time.
"""

import mimetypes
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from qa_workbench.storage.errors import EvidenceError, StorageError
from qa_workbench.storage.history import sha256_file
from qa_workbench.storage.ids import next_id
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.storage.validation import RecordSchema

REGISTERED = "registered"

EVIDENCE_SCHEMA = RecordSchema(
    prefix="EVD",
    directory="evidence",
    statuses=frozenset({REGISTERED}),
    required=("file", "original_name", "sha256", "size", "source", "description"),
    optional_timestamps=("captured_at",),
    immutable_statuses=frozenset({REGISTERED}),
    references={"derived_from": ("EVD",), "execution": ("EXEC",)},
)

FILES_DIRECTORY = "files"
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_name(name: str) -> str:
    cleaned = _UNSAFE.sub("_", name).strip(" .")
    return cleaned or "evidence"


class EvidenceStore:
    """Registers and verifies evidence for a repository that knows ``EVD``."""

    def __init__(self, repository: MarkdownRepository) -> None:
        if "EVD" not in repository.prefixes:
            raise ValueError(
                "The repository has no EVD schema; register EVIDENCE_SCHEMA."
            )
        self._repository = repository

    def register(
        self,
        file: Path,
        *,
        source: str,
        description: str,
        step: str | None = None,
        execution: str | None = None,
        source_url: str | None = None,
        derived_from: str | None = None,
        captured_at: datetime | None = None,
    ) -> Record:
        """Copy ``file`` into the evidence folder and record its integrity data.

        ``source`` says where the evidence came from (for example
        ``playwright`` or ``manual``). ``derived_from`` is the id of the
        original when this file is an annotated or processed version.
        """
        if not file.is_file():
            raise EvidenceError(f"{file} is not a file, so it cannot be evidence.")
        if not source.strip():
            raise ValueError("Evidence needs a source.")
        if not description.strip():
            raise ValueError("Evidence needs a description.")
        if source_url is not None:
            parts = urlsplit(source_url)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                raise ValueError(
                    f"source_url must be an http(s) URL, got {source_url!r}."
                )
        if derived_from is not None:
            original = self._repository.get(derived_from)
            if original.id.split("-")[0] != "EVD":
                raise EvidenceError(f"{derived_from} is not an evidence record.")

        digest = sha256_file(file)
        evidence_id = next_id("EVD", self._repository.record_ids("EVD"))
        name = _safe_name(file.name)
        relative = f"{EVIDENCE_SCHEMA.directory}/{FILES_DIRECTORY}/{evidence_id}/{name}"
        destination = self._repository.root / relative
        self._copy(file, destination, digest)

        fields: dict[str, object] = {
            "status": REGISTERED,
            "file": relative,
            "original_name": file.name,
            "media_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
            "sha256": digest,
            "size": destination.stat().st_size,
            "source": source.strip(),
            "description": description.strip(),
        }
        optional = {
            "step": step,
            "execution": execution,
            "source_url": source_url,
            "derived_from": derived_from,
            "captured_at": captured_at,
        }
        fields.update({key: value for key, value in optional.items() if value})
        try:
            record = self._repository.create(
                "EVD", fields, f"# {evidence_id}\n\n{description.strip()}\n"
            )
        except Exception:
            shutil.rmtree(destination.parent, ignore_errors=True)
            raise
        if record.id != evidence_id:
            raise EvidenceError(
                f"Evidence was stored under {evidence_id} but recorded as {record.id}."
            )
        return record

    def get(self, evidence_id: str) -> Record:
        return self._repository.get(evidence_id)

    def file_path(self, record: Record) -> Path:
        """Absolute path of the evidence file, refusing paths outside the project."""
        relative = record.metadata.get("file")
        if not isinstance(relative, str) or not relative:
            raise EvidenceError(f"{record.id} has no file path.")
        path = (self._repository.root / relative).resolve()
        if not path.is_relative_to(self._repository.root.resolve()):
            raise EvidenceError(
                f"{record.id} points outside the project folder: {relative}"
            )
        return path

    def verify(self, evidence_id: str) -> list[str]:
        """Return every integrity problem; an empty list means intact."""
        record = self._repository.get(evidence_id)
        problems = list(self._repository.verify(evidence_id))
        try:
            path = self.file_path(record)
        except EvidenceError as error:
            return [*problems, str(error)]
        if not path.is_file():
            return [*problems, f"the evidence file {path.name} is missing."]
        size = path.stat().st_size
        if size != record.metadata["size"]:
            problems.append(
                f"the file size is {size} bytes, but {record.metadata['size']} "
                "were recorded."
            )
        if sha256_file(path) != record.metadata["sha256"]:
            problems.append("the file content does not match its recorded SHA-256.")
        return problems

    def verify_all(self) -> dict[str, list[str]]:
        """Problems of every evidence record, by id; intact evidence is omitted."""
        problems: dict[str, list[str]] = {}
        for evidence_id in self._repository.record_ids("EVD"):
            try:
                found = self.verify(evidence_id)
            except StorageError as error:
                found = [str(error)]
            if found:
                problems[evidence_id] = found
        return problems

    @staticmethod
    def _copy(source: Path, destination: Path, expected_digest: str) -> None:
        if destination.parent.exists():
            raise EvidenceError(
                f"{destination.parent} already exists; remove the leftover folder "
                "before registering evidence."
            )
        destination.parent.mkdir(parents=True)
        try:
            shutil.copyfile(source, destination)
            if sha256_file(destination) != expected_digest:
                raise EvidenceError(
                    f"The copy of {source.name} does not match the original; "
                    "nothing was registered."
                )
        except BaseException:
            shutil.rmtree(destination.parent, ignore_errors=True)
            raise
