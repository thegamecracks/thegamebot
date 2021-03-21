import asyncio
import contextlib
import datetime

import aiosqlite
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
        self._conn = aiosqlite.connect(':memory:')
        self._open = False
        self._lock = asyncio.Lock()

        self.vacuum.start()

    def cog_unload(self):
        """Cancel running tasks and close the database."""
        self.vacuum.cancel()
        if self._open:
            loop = asyncio.get_running_loop()
            loop.create_task(self._conn.close())
            self._open = False

    @commands.Cog.listener()
    async def on_message(self, m):
        """Store the message in the database."""
        if m.guild is None:
            return

        cog = self.bot.get_cog('MessageTracker')
        if cog is None:
            return

        async with cog.connect() as conn:
            # Add to guild table if it does not exist already
            await conn.execute(
                'INSERT OR IGNORE INTO Guilds (id) VALUES (?)',
                (m.guild.id,)
            )
            # Store message
            await conn.execute("""
                INSERT INTO Messages (guild_id, created_at) VALUES (?, ?)
                """, (m.guild.id, m.created_at)
            )
            await conn.commit()

    @tasks.loop(hours=12)
    async def vacuum(self):
        """Remove messages older than 24 hours."""
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

        cog = self.bot.get_cog('MessageTracker')
        if cog is None:
            return

        async with cog.connect() as conn:
            await conn.execute(
                'DELETE FROM Messages WHERE (created_at < ?)',
                (yesterday,)
            )
            await conn.commit()

    @contextlib.asynccontextmanager
    async def connect(self):
        """Return the aiosqlite connection."""
        if not self._open:
            await self.setup_database()

        await self._lock.acquire()
        try:
            yield self._conn
        finally:
            self._lock.release()

    async def setup_database(self):
        """Open the database and create the tables."""
        if self._open:
            raise RuntimeError('The database is already open.')

        await self._conn
        self._open = True
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(self.TABLE_SETUP)
        await self._conn.commit()











def setup(bot):
    bot.add_cog(MessageTracker(bot))
