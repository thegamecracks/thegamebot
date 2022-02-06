#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
from typing import Optional

import disnake
from disnake.ext import commands


def min_sec(seconds: float) -> str:
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f'{minutes:.0f}:{seconds:06.3f}s'
    return f'{seconds:.3f}s'


class EditViewMixin:
    message: disnake.Message

    async def edit(self, interaction: Optional[disnake.MessageInteraction], *args, **kwargs):
        """Edit the original message with a potential interaction."""
        if interaction is None:
            await self.message.edit(*args, **kwargs)
        elif interaction.response.is_done():
            await interaction.edit_original_message(*args, **kwargs)
        else:
            await interaction.response.edit_message(*args, **kwargs)


class TimeoutView(disnake.ui.View):
    start_time: datetime.datetime

    @property
    def elapsed(self) -> datetime.timedelta:
        return disnake.utils.utcnow() - self.start_time

    @property
    def elapsed_str(self) -> str:
        return min_sec(self.elapsed.total_seconds())

    @property
    def timeout_timestamp(self) -> str:
        ends = datetime.datetime.now() + datetime.timedelta(seconds=self.timeout)  # type: ignore
        return disnake.utils.format_dt(ends, style='R')

    @property
    def timeout_done(self) -> str:
        timestamp = disnake.utils.format_dt(datetime.datetime.now(), style='R')
        return f'(ended {timestamp} from inactivity)'

    @property
    def timeout_in(self) -> str:
        return f'(ends {self.timeout_timestamp})'


class Games(commands.Cog):
    """A set of games and commands related to games."""
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
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
    bot.add_cog(base)
    for cls in cogs:
        cog = cls(bot, base)
        bot.add_cog(cog)
        for c in cog.get_commands():
            c.injected_cog = 'Games'
