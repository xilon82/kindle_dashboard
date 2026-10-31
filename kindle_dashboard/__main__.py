"""CLI: ``render`` (anteprima PNG), ``serve`` (PNG per il Kindle), ``resolve-station``."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .cache import Cache
from .collect import collect
from .config import LOCAL_CONFIG_FILENAME, ConfigError, load_config
from .exceptions import SourceError
from .render import render_panel
from .server import serve
from .sources import trains as trains_source


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except ConfigError as exc:
        print(f"errore di configurazione: {exc}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", default=LOCAL_CONFIG_FILENAME, help="file TOML di configurazione"
    )

    parser = argparse.ArgumentParser(
        prog="kindle-dashboard",
        description="Meteo, calendario e treni come PNG per un Kindle jailbroken.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser(
        "render", parents=[common], help="genera un'anteprima PNG del pannello"
    )
    render.add_argument("-o", "--output", default="preview.png", help="file PNG di destinazione")
    render.add_argument(
        "--night", action="store_true", help="anteprima della modalità notte (orario nascosto)"
    )
    render.set_defaults(handler=_cmd_render)

    server = commands.add_parser("serve", parents=[common], help="serve /panel.png al Kindle")
    server.set_defaults(handler=_cmd_serve)

    resolve = commands.add_parser(
        "resolve-station", parents=[common], help="cerca lo stop_id di una stazione"
    )
    resolve.add_argument("query", help='nome della stazione, es. "Genova Brignole"')
    resolve.add_argument("--limit", type=int, default=6, help="numero massimo di risultati")
    resolve.set_defaults(handler=_cmd_resolve_station)
    return parser


def _cmd_render(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    data = collect(config, Cache(config.cache_dir))
    if getattr(args, "night", False):
        data = replace(data, night=True)
    image = render_panel(
        data,
        (config.panel.width, config.panel.height),
        font_override=config.render.font,
        bold_override=config.render.font_bold,
        stop_priority=config.trains.stop_priority,
    )
    output = Path(args.output)
    image.save(output, format="PNG", optimize=True)
    print(f"pannello {config.panel.width}x{config.panel.height} scritto in {output.resolve()}")
    print(f"aggiornato alle {data.generated_at:%H:%M:%S} ({config.timezone})")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    host = "localhost" if config.server.host in {"0.0.0.0", "::"} else config.server.host
    print(f"pannello: http://{host}:{config.server.port}/panel.html")
    print(f"refresh consigliato: {config.panel.refresh_seconds} s - Ctrl+C per uscire")
    try:
        serve(config, Cache(config.cache_dir))
    except OSError as exc:
        print(
            f"porta {config.server.port} non disponibile ({exc}): "
            "chiudi l'istanza già in ascolto e riprova",
            file=sys.stderr,
        )
        return 1
    return 0


def _cmd_resolve_station(args: argparse.Namespace) -> int:
    try:
        base_url = load_config(args.config).trains.base_url
    except ConfigError:
        # Utile proprio durante il setup: la ricerca deve funzionare anche senza config.toml.
        base_url = trains_source.DEFAULT_BASE_URL
    try:
        results = trains_source.resolve_stations(
            args.query, base_url=base_url, limit=args.limit
        )
    except SourceError as exc:
        print(f"ricerca fallita: {exc}", file=sys.stderr)
        return 1
    if not results:
        print(f"nessuna stazione trovata per {args.query!r}", file=sys.stderr)
        return 1
    for name, stop_id in results:
        print(f"{name}  ->  {stop_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
