#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
from typing import Any, TypedDict

import discord

from bot.database import Database


class AliasDict(TypedDict):
    guild_id: int
    alias_name: str
    tag_name: str
    user_id: int | None
    created_at: datetime.datetime


class TagDict(TypedDict):
    guild_id: int
    tag_name: str
    content: str
    user_id: int | None
    uses: int
    created_at: datetime.datetime
    edited_at: datetime.datetime | None


class TagQuerier:
    """Handles querying tags and aliases from the database."""

    def __init__(self, db: Database):
        self.db = db

    async def add_alias(self, guild_id: int, alias: str, name: str, user_id: int):
        """Adds an alias for a tag.

        An entry is also added for the user if not present.

        :raises sqlite3.IntegrityError:
            Likely a tag with the same name already exists.

        """
        guild_id, name = int(guild_id), str(name)
        alias, user_id = str(alias), int(user_id)

        row = {'guild_id': guild_id, 'tag_name': name, 'alias_name': alias,
               'user_id': user_id, 'created_at': datetime.datetime.utcnow()}

        await self.db.add_row('user', {'user_id': user_id}, ignore=True)
        await self.db.add_row('tag_alias', row)

    async def add_tag(self, guild_id: int, name: str, content: str, user_id: int):
        """Adds a tag for a guild.

        An entry is also added for the user if not present.

        :raises sqlite3.IntegrityError:
            Likely a tag or an alias with the same name already exists.

        """
        guild_id, user_id = int(guild_id), int(user_id)
        name, content = str(name), str(content)

        row = {'guild_id': guild_id, 'tag_name': name, 'content': content,
               'user_id': user_id, 'created_at': discord.utils.utcnow()}

        await self.db.add_row('user', {'user_id': user_id}, ignore=True)
        await self.db.add_row('tag', row)

    async def delete_alias(self, guild_id: int, alias: str):
        guild_id, alias = int(guild_id), str(alias)

        await self.db.delete_rows('tag_alias', {'guild_id': guild_id, 'alias_name': alias})

    async def delete_tag(self, guild_id: int, name: str):
        guild_id, name = int(guild_id), str(name)

        await self.db.delete_rows('tag', {'guild_id': guild_id, 'tag_name': name})

    async def edit_tag(self, guild_id: int, name: str,
                       content: str = None, uses: int = None,
                       record_time=True):
        """Edits the content or number of uses of a tag.

        :param guild_id: The guild id of the tag being edited.
        :param name: The name of the tag being edited.
        :param content: The new content.
        :param uses: The new number of uses.
        :param record_time:
            If True, updates the edited_at column to the current time.

        """
        guild_id, name = int(guild_id), str(name)

        row = {}
        if record_time:
            row['edited_at'] = discord.utils.utcnow()
        if content is not None:
            row['content'] = str(content)
        if uses is not None:
            row['uses'] = int(uses)

        await self.db.update_rows(
            'tag', row, where={
                'guild_id': guild_id,
                'tag_name': name
            }
        )

    async def get_alias(self, guild_id: int, alias: str):
        guild_id, alias = int(guild_id), str(alias)

        return await self.db.get_one(
            'tag_alias', where={
                'guild_id': guild_id,
                'alias_name': alias
            }
        )

    async def get_aliases(self, guild_id: int, name: str):
        """Gets all of a tag's aliases."""
        guild_id, name = int(guild_id), str(name)

        return await self.db.get_rows(
            'tag_alias', where={
                'guild_id': guild_id,
                'tag_name': name
            }
        )

    async def get_tag(
        self, guild_id: int, name: str, *, include_aliases=False
    ):
        """Gets a tag from a guild.

        :param guild_id: The guild id that the tag is in.
        :param name: The name of the tag to find.
        :param include_aliases: If True, aliases are included in the search.

        """
        guild_id, name = int(guild_id), str(name)

        if include_aliases:
            query = """
            SELECT * FROM tag LEFT JOIN tag_alias USING (guild_id, tag_name)
            WHERE guild_id = ? AND (tag_name = ? OR alias_name = ?)
            """
            params = (guild_id, name, name)
        else:
            query = 'SELECT * FROM tag WHERE guild_id = ? AND tag_name = ?'
            params = (guild_id, name)

        async with self.db.connect() as conn:
            async with conn.execute(query, params) as c:
                return await c.fetchone()

    async def set_alias_author(self, guild_id: int, alias: str, user_id: int | None):
        """Sets the author of an alias.
        user_id may be None to remove the author.
        """
        guild_id, alias = int(guild_id), str(alias)

        if user_id is not None:
            user_id = int(user_id)

        await self.db.update_rows(
            'tag_alias', {'user_id': user_id}, where={
                'guild_id': guild_id,
                'alias_name': alias
            }
        )

    async def set_tag_author(self, guild_id: int, name: str, user_id: int | None):
        """Sets the author of a tag.
        user_id may be None to remove the author.
        """
        guild_id, name = int(guild_id), str(name)

        if user_id is not None:
            user_id = int(user_id)

        await self.db.update_rows(
            'tag', {'user_id': user_id}, where={
                'guild_id': guild_id,
                'tag_name': name
            }
        )

    async def unauthor_aliases(self, guild_id: int, user_id: int):
        """Removes an author's info from their aliases in a guild."""
        guild_id, user_id = int(guild_id), int(user_id)

        await self.db.update_rows(
            'tag_alias', {'user_id': None}, where={
                'guild_id': guild_id,
                'user_id': user_id
            }
        )

    async def unauthor_tags(self, guild_id: int, user_id: int):
        """Removes an author's info from their tags in a guild."""
        guild_id, user_id = int(guild_id), int(user_id)

        await self.db.update_rows(
            'tag', {'user_id': None}, where={
                'guild_id': guild_id,
                'user_id': user_id
            }
        )

    async def wipe(self, guild_id: int):
        """Wipes all tags from a guild."""
        await self.db.delete_rows('tag', {'guild_id': int(guild_id)})

    async def yield_tags(
        self, guild_id: int, *, where: dict[str, Any] = None,
        column: str = None, reverse=False
    ):
        """Yields the tags in a guild.

        Note that `column` and the keys of `where` are not escaped.

        :param guild_id: The guild to get tags from.
        :param where:
            A dictionary mapping SQL expressions with placeholders
            to their values. Only tags are yielded where these
            expressions are true.
        :param column:
            The name of the column to sort the tags by.
            If None, no ordering is applied.
        :param reverse: If True, yields the tags in descending order.
            This is only applicable if `column` is specified.

        """
        guild_id = int(guild_id)

        if where is None:
            where = {}

        where['guild_id = ?'] = guild_id

        keys: tuple[str]
        values: tuple[Any]
        keys, values = zip(*where.items())
        conditions = ' AND '.join(keys)

        order = ''
        if column:
            order = 'ORDER BY {} {}'.format(column, 'DESC' if reverse else 'ASC')

        query = f'SELECT * FROM tag WHERE {conditions} {order}'.rstrip()

        async with self.db.connect() as conn:
            async with conn.execute(query, values) as c:
                while tag := await c.fetchone():
                    yield tag
