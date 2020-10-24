"""A database for storing guild IDs.

Table dependencies:
    None
"""
from . import database as db

TABLE_GUILDS = """
CREATE TABLE IF NOT EXISTS Guilds (
    id INTEGER UNIQUE
             NOT NULL
             PRIMARY KEY
);
"""


class GuildDatabase(db.Database):
    "Provide an interface to a database with a guilds table."

    async def has_guild(self, guild_id: int):
        "Test if a guild_id exists in the database."
        return await self.get_guild(guild_id) is not None

    async def add_guild(self, guild_id: int):
        """Add a guild to the database if the guild does not exist.

        guild_id is not escaped.

        """
        if not await self.has_guild(guild_id):
            return await self.add_row('Guilds', {'id': guild_id})

    async def get_guild(self, guild_id: int, *, as_Row=True):
        """Get a guild record from the database.

        If the guild is not found, returns None.

        guild_id is not escaped.

        """
        return await self.get_one(
            'Guilds', where=f'id={guild_id}', as_Row=as_Row)

    async def remove_guild(self, guild_id: int):
        """Remove a guild from the database.

        guild_id is not escaped.

        """
        await self.delete_rows('Guilds', where=f'id={guild_id}')


def setup(connection):
    "Set up the guilds table for a sqlite3 connection."
    with connection as conn:
        conn.execute(TABLE_GUILDS)
