"""Fixture condivise. I test non devono mai toccare la rete né il filesystem utente."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kindle_dashboard.timezone_utils import zone

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rome() -> Any:
    return zone("Europe/Rome")


@pytest.fixture
def read_fixture() -> Callable[[str], str]:
    def read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return read


@pytest.fixture
def load_json(read_fixture: Callable[[str], str]) -> Callable[[str], Any]:
    def load(name: str) -> Any:
        return json.loads(read_fixture(name))

    return load
