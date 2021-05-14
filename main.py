#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import argparse
import asyncio
import collections
import contextlib
import datetime
import time
import os

import aiohttp
import discord
from discord.ext import commands
import discord_slash as dslash
import inflect
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
import pytz

from bot import checks
from bot.database import BotDatabaseMixin
from bot import errors, utils
from bot.other import discordlogger

DISABLED_INTENTS = (
    'bans', 'integrations', 'webhooks', 'invites',
    'voice_states', 'typing'
)


class TheGameBot(BotDatabaseMixin, commands.Bot):
    EXT_LIST = [
        f'bot.cogs.{c}' for c in (
            'settings',  # dependency of a lot of things
            'administrative',
            'background',
            'ciphers',
            'economy',
            'eh',
            'embedding',
            'games',
            'graphing',
            'guildirish',
            'guildsignal',
            'images',
            'messagetracker',  # dependency of info
            'info',  # dependency of helpcommand
            'helpcommand',
            'mathematics',
            'moderation',
            'notes',
            'prefix',
            'randomization',
            'reminders',
            'tags',
            'timezones',
            'undefined',
            'uptime',
        )
    ] + ['jishaku']

    def __init__(self, *args, **kwargs):
        super().__init__(super().get_prefix, *args, **kwargs)

        # Allow case-insensitive references to cogs
        # (see "?tag case insensitive cogs" on the discord.py server)
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()

        with utils.update_text('Initializing global checks',
                               'Initialized global checks'):
            checks.setup(self)

        # Add botvars
        with utils.update_text('Adding botvars',
                               'Added botvars'):
            self.session = aiohttp.ClientSession()
            self.inflector = inflect.engine()
            self.info_bootup_time = 0
            self.info_processed_commands = collections.defaultdict(int)
            self.timezones_users_inputting = set()
            self.uptime_downtimes = collections.deque()
            self.uptime_last_connect = datetime.datetime.now().astimezone()
            self.uptime_last_connect_adjusted = self.uptime_last_connect
            self.uptime_last_disconnect = self.uptime_last_connect
            self.uptime_total_downtime = datetime.timedelta()
            self.uptime_is_online = False

        # Setup slash command system
        with utils.update_text('Adding slash command extension',
                               'Added slash command extension'):
            self.slash = dslash.SlashCommand(self)

        # Load extensions
        for i, name in enumerate(self.EXT_LIST, start=1):
            print(f'Loading extension {i}/{len(self.EXT_LIST)}',
                  end='\r', flush=True)
            self.load_extension(name)
        print(f'Loaded all extensions         ')

    def get_cog(self, name):
        cog = super().get_cog(name)
        if cog is None and name.lower() == 'settings':
            raise errors.SettingsNotFound()
        return cog

    async def is_owner(self, user):
        return (await super().is_owner(user)
                or user.id in self.get_cog('Settings').get('owner_ids'))

    async def localize_datetime(self, user_id, dt, prefer_utc=True):
        """Localize a datetime to the user's region from the database,
        if they have one assigned.

        The datetime can be either naive or aware;
        the former is assumed to be in UTC.

        Always returns an aware timezone.

        Args:
            user_id (int): The ID of the user to localize the datetime to.
            dt (datetime.datetime): The datetime to localize.
            prefer_utc (bool): If the datetime has a timezone,
                localize to UTC first before going to their timezone.
                This results in datetimes always being UTC if the user
                does not have a timezone set.

        Returns:
            datetime.datetime

        """
        # Resource: https://medium.com/swlh/making-sense-of-timezones-in-python-16d8ae210c1c
        timezone = await self.dbusers.get_timezone(user_id)

        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        elif prefer_utc:
            dt = dt.astimezone(pytz.UTC)

        if timezone is not None:
            dt = dt.astimezone(timezone)

        return dt

    async def restart(self):
        """Create a file named RESTART and logout.

        The batch file running the script loop should detect
        and recognize to rerun the bot again.

        """
        open('RESTART', 'w').close()
        return await self.close()

    async def setup(self):
        """Do any asynchronous setup the bot needs."""
        with utils.update_text('Setting up databases',
                               'Set up databases'):
            await self.db_setup()

    async def start(self, *args, **kwargs):
        logger = discordlogger.get_logger()
        print('Starting bot')
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self.dbpool)
            await stack.enter_async_context(self.session)
            try:
                await super().start(*args, **kwargs)
            except KeyboardInterrupt:
                logger.info('KeyboardInterrupt: closing bot')
            except Exception:
                logger.exception('Exception raised in bot')
            finally:
                await self.close()

    async def try_user(self, id):
        return self.get_user(id) or await self.fetch_user(id)


async def main():
    start_time = time.perf_counter()

    parser = argparse.ArgumentParser()
    parser.add_argument('-M', '--members', action='store_true',
                        help='Enable privileged members intent.')
    parser.add_argument('-P', '--presences', action='store_true',
                        help='Enable privileged presences intent.')

    args = parser.parse_args()

    logger = discordlogger.get_logger()

    token = os.getenv('PyDiscordBotToken')
    if token is None:
        s = 'Could not get token from environment.'
        logger.error(s)
        return print(s)

    # Use a non-GUI based backend for matplotlib
    matplotlib.use('Agg')
    mplstyle.use(['data/discord.mplstyle', 'fast'])

    # Set up client
    intents = discord.Intents.default()
    intents.members = args.members
    intents.presences = args.presences
    for attr in DISABLED_INTENTS:
        setattr(intents, attr, False)

    bot = TheGameBot(intents=intents)
    await bot.setup()

    async def bootup_time(bot, start_time):
        """Calculate the bootup time of the bot."""
        await bot.wait_until_ready()
        bot.info_bootup_time = time.perf_counter() - start_time

    bot.loop.create_task(bootup_time(bot, start_time))

    await bot.start(token)


if __name__ == '__main__':
    asyncio.run(main())
