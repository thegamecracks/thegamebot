import discord
from discord.ext import commands

from bot.other import discordlogger

logger = discordlogger.get_logger()


class DatabaseEvents(commands.Cog):
    """Event listeners managing the database."""

    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.cleanup_tables())

    @staticmethod
    async def try_member(guild: discord.Guild, id: int):
        return guild.get_member(id) or await guild.fetch_member(id)

    async def delete_many(self, table_name, column, ids):
        async with await self.bot.dbusers.connect(writing=True) as conn:
            query = 'DELETE FROM {} WHERE {} IN ({})'.format(
                table_name, column, ', '.join([str(n) for n in ids])
            )
            await conn.execute(query)

    async def check_guild_tables(self):
        """Remove any guilds that the bot is no longer a part of."""
        db = self.bot.dbguilds
        to_remove = []

        async with await db.connect() as conn:
            async with conn.execute(f'SELECT id FROM {db.TABLE_NAME}') as c:
                while row := await c.fetchone():
                    if self.bot.get_guild(row['id']) is None:
                        to_remove.append(row['id'])

        logger.debug('Removing %d guilds from database', len(to_remove))

        if to_remove:
            await self.delete_many(db.TABLE_NAME, 'id', *to_remove)

        return to_remove

    async def check_tag_tables(self):
        """Remove user IDs from tags where the user is
        no longer a part of the guild.
        """
        db = self.bot.dbtags
        t, ta = db.TABLE_NAME, db.TABLE_ALIASES_NAME
        authors = set()
        authors_to_remove = []

        # Iterate through authors of tags/aliases and find
        # which authors are no longer in the guild
        async with await db.connect() as conn:
            async with conn.execute(
                    f'SELECT DISTINCT guild_id, user_id FROM {t}') as c:
                while row := await c.fetchone():
                    authors.add((row['guild_id'], row['user_id']))
            async with conn.execute(
                    f'SELECT DISTINCT guild_id, user_id FROM {ta}') as c:
                while row := await c.fetchone():
                    authors.add((row['guild_id'], row['user_id']))

        for guild_id, user_id in authors:
            if user_id is None:  # un-claimed tag
                continue

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                # NOTE: this shouldn't happen after checking guild table
                continue

            member = await self.try_member(guild, user_id)
            if member is None:
                authors_to_remove.append((guild_id, user_id))

        for key in authors_to_remove:
            await db.unauthor_tags(*key)
            await db.unauthor_aliases(*key)

        return authors_to_remove

    async def cleanup_tables(self):
        """Update the tables to match guild/member changes."""
        await self.bot.wait_until_ready()

        # Make sure this only happens once on startup
        if self.bot.dbevents_cleaned_up:
            return

        deleted = False
        intents = self.bot.intents
        if intents.guilds:
            logger.debug('Cleaning up guild tables')
            deleted = bool(await self.check_guild_tables()) or deleted
        if intents.guilds and intents.members:
            logger.debug('Cleaning up tag tables')
            deleted = bool(await self.check_tag_tables()) or deleted

        self.bot.dbevents_cleaned_up = True
        if deleted:
            await self.bot.dbusers.vacuum()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.bot.dbtags.unauthor_tags(member.guild.id, member.id)
        await self.bot.dbtags.unauthor_aliases(member.guild.id, member.id)










def setup(bot):
    bot.add_cog(DatabaseEvents(bot))
