"""Client for the Perific cloud API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any, TypeVar

from aiohttp import ClientError, ClientSession, ClientTimeout

REQUEST_TIMEOUT = ClientTimeout(total=10)
_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


class PerificError(Exception):
    """Base error for Perific API failures."""


class PerificAuthenticationError(PerificError):
    """Raised when credentials or an API token are rejected."""


class PerificConnectionError(PerificError):
    """Raised when the Perific API cannot be reached."""


class PerificResponseError(PerificError):
    """Raised when the Perific API returns invalid data."""


@dataclass(frozen=True, slots=True)
class Token:
    """Authentication token returned by the Perific API."""

    token: str


@dataclass(frozen=True, slots=True)
class Device:
    """A Perific device from the account overview."""

    id: int
    name: str
    item_type: str
    mac_address: str | None
    model: str | None
    system_name: str | None


@dataclass(frozen=True, slots=True)
class Packet:
    """A measurement packet, retaining only values used by the integration."""

    current: tuple[float | None, ...]
    voltage: tuple[float | None, ...]
    imported_energy: float | None
    exported_energy: float | None


@dataclass(frozen=True, slots=True)
class DevicePackets:
    """The latest packets for one device."""

    item_id: int
    minute: Packet | None
    realtime: Packet | None


class Client:
    """Asynchronous Perific API client using Home Assistant's HTTP session."""

    def __init__(self, session: ClientSession, host: str) -> None:
        self._session = session
        self._host = host.rstrip("/")

    async def authenticate(self, username: str, password: str) -> Token:
        """Authenticate and return a new token."""
        data = await self._request(
            "put",
            "/createtoken",
            json={"username": username, "password": password},
        )
        try:
            return Token(token=data["TokenInfo"]["Token"])
        except (KeyError, TypeError) as err:
            raise PerificResponseError("Authentication response lacks TokenInfo") from err

    async def get_devices(self, token: str) -> list[Device]:
        """Return devices visible to the authenticated account."""
        data = await self._request(
            "get",
            "/getaccountoverview",
            token=token,
            json={"IncludeSharedItems": True},
        )
        try:
            return [self._parse_device(item) for item in data["Items"]]
        except (KeyError, TypeError) as err:
            raise PerificResponseError("Account overview has an invalid Items payload") from err

    async def get_latest_packets(self, token: str) -> list[DevicePackets]:
        """Return the latest packets for all devices."""
        data = await self._request("put", "/getlatestpackets", token=token)
        if not isinstance(data, list):
            raise PerificResponseError("Latest-packets response is not a list")
        parsed: list[DevicePackets] = []
        for item in data:
            try:
                parsed.append(self._parse_device_packets(item))
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Skipping a Perific packet with an invalid payload")
        if data and not parsed:
            raise PerificResponseError("Latest-packets response has an invalid payload")
        return parsed

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        authentication_statuses: tuple[int, ...] = (401, 403),
        **kwargs: Any,
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Authorization"] = token
        try:
            async with self._session.request(
                method,
                f"{self._host}{path}",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as response:
                if response.status in authentication_statuses:
                    raise PerificAuthenticationError("Perific API rejected authentication")
                if response.status < 200 or response.status >= 300:
                    raise PerificResponseError(
                        f"Perific API returned HTTP {response.status}: {await response.text()}"
                    )
                try:
                    return await response.json()
                except (ClientError, ValueError) as err:
                    raise PerificResponseError(
                        "Perific API returned an invalid JSON response"
                    ) from err
        except PerificError:
            raise
        except (ClientError, asyncio.TimeoutError) as err:
            raise PerificConnectionError("Unable to connect to Perific API") from err

    @staticmethod
    def _parse_device(data: dict[str, Any]) -> Device:
        return Device(
            id=int(data["ItemId"]),
            name=str(data["Name"]),
            item_type=str(data["ItemType"]),
            mac_address=data.get("MacAddress"),
            model=data.get("ItemSubType"),
            system_name=data.get("SystemName"),
        )

    @classmethod
    def _parse_device_packets(cls, data: dict[str, Any]) -> DevicePackets:
        packets = data["LatestPackets"]
        return DevicePackets(
            item_id=int(data["ItemId"]),
            minute=cls._parse_packet(packets.get("PhaseMinute")),
            realtime=cls._parse_packet(packets.get("PhaseRealTime")),
        )

    @staticmethod
    def _parse_packet(data: dict[str, Any] | None) -> Packet | None:
        if data is None:
            return None
        payload = data["data"]
        # The API reports import current as negative and export current as positive.
        current = payload.get("hiavg") or payload.get("iavg") or []
        voltage = payload.get("huavg") or payload.get("uavg") or []
        return Packet(
            current=tuple(None if value is None else -float(value) for value in current),
            voltage=tuple(None if value is None else float(value) for value in voltage),
            imported_energy=(
                float(payload["hwi"]) if payload.get("hwi") is not None else None
            ),
            exported_energy=(
                float(payload["hwo"]) if payload.get("hwo") is not None else None
            ),
        )


async def call_with_token_refresh(
    token: str | None,
    call: Callable[[str], Awaitable[_T]],
    refresh: Callable[[], Awaitable[str]],
) -> tuple[str, _T]:
    """Call the API, refreshing the token once when it is missing or rejected."""
    current = token if token is not None else await refresh()
    try:
        return current, await call(current)
    except PerificAuthenticationError:
        current = await refresh()
        return current, await call(current)


def apparent_power_va(packet: Packet, phase: int) -> float | None:
    """Return apparent power for one phase, in volt-amperes."""
    if len(packet.current) <= phase or len(packet.voltage) <= phase:
        return None
    current = packet.current[phase]
    voltage = packet.voltage[phase]
    if current is None or voltage is None:
        return None
    return abs(current) * voltage


def total_apparent_power_va(packet: Packet) -> float | None:
    """Return the sum of per-phase apparent power, in volt-amperes."""
    values = [
        value
        for phase in range(3)
        if (value := apparent_power_va(packet, phase)) is not None
    ]
    if not values:
        return None
    return sum(values)
