"""A database for the Irish Squad server.

This stores its own users.
"""
from . import database as db
from . import userdatabase as user_db

TABLE_USERS = """
CREATE TABLE IF NOT EXISTS Users (
    id INTEGER UNIQUE
             NOT NULL
             PRIMARY KEY
);
"""
TABLE_CHARGES = """
CREATE TABLE IF NOT EXISTS Charges (
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES Users(id)
        ON DELETE CASCADE
)"""


class ChargeDatabase(user_db.UserDatabase):
    """Provide an interface to the Charges table."""

    async def add_charges(self, user_id: int, amount: int, *, add_user=False):
        """Add charges for a user.

        Args:
            user_id (int)
            amount (int)
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        if add_user:
            await self.add_user(user_id)

        charges = await self.get_charges(user_id)

        return await self.update_rows(
            'Charges',
            {'amount': charges + amount},
            where=f'user_id={user_id}'
        )

    async def delete_charges(self, user_id: int):
        """Delete a user's charges entry."""
        await self.delete_rows('Charges', where=f'note_id={note_id}')

    async def subtract_charges(self, user_id: int, amount: int,
                               *, add_user=False):
        """Subtract charges from a user.

        Note that this has no restraints; amount can become negative.

        Args:
            user_id (int)
            amount (int)
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        if add_user:
            await self.add_user(user_id)

        charges = await self.get_charges(user_id)

        return await self.update_rows(
            'Charges',
            {'amount': charges - amount},
            where=f'user_id={user_id}'
        )

    async def get_charges(self, user_id: int, add_user=True):
        """Get the number of charges a user has.

        Args:
            user_id (int): The id of the user to get notes from.
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        if add_user:
            await self.add_user(user_id)

        row = await self.get_one('Charges', where=f'user_id={user_id}')
        if row is None:
            if not await self.has_user(user_id):
                raise ValueError(
                    f'User {user_id!r} does not exist in the database')
            else:
                await self.add_row('Charges', {'user_id': user_id})
                row = await self.get_one('Charges', where=f'user_id={user_id}')
        return row['amount']


class IrishDatabase(ChargeDatabase):
    """Provide an interface to the Irish Squad's database."""


def setup(connection):
    "Set up the Users table for a sqlite3 connection."
    with connection as conn:
        conn.execute(TABLE_USERS)
        conn.execute(TABLE_CHARGES)
