"""Tests for maintenance commands sent over the RAW port."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.epson_workforce import maintenance
from custom_components.epson_workforce.maintenance import (
    NOZZLE_CHECK_JOB,
    PrinterCommandError,
    async_print_nozzle_check,
    async_send_raw,
)

# Verified on an ET-8500: prints the nozzle check pattern and ejects the page.
EXPECTED_NOZZLE_CHECK_JOB = (
    b"\x00\x00\x00\x1b\x01@EJL 1284.4\n@EJL     \n"
    b"\x1b@\x1b@\x1b(R\x08\x00\x00REMOTE1"
    b"NC\x02\x00\x00\x00"
    b"\x1b\x00\x00\x00"
    b"\x1b@\r\x0c"
    b"\x1b@\x1b(R\x08\x00\x00REMOTE1LD\x00\x00\x1b\x00\x00\x00"
    b"\x1b@\x1b(R\x08\x00\x00REMOTE1LD\x00\x00JE\x01\x00\x00\x1b\x00\x00\x00"
)


def _writer() -> MagicMock:
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    return writer


def test_nozzle_check_job_bytes():
    assert NOZZLE_CHECK_JOB == EXPECTED_NOZZLE_CHECK_JOB


async def test_send_raw_writes_and_closes():
    writer = _writer()
    with patch(
        "asyncio.open_connection", AsyncMock(return_value=(MagicMock(), writer))
    ) as open_conn:
        await async_send_raw("10.0.0.5", b"data")

    open_conn.assert_awaited_once_with("10.0.0.5", 9100)
    writer.write.assert_called_once_with(b"data")
    writer.drain.assert_awaited_once()
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_send_raw_closes_on_write_error():
    writer = _writer()
    writer.drain.side_effect = ConnectionResetError("reset by peer")
    with (
        patch("asyncio.open_connection", AsyncMock(return_value=(MagicMock(), writer))),
        pytest.raises(PrinterCommandError, match="reset by peer"),
    ):
        await async_send_raw("10.0.0.5", b"data")
    writer.close.assert_called_once()


async def test_send_raw_connection_refused():
    with (
        patch("asyncio.open_connection", AsyncMock(side_effect=ConnectionRefusedError)),
        pytest.raises(PrinterCommandError, match="ConnectionRefusedError"),
    ):
        await async_send_raw("10.0.0.5", b"data")


async def test_send_raw_timeout():
    async def _hang(*_args):
        await asyncio.sleep(10)

    with (
        patch.object(maintenance, "_TIMEOUT", 0.01),
        patch("asyncio.open_connection", _hang),
        pytest.raises(PrinterCommandError, match="timed out"),
    ):
        await async_send_raw("10.0.0.5", b"data")


async def test_print_nozzle_check_sends_job():
    with patch(
        "custom_components.epson_workforce.maintenance.async_send_raw"
    ) as send_raw:
        await async_print_nozzle_check("10.0.0.5")
    send_raw.assert_awaited_once_with("10.0.0.5", EXPECTED_NOZZLE_CHECK_JOB)
