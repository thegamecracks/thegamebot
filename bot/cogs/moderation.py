#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections

import discord
from discord.ext import commands

from bot import errors


class PurgeLimitConverter(commands.Converter):
    def __init__(self, min: int = 2, max: int = 100):
        self.min = min
        self.max = max

    async def convert(self, ctx, arg):
        n = int(arg)

        if n < self.min:
            raise errors.ErrorHandlerResponse(
                'Must purge at least {} {}.'.format(
                    self.min, ctx.bot.inflector.plural('message', self.min)
                )
            )
        elif n > self.max:
            raise errors.ErrorHandlerResponse(
                'Cannot purge more than {} {} at a time.'.format(
                    self.max, ctx.bot.inflector.plural('message', self.max)
                )
            )

        return n


class Moderation(commands.Cog):
    """Commands to be used in moderation."""

    def __init__(self, bot):
        self.bot = bot





    async def send_purged(self, channel, messages):
        plural = self.bot.inflector.plural
        n = len(messages)
        c = collections.Counter(m.author for m in messages)
        return await channel.send(
            '{} {} {} deleted!\n\n{}'.format(
                n, plural('message', n), plural('was', n),
                '\n'.join([f'**{count}** - {member.display_name}'
                           for member, count in c.most_common()])
            ), delete_after=12
        )

    @commands.group(name='purge', invoke_without_command=True)
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(
        manage_messages=True,
        read_message_history=True
    )
    async def client_purge(self, ctx, limit: PurgeLimitConverter):
        """Bulk delete messages in the current channel.

limit: The number of messages to look through. (range: 2-100)"""
        messages = await ctx.channel.purge(limit=limit, before=ctx.message)
        await self.send_purged(ctx, messages)


    @client_purge.command(name='bot')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(
        manage_messages=True,
        read_message_history=True
    )
    async def client_purge_bot(self, ctx, limit: PurgeLimitConverter):
        """Delete messages from bots.

limit: The number of messages to look through. (range: 2-100)"""
        def check(m):
            return m.author.bot

        messages = await ctx.channel.purge(
            limit=limit, check=check,
            before=ctx.message
        )
        await self.send_purged(ctx, messages)


    @client_purge.command(name='self')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.guild_only()
    @commands.check_any(
        commands.has_permissions(manage_messages=True),
        commands.is_owner()
    )
    @commands.bot_has_permissions(read_message_history=True)
    async def client_purge_self(self, ctx, limit: PurgeLimitConverter):
        """Delete messages from me.
This will also remove messages that appear to be invoking one of my commands if I have Manage Messages permission.

limit: The number of messages to look through. (range: 2-100)"""
        def check(m):
            return (
                m.author == ctx.me
                or perms.manage_messages and m.content.startswith(prefixes)
            )

        perms = ctx.me.permissions_in(ctx.channel)
        prefixes = ()
        if perms.manage_messages:
            prefixes = await ctx.bot.get_prefix(ctx.message)
            if isinstance(prefixes, str):
                prefixes = (prefixes,)
            else:
                prefixes = tuple(prefixes)

        messages = await ctx.channel.purge(
            limit=limit, check=check,
            before=ctx.message,
            bulk=perms.manage_messages
        )

        await self.send_purged(ctx, messages)










def setup(bot):
    bot.add_cog(Moderation(bot))
