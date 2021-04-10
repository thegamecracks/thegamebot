import asyncio
import os.path
from typing import Tuple

import aiosqlite


class AsyncConnection:
    """An outer context manager for an aiosqlite Connection.

    This does NOT support using nested with-statements with the same object.

    When using connection locks with `writing=True`, be careful not
    to attempt making several connections to the same database in the
    same task without unlocking, which would otherwise result in a deadlock:
        >>> async with AsyncConnection('db', writing=True) as conn1:
        ...     async with AsyncConnection('db', writing=True) as conn2:
        ...         pass  # deadlock

    Args:
        path (str): The path to the database.
        script (str): A script to execute upon entering the connection.
            Exceptions that occur will be propagated.
        writing (bool): If True, uses a lock for connections
            with the same path so that only one writing connection
            can be running at once. This prevents the error
            `sqlite3.OperationalError: database is locked`
            from occurring when a writing connection is blocked
            for over 5 seconds.

    """
    __slots__ = ('conn', 'path', 'script', 'writing')

    _write_locks = {}  # path: Lock
    # NOTE: this can grow indefinitely

    def __init__(self, path, script, *, writing=False):
        self.path = path
        self.script = script
        self.writing = writing
        self.conn = None

    def __repr__(self):
        return '{0.__class__.__name__}({0.path})'

    def _get_write_lock(self):
        path = os.path.abspath(self.path)
        lock = self._write_locks.get(path)
        if lock is None:
            lock = asyncio.Lock()
            self._write_locks[path] = lock
        return lock

    async def __aenter__(self):
        if self.writing:
            await self._get_write_lock().acquire()

        self.conn = aiosqlite.connect(self.path)
        conn = self.conn

        await conn.__aenter__()

        conn.row_factory = aiosqlite.Row

        try:
            await conn.executescript(self.script)
        except Exception as e:
            await self.__aexit__(type(e), e, e.__traceback__)
            raise

        return conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.conn.__aexit__(exc_type, exc_val, exc_tb)
        self.conn = None
        if self.writing:
            self._get_write_lock().release()


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

    PRAGMAS = 'PRAGMA foreign_keys = 1;'
    TABLE_SETUP = ''

    def __init__(self, bot, path):
        self.bot = bot
        self.path = path

    def __repr__(self):
        return '{}({!r})'.format(self.__class__.__name__, self.path)

    def connect(self, *, writing=False):
        """Create an AsyncConnection context manager."""
        return AsyncConnection(self.path, self.PRAGMAS, writing=writing)

    async def setup_table(self, conn):
        await conn.executescript(self.TABLE_SETUP)

    async def add_row(self, table: str, row: dict):
        """Add a row to a table.

        Args:
            table (str): The table name to insert into.
                Should only come from a programmatic source.
            row (dict): A dictionary of values to add.

        Returns:
            int: The last row id.

        """
        keys, placeholders, values = self.placeholder_insert(row)
        async with self.connect(writing=True) as conn:
            rowid = await conn.execute_insert(
                f'INSERT INTO {table} ({keys}) VALUES ({placeholders})',
                values
            )
            await conn.commit()
        return rowid

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
            List[aiosqlite.Row]

        """
        keys, values = self.escape_row(where, ' AND ')
        rows = None
        async with self.connect(writing=True) as conn:
            if pop:
                async with conn.execute(
                        f'SELECT * FROM {table} WHERE {keys}', values) as c:
                    rows = await c.fetchall()

            await conn.execute(
                f'DELETE FROM {table} WHERE {keys}',
                values
            )
            await conn.commit()
        return rows

    def _get_rows_query(self, table: str, *columns: str, where: dict = None):
        column_keys = ', '.join(columns) if columns else '*'

        values = None
        where_str = ''
        if where is not None:
            keys, values = self.escape_row(where, ' AND ')
            where_str = f' WHERE {keys}'

        query = f'SELECT {column_keys} FROM {table}{where_str}'

        return query, values

    async def _get_rows(self, table: str, *columns: str, where: dict = None, one: bool):
        query, values = self._get_rows_query(table, *columns, where=where)

        async with self.connect() as conn:
            if one:
                async with conn.execute(query, values) as c:
                    return await c.fetchone()
            return await conn.execute_fetchall(query, values)

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
            List[aiosqlite.Row]
            None

        """
        return await self._get_rows(table, *columns, where=where, one=False)

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
            aiosqlite.Row
            None

        """
        return await self._get_rows(table, *columns, where=where, one=True)

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
            List[aiosqlite.Row]
            None

        """
        row_keys, row_values = self.escape_row(row, ', ')
        where_keys, where_values = self.escape_row(where, ' AND ')
        rows = None

        async with self.connect(writing=True) as conn:
            if pop:
                async with conn.execute(
                        f'SELECT * FROM {table} WHERE {where_keys}',
                        where_values) as c:
                    rows = await c.fetchall()

            await conn.execute(
                f'UPDATE {table} SET {row_keys} WHERE {where_keys}',
                row_values + where_values
            )
            await conn.commit()

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
            aiosqlite.Row

        """
        query, values = self._get_rows_query(table, *columns, where=where)

        async with self.connect() as conn:
            async with conn.execute(query, values) as c:
                async for row in c:
                    yield row

    async def vacuum(self):
        """Vacuum the database."""
        async with self.connect() as db:
            await db.execute('VACUUM')

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
