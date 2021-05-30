#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import contextlib
import datetime

import asqlite
import discord
from discord.ext import commands, tasks


class MessageTracker(commands.Cog):
    """Stores the database for tracking message timestamps."""

    TABLE_SETUP = """
    CREATE TABLE IF NOT EXISTS Guilds (
        id INTEGER NOT NULL PRIMARY KEY
    );
    CREATE TABLE IF NOT EXISTS Messages (
        guild_id INTEGER NOT NULL,
        created_at TIMESTAMP,
        FOREIGN KEY(guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE
    );"""

    def __init__(self, bot):
        self.bot = bot
        self._conn = None
        self._lock = asyncio.Lock()

        self.vacuum.start()

    def cog_unload(self):
        """Cancel running tasks and close the database."""
        self.vacuum.cancel()
        if self._conn:
            self.bot.loop.create_task(self._conn.close())

    @commands.Cog.listener()
    async def on_message(self, m):
        """Store the message in the database."""
        if m.guild is None:
            return

        async with self.connect() as conn:
            async with conn.transaction():
                # Add to guild table if it does not exist already
                await conn.execute(
                    'INSERT OR IGNORE INTO Guilds (id) VALUES (?)',
                    m.guild.id
                )
                # Store message
                await conn.execute(
                    'INSERT INTO Messages (guild_id, created_at) VALUES (?, ?)',
                    m.guild.id, m.created_at
                )

    @tasks.loop(hours=12)
    async def vacuum(self):
        """Remove messages older than 24 hours."""
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

        async with self.connect() as conn:
            await conn.execute(
                'DELETE FROM Messages WHERE (created_at < ?)',
                yesterday
            )

    @contextlib.asynccontextmanager
    async def connect(self) -> asqlite.Connection:
        """Return the asqlite connection."""
        if not self._conn:
            await self.setup_database()

        await self._lock.acquire()
        try:
            yield self._conn
        finally:
            self._lock.release()

    async def setup_database(self):
        """Open the database and create the tables."""
        if self._conn:
            raise RuntimeError('The database is already open.')

        self._conn = await asqlite.connect(':memory:')
        async with self._conn.transaction():
            await self._conn.executescript(self.TABLE_SETUP)










def setup(bot):
    bot.add_cog(MessageTracker(bot))
