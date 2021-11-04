#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import dataclasses
import os.path
import sqlite3
from typing import Tuple

import asqlite


class ConnectorProtocol:
    conn: asqlite.Connection | asqlite._ContextManagerMixin
    lock: asyncio.Lock


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

    async def __aenter__(self) -> asqlite.Connection:
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
        self._connections = {}
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
                asyncio.Lock()
            )
            self._connections[path] = connector

        if writing:
            return LockingConnector(connector)
        return connector

    async def __aenter__(self):
        self._running = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for conn, lock in self._connections.values():
            await conn.close()
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
    __slots__ = ('bot', 'path')

    TABLE_SETUP = ''

    def __init__(self, bot, path):
        self.bot = bot
        self.path = path

    def __repr__(self):
        return '{}({!r})'.format(self.__class__.__name__, self.path)

    def connect(self, *, writing=False) -> Connector:
        """Create a connection to the database.
        This requires the bot's connection pool to be running.

        Usage:
            >>> database = Database(...)
            >>> async with database.connect() as conn:
            ...     await conn.execute(...)

        Raises:
            RuntimeError: The connection pool is closed.

        """
        return self.bot.dbpool.get_connector(self.path, writing=writing)

    async def setup_table(self, conn):
        await conn.executescript(self.TABLE_SETUP)

    async def add_row(self, table: str, row: dict, *, ignore=False) -> int:
        """Add a row to a table.

        Args:
            table (str): The table name to insert into.
                Should only come from a programmatic source.
            row (dict): A dictionary of values to add.
            ignore (bool): If True, any conflicts that occur when
                inserting will be ignored. Note that the lastrowid
                will not be updated if it is ignored.

        Returns:
            int: The last row id.

        """
        keys, placeholders, values = self.placeholder_insert(row)
        async with self.connect(writing=True) as conn:
            async with conn.cursor(transaction=True) as c:
                insert = 'INSERT' + ' OR IGNORE' * ignore
                await c.execute(
                    f'{insert} INTO {table} ({keys}) VALUES ({placeholders})',
                    *values
                )
                return c._cursor.lastrowid

    async def delete_rows(self, table: str, where: dict, *, pop=False):
        """Delete rows matching a dictionary of values.

        Column names are trusted to be safe.

        Args:
            table (str): The table name to delete from.
                Should only come from a programmatic source.
            where (dict): A dictionary of values to match.
            pop (bool): If True, return a list of the rows that were deleted.

        Returns:
            None
            List[sqlite3.Row]

        """
        keys, values = self.escape_row(where, ' AND ')
        rows = None
        async with self.connect(writing=True) as conn:
            async with conn.cursor(transaction=True) as c:
                if pop:
                    await c.execute(f'SELECT * FROM {table} WHERE {keys}', *values)
                    rows = await c.fetchall()

                if not pop or rows:
                    await c.execute(f'DELETE FROM {table} WHERE {keys}', *values)
        return rows

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

    async def get_rows(self, table: str, *columns: str, where: dict = None):
        """Get rows from a table.

        Column names are trusted to be safe.

        Args:
            table (str): The table name to select from.
                Should only come from a programmatic source.
            columns (str): The columns to extract.
                If no columns are provided, returns all columns.
            where (Optional[dict]): A dictionary of values to match.

        Returns:
            List[sqlite3.Row]
            None

        """
        return await self._get_rows(table, *columns, where=where)

    async def get_one(self, table: str, *columns: str, where: dict):
        """Get one row from a table.

        Column names are trusted to be safe.

        Args:
            table (str): The table name to select from.
                Should only come from a programmatic source.
            columns (str): The columns to extract.
                If no columns are provided, returns all columns.
            where (Optional[dict]): A dictionary of values to match.

        Returns:
            sqlite3.Row
            None

        """
        rows = await self._get_rows(table, *columns, where=where, limit=1)
        return rows[0] if rows else None

    async def update_rows(self, table: str, row: dict, *, where: dict, pop=False):
        """Update rows with new values.

        Column names are trusted to be safe.

        Args:
            table (str): The table name to update.
                Should only come from a programmatic source.
            row (dict): A dictionary of new values to update.
            where (dict): A dictionary of values to match.
            pop (bool): If True, returns the rows that were updated
                (before modification).

        Returns:
            List[sqlite3.Row]
            None

        """
        row_keys, row_values = self.escape_row(row, ', ')
        where_keys, where_values = self.escape_row(where, ' AND ')
        rows = None

        async with self.connect(writing=True) as conn:
            async with conn.cursor(transaction=True) as c:
                if pop:
                    await c.execute(
                        f'SELECT * FROM {table} WHERE {where_keys}',
                        *where_values
                    )
                    rows = await c.fetchall()

                await c.execute(
                    f'UPDATE {table} SET {row_keys} WHERE {where_keys}',
                    *(row_values + where_values)
                )

        return rows

    async def yield_rows(self, table: str, *columns: str, where: dict = None):
        """Yield rows from a table.

        Column names are trusted to be safe.

        Args:
            table (str): The table name to select from.
                Should only come from a programmatic source.
            columns (str): The columns to extract.
                If no columns are provided, returns all columns.
            where (Optional[dict]): A dictionary of values to match.

        Yields:
            sqlite3.Row

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
    def escape_row(row: dict, sep: str) -> Tuple[str, list]:
        """Turn a dictionary into placeholders and values.

        Example:
            >>> keys, values = escape_row(row)
            >>> await conn.execute(
            ...     f'UPDATE {table} SET {keys}',
            ...     values
            ... )

        Returns:
            Tuple[str, List[Any]]: The placeholders for the WHERE clause
                along with a list of values for each placeholder.

        """
        keys, values = [], []
        for k, v in row.items():
            keys.append(k)
            values.append(v)
        keys = sep.join([f'{k}=?' for k in row])
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
