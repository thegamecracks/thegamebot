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
    """Provide an interface to a database with a Users table."""

    async def has_user(self, user_id: int):
        """Test if a user_id exists in the database."""
        user_id = int(user_id)

        return await self.get_user(user_id) is not None

    async def add_user(self, user_id: int):
        """Add a user to the database if the user does not exist."""
        user_id = int(user_id)

        if not await self.has_user(user_id):
            return await self.add_row('Users', {'id': user_id})

    async def get_user(self, user_id: int, *, as_row=True):
        """Get a user record from the database.

        If the user is not found, returns None.

        """
        user_id = int(user_id)

        return await self.get_one(
            'Users', where=f'id={user_id}', as_row=as_row)

    async def remove_user(self, user_id: int):
        """Remove a user from the database."""
        user_id = int(user_id)

        await self.delete_rows('Users', where=f'id={user_id}')


def setup(connection):
    """Set up the Users table with a sqlite3 connection."""
    with connection as conn:
        conn.execute(TABLE_USERS)
