"""A database for the Irish Squad server.

This stores its own users.
"""
from . import database as db
from . import userdatabase as user_db

TABLE_BLACKJACK = """
CREATE TABLE IF NOT EXISTS Blackjack (
    user_id INTEGER NOT NULL,
    played INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES Users(id)
        ON DELETE CASCADE
)"""


class BlackjackDatabase(user_db.UserDatabase):
    """Provide an interface to the Blackjack table."""

    async def change(
            self, column: str, user_id: int, number: int, *, add_user=True):
        """Add or subtract X from a column.

        Note that this has no restraints.

        Args:
            column (str): The name of the column to change.
            user_id (int)
            number (int): The number of losses to add. Can be negative.
            add_user (bool)

        """
        user_id = int(user_id)

        row = await self.get_blackjack_row(user_id, add_user=add_user)

        return await self.update_rows(
            'Blackjack',
            {column: row[column] + number},
            where=f'user_id={user_id}'
        )

    async def delete_data(self, user_id: int):
        """Delete a user's blackjack data."""
        user_id = int(user_id)
        await self.delete_rows('Blackjack', where=f'user_id={user_id}')

    async def get_blackjack_row(self, user_id: int, *, add_user=True):
        user_id = int(user_id)

        if add_user:
            await self.add_user(user_id)

        row = await self.get_one('Blackjack', where=f'user_id={user_id}')
        if row is None:
            if not await self.has_user(user_id):
                raise ValueError(
                    f'User {user_id!r} does not exist in the database')
            else:
                await self.add_row('Blackjack', {'user_id': user_id})
                row = await self.get_one('Blackjack', where=f'user_id={user_id}')
        return row


class GameDatabase(db.Database):
    """Provide an interface to the various tables available."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blackjack = BlackjackDatabase(*args, **kwargs)

    async def delete_data(self, user_id: int):
        """Delete a user's data for all games."""
        user_id = int(user_id)

        await self.blackjack.delete_data(user_id)


def setup(connection):
    "Set up the game tables with a sqlite3 connection."
    with connection as conn:
        conn.execute(TABLE_BLACKJACK)
