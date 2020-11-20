import asyncio
import datetime

import aiosqlite


class Singleton(type):
    # https://stackoverflow.com/q/6760685
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class DatabaseConnection:
    """Provide an asynchronous connection to a database.

    To use a connection, use the context manager protocol:
        locked_conn = DatabaseConnection(':memory:')
        async with locked_conn as conn:
            # await conn.execute statements here

    """
    __slots__ = ['path', 'conn', 'lock']

    def __init__(self, path):
        self.path = path
        self.conn = None
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        await self.lock.acquire()
        self.conn = aiosqlite.connect(self.path)
        # Enter the context manager for conn
        await self.conn.__aenter__()
        # Enable foreign key checks
        # https://stackoverflow.com/q/29420910
        await self.conn.execute('PRAGMA foreign_keys = 1')
        return self.conn

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        await self.conn.__aexit__(exc_type, exc_value, exc_traceback)
        self.conn = None
        self.lock.release()

    def __repr__(self):
        return '{}({!r})'.format(
            self.__class__.__name__,
            self.path,
        )


class Database(metaclass=Singleton):
    """Provide a higher-level interface to a database.

    Methods:
        add_row(table, row)
        delete_rows(table, *, where)
        get_rows(table, *columns, where=None, as_Row=True)
        update_rows(table, row, *, where)

        vacuum()

        row_to_dict(Row)

    """
    # FIXME: using Singleton is probably a dumb way of making sure
    # caches of subclasses are preserved across instantiations;
    # why not just have dbsetup create all the instances?
    __slots__ = ['conn', 'last_change']

    def __init__(self, conn):
        """Create a Database with a DatabaseConnection."""
        self.conn = conn
        self.set_last_change(datetime.datetime.now(), table=None)

    def __repr__(self):
        return '{}({!r})'.format(self.__class__.__name__, self.conn)

    def set_last_change(self, when, table):
        self.last_change = {
            'when': when,
            'table': table
        }

    async def add_row(self, table: str, row: dict):
        """Add a row to a table.

        Returns the last row id that was added.

        """
        def create_keys(row: dict) -> (str, str, list):
            """Return the column placeholders and values for a row.

            NOTE: Designed to work without using the insertion order
            invariant of dict since Python 3.6.

            """
            placeholders = ', '.join(['?'] * len(row))
            keys, values = [], []
            for k, v in row.items():
                keys.append(k)
                values.append(v)
            keys = ', '.join(keys)
            return keys, placeholders, values

        keys, placeholders, values = create_keys(row)
        async with self.conn as conn:
            c = await conn.cursor()
            await c.execute(
                f'INSERT INTO {table} ({keys}) VALUES ({placeholders})',
                values
            )
            last_row_id = c.lastrowid
            await conn.commit()

        self.set_last_change(datetime.datetime.now(), table)

        return last_row_id

    async def delete_rows(self, table: str, *, where: str, pop=False):
        """Delete one or more rows from a table.

        This method requires a where parameter unlike get_rows.

        Args:
            table (str)
            where (str)
            pop (bool):
                If True, gets the rows and returns them before
                deleting the rows.

        Returns:
            None
            List[aiosqlite.Row]: A list of deleted entries if pop is True.

        """
        if pop:
            rows = await self.get_rows(table, where=where)

        async with self.conn as conn:
            await conn.execute(f'DELETE FROM {table} WHERE {where}')
            await conn.commit()

        self.set_last_change(datetime.datetime.now(), table)

        if pop:
            return rows

    async def get_one(self, table: str, *, where: str, as_Row=True):
        """Get one row from a table.

        If as_Row, rows will be returned as aiosqlite.Row objects.
        Otherwise, rows are returned as tuples.

        Returns:
            aiosqlite.Row
            tuple
            None: if no row is found.

        """
        async with self.conn as conn:
            if as_Row:
                conn.row_factory = aiosqlite.Row

            c = await conn.execute(f'SELECT * FROM {table} WHERE {where}')

            row = await c.fetchone()
            await c.close()

        return row

    async def get_rows(
            self, table: str, *, where: str = None, as_Row=True):
        """Get a list of rows from a table.

        Args:
            table (str)
            where (Optional[str]):
                An optional parameter specifying a filter.
                If left as None, returns all rows in the table.
            as_Row (bool):
                If True, rows will be returned as aiosqlite.Row objects.
                Otherwise, rows are returned as tuples.

        Returns:
            List[aiosqlite.Row]
            List[tuple]

        """
        async with self.conn as conn:
            if as_Row:
                conn.row_factory = aiosqlite.Row

            if where is not None:
                c = await conn.execute(f'SELECT * FROM {table} WHERE {where}')
            else:
                c = await conn.execute(f'SELECT * FROM {table}')

            rows = await c.fetchall()
            await c.close()
        return rows

    async def update_rows(self, table: str, row: dict, *, where: str):
        "Update one or more rows in a table."

        def create_placeholders(row: dict) -> (str, list):
            """Create the placeholders for setting keys.

            NOTE: Designed to work without using the insertion order
            invariant of dict since Python 3.6.

            """
            keys, values = [], []
            for k, v in row.items():
                keys.append(k)
                values.append(v)
            keys = ', '.join([f'{k}=?' for k in row])
            return keys, values

        keys, values = create_placeholders(row)
        async with self.conn as conn:
            await conn.execute(
                f'UPDATE {table} SET {keys} WHERE {where}',
                values
            )
            await conn.commit()

        self.set_last_change(datetime.datetime.now(), table)

    async def yield_rows(
            self, table: str, *, where: str = None, as_Row=True):
        """Yield a list of rows from a table.

        Args:
            table (str)
            where (Optional[str]):
                An optional parameter specifying a filter.
                If left as None, returns all rows in the table.
            as_Row (bool):
                If True, rows will be returned as aiosqlite.Row objects.
                Otherwise, rows are returned as tuples.

        Yields:
            List[aiosqlite.Row]
            List[tuple]

        """
        async with self.conn as conn:
            if as_Row:
                conn.row_factory = aiosqlite.Row

            if where is not None:
                c = await conn.execute(f'SELECT * FROM {table} WHERE {where}')
            else:
                c = await conn.execute(f'SELECT * FROM {table}')

            async for row in c:
                yield row
            await c.close()

    @classmethod
    def from_path(cls, path, *args, **kwargs):
        """Create a Database object along with a DatabaseConnection."""
        return cls(DatabaseConnection(path, *args, **kwargs))

    @staticmethod
    def row_to_dict(Row):
        "Convert a aiosqlite.Row into a dictionary."
        d = {}
        for k, v in zip(Row.keys(), Row):
            d[k] = v
        return d
