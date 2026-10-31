"""Gestione del fuso orario: unico punto in cui si crea un ZoneInfo."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Rome"


def zone(name: str) -> ZoneInfo:
    """Restituisce il fuso richiesto, con un errore comprensibile se manca il database IANA."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RuntimeError(
            f"fuso orario '{name}' non disponibile: installa il pacchetto 'tzdata' "
            "(python -m pip install tzdata)"
        ) from exc


def parse_instant(text: str) -> datetime:
    """Interpreta un timestamp ISO-8601 (anche con suffisso 'Z') come datetime aware."""
    value = text.strip()
    if value[-1:] in {"Z", "z"}:
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp senza fuso orario: {text!r}")
    return parsed
