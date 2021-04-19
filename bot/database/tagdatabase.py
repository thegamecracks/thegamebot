"""A database for storing user's notes.

Table dependencies:
    Guilds
    Users
"""
import datetime

from . import database as db


class TagDatabase(db.Database):
    """Provide an interface to the Tags table."""

    TABLE_NAME = 'Tags'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        guild_id INTEGER NOT NULL,
        name VARCHAR(50) NOT NULL,
        content VARCHAR(2000) NOT NULL,
        user_id INTEGER NOT NULL,
        uses INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL,
        edited_at TIMESTAMP,
        PRIMARY KEY (guild_id, name),
        FOREIGN KEY(guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES Users(id)
    );
    CREATE INDEX IF NOT EXISTS ix_tags_guilds ON {TABLE_NAME}(guild_id);
    CREATE INDEX IF NOT EXISTS ix_tags_users
        ON {TABLE_NAME}(guild_id, user_id);
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__cache = {}

    async def add_tag(
            self, guild_id: int, name: str, content: str, user_id: int):
        """Add a tag and return the added row.

        This also adds a user entry if needed.

        """
        guild_id, user_id = int(guild_id), int(user_id)
        name, content = str(name), str(content)
        d = {'guild_id': guild_id, 'name': name,
             'content': content, 'user_id': user_id,
             'created_at': datetime.datetime.utcnow()}

        await self.bot.dbusers.add_user(user_id)
        await self.add_row(self.TABLE_NAME, d)
        return await self.get_tag(guild_id, name)

    async def delete_tag(self, guild_id: int, name: str):
        """Delete a tag and return the deleted rows.

        Returns:
            List[sqlite3.Row]

        """
        guild_id, name = int(guild_id), str(name)

        # Invalidate cache
        self.__cache.pop((guild_id, name), None)

        d = {'guild_id': guild_id, 'name': name}
        return await self.delete_rows(self.TABLE_NAME, d, pop=True)

    async def edit_tag(self, guild_id: int, name: str,
                       content: str = None, uses: int = None,
                       record_time=True):
        """Edit a tag's contents and return the new row.

        Args:
            guild_id (int): The guild id of the tag.
            name (str): The name of the tag.
            content (Optional[str]): The new content to update the tag with.
            uses (Optional[int]): The new number of uses to update the tag with.
            record_time (bool): Sets the edited_at column to the current time.

        """
        guild_id, name = int(guild_id), str(name)

        d = {}
        if record_time:
            d['edited_at'] = datetime.datetime.utcnow()
        if content is not None:
            d['content'] = str(content)
        if uses is not None:
            d['uses'] = int(uses)

        await self.update_rows(
            self.TABLE_NAME, d,
            where={'guild_id': guild_id, 'name': name}
        )

        # Update cache
        key = (guild_id, name)
        self.__cache.pop(key, None)
        return await self.get_tag(guild_id, name)

    async def get_tag(self, guild_id: int, name: str):
        """Get a tag from a guild."""
        guild_id, name = int(guild_id), str(name)

        key = (guild_id, name)
        tag = self.__cache.get(key)
        if tag is not None:
            return tag

        d = {'guild_id': guild_id, 'name': name}
        tag = await self.get_one(self.TABLE_NAME, where=d)
        self.__cache[key] = tag

        return tag

    async def wipe(self, guild_id: int):
        """Wipe all tags from a guild."""
        await self.delete_rows(self.TABLE_NAME, {'guild_id': int(guild_id)})
