#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands

from main import Context, TheGameBot


class Test(commands.Cog):
    def __init__(self, bot: TheGameBot):
        self.bot = bot

    @commands.command()
    async def test(self, ctx: Context):
        settings = ctx.bot.get_settings()
        color: int = settings.get('general', 'color')

        await ctx.send(embed=discord.Embed(
            color=color,
            description='Hello world!'
        ))


async def setup(bot: TheGameBot):
    await bot.add_cog(Test(bot))
