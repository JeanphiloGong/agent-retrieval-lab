"""A tiny source tree whose line numbers are stable teaching evidence."""

ERROR_TIMEOUT = "[E104]: connection timed out"


def connect(url: str) -> str:
    """Open a connection; the example returns its URL without network I/O."""
    return url


class Client:
    def connect(self) -> str:
        return "client connection"
