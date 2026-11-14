"""Tests for Perific API parsing and token refresh."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
from aiohttp import ClientTimeout

_API_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "perific" / "api.py"
)
_spec = importlib.util.spec_from_file_location("perific_api", _API_PATH)
api = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = api
_spec.loader.exec_module(api)


class _Response:
    def __init__(
        self, status: int, payload: object, json_error: Exception | None = None
    ) -> None:
        self.status = status
        self._payload = payload
        self._json_error = json_error

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def text(self) -> str:
        return str(self._payload)

    async def json(self) -> object:
        if self._json_error:
            raise self._json_error
        return self._payload


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def request(self, method: str, url: str, **kwargs: object) -> _Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)


def _client(responses: list[_Response]) -> tuple[api.Client, _Session]:
    session = _Session(responses)
    return api.Client(session, "https://api.enegic.com"), session


@pytest.mark.asyncio
async def test_import_current_is_positive_and_zero_energy_is_kept() -> None:
    client, _session = _client(
        [
            _Response(
                200,
                [
                    {
                        "ItemId": 7,
                        "LatestPackets": {
                            "PhaseRealTime": {
                                "data": {
                                    "hiavg": [-5.5, 0.0, 1.5],
                                    "huavg": [230.0, 231.0, 232.0],
                                }
                            },
                            "PhaseMinute": {"data": {"hwi": 0.0, "hwo": 1.25}},
                        },
                    }
                ],
            )
        ]
    )

    packets = await client.get_latest_packets("token")
    realtime = packets[0].realtime
    assert realtime is not None
    assert realtime.current == pytest.approx((5.5, 0.0, -1.5))
    assert realtime.voltage == pytest.approx((230.0, 231.0, 232.0))
    assert api.apparent_power_va(realtime, 0) == pytest.approx(5.5 * 230.0)
    assert api.apparent_power_va(realtime, 2) == pytest.approx(1.5 * 232.0)
    assert api.total_apparent_power_va(realtime) == pytest.approx(
        5.5 * 230.0 + 0.0 + 1.5 * 232.0
    )
    minute = packets[0].minute
    assert minute is not None
    assert minute.imported_energy == 0.0
    assert minute.exported_energy == 1.25


@pytest.mark.asyncio
async def test_device_request_sends_shared_items_in_the_body() -> None:
    client, session = _client([_Response(200, {"Items": []})])

    assert await client.get_devices("token") == []
    call = session.calls[0]
    assert call["json"] == {"IncludeSharedItems": True}
    assert "params" not in call
    assert isinstance(call["timeout"], ClientTimeout)
    assert call["timeout"].total == 10


@pytest.mark.asyncio
async def test_authentication_statuses_are_reported_as_invalid_credentials() -> None:
    client, _session = _client([_Response(401, {})])

    with pytest.raises(api.PerificAuthenticationError):
        await client.authenticate("user", "password")


@pytest.mark.asyncio
async def test_bad_request_is_not_an_authentication_failure() -> None:
    client, _session = _client([_Response(400, {})])

    with pytest.raises(api.PerificResponseError):
        await client.authenticate("user", "password")


@pytest.mark.asyncio
async def test_invalid_device_is_skipped_when_another_device_parses() -> None:
    client, _session = _client(
        [
            _Response(
                200,
                [
                    {"ItemId": 1},
                    {
                        "ItemId": 2,
                        "LatestPackets": {
                            "PhaseRealTime": {"data": {"hiavg": [-1.0], "huavg": [230.0]}}
                        },
                    },
                ],
            )
        ]
    )

    packets = await client.get_latest_packets("token")

    assert [packet.item_id for packet in packets] == [2]
    assert api.total_apparent_power_va(packets[0].realtime) == pytest.approx(230.0)


@pytest.mark.asyncio
async def test_invalid_json_is_a_response_error_not_a_connection_error() -> None:
    client, _session = _client([_Response(200, "not json", ValueError("invalid JSON"))])

    with pytest.raises(api.PerificResponseError, match="invalid JSON"):
        await client.get_latest_packets("token")


@pytest.mark.asyncio
async def test_token_refresh_retries_once() -> None:
    calls: list[str] = []

    async def call(token: str) -> str:
        calls.append(token)
        if token != "fresh":
            raise api.PerificAuthenticationError("rejected")
        return "ok"

    async def refresh() -> str:
        calls.append("refresh")
        return "fresh"

    token, result = await api.call_with_token_refresh("stale", call, refresh)

    assert (token, result) == ("fresh", "ok")
    assert calls == ["stale", "refresh", "fresh"]


@pytest.mark.asyncio
async def test_token_refresh_does_not_retry_a_rejected_new_token() -> None:
    async def call(token: str) -> str:
        raise api.PerificAuthenticationError(token)

    async def refresh() -> str:
        raise api.PerificAuthenticationError("password rejected")

    with pytest.raises(api.PerificAuthenticationError, match="password rejected"):
        await api.call_with_token_refresh(None, call, refresh)
