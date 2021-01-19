import asyncio
from enum import Enum
import re

LIP_RESPONSE_RE = re.compile("~([A-Z]+),([0-9.]+),([0-9.]+),([0-9.]+)")
LIP_KEEPALIVE_RE = re.compile("~SYSTEM,")
LIP_EMPTY_RE = re.compile("^[\r\n]+$")
LIP_ERROR_RE = re.compile("~ERROR,")

LIP_PROTOCOL_LOGIN = "login: "
LIP_PROTOCOL_PASSWORD = "password: "
LIP_PROTOCOL_GNET = "GNET> "

LIP_USERNAME = "lutron"
LIP_PASSWORD = "integration"
LIP_PORT = 23

LIP_QUERY_CHAR = "?"
LIP_ACTION_CHAR = "#"

LIP_BUTTON_PRESS = 3
LIP_BUTTON_RELEASE = 4

LIP_KEEP_ALIVE = "?SYSTEM,10"

CONNECT_TIMEOUT = 10
SOCKET_TIMEOUT = 10

LIP_READ_TIMEOUT = 60
LIP_KEEP_ALIVE_INTERVAL = 60


class LIPConenctionState(Enum):
    NOT_CONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2


class LIPSocket:
    """A socket that reads and writes lip protocol."""

    def __init__(self, reader, writer):
        self._writer = writer
        self._reader = reader

    async def async_readline(self, timeout=SOCKET_TIMEOUT):
        buffer = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
        if buffer == b"":
            return None

        return buffer.decode("UTF-8")

    async def async_readuntil(self, seperator, timeout=SOCKET_TIMEOUT):
        buffer = await asyncio.wait_for(
            self._reader.readuntil(seperator.encode("UTF-8")), timeout=timeout
        )
        if buffer == b"":
            return None

        return buffer.decode("UTF-8")

    async def async_write_command(self, text):
        self._writer.write(text.encode("UTF-8") + b"\r\n")
        await self._writer.drain()

    def close(self):
        """Cleanup when disconnected."""
        self._writer.close()

    def __del__(self):
        """Cleanup when the object is deleted."""
        self._writer.close()
