import discord
from discord.ext import commands

from bot.database import PrefixDatabase, dbconn_users
from bot import utils


class Prefix(commands.Cog):
    qualified_name = 'Prefix'
    description = "Commands for changing the bot's prefix."

    def __init__(self, bot):
        self.bot = bot
        self.prefixdb = PrefixDatabase(dbconn_users)





    @commands.command(name='changeprefix')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def client_changeprefix(self, ctx, *, prefix):
        """Change the bot's prefix."""
        with ctx.channel.typing():
            current_prefix = (
                await self.prefixdb.get_prefix(ctx.guild.id)
            )['prefix']
            if prefix == current_prefix:
                await ctx.send('That is already the current prefix.')
            else:
                # Escape escape characters before printing
                clean_prefix = prefix.replace('\\', r'\\')
                await self.prefixdb.update_prefix(ctx.guild.id, prefix)
                await ctx.send(
                    f'Successfully changed prefix to: "{clean_prefix}"')


    @client_changeprefix.error
    async def client_changeprefix_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            # Prefix is too long
            await ctx.send(str(error))










def setup(bot):
    bot.add_cog(Prefix(bot))
