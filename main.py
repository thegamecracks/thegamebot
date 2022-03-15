#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import argparse
import asyncio
import os
import pathlib
import sqlite3
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv
import inflect

from bot import database, discordlogger, errors

EXT_LIST = [
    'bot.cogs.' + c for c in (
        'settings',  # dependency
        'eh',
        'games',
        'helpcommand',
        'notes',
        'prefix',
        'test'
    )
]
EXT_LIST.append('jishaku')

logger = discordlogger.get_logger()


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

    def __init__(self, *args, **kwargs):
        self.dbpool = database.ConnectionPool()
        self.db = database.Database(self.dbpool, self.DATABASE_MAIN_FILE)
        self.inflector = inflect.engine()

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


async def main():
    load_dotenv(override=True)

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
        intents=intents,
        case_insensitive=True,
        strip_after_prefix=True
    )

    bot.setup_db()
    print('Initialized database')

    n_extensions = len(EXT_LIST)
    for i, name in enumerate(EXT_LIST, start=1):
        state = f'Loading extension {i}/{n_extensions}\r'
        print(state, end='', flush=True)
        await bot.load_extension(name)
    print('Loaded all extensions      ')

    async with bot, bot.dbpool:
        await bot.start(token)


if __name__ == '__main__':
    # https://github.com/encode/httpx/issues/914#issuecomment-622586610
    # Fixes WinError 10038 from mcstatus and "Event loop not closed"
    if sys.version_info >= (3, 8) and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
