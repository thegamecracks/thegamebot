"""A database for storing user IDs.

Table dependencies:
    None
"""
from . import database as db


class UserDatabase(db.Database):
    """Provide an interface to a database with a Users table."""

    TABLE_NAME = 'Users'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY NOT NULL
    );
    """

    async def add_user(self, user_id: int):
        """Add a user to the database if the user does not exist."""
        user_id = int(user_id)

        if await self.get_user(user_id) is None:
            return await self.add_row(self.TABLE_NAME, {'id': user_id})

    async def delete_user(self, user_id: int):
        """Delete a user from the database."""
        user_id = int(user_id)

        # async with self.connect(writing=True) as conn:
        #     await conn.execute(
        #         f'DELETE FROM {self.TABLE_NAME} WHERE id=?', (user_id,))
        #     await conn.commit()

        return await self.delete_rows(self.TABLE_NAME, {'id': user_id})

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
