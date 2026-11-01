"""Raccolta differenziata: il calendario del comune è un iCal pubblico con un evento per giorno.

Formato osservato (Google Calendar del comune): un ``VEVENT`` all-day per ogni giorno di raccolta,
materiale nel ``SUMMARY`` (``Umido``, ``Secco``, ``Plastica``, ``Carta``), nessuna ``RRULE``. Il
parser iCal è lo stesso degli eventi: qui si aggiungono solo il raggruppamento per giorno e
l'allineamento della finestra, che permette al renderer di disegnare oggi/domani/dopodomani anche
quando un giorno è scoperto (la domenica, ad esempio, non si raccoglie nulla).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..model import WasteDay
from . import calendar
from .http import DEFAULT_TIMEOUT


def fetch_payload(ics_url: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Scarica il calendario: la validazione "è davvero un iCal" resta quella degli eventi."""
    return calendar.fetch_payload(ics_url, timeout=timeout)


def parse(payload: str, *, today: date, days: int, tz: ZoneInfo) -> tuple[WasteDay, ...]:
    """Un elemento per ognuno dei ``days`` giorni da ``today``, con i materiali di quel giorno."""
    start = datetime.combine(today, time.min, tzinfo=tz)
    events = calendar.parse_events(
        payload,
        start=start,
        end=start + timedelta(days=days),
        tz=tz,
        # Il limite di ``parse_events`` conta le occorrenze: un giorno può avere più materiali,
        # quindi va tenuto largo rispetto al numero di giorni richiesti.
        limit=days * 4,
    )

    collected: dict[date, list[str]] = {}
    for event in events:
        kind = " ".join(event.summary.split())
        if not kind:
            continue
        kinds = collected.setdefault(event.start.date(), [])
        if kind not in kinds:
            kinds.append(kind)

    return tuple(
        WasteDay(day=day, kinds=tuple(collected.get(day, ())))
        for day in (today + timedelta(days=offset) for offset in range(days))
    )
