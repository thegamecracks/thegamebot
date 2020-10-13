"""A database for storing user IDs.

Table dependencies:
    None
"""
from . import database as db

TABLE_USERS = """
CREATE TABLE IF NOT EXISTS Users (
    id INTEGER UNIQUE
             NOT NULL
             PRIMARY KEY
);
"""


class UserDatabase(db.Database):
    "Provide an interface to a database with a Users table."

    async def has_user(self, user_id: int):
        "Test if a user_id exists in the database."
        return await self.get_user(user_id) is not None

    async def add_user(self, user_id: int):
        """Add a user to the database if the user does not exist.

        user_id is not escaped.

        """
        if not await self.has_user(user_id):
            await self.add_row('Users', {'id': user_id})

    async def get_user(self, user_id: int, *, as_Row=True):
        """Get a user record from the database.

        If the user is not found, returns None.

        user_id is not escaped.

        """
        return await self.get_one(
            'Users', where=f'id={user_id}', as_Row=as_Row)

    async def remove_user(self, user_id: int):
        """Remove a user from the database.

        user_id is not escaped.

        """
        await self.delete_rows('Users', where=f'id={user_id}')


def setup(connection):
    "Set up the Users table for a sqlite3 connection."
    with connection as conn:
        conn.execute(TABLE_USERS)
