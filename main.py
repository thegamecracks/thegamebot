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

from bot import settings
from bot.other import discordlogger


def main():
    TOKEN = os.environ['PyDiscordBotToken']

    logger = discordlogger.get_logger()

    settings.setup()

    client = commands.Bot(command_prefix=settings.get_setting('prefix'))


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


    client.load_extension('bot.commands.administrative')
    client.load_extension('bot.commands.background')
    client.load_extension('bot.commands.ciphers')
    client.load_extension('bot.commands.embedtools')
    client.load_extension('bot.commands.games')
    client.load_extension('bot.commands.info')
    client.load_extension('bot.commands.nocategory')
    client.load_extension('bot.commands.mathematics')
    client.load_extension('bot.commands.randomization')

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
