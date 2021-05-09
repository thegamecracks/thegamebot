#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asqlite

from discord.ext import commands

from .currencydatabase import CurrencyDatabase
from .database import ConnectionPool
from .gamedatabase import GameDatabase
from .guilddatabase import GuildDatabase
from .irishdatabase import IrishDatabase
from .notedatabase import NoteDatabase
from .prefixdatabase import PrefixDatabase
from .reminderdatabase import ReminderDatabase
from .tagdatabase import TagDatabase
from .userdatabase import UserDatabase
from bot import errors


class BotDatabaseMixin(commands.Bot):
    DATABASE_MAIN_PATH = 'data/thegamebot.db'
    DATABASE_IRISH_PATH = 'data/irishsquad.db'

    DATABASES = ('dbusers', 'dbguilds', 'dbcurrency', 'dbgames',
                 'dbirish', 'dbnotes', 'dbprefixes', 'dbreminders',
                 'dbtags')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dbpool = ConnectionPool()
        self.dbcurrency = CurrencyDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbgames = GameDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbguilds = GuildDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbirish = IrishDatabase(self, self.DATABASE_IRISH_PATH)
        self.dbnotes = NoteDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbprefixes = PrefixDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbreminders = ReminderDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbtags = TagDatabase(self, self.DATABASE_MAIN_PATH)
        self.dbusers = UserDatabase(self, self.DATABASE_MAIN_PATH)

    async def db_setup(self):
        """Set up tables for each database."""
        for attr in self.DATABASES:
            db = getattr(self, attr)
            async with asqlite.connect(db.path) as conn:
                await db.setup_table(conn)

    async def get_prefix(self, message):
        def get_default_prefix():
            try:
                return self.get_cog('Settings').get('default_prefix')
            except errors.SettingsNotFound:
                return None

        guild = message.guild

        if guild is None:
            prefix = get_default_prefix()
        else:
            await self.dbguilds.add_guild(guild.id)
            prefix = await self.dbprefixes.get_prefix(guild.id)
            if prefix is None:
                await self.dbprefixes.add_prefix(guild.id, get_default_prefix())
                prefix = await self.dbprefixes.get_prefix(guild.id)

        if prefix is not None:
            return commands.when_mentioned_or(prefix)(self, message)
        return commands.when_mentioned(self, message)
