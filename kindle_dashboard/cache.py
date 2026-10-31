"""Ultimo payload buono per sezione: il pannello resta leggibile quando una fonte cade."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .timezone_utils import parse_instant


class Cache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def store(self, key: str, payload: Any, when: datetime) -> None:
        """Salva payload e istante di salvataggio (scrittura atomica: il server può leggerla)."""
        self._root.mkdir(parents=True, exist_ok=True)
        target = self.path(key)
        temporary = target.with_suffix(".tmp")
        document = {"saved_at": when.isoformat(), "payload": payload}
        temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)

    def load(self, key: str) -> tuple[Any, datetime] | None:
        path = self.path(key)
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
            return document["payload"], parse_instant(str(document["saved_at"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None  # cache illeggibile: si comporta come assente

    def path(self, key: str) -> Path:
        return self._root / f"{key}.json"
