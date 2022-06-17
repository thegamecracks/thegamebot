#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import argparse
import asyncio
import collections
import datetime
import logging
import os
import pathlib
import sqlite3
import sys
import time
import typing
import zoneinfo

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
import inflect
import matplotlib
import matplotlib.style as mplstyle

from bot import database, errors

EXT_LIST = [
    'bot.cogs.' + c for c in (
        'settings',  # dependency
        'dbevents',
        'eh',
        'games',
        'graphing',
        'guildsignal',
        'helpcommand',
        'info',
        'moderation',
        'notes',
        'owner',
        'prefix',
        'reminders',
        'tags',
        'test',
        'timezones',
        'uptime'
    )
]
EXT_LIST.append('jishaku')

logger = logging.getLogger('discord')
logger.handlers.clear()  # fixes duplicate logs from stream handler
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(
    filename='discord.log', encoding='utf-8', mode='w'
)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')
)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_handler.setFormatter(
    logging.Formatter('%(levelname)s in %(name)s: %(message)s')
)
logger.addHandler(stream_handler)


class UserWithTimezone(typing.TypedDict):
    user_id: int
    timezone: str


class TheGameBot(commands.Bot):
    """

    Attributes
    ----------
    dbpool: The pool for handling access to multiple database connections.
        This is automatically opened during `self.start()`.
    db: A Database instance for accessing `DATABASE_MAIN_FILE`.
    inflector: An `inflect.engine()` instance for handling grammar.

    """
    DATABASE_MAIN_FILE = 'data/thegamebot.db'
    DATABASE_MAIN_SCHEMA = 'data/thegamebot.sql'

    def __init__(self, *args, file_on_restart=False, **kwargs):
        self.file_on_restart = file_on_restart
        self.dbpool = database.ConnectionPool()
        self.db = database.Database(self.dbpool, self.DATABASE_MAIN_FILE)
        self.inflector = inflect.engine()

        self.dbevents_cleaned_up = False
        self.info_bootup_time = 0
        self.info_processed_commands = collections.defaultdict(int)
        self.session = aiohttp.ClientSession()
        self.uptime_downtimes = collections.deque()
        self.uptime_last_connect = datetime.datetime.now().astimezone()
        self.uptime_last_connect_adjusted = self.uptime_last_connect
        self.uptime_last_disconnect = self.uptime_last_connect
        self.uptime_total_downtime = datetime.timedelta()
        self.uptime_is_online = False

        super().__init__(
            *args,
            command_prefix='xkcd',  # not actually needed
            **kwargs
        )

    def setup_db(self):
        """Initialize the database if it does not exist."""
        if pathlib.Path(self.DATABASE_MAIN_FILE).exists():
            return

        with open(self.DATABASE_MAIN_SCHEMA) as f:
            script = f.read()

        conn = sqlite3.connect(self.DATABASE_MAIN_FILE)
        conn.executescript(script)
        conn.commit()
        conn.close()

    def get_bot_color(self) -> int:
        """A shorthand for getting the bot color from settings.

        If an error occurs while getting the setting, returns 0x000000.

        """
        try:
            settings = self.get_settings()
        except errors.SettingsNotFound:
            return 0

        return settings.get('general', 'color', 0)

    def get_user_color(self, user: discord.User | discord.Member):
        """Obtains the color of the given user.

        If the provided user is a discord.User, returns
        the bot's color instead of the default black.

        """
        if isinstance(user, discord.User):
            return self.get_bot_color()
        return user.color.value

    def get_default_prefix(self) -> str | None:
        """A shorthand for getting the default prefix from settings.

        If an error occurs while getting the prefix, returns None.

        """
        try:
            settings = self.get_settings()
        except errors.SettingsNotFound:
            return None

        return settings.get('general', 'default_prefix', None)

    async def get_prefix(self, message) -> list[str] | str | None:
        def wrap(*prefixes: str):
            if not prefixes or prefixes[0] is None:
                return commands.when_mentioned(self, message)
            return commands.when_mentioned_or(*prefixes)(self, message)

        if message.guild is None:
            return wrap(self.get_default_prefix())

        cog = self.get_cog('Prefix')
        if cog is None:
            return wrap(self.get_default_prefix())
        return wrap(await cog.fetch_prefix(message.guild.id))

    def get_settings(self):
        """ Retrieves the Settings cog.

        :rtype: :class:`bot.cogs.settings.Settings`
        :raises bot.errors.SettingsNotFound:
            The Settings cog was not loaded.

        """
        cog = self.get_cog('Settings')
        if cog is None:
            raise errors.SettingsNotFound()
        return cog

    async def localize_datetime(
        self, user: int | UserWithTimezone, dt: datetime.datetime
    ):
        """Localize a datetime to the user's region from the database,
        if they have one assigned.

        The datetime can be either naive or aware. If a naive datetime
        is given, it is interpreted in local time.

        If the user does not have a timezone set, the result is a datetime
        localized with `datetime.timezone.utc` instead of a
        :class:`zoneinfo.ZoneInfo`.

        :param user:
            Either the ID of the user or their database entry.
            Technically the database entry could be any dictionary
            with a "user_id" and "timezone" key.
        :param dt: The datetime to localize.
        :returns: The localized datetime (always aware).

        """
        if isinstance(user, int):
            where = {'user_id': user}
            await self.db.add_row('user', where, ignore=True)
            user = await self.db.get_one('user', 'user_id', 'timezone', where=where)
        else:
            where = {'user_id': user['user_id']}

        timezone: datetime.tzinfo = datetime.timezone.utc
        if user['timezone'] is not None:
            try:
                timezone = zoneinfo.ZoneInfo(user['timezone'])
            except zoneinfo.ZoneInfoNotFoundError:
                await self.db.update_rows('user', {'timezone': None}, where=where)
                raise

        if dt.tzinfo is None:
            dt = dt.astimezone()

        dt = dt.astimezone(timezone)

        return dt

    async def restart(self):
        if self.file_on_restart:
            open('RESTART', 'w').close()
        return await self.close()

    async def shutdown(self):
        if not self.file_on_restart:
            open('SHUTDOWN', 'w').close()
        return await self.close()


class Context(commands.Context[TheGameBot]):
    """A subclass of :class:`commands.Context` typed with the bot class."""


async def set_bootup_time(bot, start_time):
    """Calculate the bootup time of the bot."""
    await bot.wait_until_ready()
    bot.info_bootup_time = time.perf_counter() - start_time


async def main():
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-M', '--members', action='store_true',
        help='Enable privileged members intent.'
    )
    parser.add_argument(
        '-P', '--presences', action='store_true',
        help='Enable privileged presences intent.'
    )
    parser.add_argument(
        '--file-on-shutdown', action='store_true',
        help='Generate a SHUTDOWN file instead of a RESTART file.'
    )

    args = parser.parse_args()

    token = os.getenv('BotToken')
    if token is None:
        s = 'Could not get token from environment.'
        logger.error(s)
        return print(s)

    # Use a non-GUI based backend for matplotlib
    matplotlib.use('Agg')
    mplstyle.use(['data/discord.mplstyle', 'fast'])

    intents = discord.Intents(
        bans=False,
        emojis_and_stickers=True,
        guilds=True,
        integrations=False,
        invites=False,
        members=args.members,
        message_content=True,
        messages=True,
        presences=args.presences,
        reactions=True,
        typing=False,
        voice_states=False,
        webhooks=False
    )

    bot = TheGameBot(
        file_on_restart=not args.file_on_shutdown,
        intents=intents,
        case_insensitive=True,
        strip_after_prefix=True
    )

    asyncio.create_task(set_bootup_time(bot, time.perf_counter()))

    bot.setup_db()
    print('Initialized database')

    async with bot, bot.dbpool, bot.session:
        n_extensions = len(EXT_LIST)
        for i, name in enumerate(EXT_LIST, start=1):
            state = f'Loading extension {i}/{n_extensions}\r'
            print(state, end='', flush=True)
            await bot.load_extension(name)
        print('Loaded all extensions      ')

        await bot.start(token)


if __name__ == '__main__':
    # https://github.com/encode/httpx/issues/914#issuecomment-622586610
    # Fixes WinError 10038 from mcstatus and "Event loop not closed"
    if sys.version_info >= (3, 8) and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
