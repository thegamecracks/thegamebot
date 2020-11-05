import argparse
import asyncio
import os

import discord
from discord.ext import commands

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
    'bot.commands.images',
    'bot.commands.info',
    'bot.commands.notes',
    'bot.commands.prefix',
    'bot.commands.mathematics',
    'bot.commands.randomization',
    'bot.commands.reminders',
    'bot.commands.undefined',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-M', '--members', action='store_true',
                        help='Enable privileged members intent.')
    parser.add_argument('-P', '--presences', action='store_true',
                        help='Enable privileged presencesintent.')

    args = parser.parse_args()

    # Set up databases
    database.setup()

    # Set up client
    TOKEN = os.getenv('PyDiscordBotToken')

    logger = discordlogger.get_logger()

    settings.setup()

    intents = discord.Intents.default()
    intents.members = args.members
    intents.presences = args.presences

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

    print('Starting bot')
    try:
        loop.run_until_complete(bot.start(*bot_args, **bot_kwargs))
    except Exception as e:
        logger.exception('Exception raised in bot')
    finally:
        loop.run_until_complete(bot.close())
        loop.close()


if __name__ == '__main__':
    main()
