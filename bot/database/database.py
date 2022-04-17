#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import dataclasses
import os.path
import sqlite3
from typing import AsyncGenerator, Tuple

import asqlite


class AsyncRLock(asyncio.Lock):
    """An asynchronous reentrant lock."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._locking_task: asyncio.Task | None = None
        self._hold_count = 0

    async def acquire(self) -> bool:
        current_task = asyncio.current_task()

        if current_task != self._locking_task:
            await super().acquire()
            self._locking_task = current_task

        self._hold_count += 1
        return True

    def release(self):
        if self._hold_count > 0:
            self._hold_count -= 1
            if self._hold_count == 0:
                super().release()
                self._locking_task = None
        else:
            super().release()  # allow asyncio.Lock to raise RuntimeError


class ConnectorProtocol:
    conn: asqlite.Connection | asqlite._ContextManagerMixin
    lock: asyncio.Lock

    async def __aenter__(self) -> asqlite.Connection:
        raise NotImplementedError

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError


@dataclasses.dataclass
class Connector(ConnectorProtocol):
    """An object providing a context manager for acquiring
    and releasing the lock to the underlying connection.
    Returned by ConnectionPool.get_connector().
    """
    conn: asqlite.Connection | asqlite._ContextManagerMixin = dataclasses.field(hash=False)
    lock: asyncio.Lock

    # def __await__(self):
    #     if self.writing:
    #         raise ValueError('Cannot directly access a writing connection')
    #     yield self.conn

    async def __aenter__(self):
        if isinstance(self.conn, asqlite._ContextManagerMixin):
            # Finish the connection
            self.conn = await self.conn  # type: ignore

        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class LockingConnector(ConnectorProtocol):
    def __init__(self, connector: Connector):
        self._connector = connector

    @property
    def conn(self):
        return self._connector.conn

    @property
    def lock(self):
        return self._connector.lock

    async def __aenter__(self):
        await self.lock.acquire()
        return await self._connector.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()


class ConnectionPool:
    """A pool of connections to different databases.

    Once entered, use the get_connector() method to obtain Connector objects.

    Usage:
        >>> pool = ConnectionPool()
        >>> async with pool:
        ...     connector = pool.get_connector('foo.db', writing=True)
        ...     async with connector as conn:
        ...         await conn.execute('CREATE TABLE ...')

    """
    __slots__ = ('_connections', '_running')

    def __init__(self):
        self._connections: dict[str, Connector] = {}
        self._running = False

    def get_connector(self, path, *, writing: bool) -> ConnectorProtocol:
        if not self._running:
            raise RuntimeError('Cannot connect when pool is closed')

        path = os.path.abspath(path)

        connector = self._connections.get(path)
        if connector is None:
            connector = Connector(
                asqlite.connect(
                    # detect_types will allow custom data types to be converted
                    # such as DATE and TIMESTAMP
                    # https://docs.python.org/3/library/sqlite3.html#default-adapters-and-converters
                    path, detect_types=(
                        sqlite3.PARSE_DECLTYPES
                        | sqlite3.PARSE_COLNAMES
                    )
                ),
                AsyncRLock()
            )
            self._connections[path] = connector

        if writing:
            return LockingConnector(connector)
        return connector

    async def __aenter__(self):
        self._running = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for connector in self._connections.values():
            await connector.conn.close()
        self._connections.clear()
        self._running = False


class Database:
    """Provide a higher-level interface to a database.

    Methods:
        add_row(table, row)
        delete_rows(table, *, where)
        get_one(table, *, where, as_row=True)
        get_rows(table, *, where, as_row=True)
        update_rows(table, row, *, where)
        yield_rows(table, *, where)

        vacuum()

    """
    __slots__ = ('dbpool', 'path')

    TABLE_SETUP = ''

    def __init__(self, dbpool: ConnectionPool, path: str):
        self.dbpool = dbpool
        self.path = path

    def __repr__(self):
        return '{}({!r})'.format(self.__class__.__name__, self.path)

    def connect(self, *, writing=False) -> ConnectorProtocol:
        """Create a connection to the database.

        This requires the bot's connection pool to be running.

        Usage::
            >>> pool = ConnectionPool()
            >>> database = Database(pool, 'foo.db')
            >>> async with pool:
            ...     async with database.connect() as conn:
            ...         await conn.execute(...)

        Caution: when using a writing connection, avoid the use of
        other writing methods in this class or nested writing connections
        except when they are called within the same :class:`asyncio.Task`.
        Attempting to wait on another task to acquire the lock while the
        current task has the lock acquired will result in a deadlock.

        :param writing:
            If writing, the underlying connector lock is acquired before
            allowing access to the connection. This prevents attempts to
            concurrently write to the database which may result in mixing
            of transactions.
        :returns:
            A connector that can be opened with `async with` to retrieve
            an :class:`asqlite.Connection` object.
        :raises RuntimeError: The connection pool is closed.

        """
        return self.dbpool.get_connector(self.path, writing=writing)

    async def setup_table(self, conn):
        await conn.executescript(self.TABLE_SETUP)

    async def add_row(self, table: str, row: dict, *, ignore=False) -> int:
        """Add a row to a table.

        :param table: The table name to insert into.
            This should only come from a trusted source.
        :param row: A dictionary of values to add.
        :param ignore:
            If True, any conflicts that occur when inserting will be ignored.
            Note that the last row id will not be updated in this case.
        :returns: The last row id of the query.

        """
        keys, placeholders, values = self.placeholder_insert(row)
        async with self.connect(writing=True) as conn:
            async with conn.cursor() as c:
                insert = 'INSERT' + ' OR IGNORE' * ignore
                await c.execute(
                    f'{insert} INTO {table} ({keys}) VALUES ({placeholders})',
                    *values
                )
                return c._cursor.lastrowid

    async def delete_rows(self, table: str, where: dict) -> int:
        """Delete rows matching a dictionary of values.

        Column names are trusted to be safe.

        :param table: The table name to delete from.
            This should only come from a trusted source.
        :param where: A dictionary of values to match.
        :returns: The number of rows that were deleted.

        """
        keys, values = self.escape_row(where, ' AND ')
        async with self.connect(writing=True) as conn:
            async with conn.cursor() as c:
                await c.execute(f'DELETE FROM {table} WHERE {keys}', *values)
                return c._cursor.rowcount

    def _get_rows_query(
            self, table: str, *columns: str,
            where: dict = None, limit: int = 0):
        column_keys = ', '.join(columns) if columns else '*'

        keys, values = self.escape_row(where or {}, ' AND ')
        where_str = f' WHERE {keys}' * bool(keys)
        limit = f' LIMIT {limit:d}' * bool(limit)

        query = f'SELECT {column_keys} FROM {table}{where_str}{limit}'

        return query, values

    async def _get_rows(
            self, table: str, *columns: str,
            where: dict = None, limit: int = 0):
        query, values = self._get_rows_query(
            table, *columns, where=where, limit=limit)

        async with self.connect() as conn:
            async with conn.execute(query, *values) as c:
                return await c.fetchall()

    async def get_rows(
        self, table: str, *columns: str, where: dict = None
    ) -> list[sqlite3.Row]:
        """Get rows from a table.

        :param table: The table name to select from.
            This should only come from a trusted source.
        :param columns: The columns to extract.
            If no columns are provided, returns all columns.
            This should only come from a trusted source.
        :param where: An optional dictionary of values to match.
        :returns: A list of rows that were selected.

        """
        return await self._get_rows(table, *columns, where=where)

    async def get_one(
        self, table: str, *columns: str, where: dict = None
    ) -> sqlite3.Row | None:
        """Get one row from a table.

        Column names are trusted to be safe.

        :param table: The table name to select from.
            This should only come from a trusted source.
        :param columns: The columns to extract.
            If no columns are provided, returns all columns.
            This should only come from a trusted source.
        :param where: A dictionary of values to match.
        :returns: The row that was selected or `None` if not found.

        """
        rows = await self._get_rows(table, *columns, where=where, limit=1)
        return rows[0] if rows else None

    async def update_rows(self, table: str, row: dict, *, where: dict) -> int:
        """Update rows with new values.

        :param table: The table name to update.
            This should only come from a trusted source.
        :param row: A dictionary of new values to update.
            The column names should only come from a trusted source.
        :param where: A dictionary of values to match.
        :returns: The number of rows that were updated.

        """
        row_keys, row_values = self.escape_row(row, ', ', use_assignment=True)
        where_keys, where_values = self.escape_row(where, ' AND ')

        async with self.connect(writing=True) as conn:
            async with conn.cursor() as c:
                await c.execute(
                    f'UPDATE {table} SET {row_keys} WHERE {where_keys}',
                    *(row_values + where_values)
                )
                return c._cursor.rowcount

    async def yield_rows(
        self, table: str, *columns: str, where: dict = None
    ) -> AsyncGenerator[sqlite3.Row, None]:
        """Yield rows from a table.

        :param table: The table name to select from.
            This should only come from a trusted source.
        :param columns: The columns to extract.
            If no columns are provided, returns all columns.
            This should only come from a trusted source.
        :param where: A dictionary of values to match.
        :returns: An async generator yielding :class:`sqlite3.Row` objects.

        """
        query, values = self._get_rows_query(table, *columns, where=where)

        async with self.connect() as conn:
            async with conn.execute(query, *values) as c:
                while row := await c.fetchone():
                    yield row

    async def vacuum(self):
        """Vacuum the database."""
        async with self.connect(writing=True) as conn:
            await conn.execute('VACUUM')

    @staticmethod
    def placeholder_insert(row: dict) -> Tuple[str, str, list]:
        """Return the column keys, placeholders, and values for a row.

        Example:
            >>> keys, placeholders, values = placeholder_insert(row)
            >>> await cursor.execute(
            ...     f'INSERT INTO {table} ({keys}) VALUES ({placeholders})',
            ...     values
            ... )

        """
        placeholders = ', '.join(['?'] * len(row))
        keys, values = [], []
        for k, v in row.items():
            keys.append(k)
            values.append(v)
        keys = ', '.join(keys)
        return keys, placeholders, values

    @staticmethod
    def escape_row(row: dict, sep: str, *, use_assignment=False) -> Tuple[str, list]:
        """Turn a dictionary into placeholders and values.

        Example usage::

            >>> keys, values = Database.escape_row(row, ', ')
            >>> await conn.execute(
            ...     f'UPDATE {table} SET {keys}',
            ...     values
            ... )

        :param row: The row to convert into a query.
        :param sep: The operator separating each key/value pair, e.g. `' AND '`.
        :param use_assignment:
            If True, uses the "=" operator, suitable for UPDATE queries.
            Else, uses the "IS" operator which will match nulls correctly.
        :returns: A string of placeholders for the WHERE clause
            along with a list of values for each placeholder.

        """
        op = ' = ' if use_assignment else ' IS '
        keys, values = [], []
        for k, v in row.items():
            keys.append(k)
            values.append(v)
        keys = sep.join([f'{k}{op}?' for k in row])
        return keys, values

    @classmethod
    def create_where(cls, row: dict) -> str:
        """Create a WHERE string from a row."""
        row = cls.remove_none(row.copy())
        if not row:
            return '1'
        return ' AND '.join([f'{k}={v}' for k, v in row.items()])

    @staticmethod
    def remove_none(row: dict) -> dict:
        """Remove None values from a dictionary."""
        invalid = [k for k, v in row.items() if v is None]
        for k in invalid:
            del row[k]
        return row
