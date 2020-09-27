import asyncio

import discord
from discord.ext import commands

from bot.classes import paginator


class Games(commands.Cog):
    qualified_name = 'Games'
    description = 'Commands with interactive games.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(name='testpages')
    async def client_testpages(self, ctx):
        embeds = [
            discord.Embed(title="test page 1",
                description="This is just some test content!", color=0x115599),
            discord.Embed(title="test page 2",
                description="Nothing interesting here.", color=0x5599ff),
            discord.Embed(title="test page 3",
                description="Why are you still here?", color=0x191638)
        ]

        pages = paginator.RemovableReactBotEmbedPaginator(ctx, embeds)
        await pages.run()










def setup(bot):
    bot.add_cog(Games(bot))
