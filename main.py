try:
    from discord.ext import commands
    import discord
except ModuleNotFoundError:
    print('The discord.py package is missing!')
    while True:
        pass

import asyncio
import os
import time

from bot import database
from bot import settings
from bot.other import discordlogger

cogs = [
    'bot.commands.administrative',
    'bot.commands.background',
    'bot.commands.ciphers',
    'bot.commands.embedtools',
    'bot.commands.games',
    'bot.commands.info',
    'bot.commands.nocategory',
    'bot.commands.notes',
    'bot.commands.mathematics',
    'bot.commands.randomization',
]


def main():
    # Set up databases
    database.setup()

    # Set up client
    TOKEN = os.environ['PyDiscordBotToken']

    logger = discordlogger.get_logger()

    settings.setup()

    intents = discord.Intents.default()

    client = commands.Bot(
        command_prefix=settings.get_setting('prefix'),
        intents=intents
    )


    @client.event
    async def on_connect():
        print(time.strftime(
            'Connection: Connected to Discord, %c UTC',
            time.gmtime()))


    @client.event
    async def on_disconnect():
        print(time.strftime(
            'Connection: Lost connection to Discord, %c UTC',
            time.gmtime()))


    @client.event
    async def on_ready():
        print(time.strftime(
            'Bot is ready, %c UTC',
            time.gmtime()))
        username = 'Logged in as ' + client.user.name
        user_id = client.user.id
        print(
            username,
            user_id,
            '-' * max(len(username), len(str(user_id))),
            sep='\n'
        )


    @client.event
    async def on_resumed():
        """Unknown event."""
        print('Resuming session.')


    for name in cogs:
        client.load_extension(name)

    loop = asyncio.get_event_loop()
    bot_args = [TOKEN]
    bot_kwargs = dict()

    try:
        loop.run_until_complete(client.start(*bot_args, **bot_kwargs))
    except Exception as e:
        logger.exception('Exception raised in bot')
    finally:
        loop.run_until_complete(client.close())
        loop.close()


if __name__ == '__main__':
    main()
