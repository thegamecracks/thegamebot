import datetime

import aiosqlite


class Database:
    """Provide a higher-level interface to a database.

    Methods:
        add_row(table, row)
        delete_rows(table, *, where)
        get_rows(table, *columns, where=None, as_row=True)
        update_rows(table, row, *, where)

        vacuum()

        row_to_dict(Row)

    """
    __slots__ = ['path', 'last_change']

    PRAGMAS = 'PRAGMA foreign_keys = 1'

    def __init__(self, path):
        self.path = path
        self.set_last_change(datetime.datetime.now(), table=None)

    def __repr__(self):
        return '{}({!r})'.format(self.__class__.__name__, self.path)

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
        async with aiosqlite.connect(self.path) as db:
            await db.execute(self.PRAGMAS)
            c = await db.cursor()
            await c.execute(
                f'INSERT INTO {table} ({keys}) VALUES ({placeholders})',
                values
            )
            last_row_id = c.lastrowid
            await db.commit()

        self.set_last_change(datetime.datetime.now(), table)

        return last_row_id

    async def delete_rows(self, table: str, *, where: str, pop=False):
        """Delete one or more rows from a table.

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

        async with aiosqlite.connect(self.path) as db:
            await db.execute(self.PRAGMAS)
            await db.execute(f'DELETE FROM {table} WHERE {where}')
            await db.commit()

        self.set_last_change(datetime.datetime.now(), table)

        if pop:
            return rows

    async def get_one(self, table: str, *, where: str = '1', as_row=True):
        """Get one row from a table.

        If as_row, rows will be returned as aiosqlite.Row objects.
        Otherwise, rows are returned as tuples.

        Returns:
            aiosqlite.Row
            tuple
            None: if no row is found.

        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(self.PRAGMAS)
            if as_row:
                db.row_factory = aiosqlite.Row

            c = await db.execute(f'SELECT * FROM {table} WHERE {where}')

            row = await c.fetchone()
            await c.close()

        return row

    async def get_rows(self, table: str, *, where: str = '1', as_row=True):
        """Get a list of rows from a table.

        Args:
            table (str)
            where (Optional[str]):
                An optional parameter specifying a condition.
                By default, returns all rows in the table.
            as_row (bool):
                If True, rows will be returned as aiosqlite.Row objects.
                Otherwise, rows are returned as tuples.

        Returns:
            List[aiosqlite.Row]
            List[tuple]

        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(self.PRAGMAS)
            if as_row:
                db.row_factory = aiosqlite.Row

            c = await db.execute(f'SELECT * FROM {table} WHERE {where}')

            rows = await c.fetchall()
            await c.close()
        return rows

    async def update_rows(self, table: str, row: dict, *, where: str):
        """Update one or more rows in a table."""

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
        async with aiosqlite.connect(self.path) as db:
            await db.execute(self.PRAGMAS)
            await db.execute(
                f'UPDATE {table} SET {keys} WHERE {where}',
                values
            )
            await db.commit()

        self.set_last_change(datetime.datetime.now(), table)

    async def vacuum(self):
        """Vacuum the database."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute('VACUUM')

    async def yield_rows(
            self, table: str, *, where: str = '1', as_row=True):
        """Yield a list of rows from a table.

        Args:
            table (str)
            where (Optional[str]):
                An optional parameter specifying a condition.
                By default, yields all rows in the table.
            as_row (bool):
                If True, rows will be returned as aiosqlite.Row objects.
                Otherwise, rows are returned as tuples.

        Yields:
            List[aiosqlite.Row]
            List[tuple]

        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(self.PRAGMAS)
            if as_row:
                db.row_factory = aiosqlite.Row

            c = await db.execute(f'SELECT * FROM {table} WHERE {where}')

            async for row in c:
                yield row
            await c.close()

    @staticmethod
    def row_to_dict(row):
        """Convert an aiosqlite.Row into a dictionary."""
        d = {}
        for k, v in zip(row.keys(), row):
            d[k] = v
        return d
