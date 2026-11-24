"""Maintenance commands sent to the printer's RAW print port.

Epson inkjets accept "Remote Mode" commands embedded in a print job. They are
only partly documented; the sequences below follow Gutenprint (escputil) and
epson_escp2.
"""

from __future__ import annotations

import asyncio

RAW_PORT = 9100
_TIMEOUT = 15

_INITIALIZE = b"\x1b@"
_EXIT_PACKET_MODE = b"\x00\x00\x00\x1b\x01@EJL 1284.4\n@EJL     \n"
_REMOTE_MODE = b"\x1b(R\x08\x00\x00REMOTE1"
_EXIT_REMOTE_MODE = b"\x1b\x00\x00\x00"
_FORM_FEED = b"\x0c"


def _remote_cmd(cmd: bytes, args: bytes) -> bytes:
    return cmd + len(args).to_bytes(2, "little") + args


_LOAD_SETTINGS = _remote_cmd(b"LD", b"")
_JOB_END = _remote_cmd(b"JE", b"\x00")

NOZZLE_CHECK_JOB = (
    _EXIT_PACKET_MODE
    + _INITIALIZE
    + _INITIALIZE
    + _REMOTE_MODE
    + _remote_cmd(b"NC", b"\x00\x00")
    + _EXIT_REMOTE_MODE
    # NC prints the pattern onto the current page but does not eject it; the
    # printer keeps waiting for more data until it gets a form feed.
    + _INITIALIZE
    + b"\r"
    + _FORM_FEED
    # Reload the stored settings (drops job-level overrides, no factory reset)
    # and close the job.
    + _INITIALIZE
    + _REMOTE_MODE
    + _LOAD_SETTINGS
    + _EXIT_REMOTE_MODE
    + _INITIALIZE
    + _REMOTE_MODE
    + _LOAD_SETTINGS
    + _JOB_END
    + _EXIT_REMOTE_MODE
)


class PrinterCommandError(Exception):
    """A command could not be delivered to the printer."""


async def async_send_raw(host: str, data: bytes, port: int = RAW_PORT) -> None:
    """Send data to the printer's RAW port (JetDirect, no reply expected)."""
    try:
        async with asyncio.timeout(_TIMEOUT):
            _, writer = await asyncio.open_connection(host, port)
            try:
                writer.write(data)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
    except TimeoutError as err:
        raise PrinterCommandError(f"timed out after {_TIMEOUT}s") from err  # noqa: TRY003
    except OSError as err:
        raise PrinterCommandError(str(err) or type(err).__name__) from err


async def async_print_nozzle_check(host: str) -> None:
    """Print the printer's built-in nozzle check pattern."""
    await async_send_raw(host, NOZZLE_CHECK_JOB)
