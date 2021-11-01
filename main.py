#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import argparse
import asyncio
import collections
import datetime
import os
import sys
import time

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
import inflect
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle
import pytz

from bot import checks
from bot.database import BotDatabaseMixin
from bot import errors, utils
from bot.other import discordlogger

USE_RESTART_FILE = False

logger = discordlogger.get_logger()


class TheGameBot(BotDatabaseMixin, commands.Bot):
    EXT_LIST = [
        'bot.cogs.' + c for c in (
            'settings',  # dependency of a lot of things
            'administrative',
            'background',
            'ciphers',
            'dbevents',
            'economy',
            'eh',
            'embedding',
            'gamecog',
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
            'prog',
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
            self.dbevents_cleaned_up = False
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

    async def localize_datetime(
            self, user, dt, assume_utc=True, return_row=False):
        """Localize a datetime to the user's region from the database,
        if they have one assigned.

        The datetime can be either naive or aware;
        the former is assumed to be in UTC if `assume_utc` is True.

        Always returns an aware timezone.

        Args:
            user (Union[int, sqlite3.Row]):
                Either the ID of the user or their database entry.
                Technically the database entry could be any object so long
                as the "id" and "timezone" keys exist.
            dt (datetime.datetime): The datetime to localize.
            assume_utc (bool):
                If True, assumes naive datetimes to be in UTC.
                If False, assumes naive datetimes are in the
                user's timezone if available, UTC otherwise.
            return_row (bool): If true, return the user's database
                entry along with the datetime.
                If `user` is not an integer, this will return the same object.

        Returns:
            datetime.datetime: The localized datetime (always aware).
            Tuple[datetime.datetime, sqlite3.Row]:
                The localized datetime along with the user's database entry
                if return_row is True.

        """
        # Resource: https://medium.com/swlh/making-sense-of-timezones-in-python-16d8ae210c1c
        if isinstance(user, int):
            user = await self.dbusers.get_user(user)
        timezone = await self.dbusers.convert_timezone(user)

        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
            assume_utc = True

        if timezone is not None:
            if assume_utc:
                dt = dt.astimezone(timezone)
            else:
                dt = timezone.localize(dt.replace(tzinfo=None))

        if return_row:
            return dt, user
        return dt

    async def restart(self):
        """Close the bot and inform the parent process
        that the bot should be restarted.
        """
        if USE_RESTART_FILE:
            open('RESTART', 'w').close()
        return await self.close()

    async def shutdown(self):
        """Close the bot and inform the parent process
        that the bot should shut down.
        """
        if not USE_RESTART_FILE:
            open('SHUTDOWN', 'w').close()
        return await self.close()

    async def setup(self):
        """Do any asynchronous setup the bot needs."""
        with utils.update_text('Setting up databases',
                               'Set up databases'):
            await self.db_setup()

        with utils.update_text('Syncing slash commands',
                               'Synced slash commands'):
            await self.create_slash_commands()

    async def start(self, *args, **kwargs):
        logger = discordlogger.get_logger()
        print('Starting bot')
        async with self.dbpool, self.session:
            try:
                await super().start(*args, **kwargs)
            except KeyboardInterrupt:
                logger.info('KeyboardInterrupt: closing bot')
            finally:
                await self.close()

    async def strftime_user(
            self, user, dt: datetime.datetime, *args,
            return_row=False, respect_settings=True, **kwargs):
        """A version of utils.strftime_zone() that automatically
        localizes a datetime to a given user and censors the
        timezone info if needed.

        Extra arguments are passed into utils.strftime_zone().

        Args:
            user (Union[int, sqlite3.Row]):
                Either the ID of the user or their database entry.
                Technically the database entry could be any object so long
                as the "id", "timezone", and "timezone_public" keys exist.
            dt (datetime.datetime): The datetime to localize.
            return_row (bool): If true, return the user's database
                entry along with the datetime.
                If `user` is not an integer, this will return the same object.
            respect_settings (bool): If False, this will skip censoring
                the timezone even if their settings ask for it.

        Returns:
            str

        """
        dt, user = await self.localize_datetime(user, dt, return_row=True)

        if respect_settings and not user['timezone_public']:
            dt = dt.replace(tzinfo=None)

        s = utils.strftime_zone(dt, *args, **kwargs)

        if return_row:
            return s, user
        return s


async def main():
    load_dotenv(override=True)

    start_time = time.perf_counter()

    parser = argparse.ArgumentParser()
    parser.add_argument('-M', '--members', action='store_true',
                        help='Enable privileged members intent.')
    parser.add_argument('-P', '--presences', action='store_true',
                        help='Enable privileged presences intent.')

    args = parser.parse_args()

    token = os.getenv('BotToken')
    if token is None:
        s = 'Could not get token from environment.'
        logger.error(s)
        return print(s)

    # Use a non-GUI based backend for matplotlib
    matplotlib.use('Agg')
    mplstyle.use(['data/discord.mplstyle', 'fast'])

    # Set up client
    intents = discord.Intents(
        bans=False,
        emojis_and_stickers=True,
        guilds=True,
        integrations=False,
        invites=False,
        members=args.members,
        messages=True,
        presences = args.presences,
        reactions=True,
        typing=False,
        voice_states=False,
        webhooks=False
    )

    bot = TheGameBot(intents=intents, case_insensitive=True, strip_after_prefix=True)

    async def bootup_time(bot, start_time):
        """Calculate the bootup time of the bot."""
        await bot.wait_until_ready()
        bot.info_bootup_time = time.perf_counter() - start_time

    bot.loop.create_task(bootup_time(bot, start_time))

    try:
        await bot.start(token)
    finally:
        settings = bot.get_cog('Settings')
        if settings is not None:
            settings.save()


if __name__ == '__main__':
    # https://github.com/encode/httpx/issues/914#issuecomment-622586610
    # Fixes WinError 10038 from mcstatus and "Event loop not closed"
    if sys.version_info >= (3, 8) and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except BaseException:
        logger.exception('Exception logged by asyncio.run()')
