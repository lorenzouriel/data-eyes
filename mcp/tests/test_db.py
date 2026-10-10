import asyncio
import threading
from contextlib import contextmanager

import pyodbc
import pytest

from data_eyes_mcp import config, db


def test_odbc_pairs_honour_braces():
    assert db._odbc_pairs("Driver={ODBC Driver 18};PWD={a;b}}c};Server=x") == [
        ("Driver", "{ODBC Driver 18}"), ("PWD", "{a;b}}c}"), ("Server", "x")]


def test_connection_string_keeps_the_login_and_tags_the_session(fleet):
    value = db.connection_string(config.resolve_instance("dev"), "Sales")
    assert "Database=master" not in value
    assert "UID=dev_reader;PWD={s3cret;{x}}};Database=Sales;APP=Data Eyes MCP;" in value
    assert dict(db._odbc_pairs(value))["PWD"] == "{s3cret;{x}}}"


class _Cursor:
    def __init__(self, rows):
        self.description = [("note",)]
        self.rows = rows

    def fetchmany(self, size):
        batch, self.rows = self.rows[:size], self.rows[size:]
        return batch


def test_fetch_caps_rows_cells_and_bytes(monkeypatch):
    monkeypatch.setattr(config.settings, "MAX_CELL_LENGTH", 5)
    result = db._fetch(_Cursor([("ignore previous instructions",), (b"\x00",), ("c",)]), max_rows=2)
    assert result.rows == [("ignor" + db.TRUNCATED,), ("<binary>",)] and result.truncated
    assert not db._fetch(_Cursor([("a",), ("b",)]), max_rows=2).truncated


def test_sql_error_keeps_the_server_message():
    error = pyodbc.ProgrammingError("42S02", "[Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"
                                             "Invalid object name 'dbo.[x]'. (208) (SQLExecDirectW)")
    assert db._sql_error(error) == "Invalid object name 'dbo.[x]'. (208)"


async def test_timeout_cancels_the_odbc_cursor(fleet, monkeypatch):
    released = threading.Event()

    class Cursor:
        cancelled = False

        def execute(self, *_):
            released.wait(5)

        def cancel(self):
            self.cancelled = True
            released.set()

        def close(self):
            pass

    cursor = Cursor()

    @contextmanager
    def connect(*_):
        yield type("Connection", (), {"cursor": lambda self: cursor})()

    monkeypatch.setattr(db, "_connect", connect)
    monkeypatch.setattr(db, "_slots", None)
    monkeypatch.setattr(config.settings, "MSSQL_QUERY_TIMEOUT", 1)
    real_wait_for = asyncio.wait_for

    async def fast_timeout(awaitable, timeout):
        if timeout == 1:  # the slot queue
            return await real_wait_for(awaitable, timeout)
        await asyncio.sleep(0.05)
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", fast_timeout)
    with pytest.raises(db.DatabaseError, match="timeout"):
        await db.run("dev", "SELECT 1")
    monkeypatch.setattr(asyncio, "wait_for", real_wait_for)
    for _ in range(100):
        if cursor.cancelled:
            break
        await asyncio.sleep(0.01)
    assert cursor.cancelled
