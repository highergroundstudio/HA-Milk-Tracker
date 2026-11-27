"""Serve the bundled Lovelace cards.

The cards are served by a small view instead of a static path so the browser
re-validates them on every page load (``Cache-Control: no-cache`` + ETag).
HACS writes updated files to disk immediately, so a card-only update shows up
after a browser refresh, with no Home Assistant restart. Unchanged files
cost a 304 response.
"""

from __future__ import annotations

import hashlib
from http import HTTPStatus
from pathlib import Path

from aiohttp import web
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import FRONTEND_FILE, FRONTEND_URL_BASE

CARDS_PATH = Path(__file__).parent / "frontend" / FRONTEND_FILE
CARDS_URL = f"{FRONTEND_URL_BASE}/{FRONTEND_FILE}"


class MilkTrackerCardsView(HomeAssistantView):
    """Serve milk-tracker-cards.js, always fresh from disk."""

    url = CARDS_URL
    name = "milk_tracker:cards"
    requires_auth = False  # loaded by the frontend like any other module

    def __init__(self) -> None:
        self._cache: tuple[float, bytes, str] | None = None

    def _load(self) -> tuple[bytes, str]:
        mtime = CARDS_PATH.stat().st_mtime
        if self._cache is None or self._cache[0] != mtime:
            body = CARDS_PATH.read_bytes()
            self._cache = (mtime, body, hashlib.sha256(body).hexdigest()[:16])
        return self._cache[1], self._cache[2]

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body, digest = await hass.async_add_executor_job(self._load)
        etag = f'"{digest}"'
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=HTTPStatus.NOT_MODIFIED, headers=headers)
        return web.Response(body=body, content_type="application/javascript", headers=headers)


def async_register_frontend(hass: HomeAssistant) -> None:
    hass.http.register_view(MilkTrackerCardsView())
    # No version in the URL: freshness comes from the ETag check above.
    add_extra_js_url(hass, CARDS_URL)
