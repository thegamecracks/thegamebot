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
    @commands.max_concurrency(1, commands.BucketType.channel)
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
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def client_multimath(
            self, ctx,
            players='only me',
            members: commands.Greedy[discord.User] = None):
        """Answer simple multiple-choice math expressions.

If the first parameter says "allow", you can then specify which other members are allowed to play, by mention or name:
> multimath allow Alice#1234 Bob
If no members are specified after "allow", anyone can play:
> multimath allow
Otherwise, only you can play:
> multimath"""
        if 'allow' in players.lower():
            if members:
                # Player whitelist
                users = members
                users.append(ctx.author)
            else:
                # All players
                users = True
        else:
            if members:
                # Argument error
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    'You cannot specify which members can play if you do '
                    'not allow others. See the help message for more info.'
                )
            else:
                # Solo
                users = None

        game = multimath.BotMultimathGame(ctx)

        await game.run(users=users)










def setup(bot):
    bot.add_cog(Games(bot))
