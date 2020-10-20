import asyncio
import os

from discord.ext import commands
import discord
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
    'bot.commands.info',
    'bot.commands.notes',
    'bot.commands.prefix',
    'bot.commands.mathematics',
    'bot.commands.randomization',
    'bot.commands.undefined',
]


def main():
    # Set up databases
    database.setup()

    # Set up client
    TOKEN = os.environ['PyDiscordBotToken']

    logger = discordlogger.get_logger()

    settings.setup()

    intents = discord.Intents.default()
    intents.presences = False
    intents.members = False

    bot = commands.Bot(
        command_prefix=database.get_prefix(),
        help_command=helpcommand.HelpCommand(),
        intents=intents
    )

    eventhandlers.setup(bot)

    for name in cogs:
        bot.load_extension(name)

    loop = asyncio.get_event_loop()
    bot_args = [TOKEN]
    bot_kwargs = dict()

    try:
        loop.run_until_complete(bot.start(*bot_args, **bot_kwargs))
    except Exception as e:
        logger.exception('Exception raised in bot')
    finally:
        loop.run_until_complete(bot.close())
        loop.close()


if __name__ == '__main__':
    main()
