"""Lettura tollerante dei valori JSON.

Le fonti restituiscono ``None`` per un campo opzionale mancante invece di far esplodere il
``parse``: una cache scritta prima dell'introduzione di un campo deve restare ri-analizzabile
(è il motivo per cui ``fetch_payload`` e ``parse`` sono separati).
"""

from __future__ import annotations


def optional_float(value: object) -> float | None:
    """Numero come float; ``None`` se il valore non è numerico (i bool non contano)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def optional_int(value: object) -> int | None:
    """Numero arrotondato all'intero; ``None`` se non è numerico."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value))


def series_float(series: object, index: int) -> float | None:
    """Valore ``index`` di una serie giornaliera opzionale (es. ``wind_speed_10m_max``)."""
    if not isinstance(series, list) or index >= len(series):
        return None
    return optional_float(series[index])


def series_int(series: object, index: int) -> int | None:
    """Come :func:`series_float`, ma arrotondato: le direzioni sono gradi interi."""
    if not isinstance(series, list) or index >= len(series):
        return None
    return optional_int(series[index])
