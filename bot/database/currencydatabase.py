"""A database for storing user's notes.

Table dependencies:
    Guilds
    Users
"""
from . import database as db


class CurrencyDatabase(db.Database):
    """Provide an interface to a UserDatabase with a Currency table."""

    TABLE_NAME = 'Currency'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        cents INTEGER NOT NULL DEFAULT 0,
        CHECK (cents >= 0),
        PRIMARY KEY (guild_id, user_id),
        FOREIGN KEY(guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES Users(id)
            ON DELETE CASCADE
    );
    """

    async def add_entry(self, guild_id: int, user_id: int):
        """Add a row to the table if it does not exist and return the row.

        This also adds a user entry if needed.

        """
        async def get_row():
            return await self.get_one(self.TABLE_NAME, where=d)

        guild_id, user_id = int(guild_id), int(user_id)
        d = {'guild_id': guild_id, 'user_id': user_id}

        row = await get_row()
        if row is None:
            await self.bot.dbusers.add_user(user_id)
            await self.add_row(self.TABLE_NAME, d)
            row = await get_row()
        return row

    async def change_cents(
            self, guild_id: int, user_id: int, cents: int,
            *, keep_positive=False) -> int:
        """Change the number of cents a user has in a guild.

        Automatically adds an entry if the user does not have one.

        Returns the user's new cents.

        Args:
            guild_id (int)
            user_id (int)
            cents (int)
            keep_positive (bool): If True, sets the user's cents to 0
                if it would otherwise become negative.
                Otherwise, raises sqlite3.IntegrityError if the check fails.

        Raises:
            sqlite3.IntegrityError

        """
        guild_id, user_id, cents = int(guild_id), int(user_id), int(cents)

        new_cents = await self.get_cents(guild_id, user_id) + cents
        new_cents = max(0, new_cents) if keep_positive else new_cents

        await self.update_rows(
            self.TABLE_NAME,
            {'cents': new_cents},
            where={'guild_id': guild_id, 'user_id': user_id}
        )

        return new_cents

    async def exchange_cents(
            self, guild_id: int, user1: int, user2: int, cents: int):
        """Give some amount of money from the first user to the second user.

        Automatically adds entries if either user does not have one.

        Raises:
            sqlite3.IntegrityError

        """
        guild_id, cents = int(guild_id), int(cents)
        user1, user2 = int(user1), int(user2)

        await self.add_entry(guild_id, user1)
        await self.add_entry(guild_id, user2)

        async with self.connect(writing=True) as conn:
            await conn.execute(
                f'UPDATE {self.TABLE_NAME} SET cents = cents - ? '
                'WHERE guild_id=? AND user_id=?',
                (cents, guild_id, user1)
            )
            await conn.execute(
                f'UPDATE {self.TABLE_NAME} SET cents = cents + ? '
                'WHERE guild_id=? AND user_id=?',
                (cents, guild_id, user2)
            )
            await conn.commit()

    async def get_cents(self, guild_id: int, user_id: int) -> int:
        """Get a user's cents in a guild.

        Automatically adds an entry if the user does not have one.

        """
        guild_id, user_id = int(guild_id), int(user_id)
        return (await self.add_entry(guild_id, user_id))['cents']

    async def wipe(self, guild_id: int):
        """Wipe the economy for a guild."""
        guild_id = int(guild_id)
        await self.delete_rows(self.TABLE_NAME, {'guild_id': guild_id})
