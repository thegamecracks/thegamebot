#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import re
import sqlite3

import disnake
from disnake.ext import commands

from main import TheGameBot


class Prefix(commands.Cog):
    """Commands for changing the bot's prefix."""
    PREFIX_SIZE_LIMIT = 20

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.cache: dict[int, str] = {}
        self.mention_prefix_cooldown = commands.CooldownMapping.from_cooldown(
            1, 15, commands.BucketType.member)

    async def fetch_prefix(self, guild_id: int) -> str | None:
        prefix = self.cache.get(guild_id)
        if prefix is not None:
            return prefix

        condition = {'guild_id': guild_id}
        db = self.bot.db
        row = await db.get_one('guild', 'prefix', where=condition)

        prefix: str | None
        if row is None:
            prefix = self.bot.get_default_prefix()
            row = {'guild_id': guild_id, 'prefix': prefix}
            await db.add_row('guild', row)
        elif row['prefix'] is None:
            prefix = self.bot.get_default_prefix()
            row = {'prefix': prefix}
            await db.update_rows('guild', row, where=condition)
        else:
            prefix = row['prefix']

        if prefix is not None:
            self.cache[guild_id] = prefix
        # if prefix is None then something went wrong with
        # getting the default prefix, in that case don't cache
        # as it might get fixed live

        return prefix

    async def update_prefix(self, guild_id: int, prefix: str):
        """Updates the prefix for a given guild.

        :raises sqlite3.IntegrityError: The prefix is too long.

        """
        async with self.bot.db.connect(writing=True) as conn:
            await conn.execute(
                'INSERT INTO guild (guild_id, prefix) VALUES (?, ?) '
                'ON CONFLICT (guild_id) DO UPDATE SET prefix=?',
                guild_id, prefix, prefix
            )

        self.cache[guild_id] = prefix

    @commands.Cog.listener('on_message')
    async def show_prefix_on_message(self, message: disnake.Message):
        # Ignore messages that are from bot or didn't mention the bot
        if (message.author == self.bot.user
                or self.bot.user not in message.mentions):
            return

        bot_mention = re.compile(f'<@!?{self.bot.user.id}>')

        # Check if the message content ONLY consists of the mention
        # and return otherwise
        if not bot_mention.fullmatch(message.content):
            return

        # Check cooldown
        if self.mention_prefix_cooldown.update_rate_limit(message):
            return

        # Get prefix(es)
        prefix = await self.bot.get_prefix(message)

        if isinstance(prefix, str):
            prefix = [prefix]
        else:
            # Remove bot mentions in the prefixes
            prefix = [p for p in prefix if not bot_mention.match(p)]

        # Send available prefix(es)
        if len(prefix) == 1:
            await message.channel.send(f'My prefix here is "{prefix[0]}".')
        else:
            await message.channel.send('My prefixes here are {}.'.format(
                self.bot.inflector.join([f'"{p}"' for p in prefix]))
            )

    @commands.command(name='changeprefix')
    @commands.check_any(
        commands.has_guild_permissions(manage_guild=True),
        commands.is_owner()
    )
    @commands.guild_only()
    @commands.cooldown(2, 30, commands.BucketType.guild)
    async def change_prefix(self, ctx, prefix):
        """Change the bot's prefix.

For prefixes ending with a space or multi-word prefixes, you must specify it with double quotes:
<command> "myprefix " """
        prefix = prefix.lstrip()

        if not prefix:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send('An empty prefix is not allowed.')

        current_prefix = await self.fetch_prefix(ctx.guild.id)

        if prefix == current_prefix:
            await ctx.send('That is already the current prefix.')
        else:
            # Escape characters before printing
            clean_prefix = prefix.replace('\\', r'\\')
            await self.update_prefix(ctx.guild.id, prefix)
            await ctx.send(f'Successfully changed prefix to: "{clean_prefix}"')

    @change_prefix.error
    async def change_prefix_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, sqlite3.IntegrityError):
            await ctx.send('Your prefix must be a maximum of 20 characters.')
            ctx.handled = True


def setup(bot):
    bot.add_cog(Prefix(bot))
