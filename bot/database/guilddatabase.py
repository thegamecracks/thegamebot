"""A database for storing guild IDs.

Table dependencies:
    None
"""
from . import database as db


class GuildDatabase(db.Database):
    """Provide an interface to a database with a guilds table."""

    TABLE_NAME = 'Guilds'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY NOT NULL
    );
    """

    async def add_guild(self, guild_id: int):
        """Add a guild to the database if the guild does not exist."""
        guild_id = int(guild_id)
        if await self.get_guild(guild_id) is None:
            return await self.add_row(self.TABLE_NAME, {'id': guild_id})

    async def delete_guild(self, guild_id: int):
        """Delete a guild from the database."""
        guild_id = int(guild_id)
        return await self.delete_rows(self.TABLE_NAME, {'id': guild_id})

    async def get_guild(self, guild_id: int):
        """Get a guild record from the database.

        If the guild is not found, returns None.

        """
        guild_id = int(guild_id)
        return await self.get_one(self.TABLE_NAME, where={'id': guild_id})
