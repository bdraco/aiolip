import asyncio
import logging
import socket
import time

from .data import LIP_PROTOCOL_MODE_TO_LIPMODE, LIPMessage, LIPMode
from .exceptions import LIPConnectionStateError, LIPProtocolError
from .protocol import (
    CONNECT_TIMEOUT,
    LIP_ACTION_CHAR,
    LIP_EMPTY_RE,
    LIP_ERROR_RE,
    LIP_KEEP_ALIVE,
    LIP_KEEP_ALIVE_INTERVAL,
    LIP_KEEPALIVE_RE,
    LIP_PASSWORD,
    LIP_PORT,
    LIP_PROTOCOL_GNET,
    LIP_PROTOCOL_LOGIN,
    LIP_PROTOCOL_PASSWORD,
    LIP_QUERY_CHAR,
    LIP_READ_TIMEOUT,
    LIP_RESPONSE_RE,
    LIP_USERNAME,
    SOCKET_TIMEOUT,
    LIPConenctionState,
    LIPSocket,
)

_LOGGER = logging.getLogger(__name__)


class LIP:
    """Async class to speak LIP."""

    def __init__(self):
        """Create the LIP class."""
        self.connection_state = LIPConenctionState.NOT_CONNECTED
        self._lip = None
        self._host = None
        self._read_connect_lock = asyncio.Lock()
        self._disconnect_event = asyncio.Event()
        self._reconnecting_event = asyncio.Event()
        self._subscriptions = []
        self._last_keep_alive_response = None
        self._keep_alive_task = None
        self.loop = None

    async def async_connect(self, server_addr):
        """Connect to the bridge via LIP."""
        self.loop = asyncio.get_event_loop()

        if self.connection_state != LIPConenctionState.NOT_CONNECTED:
            raise LIPConnectionStateError

        self._disconnect_event.clear()

        try:
            await self._async_connect(server_addr)
        except asyncio.TimeoutError:
            _LOGGER.debug("Timed out while trying to connect to %s", server_addr)
            self.connection_state = LIPConenctionState.NOT_CONNECTED
            raise

    async def _async_connect(self, server_addr):
        """Make the connection."""
        _LOGGER.debug("Connecting to %s", server_addr)
        self.connection_state = LIPConenctionState.CONNECTING
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                server_addr,
                LIP_PORT,
                family=socket.AF_INET,
            ),
            timeout=CONNECT_TIMEOUT,
        )
        self._lip = LIPSocket(reader, writer)
        _verify_expected_response(
            await self._lip.async_readuntil(" "), LIP_PROTOCOL_LOGIN
        )
        await self._lip.async_write_command(LIP_USERNAME)
        _verify_expected_response(
            await self._lip.async_readuntil(" "), LIP_PROTOCOL_PASSWORD
        )
        await self._lip.async_write_command(LIP_PASSWORD)
        _verify_expected_response(
            await self._lip.async_readuntil(" "), LIP_PROTOCOL_GNET
        )
        self.connection_state = LIPConenctionState.CONNECTED
        self._host = server_addr
        self._reconnecting_event.clear()
        _LOGGER.debug("Connected to %s", server_addr)

    async def _async_disconnected(self):
        """Reconnect after disconnected."""
        if self._reconnecting_event.is_set():
            return

        if self._lip:
            self._lip.close()
            self._lip = None

        self._reconnecting_event.set()
        async with self._read_connect_lock:
            self.connection_state = LIPConenctionState.NOT_CONNECTED
            while not self._disconnect_event.is_set():
                try:
                    await self._async_connect(self._host)
                    return
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "Timed out while trying to reconnect to %s", self._host
                    )
                    pass

    async def async_stop(self):
        """Disconnect from the bridge."""
        self._disconnect_event.set()
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            self._keep_alive_task = None
        self._lip.close()

    async def _async_keep_alive_or_reconnect(self):
        """Keep alive or reconnect."""
        connection_error = False
        try:
            await self._lip.async_write_command(LIP_KEEP_ALIVE)
        except (asyncio.TimeoutError, ConnectionResetError) as ex:
            _LOGGER.debug("Lutron bridge disconnected: %s", ex)
            connection_error = True

        if connection_error or self._last_keep_alive_response < time.time() - (
            LIP_KEEP_ALIVE_INTERVAL + SOCKET_TIMEOUT
        ):
            _LOGGER.debug("Lutron bridge keep alive timeout, reconnecting.")
            await self._async_disconnected()
            self._last_keep_alive_response = time.time()

    def _keepalive_watchdog(self):
        """Send keep alives."""
        if (
            self._disconnect_event.is_set()
            or self.connection_state != LIPConenctionState.CONNECTED
        ):
            return

        asyncio.create_task(self._async_keep_alive_or_reconnect())

        self._keep_alive_task = self.loop.call_later(
            LIP_KEEP_ALIVE_INTERVAL, self._keepalive_watchdog
        )

    async def async_run(self):
        """Start interacting with the bridge."""
        if self.connection_state != LIPConenctionState.CONNECTED:
            raise LIPConnectionStateError

        self._last_keep_alive_response = time.time()
        self._keepalive_watchdog()

        while not self._disconnect_event.is_set():
            await self._async_run_once()

    async def _async_run_once(self):
        """Process one message or event."""
        async with self._read_connect_lock:
            read_task = asyncio.create_task(self._lip.async_readline())

            _, pending = await asyncio.wait(
                (
                    read_task,
                    self._disconnect_event.wait(),
                    self._reconnecting_event.wait(),
                ),
                timeout=LIP_READ_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for coro in pending:
                coro.cancel()

        if self._disconnect_event.is_set():
            _LOGGER.debug("Stopping run because of disconnect_event")
            return

        if isinstance(read_task.exception(), asyncio.TimeoutError) or isinstance(
            read_task.exception(), BrokenPipeError
        ):
            return

        self._process_message(read_task.result())

    def _process_message(self, response):
        """Process a lip message."""
        if response is not None and response.startswith(LIP_PROTOCOL_GNET):
            response = response[len(LIP_PROTOCOL_GNET) :]

        if not response or LIP_EMPTY_RE.match(response):
            return

        match = LIP_RESPONSE_RE.match(response)
        if match:
            try:
                message = LIPMessage(
                    LIP_PROTOCOL_MODE_TO_LIPMODE.get(match.group(1), LIPMode.UNKNOWN),
                    int(match.group(2)),
                    int(match.group(3)),
                    float(match.group(4)),
                )
                for callback in self._subscriptions:
                    callback(message)
            except ValueError:
                pass
        elif LIP_KEEPALIVE_RE.match(response):
            self._last_keep_alive_response = time.time()
        elif LIP_ERROR_RE.match(response):
            _LOGGER.error("Protocol Error: %s", response)
        else:
            _LOGGER.debug("Unknown lutron message: %s", response)

    async def query(self, mode, integration_id, action, *args):
        """Query the bridge."""
        await self._async_send_command(
            LIP_QUERY_CHAR, mode, integration_id, action, *args
        )

    async def action(self, mode, integration_id, action, *args):
        """Do an action on the bridge."""
        await self._async_send_command(
            LIP_ACTION_CHAR, mode, integration_id, action, *args
        )

    def subscribe(self, callback):
        """Subscribe to lip events."""

        def _unsub_callback():
            self._subscriptions.remove(callback)

        self._subscriptions.append(callback)
        return _unsub_callback

    async def _async_send_command(self, protocol_header, mode, *cmd):
        """Send a command."""
        if self.connection_state != LIPConenctionState.CONNECTED:
            raise LIPConnectionStateError

        assert isinstance(mode, LIPMode)

        request = ",".join([mode.name, *[str(key) for key in cmd]])
        await self._lip.async_write_command(f"{protocol_header}{request}")


def _verify_expected_response(received, expected):
    if not received.startswith(expected):
        raise LIPProtocolError(received, expected)
