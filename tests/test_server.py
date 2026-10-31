"""Test del server HTTP: endpoint reali su porta effimera, senza rendering vero."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from datetime import datetime

import pytest
from PIL import Image

from kindle_dashboard import server
from kindle_dashboard.cache import Cache
from kindle_dashboard.config import Config, ServerConfig
from kindle_dashboard.model import PanelData
from kindle_dashboard.timezone_utils import zone

FAKE_PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    refresh_seconds = 300

    def png(self) -> bytes:
        return FAKE_PNG


def start(tmp_path, monkeypatch) -> tuple[server.ThreadingHTTPServer, threading.Thread]:
    monkeypatch.setattr(server, "PanelService", FakeService)
    config = Config(server=ServerConfig(host="127.0.0.1", port=0), cache_dir=tmp_path)
    httpd = server.build_server(config, Cache(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def test_health_and_panel_endpoints(tmp_path, monkeypatch):
    httpd, thread = start(tmp_path, monkeypatch)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
            assert response.status == 200
            assert response.read() == b"ok\n"

        with urllib.request.urlopen(f"{base}/panel.png", timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/png"
            assert response.headers["Cache-Control"] == "no-store"
            assert response.read() == FAKE_PNG
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_panel_html_points_at_png_and_autorefreshes(tmp_path, monkeypatch):
    httpd, thread = start(tmp_path, monkeypatch)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/panel.html", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.headers["Content-Type"] == "text/html; charset=utf-8"
        assert 'http-equiv="refresh" content="300"' in body
        assert 'src="/panel.png?t=' in body
        assert "max-height:100vh" in body
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_second_instance_cannot_steal_the_listening_port(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PanelService", FakeService)
    first = server.build_server(
        Config(server=ServerConfig(host="127.0.0.1", port=0), cache_dir=tmp_path), Cache(tmp_path)
    )
    port = first.server_address[1]
    try:
        with pytest.raises(OSError):
            second = server.build_server(
                Config(server=ServerConfig(host="127.0.0.1", port=port), cache_dir=tmp_path),
                Cache(tmp_path),
            )
            second.server_close()
    finally:
        first.server_close()


def test_panel_service_guards_against_duplicate_requests(tmp_path, monkeypatch):
    calls = {"count": 0}

    def fake_collect(config, cache):
        calls["count"] += 1
        return PanelData(generated_at=datetime.now(zone("Europe/Rome")), timezone="Europe/Rome")

    monkeypatch.setattr(server, "collect", fake_collect)
    monkeypatch.setattr(server, "render_panel", lambda *args, **kwargs: Image.new("L", (10, 10)))
    config = Config(server=ServerConfig(host="127.0.0.1", port=0), cache_dir=tmp_path)
    service = server.PanelService(config, Cache(tmp_path))

    service.png()
    service.png()
    assert calls["count"] == 1

    service._collected_at -= 10  # oltre la guardia: si raccoglie di nuovo
    service.png()
    assert calls["count"] == 2


def test_unknown_path_returns_404(tmp_path, monkeypatch):
    httpd, thread = start(tmp_path, monkeypatch)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        try:
            urllib.request.urlopen(f"{base}/nope", timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("atteso HTTP 404")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
