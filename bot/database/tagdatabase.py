"""A database for storing user's notes.

Table dependencies:
    Guilds
    Users
"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
from typing import Optional

from . import database as db


class TagDatabase(db.Database):
    """Provide an interface to the Tags table."""

    TABLE_NAME = 'Tags'
    TABLE_ALIASES_NAME = 'TagAliases'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        guild_id INTEGER NOT NULL,
        name VARCHAR(50) NOT NULL,
        content VARCHAR(2000) NOT NULL,
        user_id INTEGER,
        uses INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL,
        edited_at TIMESTAMP,
        PRIMARY KEY (guild_id, name),
        FOREIGN KEY (guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES Users(id)
            ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS ix_tags_guilds ON {TABLE_NAME}(guild_id);
    CREATE INDEX IF NOT EXISTS ix_tags_users
        ON {TABLE_NAME}(guild_id, user_id);
    CREATE TABLE IF NOT EXISTS {TABLE_ALIASES_NAME} (
        guild_id INTEGER NOT NULL,
        alias VARCHAR(50) NOT NULL,
        name VARCHAR(50) NOT NULL,
        user_id INTEGER,
        created_at TIMESTAMP NOT NULL,
        PRIMARY KEY (guild_id, alias),
        FOREIGN KEY (guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE,
        FOREIGN KEY (guild_id, name) REFERENCES {TABLE_NAME}
            ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES Users(id)
            ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS ix_tags_name_to_aliases
        ON {TABLE_ALIASES_NAME}(guild_id, name);
    CREATE INDEX IF NOT EXISTS ix_tags_user_to_aliases
        ON {TABLE_ALIASES_NAME}(guild_id, user_id);
    -- Ensure alias and name don't both exist together
    CREATE TRIGGER IF NOT EXISTS no_tag_alias_if_name
        AFTER INSERT ON {TABLE_ALIASES_NAME}
        WHEN EXISTS (SELECT * FROM {TABLE_NAME} WHERE name=NEW.alias)
        BEGIN
            SELECT RAISE(ABORT, "a tag with the same name already exists");
        END;
    CREATE TRIGGER IF NOT EXISTS no_tag_name_if_alias
        AFTER INSERT ON {TABLE_NAME}
        WHEN EXISTS (SELECT * FROM {TABLE_ALIASES_NAME} WHERE alias=NEW.name)
        BEGIN
            SELECT RAISE(ABORT, "an alias with the same name already exists");
        END;
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__cache = {}  # (guild_id, name): sqlite3.Row
        self.__alias_cache = {}
        # (guild_id, alias): (name, sqlite3.Row)

    def _cache_delete_alias(self, guild_id: int, alias: str):
        self.__alias_cache.pop((guild_id, alias), None)

    async def _cache_delete_aliases_by_name(self, guild_id: int, name: str):
        async with self.connect() as conn:
            async with conn.execute(
                    f'SELECT alias FROM {self.TABLE_ALIASES_NAME} '
                    'WHERE guild_id = ? AND name = ?',
                    guild_id, name) as c:
                while row := await c.fetchone():
                    self._cache_delete_alias(guild_id, row['alias'])

    async def _cache_delete_aliases_by_user(self, guild_id: int, user_id: int):
        async with self.connect() as conn:
            async with conn.execute(
                    f'SELECT alias FROM {self.TABLE_ALIASES_NAME} '
                    'WHERE guild_id = ? AND user_id = ?',
                    guild_id, user_id) as c:
                while row := await c.fetchone():
                    self._cache_delete_alias(guild_id, row['alias'])

    def _cache_delete_tag(self, guild_id: int, name: str):
        self.__cache.pop((guild_id, name), None)

    async def _cache_delete_tags_by_user(self, guild_id: int, user_id: int):
        async with self.connect() as conn:
            async with conn.execute(
                    f'SELECT name FROM {self.TABLE_NAME} '
                    'WHERE guild_id = ? AND user_id = ?',
                    guild_id, user_id) as c:
                while row := await c.fetchone():
                    self._cache_delete_tag(guild_id, row['name'])

    async def add_alias(
            self, guild_id: int, alias: str, name: str, user_id: int) -> None:
        """Add an alias for a tag and return the added row.

        Raises:
            sqlite3.IntegrityError: likely a tag with the same name
                already exists.

        """
        guild_id, name = int(guild_id), str(name)
        alias, user_id = str(alias), int(user_id)

        d = {'guild_id': guild_id, 'name': name, 'alias': alias,
             'user_id': user_id, 'created_at': datetime.datetime.utcnow()}

        await self.add_row(self.TABLE_ALIASES_NAME, d)
        return await self.get_alias(guild_id, alias)

    async def add_tag(
            self, guild_id: int, name: str, content: str, user_id: int):
        """Add a tag and return the added row.

        This also adds a user entry if needed.

        Raises:
            sqlite3.IntegrityError:
                likely a tag or an alias with the same name already exists.

        """
        guild_id, user_id = int(guild_id), int(user_id)
        name, content = str(name), str(content)
        d = {'guild_id': guild_id, 'name': name,
             'content': content, 'user_id': user_id,
             'created_at': datetime.datetime.utcnow()}

        await self.bot.dbusers.add_user(user_id)
        await self.add_row(self.TABLE_NAME, d)
        return await self.get_tag(guild_id, name)

    async def delete_alias(self, guild_id: int, alias: str) -> None:
        """Delete an alias."""
        guild_id, alias = int(guild_id), str(alias)

        self._cache_delete_alias(guild_id, alias)

        d = {'guild_id': guild_id, 'alias': alias}
        await self.delete_rows(self.TABLE_ALIASES_NAME, d)

    async def delete_tag(self, guild_id: int, name: str):
        """Delete a tag and return the deleted rows.

        Returns:
            List[sqlite3.Row]

        """
        guild_id, name = int(guild_id), str(name)

        self._cache_delete_tag(guild_id, name)
        await self._cache_delete_aliases_by_name(guild_id, name)

        d = {'guild_id': guild_id, 'name': name}
        rows = await self.delete_rows(self.TABLE_NAME, d, pop=True)

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

    async def get_alias(self, guild_id: int, alias: str):
        """Get a specific alias."""
        guild_id, alias = int(guild_id), str(alias)

        name_and_alias = self.__alias_cache.get((guild_id, alias))
        if name_and_alias:
            return name_and_alias[1]

        d = {'guild_id': guild_id, 'alias': alias}
        r = await self.get_one(self.TABLE_ALIASES_NAME, where=d)

        if r:
            self.__alias_cache[(guild_id, r['alias'])] = (r['name'], r)

        return r

    async def get_aliases(self, guild_id: int, name: str):
        """Get all of a tag's aliases as a list of rows.

        This will always do a database lookup, as the cache may only be
        partially complete from some get_alias calls which is
        indistinguishable from an actually complete cache of aliases.

        Returns:
            List[sqlite3.Row]

        """
        guild_id, name = int(guild_id), str(name)

        aliases = await self.get_rows(
            self.TABLE_ALIASES_NAME, where={
                'guild_id': guild_id,
                'name': name
            }
        )

        for r in aliases:
            self.__alias_cache[(guild_id, r['alias'])] = (name, r)

        return aliases

    async def get_tag(
            self, guild_id: int, name: str, *, include_aliases=False):
        """Get a tag from a guild.

        NOTE: the number of columns in the row returned may vary
        depending on caching. If include_aliases is True and the tag
        was not cached, i.e. there wasn't a query where
        include_aliases=False was successful, then a successful
        fetch will return a row with columns from the aliases table being
        included, which may be None if it matched the tag's name directly.

        """
        guild_id, name = int(guild_id), str(name)

        key = (guild_id, name)
        tag = self.__cache.get(key)
        if tag is None and include_aliases:
            tag = self.__cache.get(self.__alias_cache.get(key))
        if tag is not None:
            return tag

        if include_aliases:
            async with self.connect() as conn:
                async with conn.cursor() as c:
                    t, t_aliases = self.TABLE_NAME, self.TABLE_ALIASES_NAME
                    await c.execute(f"""
                        SELECT * FROM {t} LEFT JOIN {t_aliases}
                            ON {t}.name = {t_aliases}.name
                        WHERE {t}.name = ? OR {t_aliases}.alias = ?
                    """, name, name)
                    tag = await c.fetchone()
                    if tag:
                        key = (guild_id, tag['name'])
        else:
            d = {'guild_id': guild_id, 'name': name}
            tag = await self.get_one(self.TABLE_NAME, where=d)
        self.__cache[key] = tag

        return tag

    async def set_alias_author(
            self, guild_id: int, alias: str, user_id: Optional[int]):
        """Set the author of an alias.
        user_id may be None to remove the author.
        """
        guild_id, alias = int(guild_id), str(alias)

        if user_id is not None:
            user_id = int(user_id)

        self._cache_delete_alias(guild_id, alias)

        async with self.connect(writing=True) as conn:
            await conn.execute(
                f'UPDATE {self.TABLE_ALIASES_NAME} SET user_id = ? '
                'WHERE guild_id = ? AND alias = ?',
                user_id, guild_id, alias
            )

    async def set_tag_author(
            self, guild_id: int, name: str, user_id: Optional[int]):
        """Set the author of a tag.
        user_id may be None to remove the author.
        """
        guild_id, name = int(guild_id), str(name)

        if user_id is not None:
            user_id = int(user_id)

        self._cache_delete_tag(guild_id, name)

        async with self.connect(writing=True) as conn:
            await conn.execute(
                f'UPDATE {self.TABLE_NAME} SET user_id = ? '
                'WHERE guild_id = ? AND name = ?',
                user_id, guild_id, name
            )

    async def unauthor_aliases(self, guild_id: int, user_id: int):
        """Remove an author's info from their aliases in a guild."""
        guild_id, user_id = int(guild_id), int(user_id)

        await self._cache_delete_aliases_by_user(guild_id, user_id)

        async with self.connect(writing=True) as conn:
            await conn.execute(
                f'UPDATE {self.TABLE_ALIASES_NAME} SET user_id = NULL '
                'WHERE guild_id = ? AND user_id = ?',
                guild_id, user_id
            )

    async def unauthor_tags(self, guild_id: int, user_id: int):
        """Remove an author's info from their tags in a guild."""
        guild_id, user_id = int(guild_id), int(user_id)

        await self._cache_delete_tags_by_user(guild_id, user_id)

        async with self.connect(writing=True) as conn:
            await conn.execute(
                f'UPDATE {self.TABLE_NAME} SET user_id = NULL '
                'WHERE guild_id = ? AND user_id = ?',
                guild_id, user_id
            )

    async def wipe(self, guild_id: int):
        """Wipe all tags from a guild."""
        await self.delete_rows(self.TABLE_NAME, {'guild_id': int(guild_id)})

    async def yield_tags_ordered(
            self, guild_id: int, *, column: Optional[str] = None,
            where: Optional[dict] = None, reverse=False):
        """Yield all tags in a guild ordered by a given column.

        Note that `column` and the keys of `where` are not escaped.

        Args:
            guild_id (int): The guild to get tags from.
            column (Optional[str]):
                The name of the column to sort the tags by.
            where (Optional[dict]):
                A dictionary mapping SQL expressions with placeholders
                to their values.
                Only shows tags where all the given expressions evaluate
                to true.
                Example:
                    {'user_id = ?': 1234,
                     'created_at > ?': datetime.datetime.utcnow()
                                       - datetime.timedelta(hours=1)}
            reverse (bool): If True, yields the tags in descending order.
                Unapplicable if `column` is unspecified.

        """
        guild_id = int(guild_id)

        if where is None:
            where = {}
        where['guild_id = ?'] = guild_id
        keys, values = zip(*where.items())
        conditions = ' AND '.join(keys)

        order = ''
        if column:
            order = ' ORDER BY {} {}'.format(column, 'DESC' if reverse else 'ASC')

        async with self.connect() as conn:
            async with conn.execute(
                    f'SELECT * FROM {self.TABLE_NAME} '
                    f'WHERE {conditions}{order}',
                    *values) as c:
                while tag := await c.fetchone():
                    self.__cache[(guild_id, tag['name'])] = tag
                    yield tag
