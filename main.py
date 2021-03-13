import argparse
import asyncio
import collections
import datetime
import time
import os

import discord
from discord.ext import commands
import discord_slash as dslash
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle

from bot import checks
from bot.database import BotDatabaseMixin
from bot import eventhandlers
from bot import settings
from bot import utils
from bot.other import discordlogger

cogs = [
    f'bot.commands.{c}' for c in (
        'administrative',
        'background',
        'ciphers',
        'embedding',
        'games',
        'graphing',
        'guildirish',
        'images',
        'messagetracker',  # dependency of info
        'info',  # dependency of helpcommand
        'helpcommand',
        'mathematics',
        'notes',
        'prefix',
        'randomization',
        'reminders',
        'undefined',
        'uptime',
    )
]
cogs.extend(('jishaku',))

disabled_intents = [
    'bans', 'integrations', 'webhooks', 'invites',
    'voice_states', 'typing'
]



class Bot(BotDatabaseMixin, commands.Bot):
    """A custom version of Bot that allows case-insensitive references
    to cogs. See "?tag case insensitive cogs" on the discord.py server.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(super().get_prefix, *args, **kwargs)
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()

    async def restart(self):
        """Create a file named RESTART and logout.

        The batch file running the script loop should detect
        and recognize to rerun the bot again.

        """
        open('RESTART', 'w').close()
        return await self.logout()


async def main():
    start_time = time.perf_counter()

    parser = argparse.ArgumentParser()
    parser.add_argument('-M', '--members', action='store_true',
                        help='Enable privileged members intent.')
    parser.add_argument('-P', '--presences', action='store_true',
                        help='Enable privileged presences intent.')

    args = parser.parse_args()

    TOKEN = os.getenv('PyDiscordBotToken')
    if TOKEN is None:
        return print('Could not get token from environment.')

    # Use a non-GUI based backend for matplotlib
    matplotlib.use('Agg')
    mplstyle.use(['data/discord.mplstyle', 'fast'])

    # Set up client
    logger = discordlogger.get_logger()
    settings.setup()

    intents = discord.Intents.default()
    intents.members = args.members
    intents.presences = args.presences
    for attr in disabled_intents:
        setattr(intents, attr, False)

    bot = Bot(intents=intents)

    with utils.update_text('Setting up databases',
                           'Set up databases'):
        await bot.db_setup()
    with utils.update_text('Initializing global checks',
                           'Initialized global checks'):
        checks.setup(bot)
    with utils.update_text('Registering event handlers',
                           'Registered event handlers'):
        eventhandlers.setup(bot)

    # Add botvars
    with utils.update_text('Adding botvars',
                           'Added botvars'):
        bot.info_bootup_time = 0
        bot.info_processed_commands = collections.defaultdict(int)
        bot.uptime_last_connect = datetime.datetime.now().astimezone()
        bot.uptime_last_connect_adjusted = bot.uptime_last_connect
        bot.uptime_last_disconnect = bot.uptime_last_connect
        bot.uptime_total_downtime = datetime.timedelta()
        bot.uptime_is_online = False

    # Setup slash command system
    with utils.update_text('Adding slash command extension',
                           'Added slash command extension'):
        bot.slash = dslash.SlashCommand(bot)

    # Load extensions
    for i, name in enumerate(cogs, start=1):
        print(f'Loading extension {i}/{len(cogs)}', end='\r', flush=True)
        bot.load_extension(name)
    print(f'Loaded all extensions         ')

    # Clean up
    del parser, args, attr, i, name

    async def bootup_time(bot, start_time):
        """Calculate the bootup time of the bot."""
        await bot.wait_until_ready()
        bot.info_bootup_time = time.perf_counter() - start_time

    # Create tasks
    loop = asyncio.get_running_loop()

    loop.create_task(bootup_time(bot, start_time))

    # Start the bot
    print('Starting bot')
    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt: closing bot')
    except Exception:
        logger.exception('Exception raised in bot')
    finally:
        await bot.close()


if __name__ == '__main__':
    asyncio.run(main())
