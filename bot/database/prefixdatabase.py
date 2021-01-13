"""A database for storing user's prefixes.

Table dependencies:
    Users
"""
from . import guilddatabase as guild_db
from bot import settings

TABLE_PREFIXES = """
CREATE TABLE IF NOT EXISTS Prefixes (
    guild_id INTEGER NOT NULL,
    prefix TEXT NOT NULL,
    FOREIGN KEY(guild_id) REFERENCES Guilds(id)
        ON DELETE CASCADE
);
"""


class PrefixDatabase(guild_db.GuildDatabase):
    """Provide an interface to a GuildDatabase with a Prefixes table."""

    __slots__ = ['prefix_cache']

    PREFIX_SIZE_LIMIT = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefix_cache = {}

    async def has_prefix(self, guild_id: int):
        """Test if a prefix for a guild exists in the database."""
        guild_id = int(guild_id)

        return await self.get_prefix(guild_id) is not None

    async def add_prefix(
            self, guild_id: int, prefix: str = None, *, add_guild=False):
        """Add a prefix for a guild.

        The prefix is constrained by PREFIX_SIZE_LIMIT.

        Args:
            guild_id (int)
            prefix (Optional[str]): The prefix to set the guild with.
                If no prefix is provided, uses default_prefix in settings.
            add_guild (bool):
                If True, automatically adds the guild_id to the Guilds table.
                Otherwise, the guild_id foreign key can be violated.

        """
        guild_id = int(guild_id)

        if prefix is None:
            prefix = settings.get_setting('default_prefix')

        if len(prefix) > self.PREFIX_SIZE_LIMIT:
            raise ValueError(
                f'Prefix cannot be over {self.PREFIX_SIZE_LIMIT:,} '
                'characters long.'
            )

        if add_guild:
            await self.add_guild(guild_id)

        if not await self.has_prefix(guild_id):
            result = await self.add_row(
                'Prefixes', {'guild_id': guild_id, 'prefix': prefix})

            self.prefix_cache[guild_id] = prefix

            return result

    async def delete_prefix(self, guild_id: int, pop=False):
        """Delete a prefix from a guild.

        guild_id is not escaped.

        Args:
            guild_id (int)
            pop (bool): If True, gets the prefixes before deleting them.

        Returns:
            None
            List[aiosqlite.Row]: A list of deleted entries if pop is True.

        """
        guild_id = int(guild_id)

        prefixes = await self.delete_rows(
            'Prefixes', where=f'guild_id={guild_id}', pop=pop)

        self.prefix_cache.pop(guild_id, None)

        return prefixes

    async def get_prefix(self, guild_id: int, *, as_row=True):
        """Get the prefix for a guild.

        guild_id is not escaped.

        Returns:
            str

        """
        guild_id = int(guild_id)

        prefix = self.prefix_cache.get(guild_id)
        if prefix is not None:
            return prefix

        query = await self.get_one(
            'Prefixes', where=f'guild_id={guild_id}', as_row=as_row)

        if query is None:
            return

        prefix = query['prefix']

        self.prefix_cache[guild_id] = prefix

        return prefix

    async def update_prefix(self, guild_id: int, prefix: str):
        """Update a prefix for a guild.

        The prefix is constrained by PREFIX_SIZE_LIMIT.

        """
        guild_id = int(guild_id)

        if len(prefix) > self.PREFIX_SIZE_LIMIT:
            raise ValueError(
                f'Prefix cannot be over {self.PREFIX_SIZE_LIMIT:,} '
                'characters long.'
            )

        await self.update_rows(
            'Prefixes', {'prefix': prefix}, where=f'guild_id={guild_id}')

        self.prefix_cache[guild_id] = prefix


def setup(connection):
    """Set up the prefixes table with a sqlite3 connection."""
    with connection as conn:
        conn.execute(TABLE_PREFIXES)
