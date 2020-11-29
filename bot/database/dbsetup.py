"""Provides functions for setting up the bot's databases."""
import asyncio
import sqlite3

from discord.ext import commands

from . import database
from . import guilddatabase
from . import notedatabase
from . import prefixdatabase
from . import reminderdatabase
from . import userdatabase
from bot import settings

DATABASE_USERS = './data/userdb.db'


def get_prefix():
    """Return a function for getting the bot prefix.
    Should be used in bot.command_prefix.

    This also allows mentioning the bot.

    Usage:
        commands.Bot(command_prefix=get_prefix())

    """
    db = prefixdatabase.PrefixDatabase(DATABASE_USERS)

    async def inner(bot, message):
        guild = message.guild

        # If in DMs, get default prefix or use prefix-less invokation
        if guild is None:
            return commands.when_mentioned_or(
                settings.get_setting('default_prefix')
            )(bot, message)

        # Else, fetch guild prefix
        guild_id = guild.id
        await db.add_prefix(guild_id, add_guild=True)
        prefix = await db.get_prefix(guild_id)

        if prefix is not None:
            return commands.when_mentioned_or(prefix)(bot, message)
        return commands.when_mentioned(bot, message)

    return inner


def setup_database_users(connection):
    "Setup the tables for the Users database."
    userdatabase.setup(connection)
    notedatabase.setup(connection)
    reminderdatabase.setup(connection)
    print('Verified user database')
    guilddatabase.setup(connection)
    prefixdatabase.setup(connection)
    print('Verified guild database')


def setup():
    setup_database_users(sqlite3.connect(DATABASE_USERS))
