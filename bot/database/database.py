import asyncio
import sqlite3
import threading


class DatabaseConnection:
    """Provide a connection to a database safeguarding it with
    a threading lock.

    To create a connection, use the context manager protocol:
        locked_conn = DatabaseConnection(':memory:')
        with locked_conn as conn:
            # conn.execute statements here
        # conn automatically closes and lock is released

    """

    def __init__(self, database_path, blocking=True, timeout=-1):
        self.database_path = database_path
        self.blocking = blocking
        self.timeout = timeout
        self.lock = threading.Lock()
        self.conn = None

    def __enter__(self):
        if self.lock.acquire(self.blocking, self.timeout):
            self.conn = sqlite3.connect(self.database_path)
            # Enter the context manager for conn
            self.conn.__enter__()
            # Enable foreign key checks
            # https://stackoverflow.com/q/29420910
            self.conn.execute('PRAGMA foreign_keys = 1')
            return self.conn
        raise asyncio.TimeoutError(
            f'Timed out trying to connect to {self.database_path!r}')

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.conn.__exit__(exc_type, exc_value, exc_traceback)
        self.conn.close()
        self.conn = None
        self.lock.release()

    def __repr__(self):
        return '{}({!r}, blocking={!r}, timeout={!r})'.format(
            self.__class__.__name__,
            self.database_path,
            self.blocking,
            self.timeout
        )


class Database:
    """Provide a higher-level interface to a database.

    Methods:
        add_row(table, row)
        delete_rows(table, *, where)
        get_rows(table, *columns, where=None, as_Row=True)
        update_rows(table, row, *, where)

        vacuum()

        row_to_dict(Row)

    """
    def __init__(self, database_connection):
        """Create a Database with a DatabaseConnection.

        Use this to construct database interfaces sharing the same lock.

        """
        self.conn = database_connection

    def __repr__(self):
        return '{}({!r})'.format(self.__class__.__name__, self.conn)

    def add_row(self, table: str, row: dict):
        "Add a row to a table."

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
        with self.conn as conn:
            conn.execute(
                f'INSERT INTO {table} ({keys}) VALUES ({placeholders})',
                values
            )

    def delete_rows(self, table: str, *, where: str, pop=False):
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
            List[sqlite3.Row]: A list of deleted entries if pop is True.

        """
        if pop:
            rows = self.get_rows(table, where=where)

        with self.conn as conn:
            conn.execute(f'DELETE FROM {table} WHERE {where}')

        if pop:
            return rows

    def get_one(self, table: str, *, where: str, as_Row=True):
        """Get one row from a table.

        If as_Row, rows will be returned as sqlite3.Row objects.
        Otherwise, rows are returned as tuples.

        """
        with self.conn as conn:
            if as_Row:
                conn.row_factory = sqlite3.Row

            c = conn.cursor()
            c.execute(f'SELECT * FROM {table} WHERE {where}')

            row = c.fetchone()
            c.close()

        return row

    def get_rows(self, table: str, *, where: str = None, as_Row=True):
        """Get/yield a list of rows from a table.

        Args:
            table (str)
            where (Optional[str]):
                An optional parameter specifying a filter.
                If left as None, returns all rows in the table.
            as_Row (bool):
                If True, rows will be returned as sqlite3.Row objects.
                Otherwise, rows are returned as tuples.

        Returns:
            List[sqlite3.Row]
            List[tuple]

        """
        with self.conn as conn:
            if as_Row:
                conn.row_factory = sqlite3.Row

            c = conn.cursor()
            if where is not None:
                c.execute(f'SELECT * FROM {table} WHERE {where}')
            else:
                c.execute(f'SELECT * FROM {table}')

            rows = list(c)
            c.close()
            return rows

    def update_rows(self, table: str, row: dict, *, where: str):
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
        with self.conn as conn:
            conn.execute(
                f'UPDATE {table} SET {keys} WHERE {where}',
                values
            )

    @classmethod
    def from_path(cls, path, blocking=True, timeout=-1):
        """Create a Database object along with a DatabaseConnection."""
        return cls(DatabaseConnection(path, blocking, timeout))

    @staticmethod
    def row_to_dict(Row: sqlite3.Row):
        "Convert a sqlite3.Row into a dictionary."
        d = {}
        for k, v in zip(Row.keys(), Row):
            d[k] = v
        return d
