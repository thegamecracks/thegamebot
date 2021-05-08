import collections
import functools
from typing import Union

import discord
from discord.ext import commands

from bot import converters, utils


def converter_partial(conv, *args, **kwargs):
    class PartialConverter(conv):
        def __init__(self):
            super().__init__(*args, **kwargs)
    return PartialConverter


class Testing(commands.Cog, command_attrs={'hidden': True}):
    """Testing commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await ctx.bot.is_owner(ctx.author)





    @commands.command(name='polltest')
    async def client_poll(self, ctx):
        yes = '\N{WHITE HEAVY CHECK MARK}'
        no = '\N{CROSS MARK}'
        choices = [yes, no]
        m = await ctx.send('Poll test')

        for e in choices:
            await m.add_reaction(e)
        await m.add_reaction('\N{OCTAGONAL SIGN}')

        def check(r, u):
            return (u == ctx.author and r.message == m
                    and r.emoji == '\N{OCTAGONAL SIGN}')

        try:
            await ctx.bot.wait_for('reaction_add', check=check, timeout=30)
        except asyncio.TimeoutError:
            pass

        m = await m.channel.fetch_message(m.id)

        d = {}
        for e in choices:
            r = discord.utils.get(m.reactions, emoji=e)
            d[e] = r.count - 1

        result = '\n'.join([f'{k}: {v}' for k, v in d.items()])

        await ctx.send(result)





    @commands.command(name='getuser')
    async def client_convert_user(
            self, ctx, *, user: discord.User):
        await ctx.send(str(user))





    @commands.command(name='rolemoji')
    async def client_role_emoji(
            self, ctx, *args: Union[discord.Role,
            converter_partial(converters.UnicodeEmojiConverter, partial_emoji=True)]):
        names = ', '.join([x.name for x in args])
        await ctx.send(names)





    @commands.command(name='parsementions')
    async def client_parse_mentions(
            self, ctx, *mentions: commands.Greedy[
                Union[discord.TextChannel, discord.Member]],
            text: commands.clean_content):
        # NOTE: when typehinted with discord.User, mentioning the bot
        # gives ClientUser instead of User
        c = collections.Counter(type(m) for m in mentions)

        description = [
            '{} mentions: {}'.format(
                k.__name__.replace('Channel', ''),
                v
            )
            for k, v in c.most_common()
        ]
        description = '\n'.join(description)

        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot),
            description=description
        )

        await ctx.send(text, embed=embed)










def setup(bot):
    bot.add_cog(Testing(bot))
