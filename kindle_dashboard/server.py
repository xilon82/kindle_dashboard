"""Server HTTP minimale (stdlib): espone il pannello come PNG già alla risoluzione del Kindle."""

from __future__ import annotations

import io
import threading
import time
from dataclasses import replace
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .cache import Cache
from .collect import collect
from .config import Config
from .model import PanelData
from .render import render_panel
from .schedule import is_night
from .schedule import refresh_seconds as schedule_refresh_seconds
from .timezone_utils import zone

# Se telefono e Kindle chiedono il pannello nello stesso istante si raccoglie una volta sola.
_COLLECT_GUARD_SECONDS = 5


class PanelService:
    """Dati raccolti e PNG ridisegnato a ogni richiesta.

    Non c'è un TTL sui dati: la cadenza è quella con cui il browser ricarica la pagina (90 s di
    giorno, un'ora di notte), quindi un TTL separato creerebbe solo un disallineamento fra orologio
    e dati. La guardia breve serve unicamente contro le richieste doppie.
    """

    def __init__(self, config: Config, cache: Cache) -> None:
        self._config = config
        self._cache = cache
        self._lock = threading.Lock()
        self._data: PanelData | None = None
        self._collected_at = 0.0

    @property
    def refresh_seconds(self) -> int:
        moment = datetime.now(zone(self._config.timezone))
        return schedule_refresh_seconds(moment, self._config.schedule)

    def png(self) -> bytes:
        with self._lock:
            moment = datetime.now(zone(self._config.timezone))
            data = self._current_data()
            return self._render(
                replace(
                    data,
                    rendered_at=moment,
                    night=is_night(moment, self._config.schedule),
                )
            )

    def _current_data(self) -> PanelData:
        age = time.monotonic() - self._collected_at
        if self._data is None or age >= _COLLECT_GUARD_SECONDS:
            self._data = collect(self._config, self._cache)
            self._collected_at = time.monotonic()
        return self._data

    def _render(self, data: PanelData) -> bytes:
        image = render_panel(
            data,
            (self._config.panel.width, self._config.panel.height),
            font_override=self._config.render.font,
            bold_override=self._config.render.font_bold,
            stop_priority=self._config.trains.stop_priority,
        )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


def build_server(config: Config, cache: Cache) -> ThreadingHTTPServer:
    """Server già pronto (porta 0 = effimera, utile nei test)."""
    httpd = _PanelHTTPServer(
        (config.server.host, config.server.port), _handler(PanelService(config, cache))
    )
    httpd.daemon_threads = True
    return httpd


class _PanelHTTPServer(ThreadingHTTPServer):
    """Su Windows `allow_reuse_address` lascia a una seconda istanza rubare la porta già in ascolto:
    il nuovo processo parte, la vecchia versione resta a servire e sembra che le modifiche non
    abbiano effetto. Meglio un errore chiaro "porta occupata"."""

    allow_reuse_address = False


def serve(config: Config, cache: Cache) -> None:
    httpd = build_server(config, cache)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def html_panel(refresh_seconds: int, cache_key: int | None = None) -> str:
    """Pagina per il browser del Kindle: mostra il PNG e si ricarica da sola.

    Versione allineata a quella che funziona su Windows (Kindle 4 OK):
    - meta refresh (non JS setTimeout)
    - CSS con vh (NetFront lo ignora se non supportato)
    - niente Connection: close esplicito (HTTP/1.0 chiude da solo)
    """
    interval = max(1, refresh_seconds)
    suffix = f"?t={cache_key}" if cache_key is not None else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="it"><head><meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="{interval}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<style>html,body{margin:0;padding:0;height:100%;background:#fff;overflow:hidden}"
        "img{display:block;margin:0 auto;max-width:100%;max-height:100vh}</style>\n"
        f"<title>kindle-dashboard</title></head>\n"
        f'<body><img src="/panel.png{suffix}" alt="pannello"></body></html>\n'
    )


def _handler(service: PanelService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "kindle-dashboard/0.1"

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/panel.png":
                try:
                    payload = service.png()
                except Exception as exc:  # un errore di rendering non deve uccidere il server
                    self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, f"render fallito: {exc}\n")
                    return
                self._send(HTTPStatus.OK, "image/png", payload)
            elif path == "/health":
                self._send_text(HTTPStatus.OK, "ok\n")
            elif path in {"/panel.html", "/"}:
                self._send(
                    HTTPStatus.OK,
                    "text/html; charset=utf-8",
                    html_panel(service.refresh_seconds, int(time.time())).encode("utf-8"),
                )
            else:
                self._send_text(HTTPStatus.NOT_FOUND, "non trovato\n")

        def _send_text(self, status: HTTPStatus, text: str) -> None:
            self._send(status, "text/plain; charset=utf-8", text.encode("utf-8"))

        def _send(self, status: HTTPStatus, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            """Silenzio: il device chiede il pannello ogni pochi minuti, il log sarebbe solo rumore."""

    return Handler
