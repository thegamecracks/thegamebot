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
from bot import database
from bot import eventhandlers
from bot.commands import helpcommand
from bot import settings
from bot import utils
from bot.other import discordlogger

cogs = [
    'bot.commands.administrative',
    'bot.commands.background',
    'bot.commands.ciphers',
    'bot.commands.embedding',
    'bot.commands.games',
    'bot.commands.graphing',
    'bot.commands.guildirish',
    'bot.commands.images',
    'bot.commands.info',
    'bot.commands.notes',
    'bot.commands.prefix',
    'bot.commands.mathematics',
    'bot.commands.randomization',
    'bot.commands.reminders',
    'bot.commands.undefined',
    'jishaku',
]

disabled_intents = [
    'bans', 'integrations', 'webhooks', 'invites',
    'voice_states', 'typing'
]



class Bot(commands.Bot):
    """A custom version of Bot that allows case-insensitive references
    to cogs. See "?tag case insensitive cogs" on the discord.py server.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()


async def main():
    start_time = time.perf_counter()

    parser = argparse.ArgumentParser()
    parser.add_argument('-M', '--members', action='store_true',
                        help='Enable privileged members intent.')
    parser.add_argument('-P', '--presences', action='store_true',
                        help='Enable privileged presences intent.')

    args = parser.parse_args()

    # Set up databases
    database.setup()

    # Use a non-GUI based backend for matplotlib
    matplotlib.use('Agg')
    mplstyle.use(['data/discord.mplstyle', 'fast'])

    # Set up client
    TOKEN = os.getenv('PyDiscordBotToken')
    logger = discordlogger.get_logger()
    settings.setup()

    intents = discord.Intents.default()
    intents.members = args.members
    intents.presences = args.presences
    for attr in disabled_intents:
        setattr(intents, attr, False)

    bot = Bot(
        command_prefix=database.get_prefix(),
        help_command=helpcommand.HelpCommand(),
        intents=intents
    )

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
        bot.slash = dslash.SlashCommand(
            bot, auto_register=True, override_type=True
        )

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
