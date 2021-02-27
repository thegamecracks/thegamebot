"""A database for the Games cog.

Table dependencies:
    Users
"""
from . import database as db


class BlackjackDatabase(db.Database):
    """Provide an interface to the Blackjack table."""

    TABLE_NAME = 'Blackjack'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        user_id INTEGER NOT NULL,
        played INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        blackjacks INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES Users(id)
            ON DELETE CASCADE
    );
    """

    async def change(self, column: str, user_id: int, number: int):
        """Add or subtract X from a column.

        Note that this has no restraints.

        Automatically adds a row if it does not exist
        and the user already has an entry in the Users table.

        Args:
            column (str): The name of the column to change.
                This is trusted to be safe.
            user_id (int)
            number (int): The number of losses to add. Can be negative.

        """
        user_id = int(user_id)

        row = await self.get_blackjack_row(user_id)

        new = row[column] + number

        # async with self.connect() as conn:
        #     await conn.execute(
        #         f'UPDATE {self.TABLE_NAME} SET {column}=? WHERE user_id=?',
        #         (new, user_id)
        #     )
        #     await conn.commit()

        return await self.update_rows(
            self.TABLE_NAME, {column: new}, where={'user_id': user_id})

    async def delete_data(self, user_id: int):
        """Delete a user's blackjack data."""
        user_id = int(user_id)

        # async with self.connect() as conn:
        #     await conn.execute(
        #         f'DELETE FROM {self.TABLE_NAME} WHERE user_id=?',
        #         (user_id,)
        #     )
        #     await conn.commit()

        return await self.delete_rows(self.TABLE_NAME, {'user_id': user_id})

    async def get_blackjack_row(self, user_id: int):
        """Get the blackjack data for a user.

        Automatically adds a row if it already exists
        and the user already has an entry in the Users table.

        """
        async def get_row():
            return await self.get_one(
                self.TABLE_NAME, where={'user_id': user_id})

        user_id = int(user_id)

        row = await get_row()
        if row is None:
            await self.add_row('Blackjack', {'user_id': user_id})
            row = await get_row()
        return row


class GameDatabase(db.Database):
    """Provide an interface to the various tables available."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blackjack = BlackjackDatabase(*args, **kwargs)

    @property
    def TABLE_SETUP(self):
        return (
            self.blackjack.TABLE_SETUP,
        )

    async def delete_data(self, user_id: int):
        """Delete a user's data for all games."""
        user_id = int(user_id)

        await self.blackjack.delete_data(user_id)
