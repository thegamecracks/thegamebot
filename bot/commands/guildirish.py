import asyncio

import discord
from discord.ext import commands
import inflect

from bot.database import IrishDatabase, DATABASE_IRISH
from bot import checks
from bot import utils

inflector = inflect.engine()


def has_guild_permissions_dm_safe(*args, **kwargs):
    """A variant of has_guild_permissions that does not throw NoPrivateMessage
    in DMs."""
    original = commands.has_guild_permissions(*args, **kwargs).predicate
    async def predicate(ctx):
        return ctx.guild is not None and await original(ctx)
    return commands.check(predicate)


class IrishSquad(commands.Cog):
    qualified_name = 'Irish Squad'
    description = 'Commands for Irish Squad.'

    GUILD_ID = 153553830670368769

    def __init__(self, bot):
        self.bot = bot
        self.db = IrishDatabase(DATABASE_IRISH)

        if not self.bot.intents.members:
            self.description += ('\n**NOTE**: This category will not be '
                                 'available in DMs at this time.')


    def cog_check(self, ctx):
        if isinstance(ctx.author, discord.Member):
            return ctx.author.guild.id == self.GUILD_ID

        # In DMs; check if user is part of the guild
        guild = ctx.bot.get_guild(self.GUILD_ID)
        if guild is None:
            # RIP
            return False

        # NOTE: this requires members intent
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
            "The squad has a total of {0} plural('charge', {0}).".format(total)
        ))





    @client_charges.command(name='reset')
    @commands.check_any(
        has_guild_permissions_dm_safe(manage_guild=True),
        checks.is_bot_owner()
    )
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def client_charges_reset(self, ctx):
        """Reset the number of charges everyone has.
This requires a confirmation."""
        embed = discord.Embed(
            color=utils.get_bot_color(),
            description="**Are you sure you want to reset Irish Squad's "
                        'number of charges?**'
        ).set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.avatar_url
        )

        message = await ctx.send(embed=embed)

        emoji = {'\N{WHITE HEAVY CHECK MARK}': 0x77B255,
                 '\N{CROSS MARK}': 0xDD2E44}
        for e in emoji:
            await message.add_reaction(e)

        def check(r, u):
            return r.emoji in emoji and u == ctx.author

        try:
            reaction, user = await self.bot.wait_for(
                'reaction_add', check=check, timeout=30
            )
        except asyncio.TimeoutError:
            embed.color = emoji['\N{CROSS MARK}']
            embed.description = 'Cancelled charge wipe.'
            return await message.edit(embed=embed)
        else:
            confirmed = reaction.emoji == '\N{WHITE HEAVY CHECK MARK}'

        if confirmed:
            await self.db.delete_rows('Charges', where='1')

            embed.color = emoji['\N{WHITE HEAVY CHECK MARK}']
            embed.description = 'Completed charge wipe!'
        else:
            embed.color = emoji['\N{CROSS MARK}']
            embed.description = 'Cancelled charge wipe.'

        await message.edit(embed=embed)










def setup(bot):
    bot.add_cog(IrishSquad(bot))
