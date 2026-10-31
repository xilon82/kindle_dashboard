"""Giorno/notte: unico punto in cui si decide l'intervallo di aggiornamento.

Regola: l'intervallo non supera mai il prossimo cambio di fascia. Senza questo limite chi ricarica
alle 06:29 (ancora notte) con un intervallo notturno di un'ora tornerebbe alla cadenza diurna solo
alle 07:29.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class Schedule:
    night_start: time
    night_end: time
    day_seconds: int
    night_seconds: int


def is_night(moment: datetime, schedule: Schedule) -> bool:
    """Vero dentro la finestra notturna, anche quando scavalca la mezzanotte (23:00 → 06:30)."""
    clock = moment.timetz().replace(tzinfo=None)
    return clock >= schedule.night_start or clock < schedule.night_end


def next_boundary(moment: datetime, schedule: Schedule) -> datetime:
    """Primo istante futuro in cui la fascia cambia (inizio o fine della notte)."""
    candidates: list[datetime] = []
    for offset in (0, 1):
        day = moment.date() + timedelta(days=offset)
        for clock in (schedule.night_start, schedule.night_end):
            candidate = datetime.combine(day, clock, tzinfo=moment.tzinfo)
            if candidate > moment:
                candidates.append(candidate)
    return min(candidates)


def refresh_seconds(moment: datetime, schedule: Schedule) -> int:
    """Intervallo di ricarica: quello della fascia corrente, tagliato al prossimo confine."""
    base = schedule.night_seconds if is_night(moment, schedule) else schedule.day_seconds
    remaining = int((next_boundary(moment, schedule) - moment).total_seconds())
    return max(1, min(base, remaining))
