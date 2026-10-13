"""Keep OpenAI 3's httpx2 transport inside the same offline mocks as httpx."""

import importlib
import importlib.util
from typing import Any

import httpx
import pytest
import respx


@pytest.fixture(autouse=True)
def mock_httpx2_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    # RESPX intercepts httpx, while OpenAI 3 uses httpx2 by default.
    if importlib.util.find_spec("httpx2") is None:
        return
    httpx2 = importlib.import_module("httpx2")

    def handle(_transport: Any, request: Any) -> Any:
        response = respx.mock.handler(
            httpx.Request(request.method, str(request.url), headers=request.headers, content=request.read())
        )
        return httpx2.Response(response.status_code, headers=response.headers, content=response.read())

    async def handle_async(_transport: Any, request: Any) -> Any:
        response = await respx.mock.async_handler(
            httpx.Request(request.method, str(request.url), headers=request.headers, content=await request.aread())
        )
        return httpx2.Response(response.status_code, headers=response.headers, content=await response.aread())

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", handle)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", handle_async)
