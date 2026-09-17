"""Shared source-fidelity helpers for the dossier provenance tests."""

import hashlib
from pathlib import Path


def source_digest(path: Path) -> str:
    """Digest a case source's content, independent of the checkout's line endings.

    Dossiers are packaged from text read with universal newlines, so the recorded
    provenance digest describes that content. Hashing the raw bytes would instead
    record whichever line endings a contributor's platform checked out, which made
    the same commit verify on one machine and fail on another.
    """
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
