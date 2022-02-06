#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import argparse
import asyncio
import os
import sys

import disnake
from disnake.ext import commands
from dotenv import load_dotenv

from bot import errors, discordlogger

EXT_LIST = [
    'bot.cogs.' + c for c in (
        'settings',  # dependency
        'eh',
        'games',
        'helpcommand',
        'test'
    )
]
EXT_LIST.append('jishaku')

logger = discordlogger.get_logger()


class TheGameBot(commands.Bot):
    def get_bot_color(self) -> int:
        """Gets the bot's set color from settings.

        :raises bot.errors.SettingsNotFound:
            The Settings cog was not loaded.
        :raises KeyError:
            The settings file is missing the general-color key.

        """
        settings = self.get_settings()
        return settings.get('general', 'color')

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

    async def start(self, *args, **kwargs):
        n_extensions = len(EXT_LIST)
        for i, name in enumerate(EXT_LIST, start=1):
            state = f'Loading extension {i}/{n_extensions}\r'
            print(state, end='', flush=True)
            self.load_extension(name)
        print('Loaded all extensions      ')

        return await super().start(*args, **kwargs)


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

    # Set up client
    intents = disnake.Intents(
        bans=False,
        emojis_and_stickers=True,
        guilds=True,
        integrations=False,
        invites=False,
        members=args.members,
        messages=True,
        presences=args.presences,
        reactions=True,
        typing=False,
        voice_states=False,
        webhooks=False
    )

    bot = TheGameBot(
        intents=intents,
        command_prefix=';;',
        case_insensitive=True,
        strip_after_prefix=True
    )

    await bot.start(token)


if __name__ == '__main__':
    # https://github.com/encode/httpx/issues/914#issuecomment-622586610
    # Fixes WinError 10038 from mcstatus and "Event loop not closed"
    if sys.version_info >= (3, 8) and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
