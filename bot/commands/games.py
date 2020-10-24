import asyncio

import discord
from discord.ext import commands

from bot.classes.games import multimath
from bot.classes import paginator


class Games(commands.Cog):
    qualified_name = 'Games'
    description = 'Commands with interactive games.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(name='testpages')
    @commands.cooldown(2, 30, commands.BucketType.channel)
    async def client_testpages(self, ctx):
        "Create a simple paginator."
        embeds = [
            discord.Embed(title="test page 1",
                description="This is just some test content!", color=0x115599),
            discord.Embed(title="test page 2",
                description="Nothing interesting here.", color=0x5599ff),
            discord.Embed(title="test page 3",
                description="Why are you still here?", color=0x191638)
        ]

        pages = paginator.RemovableReactBotEmbedPaginator(
            ctx, embeds)
        await pages.run()





    @commands.command(name='multimath')
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def client_multimath(
            self, ctx,
            allow_others: bool = False,
            members: commands.Greedy[discord.User] = None):
        """Answer simple multiple-choice math expressions.

allow_others: If yes, you can specify which other members are allowed
to play, either by mention or name. Otherwise, only you can play.
members: If you allowed others, you can specify which members can play.
If no members are specified, everyone can play."""
        if not allow_others:
            users = None
        elif members is None:
            users = True
        else:
            users = members
            users.append(ctx.author)

        game = multimath.BotMultimathGame(ctx)

        await game.run(users=users)










def setup(bot):
    bot.add_cog(Games(bot))
