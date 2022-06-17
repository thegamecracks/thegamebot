#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
import os
from typing import Union

import abattlemetrics as abm
from discord.ext import commands

from main import TheGameBot

abm_log = logging.getLogger('abattlemetrics')
abm_log.setLevel(logging.INFO)
if not abm_log.hasHandlers():
    handler = logging.FileHandler(
        'abattlemetrics.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    abm_log.addHandler(handler)


def format_hour_and_minute(seconds: Union[float, int]) -> str:
    seconds = round(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02d}h'


# Base cog
class SignalHill(commands.Cog):
    """Commands for Signal Hill."""
    qualified_name = 'Signal Hill'

    # HACK: filled in setup() so we can have a class attribute
    GUILD_ID: int
    BM_SERVER_ID_INA: int

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.bm_client = abm.BattleMetricsClient(
            self.bot.session,
            token=os.getenv('BattlemetricsToken')
        )

    @property
    def guild(self):
        return self.bot.get_guild(self.GUILD_ID)


# noinspection PyProtectedMember
async def setup(bot: TheGameBot):
    settings = bot.get_settings()
    SignalHill.GUILD_ID = settings.get('signal_hill', 'guild_id')
    SignalHill.BM_SERVER_ID_INA = settings.get('signal_hill', 'ina_server_id')

    from . import status, giveaway

    cogs = (
        status._SignalHill_Status,
        giveaway._SignalHill_Giveaway
    )

    base = SignalHill(bot)
    await bot.add_cog(base)

    for cls in cogs:
        cog = cls(bot, base)
        await bot.add_cog(cog)
        for c in cog.get_commands():
            c.injected_cog = 'SignalHill'
