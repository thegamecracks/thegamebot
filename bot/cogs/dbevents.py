#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import logging
from typing import Any

import discord
from discord.ext import commands

from bot import utils
from main import TheGameBot

logger = logging.getLogger('discord')


class DatabaseEvents(commands.Cog):
    """Event listeners managing the database."""

    def __init__(self, bot: TheGameBot):
        self.bot = bot

        # cleanup_tables() requires bot to be ready, however
        # doing so in the cog_load() method would deadlock the
        # loading process, so we use a task here
        asyncio.create_task(self.cleanup_tables())

    async def delete_many(self, table_name: str, column: str, ids: list[int]):
        async with self.bot.db.connect(writing=True) as conn:
            query = 'DELETE FROM {} WHERE {} IN ({})'.format(
                table_name, column, ', '.join([str(n) for n in ids])
            )
            await conn.execute(query)

    async def check_guild_tables(self) -> list[int]:
        """Remove any guilds that the bot is no longer a part of.

        This assumes that the bot is not sharded and
        the guilds intent is enabled.

        """
        to_remove = []

        async with self.bot.db.connect() as conn:
            async with conn.execute(f'SELECT guild_id FROM guild') as c:
                while row := await c.fetchone():
                    guild_id = row['guild_id']
                    if self.bot.get_guild(guild_id) is None:
                        to_remove.append(guild_id)

        logger.debug('Removing %d guilds from database', len(to_remove))

        if to_remove:
            await self.delete_many('guild', 'guild_id', to_remove)

        return to_remove

    async def check_tag_tables(self, cog) -> list[tuple[int, int]]:
        """Remove user IDs from tags where the user is
        no longer a part of the guild.
        """
        authors = set()
        authors_to_remove = []

        # Iterate through authors of tags/aliases and find
        # which authors are no longer in the guild
        async with self.bot.db.connect() as conn:
            async with conn.execute(
                    f'SELECT DISTINCT guild_id, user_id FROM tag') as c:
                while row := await c.fetchone():
                    authors.add((row['guild_id'], row['user_id']))

            async with conn.execute(
                    f'SELECT DISTINCT guild_id, user_id FROM tag_alias') as c:
                while row := await c.fetchone():
                    authors.add((row['guild_id'], row['user_id']))

        for guild_id, user_id in authors:
            if user_id is None:  # un-claimed tag
                continue

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                # NOTE: this shouldn't happen after checking guild table
                continue

            member = await utils.getch_member(guild, user_id)
            if member is None:
                authors_to_remove.append((guild_id, user_id))

        for key in authors_to_remove:
            await cog.tags.unauthor_tags(*key)
            await cog.tags.unauthor_aliases(*key)

        return authors_to_remove

    async def cleanup_tables(self):
        """Update the tables to match guild/member changes."""
        await self.bot.wait_until_ready()

        # Make sure this only happens once on startup
        if self.bot.dbevents_cleaned_up:
            return

        deleted = False
        intents = self.bot.intents
        if intents.guilds:
            logger.debug('Cleaning up guild tables')
            deleted = bool(await self.check_guild_tables()) or deleted
        if intents.guilds and intents.members:
            cog: Any = self.bot.get_cog('Tags')
            if cog is not None:
                logger.debug('Cleaning up tag tables')
                deleted = bool(await self.check_tag_tables(cog)) or deleted

        self.bot.dbevents_cleaned_up = True
        if deleted:
            await self.bot.db.vacuum()

    @commands.Cog.listener('on_member_remove')
    async def update_tags_on_removed_member(self, member: discord.Member):
        cog: Any = self.bot.get_cog('Tags')
        if cog is not None:
            await cog.tags.unauthor_tags(member.guild.id, member.id)
            await cog.tags.unauthor_aliases(member.guild.id, member.id)


async def setup(bot: TheGameBot):
    await bot.add_cog(DatabaseEvents(bot))
