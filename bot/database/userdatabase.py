"""A database for storing user IDs.

Table dependencies:
    None
"""
from typing import Optional

import pytz

from . import database as db


class UserDatabase(db.Database):
    """Provide an interface to a database with a Users table."""

    TABLE_NAME = 'Users'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY NOT NULL,
        timezone TEXT
    );
    """

    async def add_user(self, user_id: int, *, timezone: str = ''):
        """Add a user to the database if the user does not exist.

        Returns:
            int: The lastrowid returned by add_row().
            None: the row already exists.

        """
        user_id, timezone = int(user_id), str(timezone)

        if await self.get_user(user_id) is None:
            return await self.add_row(
                self.TABLE_NAME, {
                    'id': user_id,
                    'timezone': timezone
                }
            )

    async def delete_user(self, user_id: int):
        """Delete a user from the database."""
        user_id = int(user_id)

        # async with self.connect(writing=True) as conn:
        #     await conn.execute(
        #         f'DELETE FROM {self.TABLE_NAME} WHERE id=?', (user_id,))
        #     await conn.commit()

        return await self.delete_rows(self.TABLE_NAME, {'id': user_id})

    async def get_timezone(self, user_id: int) -> Optional[pytz.BaseTzInfo]:
        """Get the timezone of a given user.

        In the case that an invalid timezone is inserted into the database,
        this will nullify it before propagating the exception.

        If the user entry does not exist, this will not add the entry and
        return None.

        """
        user_id = int(user_id)

        async with self.connect() as conn:
            async with conn.execute(
                    f'SELECT timezone FROM {self.TABLE_NAME} WHERE id=?',
                    (user_id,)) as c:
                row = await c.fetchone()

        timezone = row['timezone'] if row is not None else None
        if timezone is None:
            return

        try:
            return pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await self.update_rows(self.TABLE_NAME, {'timezone': None},
                                   where={'id': user_id})
            raise

    async def get_user(self, user_id: int):
        """Get a user record from the database.

        If the user is not found, returns None.

        """
        user_id = int(user_id)

        # async with self.connect() as conn:
        #     async with await conn.execute(
        #             f'SELECT * FROM {self.TABLE_NAME} WHERE id=?',
        #             (user_id,)) as c:
        #         return await c.fetchone()

        return await self.get_one(self.TABLE_NAME, where={'id': user_id})
