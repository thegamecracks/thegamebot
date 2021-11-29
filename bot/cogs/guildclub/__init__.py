#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from discord.ext import commands


class CSClub(commands.Cog):
    """Commands for CS Club."""
    qualified_name = 'CS Club'

    GUILD_ID = 901195466656604211

    def __init__(self, bot):
        self.bot = bot

    @property
    def guild(self):
        return self.bot.get_guild(self.GUILD_ID)


def setup(bot):
    from . import (
        suggestions
    )

    cogs = (
        suggestions._CSClub_Suggestions,
    )

    base = CSClub(bot)
    bot.add_cog(base)

    for cls in cogs:
        cog = cls(bot, base)
        bot.add_cog(cog)
        for c in cog.get_commands():
            c.injected_cog = 'CSClub'
