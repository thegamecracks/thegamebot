import argparse
import asyncio
import collections
import datetime
import os
import sys
import time

import aiohttp
import discord
from discord.ext import commands, ipc
import discord_slash as dslash
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.style as mplstyle

from bot import checks
from bot.database import BotDatabaseMixin
from bot import eventhandlers
from bot.commands import helpcommand
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
        'info',
        'ipc',
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
    def __init__(self, *args, run_ipc=True, **kwargs):
        super().__init__(super().get_prefix, *args, **kwargs)
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()

        ipc = None
        if run_ipc:
            ipc = ipc.Server(self, secret_key=os.getenv('PyDiscordBotIPCKey'))
        self.ipc = ipc

    async def on_ipc_ready(self):
        print('IPC is ready')

    async def on_ipc_error(self, endpoint, error):
        """Called upon an error being raised within an IPC route"""
        print('IPC endpoint', endpoint, 'raised an error:', error)


async def run_ipc_server(bot):
    """Start the bot's IPC server.

    This is basically a copy of ipc.Server.start except
    asynchronous methods are executed using async/await
    instead of loop.run_until_complete.

    """
    self = bot.ipc

    self.bot.dispatch("ipc_ready")

    self._server = aiohttp.web.Application()
    self._server.router.add_route("GET", "/", self.handle_accept)

    if self.do_multicast:
        self._multicast_server = aiohttp.web.Application()
        self._multicast_server.router.add_route("GET", "/", self.handle_multicast)

        await self._Server__start(self._multicast_server, self.multicast_port)

    await self._Server__start(self._server, self.port)


class IPCClientProcess:
    """Context manager to spawn a subprocess running
    the IPC client and webserver."""

    def __init__(self):
        self.proc = None

    async def __aenter__(self):
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, 'webserver\webserver.py',
            stdout=asyncio.subprocess.PIPE
        )

        loop = asyncio.get_running_loop()
        loop.create_task(self.relay())

        return self

    async def __aexit__(self, exc_type, exc_val, exc_traceback):
        proc, self.proc = self.proc, None
        proc.terminate()
        await proc.wait()

    async def relay(self):
        proc = self.proc
        while proc.returncode is None:
            stdout = await proc.stdout.readline()
            if stdout:
                print(stdout.decode(), end='')

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
    parser.add_argument(
        '-W', '--webserver', dest='ipc', action='store_true',
        help='Enable the bot webserver.'
    )

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

    bot = Bot(
        help_command=helpcommand.HelpCommand(),
        intents=intents,
        run_ipc=args.ipc
    )

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

    if args.ipc:
        # Start IPC server
        await run_ipc_server(bot)

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
    async with IPCClientProcess():
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
