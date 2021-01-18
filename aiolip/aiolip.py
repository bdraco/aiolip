import asyncio
import re
import socket
from dataclasses import dataclass
from enum import Enum

LIP_USERNAME = "lutron"
LIP_PASSWORD = "integration"
LIP_PORT = 23

LIP_RESPONSE_RE = re.compile("~([A-Z]+),([0-9.]+),([0-9.]+),([0-9.]+)")

LIP_PROTOCOL_LOGIN = "login: "
LIP_PROTOCOL_PASSWORD = "password: "
LIP_PROTOCOL_GNET = "GNET> "

LIP_QUERY_CHAR = "?"
LIP_ACTION_CHAR = "#"

LIP_BUTTON_PRESS = 3
LIP_BUTTON_RELEASE = 4

LIP_KEEP_ALIVE = "?SYSTEM,10"

CONNECT_TIMEOUT = 10
SOCKET_TIMEOUT = 10

LIP_READ_TIMEOUT = 60
LIP_KEEP_ALIVE_INTERVAL = 60


@dataclass
class LIPMessage:
    """Class for LIP messages."""

    mode: str
    integration_id: int
    action_number: int
    value: float


class LIPConnectionStateError(Exception):
    """An exception to represent a conneciton state error."""

    def __str__(self) -> str:
        """Return string representation."""
        return "Lutron Integration Protcol is not connected."


class LIPProtocolError(Exception):
    """An exception to represent a protocol error."""

    def __init__(self, received, expected):
        self.received = received
        self.expected = expected

    def __str__(self) -> str:
        """Return string representation."""
        return f"Lutron Protocol Error received=[{self.received}] expected=[{self.expected}]"


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
        buffer = await asyncio.wait_for(self._reader.readuntil(seperator.encode("ASCII")), timeout=timeout)
        if buffer == b"":
            return None

        return buffer.decode("UTF-8")

    async def async_write_command(self, text):
        self._writer.write(text.encode("ASCII") + b"\r\n")
        await self._writer.drain()

    def __del__(self):
        """Cleanup when the object is deleted."""
        self._writer.close()


class LIP:
    """Async class to speak LIP."""

    def __init__(self):
        """Create the LIP class."""
        self._connection_state = LIPConenctionState.NOT_CONNECTED
        self._lip = None
        self._host = None
        self._disconnect_event = None
        self._subscriptions = []
        self.loop = None

    def connection_state(self):
        """The current state of the connection."""
        return self._connection_state

    async def async_connect(self, server_addr):
        """Connect to the bridge via LIP."""
        self.loop = asyncio.get_event_loop()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                server_addr,
                LIP_PORT,
                family=socket.AF_INET,
            ),
            timeout=CONNECT_TIMEOUT,
        )
        self._lip = LIPSocket(reader, writer)
        _verify_expected_response(await self._lip.async_readuntil(" "), LIP_PROTOCOL_LOGIN)
        await self._lip.async_write_command(LIP_USERNAME)
        _verify_expected_response(await self._lip.async_readuntil(" "), LIP_PROTOCOL_PASSWORD)
        await self._lip.async_write_command(LIP_PASSWORD)
        _verify_expected_response(await self._lip.async_readuntil(" "), LIP_PROTOCOL_GNET)

        self._connection_state = LIPConenctionState.CONNECTED
        self._disconnect_event = asyncio.Event()
        self._host = server_addr

    async def _async_reconnect(self):
        """Reconnect after disconnected."""
        await self.async_connect(self._host)

    async def async_stop(self):
        """Disconnect from the bridge."""
        self._disconnect_event.set()
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            self._keep_alive_task = None

    async def _keep_alive_or_reconnect(self):
        """Start keep alive."""
        try:
            await self._async_send_keep_alive()
        except ConnectionResetError:
            await self._async_reconnect()

        if self._disconnect_event.is_set():
            return

        self._keep_alive_task = self.loop.call_later(
            LIP_KEEP_ALIVE_INTERVAL, self._keep_alive_or_reconnect
        )

    async def async_start(self):
        """Start interacting with the bridge."""

        self._verify_connected()
        await self._keep_alive_or_reconnect()

        while True:
            disconnect_task = asyncio.create_task(self._disconnect_event.wait())
            read_task = asyncio.create_task(self._lip.async_readline())
            try:
                await asyncio.wait(
                    (read_task, disconnect_task), timeout=LIP_READ_TIMEOUT
                )
            except asyncio.TimeoutError:
                continue

            if self._disconnect_event.is_set():
                return

            match = read_task.result().match(LIP_RESPONSE_RE)
            if match:
                try:
                    message = LIPMessage(
                        match.group(1).decode("utf-8"),
                        int(match.group(2)),
                        int(match.group(3)),
                        float(match.group(4)),
                    )
                    for callback in self._subscriptions:
                        callback(message)
                except ValueError:
                    pass

    async def query(self, mode, integration_id, action, *args):
        """Query the bridge."""
        await self._async_send_command(LIP_QUERY_CHAR, [mode, integration_id, action, *args])

    async def action(self, mode, integration_id, action, *args):
        """Do an action on the bridge."""
        await self._async_send_command(LIP_ACTION_CHAR, [mode, integration_id, action, *args])

    async def _async_send_command(self, protocol_header, cmd):
        self._verify_connected()
        request = ",".join(cmd)
        await self._lip.async_write_command(f"{protocol_header}{request}")

    def subscribe(self, callback):
        """Subscribe to lip events."""

        def _unsub_callback():
            self._subscriptions.remove(callback)

        self._subscriptions.append(callback)
        return _unsub_callback

    def _verify_connected(self):
        """Throw if we are disconnected."""
        if self._connection_state != LIPConenctionState.CONNECTED:
            raise LIPConnectionStateError


def _verify_expected_response(expected, received):
    if not expected.startswith(received):
        raise LIPProtocolError(expected, received)


async def main():
    lip = LIP()

    await lip.async_connect("192.168.209.70")

    def message(msg):
        import pprint

        pprint.pprint(msg)

    lip.subscribe(message)
    await lip.async_start()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
