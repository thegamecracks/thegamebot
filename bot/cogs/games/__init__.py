#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
from typing import Optional

import discord
from discord.ext import commands

from main import TheGameBot


def min_sec(seconds: float) -> str:
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f'{minutes:.0f}:{seconds:06.3f}s'
    return f'{seconds:.3f}s'


class EditViewMixin:
    message: discord.Message

    async def edit(self, interaction: Optional[discord.Interaction], *args, **kwargs):
        """Edit the original message with a potential interaction."""
        if interaction is None:
            await self.message.edit(*args, **kwargs)
        elif interaction.response.is_done():
            await interaction.edit_original_response(*args, **kwargs)
        else:
            await interaction.response.edit_message(*args, **kwargs)


class TimeoutView(discord.ui.View):
    start_time: datetime.datetime

    @property
    def elapsed(self) -> datetime.timedelta:
        return discord.utils.utcnow() - self.start_time

    @property
    def elapsed_str(self) -> str:
        return min_sec(self.elapsed.total_seconds())

    @property
    def timeout_timestamp(self) -> str:
        ends = datetime.datetime.now() + datetime.timedelta(seconds=self.timeout)  # type: ignore
        return discord.utils.format_dt(ends, style='R')

    @property
    def timeout_done(self) -> str:
        timestamp = discord.utils.format_dt(datetime.datetime.now(), style='R')
        return f'(ended {timestamp} from inactivity)'

    @property
    def timeout_in(self) -> str:
        return f'(ends {self.timeout_timestamp})'


class Games(commands.Cog):
    """A set of games and commands related to games."""
    def __init__(self, bot: TheGameBot):
        self.bot = bot


async def setup(bot: TheGameBot):
    from . import (
        hangman,
        memory,
        minesweeper,
        rps
    )

    cogs = (
        hangman._Hangman,
        memory._Memory,
        minesweeper._Minesweeper,
        rps._RPS
    )

    base = Games(bot)
    await bot.add_cog(base)
    for cls in cogs:
        cog = cls(bot, base)
        await bot.add_cog(cog)
        for c in cog.get_commands():
            c.injected_cog = 'Games'
