"""Helper di impaginazione: troncamento, separatori, etichette di data."""

from __future__ import annotations

from datetime import date, timedelta

from PIL import ImageDraw

from .fonts import Font

ELLIPSIS = "…"
WEEKDAYS = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")
MONTHS = ("GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC")
# Sedici settori e non otto: in barca la differenza fra NE e NNE si sente, e nel pannello lo
# spazio per un carattere in più c'è. Le sigle sono quelle italiane (O = Ovest, SO = Sud-Ovest).
COMPASS_POINTS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
)


# Nomi tradizionali del Mediterraneo, uno per settore. Gli intermedi sono composti dai due venti
# principali *nell'ordine delle lettere della sigla*: la prima lettera dà il primo nome, il resto il
# secondo (OSO = Ponente-Libeccio, NNO = Tramontana-Maestrale). "Levante" da solo racconterebbe una
# direzione che non è quella indicata dalla sigla, e l'ordine alfabetico evita che lo stesso nome
# compaia con due grafie: si legge la sigla e si sa a quale punto cardinale è legata.
WIND_NAMES = (
    "Tramontana",            # N
    "Tramontana-Grecale",    # NNE
    "Grecale",               # NE
    "Levante-Grecale",       # ENE
    "Levante",               # E
    "Levante-Scirocco",      # ESE
    "Scirocco",              # SE
    "Ostro-Scirocco",        # SSE
    "Ostro",                 # S
    "Ostro-Libeccio",        # SSO
    "Libeccio",              # SO
    "Ponente-Libeccio",      # OSO
    "Ponente",               # O
    "Ponente-Maestrale",     # ONO
    "Maestrale",             # NO
    "Tramontana-Maestrale",  # NNO
)


def _sector(degrees: float) -> int:
    """Indice 0-15 del settore di provenienza: unica conversione usata da sigla e nome."""
    return round((float(degrees) % 360) / 22.5) % len(COMPASS_POINTS)


def compass(degrees: float | None) -> str:
    """Direzione di provenienza a 16 settori (``NNE``); vuota se il dato manca."""
    if degrees is None:
        return ""
    return COMPASS_POINTS[_sector(degrees)]


def wind_name(degrees: float | None) -> str:
    """Nome tradizionale del vento (``Levante-Scirocco``) per la direzione; vuoto se manca."""
    if degrees is None:
        return ""
    return WIND_NAMES[_sector(degrees)]


def fit_text(text: str, font: Font, max_width: float) -> str:
    """Accorcia il testo con un ellissi per rientrare in ``max_width``."""
    if max_width <= 0:
        return ""
    if font.getlength(text) <= max_width:
        return text
    trimmed = text
    while trimmed and font.getlength(trimmed + ELLIPSIS) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed.rstrip()}{ELLIPSIS}" if trimmed else ""


def wrap_text(text: str, font: Font, max_width: float, *, lines: int = 2) -> tuple[str, ...]:
    """Spezza ``text`` in al massimo ``lines`` righe, con l'ellissi sull'ultima.

    Il taglio cade su uno spazio — mai dentro una parola — e l'ultima riga passa da `fit_text`:
    quello che non entra diventa ellissi invece di sparire. Il numero di righe è noto *prima* di
    disegnare, così chi chiama può decidere l'altezza della riga e, se non c'è spazio, tornare a
    una riga sola (`lines=1`) senza perdere la voce.
    """
    if max_width <= 0 or lines < 1:
        return ()
    words = text.split()
    if not words:
        return ()
    result: list[str] = []
    index = 0
    while index < len(words) and len(result) < lines - 1:
        current = words[index]
        index += 1
        while index < len(words):
            candidate = f"{current} {words[index]}"
            if font.getlength(candidate) > max_width:
                break
            current = candidate
            index += 1
        if font.getlength(current) > max_width:
            # Una parola singola più larga della riga: non ha senso spezzarla a metà, si lascia
            # all'ultima riga che la accorcia con l'ellissi.
            break
        result.append(current)
    tail = " ".join(words[index:])
    if tail:
        result.append(fit_text(tail, font, max_width))
    return tuple(result)


def divider(
    draw: ImageDraw.ImageDraw, left: float, right: float, y: float, thickness: int = 2
) -> None:
    draw.rectangle([left, y, right, y + max(1, thickness)], fill="black")


def date_label(day: date) -> str:
    """Es. ``SAB 31 OTT 2026``."""
    return f"{WEEKDAYS[day.weekday()]} {day.day:02d} {MONTHS[day.month - 1]} {day.year}"


def relative_day(day: date, today: date) -> str:
    """``OGGI``/``DOM``: compatto per le colonne strette."""
    return "OGGI" if day == today else WEEKDAYS[day.weekday()]


def waste_day_label(day: date, today: date) -> str:
    """``OGGI``/``DOMANI``, poi il giorno della settimana: nella colonna stretta le date non ci stanno."""
    if day == today:
        return "OGGI"
    if day == today + timedelta(days=1):
        return "DOMANI"
    return WEEKDAYS[day.weekday()]
