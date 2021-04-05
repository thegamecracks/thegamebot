"""A database for storing user's prefixes.

Table dependencies:
    Users
"""
from . import database as db


class PrefixDatabase(db.Database):
    """Provide an interface to a GuildDatabase with a Prefixes table."""
    __slots__ = ('prefix_cache',)

    PREFIX_SIZE_LIMIT = 20

    TABLE_NAME = 'Prefixes'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        guild_id INTEGER PRIMARY KEY NOT NULL,
        prefix TEXT NOT NULL,
        FOREIGN KEY(guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE
    );
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefix_cache = {}

    async def add_prefix(self, guild_id: int, prefix: str = None):
        """Add a prefix for a guild if it does not exist.

        The prefix is constrained by PREFIX_SIZE_LIMIT.

        Args:
            guild_id (int)
            prefix (str): The prefix to set the guild with.

        """
        guild_id = int(guild_id)

        if len(prefix) > self.PREFIX_SIZE_LIMIT:
            raise ValueError(
                f'Prefix cannot be over {self.PREFIX_SIZE_LIMIT:,} '
                'characters long.'
            )

        stored_prefix = await self.get_prefix(guild_id)
        if stored_prefix is None:
            await self.add_row(self.TABLE_NAME, {'guild_id': guild_id, 'prefix': prefix})

            self.prefix_cache[guild_id] = prefix
        else:
            self.prefix_cache[guild_id] = stored_prefix

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
            self.TABLE_NAME, where={'guild_id': guild_id}, pop=pop)

        self.prefix_cache.pop(guild_id, None)

        return prefixes

    async def get_prefix(self, guild_id: int):
        """Get the prefix for a guild if it exists.

        guild_id is not escaped.

        Returns:
            str
            None

        """
        guild_id = int(guild_id)

        prefix = self.prefix_cache.get(guild_id)
        if prefix is not None:
            return prefix

        query = await self.get_one(
            self.TABLE_NAME, 'prefix', where={'guild_id': guild_id})

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
            self.TABLE_NAME, {'prefix': prefix}, where={'guild_id': guild_id})

        self.prefix_cache[guild_id] = prefix
