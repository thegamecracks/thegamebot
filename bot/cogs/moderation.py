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





    async def send_purged(self, channel, n):
        plural = self.bot.inflector.plural
        return await channel.send(
            '{} {} {} deleted!'.format(
                n, plural('message', n), plural('was', n)),
            delete_after=6
        )

    @commands.group(name='purge', invoke_without_command=True)
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def client_purge(self, ctx, limit: PurgeLimitConverter):
        """Bulk delete messages in the current channel.

limit: The number of messages to look through. (range: 2-100)"""
        n = len(await ctx.channel.purge(limit=limit))
        await self.send_purged(ctx, n)


    @client_purge.command(name='bot')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def client_purge_bot(self, ctx, limit: PurgeLimitConverter):
        """Delete messages from bots.

limit: The number of messages to look through. (range: 2-100)"""
        def check(m):
            return m.author.bot

        n = len(await ctx.channel.purge(limit=limit, check=check))
        await self.send_purged(ctx, n)


    @client_purge.command(name='self')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.has_permissions(manage_messages=True)
    async def client_purge_self(self, ctx, limit: PurgeLimitConverter):
        """Delete messages from me.

limit: The number of messages to look through. (range: 2-100)"""
        def check(m):
            return m.author == ctx.me

        perms = ctx.me.permissions_in(ctx.channel)

        n = len(await ctx.channel.purge(limit=limit, check=check,
                                        bulk=perms.manage_messages))
        await self.send_purged(ctx, n)










def setup(bot):
    bot.add_cog(Moderation(bot))
