from pathlib import Path
from typing import Protocol

_EXTENSIONS = {"text/html": ".html", "application/pdf": ".pdf"}


class ArchiveStore(Protocol):
    def save(self, utility_id: str, sha256: str, content_type: str, content: bytes) -> str:
        """Store raw bytes and return a path that identifies them in this store."""
        ...


class LocalArchive:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, utility_id: str, sha256: str, content_type: str, content: bytes) -> str:
        relative = Path(utility_id) / f"{sha256}{_EXTENSIONS.get(content_type, '.bin')}"
        target = self.root / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return relative.as_posix()
