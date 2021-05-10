#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.

# TODO: remove guild from database when removed
import re

import discord
from discord.ext import commands


class Prefix(commands.Cog):
    """Commands for changing the bot's prefix."""
    qualified_name = 'Prefix'

    def __init__(self, bot):
        self.bot = bot
        self.mention_prefix_cooldown = commands.CooldownMapping.from_cooldown(
            1, 15, commands.BucketType.member)





    @commands.Cog.listener()
    async def on_message(self, message):
        """Send the bot's prefix if mentioned."""
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
        commands.is_owner())
    @commands.guild_only()
    @commands.cooldown(2, 30, commands.BucketType.guild)
    async def client_changeprefix(self, ctx, prefix):
        """Change the bot's prefix.

For prefixes ending with a space or multi-word prefixes, specify it with double quotes:
<command> "myprefix " """
        prefix = prefix.lstrip()
        db = self.bot.dbprefixes

        if not prefix:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send('An empty prefix is not allowed.')

        current_prefix = (
            await db.get_prefix(ctx.guild.id)
        )

        if prefix == current_prefix:
            await ctx.send('That is already the current prefix.')
        else:
            # Escape escape characters before printing
            clean_prefix = prefix.replace('\\', r'\\')
            await db.update_prefix(ctx.guild.id, prefix)
            await ctx.send(f'Successfully changed prefix to: "{clean_prefix}"')


    @client_changeprefix.error
    async def client_changeprefix_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            # Prefix is too long
            await ctx.send(str(error))










def setup(bot):
    bot.add_cog(Prefix(bot))
