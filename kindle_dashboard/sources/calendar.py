"""Parser iCalendar per i calendari Google (eventi singoli, ricorrenze comuni, override).

Limiti dichiarati: si espandono ``FREQ`` DAILY/WEEKLY/MONTHLY/YEARLY con ``INTERVAL``, ``COUNT``,
``UNTIL`` e ``BYDAY`` (solo per WEEKLY). Altri ``BY*`` vengono ignorati; un ``TZID`` sconosciuto
ricade sul fuso del pannello invece di far fallire l'intera sezione.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..exceptions import SourceError
from ..model import CalEvent
from ..timezone_utils import parse_instant, zone
from .http import DEFAULT_TIMEOUT, get_text

MAX_OCCURRENCES = 500
_WEEKDAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


@dataclass(frozen=True)
class _RawEvent:
    uid: str
    summary: str
    start: datetime
    end: datetime | None
    all_day: bool
    rrule: str | None
    exdates: tuple[datetime, ...]
    recurrence_id: datetime | None
    cancelled: bool


def fetch_payload(ics_url: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    if "/calendar/embed" in ics_url:
        raise SourceError("calendario: serve l'URL iCal, non la pagina embed")
    text = get_text(ics_url, timeout=timeout)
    if "BEGIN:VCALENDAR" not in text:
        raise SourceError("calendario: la risposta non sembra un file iCal")
    return text


def parse_events(
    text: str,
    *,
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    limit: int,
) -> tuple[CalEvent, ...]:
    """Eventi che iniziano in ``[start, end)``, ordinati e limitati a ``limit``."""
    raw_events = _parse_raw(text, tz)

    overrides: dict[tuple[str, datetime], _RawEvent] = {
        (event.uid, event.recurrence_id): event
        for event in raw_events
        if event.recurrence_id is not None
    }

    collected: list[CalEvent] = []
    for event in raw_events:
        if event.recurrence_id is not None or event.cancelled:
            continue
        for occurrence in _expand(event, start, end):
            if occurrence in event.exdates:
                continue
            if (event.uid, occurrence) in overrides:
                continue  # l'occorrenza spostata viene emessa come evento singolo
            collected.append(_to_event(event, occurrence, tz))

    for override in overrides.values():
        if override.cancelled or not start <= override.start < end:
            continue
        collected.append(_to_event(override, override.start, tz))

    collected.sort(key=lambda item: item.start)
    return tuple(collected[:limit])


def _to_event(event: _RawEvent, occurrence: datetime, tz: ZoneInfo) -> CalEvent:
    return CalEvent(
        start=occurrence.astimezone(tz),
        summary=event.summary or "(senza titolo)",
        all_day=event.all_day,
        end=None if event.end is None else event.end.astimezone(tz),
    )


def _expand(event: _RawEvent, window_start: datetime, window_end: datetime) -> Iterator[datetime]:
    rule = _parse_rule(event.rrule)
    if not rule:
        if window_start <= event.start < window_end:
            yield event.start
        return

    frequency = rule.get("FREQ", "").upper()
    interval = _positive_int(rule.get("INTERVAL"), default=1) or 1
    count = _positive_int(rule.get("COUNT"), default=None)
    until_value = rule.get("UNTIL")
    until: datetime | None = None
    if until_value:
        parsed_until = _datetime_value(until_value, tzid=None, default_tz=event.start.tzinfo)
        until = None if parsed_until is None else parsed_until[0]
    by_day = [item.strip().upper()[-2:] for item in rule.get("BYDAY", "").split(",") if item.strip()]

    produced = 0
    scanned = 0
    for candidate in _candidates(frequency, event.start, interval, by_day):
        scanned += 1
        if scanned > MAX_OCCURRENCES:
            return
        if candidate < event.start:
            continue
        if until is not None and candidate > until:
            return
        if count is not None and produced >= count:
            return
        produced += 1
        if candidate >= window_end:
            return
        if candidate >= window_start:
            yield candidate


def _candidates(
    frequency: str, start: datetime, interval: int, by_day: list[str]
) -> Iterator[datetime]:
    if frequency == "DAILY":
        index = 0
        while True:
            yield start + timedelta(days=interval * index)
            index += 1
    elif frequency == "WEEKLY":
        weekdays = sorted({_WEEKDAY_CODES[code] for code in by_day if code in _WEEKDAY_CODES})
        if not weekdays:
            weekdays = [start.weekday()]
        week_start = start - timedelta(days=start.weekday())
        index = 0
        while True:
            base = week_start + timedelta(weeks=interval * index)
            for weekday in weekdays:
                yield base + timedelta(days=weekday)
            index += 1
    elif frequency == "MONTHLY":
        index = 0
        while True:
            yield _add_months(start, interval * index)
            index += 1
    elif frequency == "YEARLY":
        index = 0
        while True:
            yield _add_months(start, 12 * interval * index)
            index += 1
    else:
        yield start


def _add_months(moment: datetime, months: int) -> datetime:
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, _days_in_month(year, month))
    return moment.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (following - timedelta(days=1)).day


def _parse_rule(rule: str | None) -> dict[str, str]:
    if not rule:
        return {}
    parsed: dict[str, str] = {}
    for chunk in rule.split(";"):
        key, _, value = chunk.partition("=")
        if key and value:
            parsed[key.strip().upper()] = value.strip()
    return parsed


def _positive_int(value: str | None, *, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        number = int(value)
    except ValueError:
        return default
    return number if number > 0 else default


def _parse_raw(text: str, default_tz: ZoneInfo) -> list[_RawEvent]:
    events: list[_RawEvent] = []
    for block in _vevent_blocks(text):
        properties = _properties(block)
        starts = properties.get("DTSTART")
        if not starts:
            continue
        parsed_start = _datetime_value(starts[0][0], tzid=starts[0][1].get("TZID"), default_tz=default_tz)
        if parsed_start is None:
            continue
        start, all_day = parsed_start

        end: datetime | None = None
        ends = properties.get("DTEND")
        if ends:
            parsed_end = _datetime_value(ends[0][0], tzid=ends[0][1].get("TZID"), default_tz=default_tz)
            if parsed_end is not None:
                end = parsed_end[0]

        exdates: list[datetime] = []
        for value, params in properties.get("EXDATE") or []:
            for piece in value.split(","):
                parsed_ex = _datetime_value(piece, tzid=params.get("TZID"), default_tz=default_tz)
                if parsed_ex is not None:
                    exdates.append(parsed_ex[0])

        recurrence_id: datetime | None = None
        recurrence_props = properties.get("RECURRENCE-ID")
        if recurrence_props:
            parsed_recurrence = _datetime_value(
                recurrence_props[0][0], tzid=recurrence_props[0][1].get("TZID"), default_tz=default_tz
            )
            if parsed_recurrence is not None:
                recurrence_id = parsed_recurrence[0]

        events.append(
            _RawEvent(
                uid=_first(properties, "UID"),
                summary=_unescape(_first(properties, "SUMMARY")).strip(),
                start=start,
                end=end,
                all_day=all_day,
                rrule=_first(properties, "RRULE") or None,
                exdates=tuple(exdates),
                recurrence_id=recurrence_id,
                cancelled=_first(properties, "STATUS").upper() == "CANCELLED",
            )
        )
    return events


def _vevent_blocks(text: str) -> Iterator[list[str]]:
    block: list[str] | None = None
    for line in _unfold(text):
        marker = line.strip().upper()
        if marker == "BEGIN:VEVENT":
            block = []
        elif marker == "END:VEVENT":
            if block is not None:
                yield block
            block = None
        elif block is not None:
            block.append(line)


def _unfold(text: str) -> list[str]:
    """Applica il line folding RFC 5545: le righe che iniziano con spazio/tab continuano la precedente."""
    lines: list[str] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for raw in normalized.split("\n"):
        if raw[:1] in {" ", "\t"} and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw)
    return lines


def _properties(block: list[str]) -> dict[str, list[tuple[str, dict[str, str]]]]:
    properties: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for line in block:
        name_and_params, separator, value = line.partition(":")
        if not separator:
            continue
        parts = name_and_params.split(";")
        name = parts[0].strip().upper()
        params: dict[str, str] = {}
        for raw_param in parts[1:]:
            key, _, param_value = raw_param.partition("=")
            if key.strip():
                params[key.strip().upper()] = param_value.strip()
        properties.setdefault(name, []).append((value, params))
    return properties


def _first(properties: dict[str, list[tuple[str, dict[str, str]]]], name: str) -> str:
    values = properties.get(name)
    return values[0][0].strip() if values else ""


def _datetime_value(
    value: str, *, tzid: str | None, default_tz: ZoneInfo
) -> tuple[datetime, bool] | None:
    """Interpreta un valore DATE/DATE-TIME iCal: restituisce l'istante e se è una giornata intera."""
    text = value.strip()
    if not text:
        return None
    if text[-1:] in {"Z", "z"}:
        try:
            return parse_instant(text).astimezone(default_tz), False
        except ValueError:
            return None
    if "T" in text:
        try:
            parsed = datetime.strptime(text, "%Y%m%dT%H%M%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=_zone_or_default(tzid, default_tz)), False
    try:
        day = datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None
    return datetime.combine(day, time.min, tzinfo=default_tz), True


def _zone_or_default(tzid: str | None, default_tz: ZoneInfo) -> ZoneInfo:
    if not tzid:
        return default_tz
    try:
        return zone(tzid)
    except RuntimeError:
        return default_tz


def _unescape(value: str) -> str:
    return (
        value.replace("\\N", "\n")
        .replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )
