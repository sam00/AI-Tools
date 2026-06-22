"""CCR — TokenTrim Content Retrieval store.

Reversible compression works by caching the *original* content locally, keyed by
a short stable reference id derived from its hash. Compressed output embeds a
marker like ``[tokentrim:ref a1b2c3d4 +812 tokens]`` so an agent (or a human) can
recover the full content on demand via :func:`retrieve`.

The store is local-first and file-backed (no network, no database). Entries
expire after a configurable TTL and are pruned lazily on access.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

REF_MARKER_PREFIX = "tokentrim:ref"


def make_ref(content: str) -> str:
    """Return a short, stable reference id for a piece of content."""
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
    return digest[:12]


@dataclass
class StoreEntry:
    ref: str
    content: str
    kind: str
    created_at: float


class ContentStore:
    """File-backed reversible content store."""

    def __init__(self, store_dir: str = ".tokentrim/store", ttl: int = 86_400) -> None:
        self.dir = Path(store_dir)
        self.ttl = ttl
        self._mem: dict[str, StoreEntry] = {}

    def _path(self, ref: str) -> Path:
        return self.dir / f"{ref}.json"

    def put(self, content: str, kind: str = "unknown") -> str:
        ref = make_ref(content)
        entry = StoreEntry(ref=ref, content=content, kind=kind, created_at=time.time())
        self._mem[ref] = entry
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self._path(ref).with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "ref": ref,
                        "kind": kind,
                        "created_at": entry.created_at,
                        "content": content,
                    }
                ),
                encoding="utf-8",
            )
            os.replace(tmp, self._path(ref))
        except OSError:
            # Memory-only fallback when the filesystem is read-only (e.g. sandbox).
            pass
        return ref

    def get(self, ref: str) -> StoreEntry | None:
        entry = self._mem.get(ref)
        if entry is None:
            entry = self._load(ref)
        if entry is None:
            return None
        if self.ttl > 0 and (time.time() - entry.created_at) > self.ttl:
            self.delete(ref)
            return None
        return entry

    def retrieve(self, ref: str) -> str | None:
        entry = self.get(ref)
        return entry.content if entry else None

    def _load(self, ref: str) -> StoreEntry | None:
        path = self._path(ref)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        entry = StoreEntry(
            ref=data["ref"],
            content=data["content"],
            kind=data.get("kind", "unknown"),
            created_at=data.get("created_at", time.time()),
        )
        self._mem[ref] = entry
        return entry

    def delete(self, ref: str) -> None:
        self._mem.pop(ref, None)
        try:
            self._path(ref).unlink(missing_ok=True)
        except OSError:
            pass

    def prune(self) -> int:
        """Remove expired entries. Returns the number pruned."""
        if self.ttl <= 0:
            return 0
        now = time.time()
        pruned = 0
        for ref, entry in list(self._mem.items()):
            if (now - entry.created_at) > self.ttl:
                self.delete(ref)
                pruned += 1
        if self.dir.exists():
            for path in self.dir.glob("*.json"):
                try:
                    created = json.loads(path.read_text(encoding="utf-8")).get("created_at", now)
                except (OSError, json.JSONDecodeError):
                    continue
                if (now - created) > self.ttl:
                    try:
                        path.unlink(missing_ok=True)
                        pruned += 1
                    except OSError:
                        pass
        return pruned


_default_store: ContentStore | None = None


def get_store(store_dir: str = ".tokentrim/store", ttl: int = 86_400) -> ContentStore:
    global _default_store
    if _default_store is None or str(_default_store.dir) != store_dir:
        _default_store = ContentStore(store_dir, ttl)
    return _default_store
