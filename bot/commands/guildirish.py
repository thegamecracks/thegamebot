import discord
from discord.ext import commands
import inflect

from bot.database import IrishDatabase, DATABASE_IRISH
from bot import checks

inflector = inflect.engine()


class IrishSquad(commands.Cog):
    qualified_name = 'Irish Squad'
    description = 'Commands for Irish Squad.'

    GUILD_ID = 153553830670368769

    def __init__(self, bot):
        self.bot = bot
        self.db = IrishDatabase(DATABASE_IRISH)


    def cog_check(self, ctx):
        # Prevent cog being used outside of guild or DMs
        if isinstance(ctx.author, discord.Member):
            return ctx.author.guild.id == self.GUILD_ID

        # In DMs; check if user is part of the guild
        guild = ctx.bot.get_guild(self.GUILD_ID)
        if guild is None:
            # RIP
            return False

        return guild.get_member(ctx.author.id) is not None





    @commands.group(name='charges', aliases=('charge',),
                    invoke_without_command=True)
    async def client_charges(self, ctx):
        """Commands for tracking the amount of charges in the squad."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.')
    
    @client_charges.command(name='add')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_addcharges(self, ctx, *, amount: int):
        """Add to the number of charges you have."""
        if amount < 1:
            return await ctx.send('You must add at least one charge.')

        await ctx.channel.trigger_typing()

        await self.db.add_charges(ctx.author.id, amount)
        new_charges = await self.db.get_charges(ctx.author.id)

        await ctx.send(
            inflector.inflect(
                "Added {0} plural('charge', {0})! "
                "You now have {1} plural('charge', {1}).".format(
                    amount, new_charges
                )
            )
        )





    @client_charges.command(name='remove')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_removecharges(self, ctx, amount: int):
        """Subtract from the number of charges you have."""
        if amount < 1:
            return await ctx.send('You must remove at least one charge.')

        await ctx.channel.trigger_typing()

        charges = await self.db.get_charges(ctx.author.id)
        new_charges = charges - amount

        if new_charges < 0:
            return await ctx.send(inflector.inflect(
                "Cannot remove {0} plural('charge', {0}); "
                "you only have {1} plural('charge', {1}).".format(
                    amount, charges)
            ))

        await self.db.subtract_charges(ctx.author.id, amount)
        await ctx.send(
            inflector.inflect(
                "Removed {0} plural('charge', {0})! "
                "You now have {1} plural('charge', {1}).".format(
                    amount, new_charges
                )
            )
        )





    @client_charges.command(name='amount')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_charges_amount(self, ctx, user: discord.Member = None):
        """Show the amount of charges you or someone else has."""
        await ctx.channel.trigger_typing()

        user = user if user is not None else ctx.author
        charges = await self.db.get_charges(user.id)

        if user == ctx.author:
            await ctx.send(inflector.inflect(
                "You have {0} plural('charge', {0}).".format(charges)
            ))
        else:
            await ctx.send(inflector.inflect(
                "{0} has {1} plural('charge', {1}).".format(
                    user.display_name, charges)
            ))





    @client_charges.command(name='total')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    async def client_charges_guildtotal(self, ctx):
        """Show the squad's total charges."""
        await ctx.channel.trigger_typing()

        rows = await self.db.get_rows('Charges')

        total = sum(r['amount'] for r in rows)

        await ctx.send(inflector.inflect(
            "The guild has a total of {0} plural('charge', {0}).".format(total)
        ))










def setup(bot):
    bot.add_cog(IrishSquad(bot))
