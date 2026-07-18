"""Dobles de prueba para no tocar la red real."""
from __future__ import annotations

import sys
from pathlib import Path

# Permite `import services_monitor` al correr los tests desde cualquier cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "", json_data=None) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_data if json_data is not None else {"ok": True}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    """Devuelve respuestas (o lanza excepciones) de una cola configurable."""

    def __init__(self, request_results=None, post_results=None) -> None:
        self._req = list(request_results or [])
        self._post = list(post_results or [])
        self.request_calls: list[tuple] = []
        self.post_calls: list[tuple] = []

    def request(self, method, url, **kw):
        self.request_calls.append((method, url, kw))
        item = self._req.pop(0) if self._req else FakeResponse()
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, **kw):
        self.post_calls.append((url, kw))
        item = self._post.pop(0) if self._post else FakeResponse()
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        pass
