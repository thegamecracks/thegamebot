#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import time

import discord
from discord.ext import commands

from main import TheGameBot


class EventHandlers(commands.Cog):
    """Event handlers for the bot."""
    qualified_name = 'Event Handlers'

    EVENTS = (
        'on_connect',
        'on_disconnect',
        'on_ready',
        'on_resumed',
    )

    def __init__(self, bot):
        self.bot = bot

        self._old_events = {}
        self.setup_events()

    def cog_unload(self):
        self.teardown_events()

    def setup_events(self):
        """Add the cog's custom event handlers to the bot."""
        for name in self.EVENTS:
            coro = getattr(self, name)
            old = getattr(self.bot, name, None)
            self.bot.event(coro)
            if old is not None:
                self._old_events[name] = old

    def teardown_events(self):
        """Restore the bot's original event handlers."""
        for name, coro in self._old_events.items():
            setattr(self.bot, name, coro)

    # Events
    async def on_connect(self):
        print(time.strftime(
            'Connection: Connected to Discord, %c',
            time.localtime()))

    async def on_disconnect(self):
        print(time.strftime(
            'Connection: Lost connection to Discord, %c',
            time.localtime()))

    async def on_ready(self):
        s = time.strftime(
            'Bot is ready, %c',
            time.localtime()
        )
        line = '-' * len(s)
        print(s, line, sep='\n')

    async def on_resumed(self):
        s = time.strftime(
            'Connection: Reconnected to Discord, %c',
            time.localtime()
        )
        print(s)


async def setup(bot: TheGameBot):
    await bot.add_cog(EventHandlers(bot))
