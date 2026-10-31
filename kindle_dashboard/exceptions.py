"""Eccezioni del progetto."""

from __future__ import annotations


class SourceError(RuntimeError):
    """Una fonte dati (meteo, calendario, treni) non ha risposto come previsto.

    È un errore recuperabile: il chiamante mostra i dati in cache oppure una sezione vuota.
    """


class ConfigError(RuntimeError):
    """Il file di configurazione è assente o non valido."""
