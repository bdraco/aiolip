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
