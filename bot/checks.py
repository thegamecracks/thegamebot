#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from discord.ext import commands


# Checks
def used_in_guild(*guild_ids):
    """Check if a command was used in a given set of guilds."""
    async def predicate(ctx):
        await commands.guild_only().predicate(ctx)
        return ctx.guild.id in guild_ids

    return commands.check(predicate)
