"""Provides functions for setting up the bot's databases."""
import asyncio
import sqlite3

from discord.ext import commands

from . import database
from . import gamedatabase
from . import guilddatabase
from . import irishdatabase
from . import notedatabase
from . import prefixdatabase
from . import reminderdatabase
from . import userdatabase
from bot import settings
from bot import utils

DATABASE_USERS = './data/userdb.db'
DATABASE_IRISH = './data/irishdb.db'

GameDatabase = gamedatabase.GameDatabase(DATABASE_USERS)
GuildDatabase = guilddatabase.GuildDatabase(DATABASE_USERS)
IrishDatabase = irishdatabase.IrishDatabase(DATABASE_IRISH)
NoteDatabase = notedatabase.NoteDatabase(DATABASE_USERS)
PrefixDatabase = prefixdatabase.PrefixDatabase(DATABASE_USERS)
ReminderDatabase = reminderdatabase.ReminderDatabase(DATABASE_USERS)
UserDatabase = userdatabase.UserDatabase(DATABASE_USERS)


def get_prefix():
    """Return a function for getting the bot prefix.
    Should be used in bot.command_prefix.

    This also allows mentioning the bot.

    Usage:
        commands.Bot(command_prefix=get_prefix())

    """
    async def inner(bot, message):
        guild = message.guild

        # If in DMs, get default prefix
        if guild is None:
            return commands.when_mentioned_or(
                settings.get_setting('default_prefix')
            )(bot, message)

        # Else, fetch guild prefix
        guild_id = guild.id
        await PrefixDatabase.add_prefix(guild_id, add_guild=True)
        prefix = await PrefixDatabase.get_prefix(guild_id)

        if prefix is not None:
            return commands.when_mentioned_or(prefix)(bot, message)
        return commands.when_mentioned(bot, message)

    return inner


def setup_database_users(connection):
    "Setup the tables for the Users database."
    with utils.update_text('Verifying user database',
                           'Verified user database'):
        userdatabase.setup(connection)
        notedatabase.setup(connection)
        reminderdatabase.setup(connection)
        gamedatabase.setup(connection)
    with utils.update_text('Verifying guild database',
                           'Verified guild database'):
        guilddatabase.setup(connection)
        prefixdatabase.setup(connection)


def setup_database_guild_specific(connection):
    with utils.update_text('Verifying guild-specific databases',
                           'Verified guild-specific databases'):
        irishdatabase.setup(connection)


def setup():
    setup_database_users(sqlite3.connect(DATABASE_USERS))
    setup_database_guild_specific(sqlite3.connect(DATABASE_IRISH))
