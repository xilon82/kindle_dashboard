"""Client HTTP minimale su urllib: nessuna dipendenza esterna, retry solo dove ha senso."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

from ..exceptions import SourceError

USER_AGENT = "kindle-dashboard/0.1"
DEFAULT_TIMEOUT = 10.0
ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1.0


def get_bytes(
    url: str,
    params: Sequence[tuple[str, object]] | Mapping[str, object] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """GET con User-Agent, timeout e un solo retry sugli errori transitori (5xx, rete)."""
    query = _query(params)
    full_url = f"{url}?{query}" if query else url
    target = _host(full_url)
    last_error: SourceError | None = None
    for attempt in range(1, ATTEMPTS + 1):
        request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = SourceError(f"{target}: HTTP {exc.code}")
            if exc.code < 500:
                break  # un 4xx non migliora ritentando
        except OSError as exc:  # URLError, timeout e problemi di connessione sono tutti OSError
            last_error = SourceError(f"{target}: {_reason(exc)}")
        if attempt < ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS * attempt)
    raise last_error if last_error is not None else SourceError(f"{target}: errore sconosciuto")


def get_json(
    url: str,
    params: Sequence[tuple[str, object]] | Mapping[str, object] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    payload = get_bytes(url, params, timeout=timeout)
    try:
        return json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"{_host(url)}: risposta non JSON ({exc})") from exc


def get_text(
    url: str,
    params: Sequence[tuple[str, object]] | Mapping[str, object] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    return get_bytes(url, params, timeout=timeout).decode("utf-8-sig", errors="replace")


def _query(params: Sequence[tuple[str, object]] | Mapping[str, object] | None) -> str:
    if not params:
        return ""
    items = params.items() if isinstance(params, Mapping) else params
    return urllib.parse.urlencode([(key, _scalar(value)) for key, value in items])


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc or url


def _reason(exc: OSError) -> str:
    reason = getattr(exc, "reason", None)
    return str(reason) if reason is not None else type(exc).__name__
