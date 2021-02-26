import aiosqlite

from discord.ext import commands

from .gamedatabase import GameDatabase
from .guilddatabase import GuildDatabase
from .irishdatabase import IrishDatabase
from .notedatabase import NoteDatabase
from .prefixdatabase import PrefixDatabase
from .reminderdatabase import ReminderDatabase
from .userdatabase import UserDatabase
from bot import settings


class BotDatabaseMixin:
    DATABASE_MAIN_PATH = 'data/thegamebot.db'
    DATABASE_IRISH_PATH = 'data/irishsquad.db'

    DATABASES = ('dbusers', 'dbguilds', 'dbgames', 'dbirish', 'dbnotes',
                 'dbprefixes', 'dbreminders')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dbgames = GameDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbguilds = GuildDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbirish = IrishDatabase(self, self.DATABASE_IRISH_PATH)
        self.dbnotes = NoteDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbprefixes = PrefixDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbreminders = ReminderDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbusers = UserDatabase(self, self.DATABASE_MAIN_PATH)

    async def db_setup(self):
        """Set up tables for each database."""
        for attr in self.DATABASES:
            db = getattr(self, attr)
            async with aiosqlite.connect(db.path) as conn:
                await db.setup_table(conn)

    async def get_prefix(self, message):
        guild = message.guild

        # If in DMs, get default prefix
        if guild is None:
            return commands.when_mentioned_or(
                settings.get_setting('default_prefix')
            )(self, message)

        # Else, fetch guild prefix
        guild_id = guild.id
        await self.dbguilds.add_guild(guild_id)
        await self.dbprefixes.add_prefix(guild_id)
        prefix = await self.dbprefixes.get_prefix(guild_id)

        if prefix is not None:
            return commands.when_mentioned_or(prefix)(self, message)
        return commands.when_mentioned(self, message)
