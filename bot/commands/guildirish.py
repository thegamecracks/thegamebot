import discord
from discord.ext import commands
import inflect

from bot.classes.confirmation import AdaptiveConfirmation
from bot.database import IrishDatabase
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

    CHARGE_LEADERBOARD_MAX = 10

    def __init__(self, bot):
        self.bot = bot
        self.db = IrishDatabase

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

        # NOTE: this requires members intent in DMs
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
                "Added {0:,} plural('charge', {0})! "
                "You now have {1:,} plural('charge', {1}).".format(
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
                "Cannot remove {0:,} plural('charge', {0}); "
                "you only have {1:,} plural('charge', {1}).".format(
                    amount, charges)
            ))

        await self.db.subtract_charges(ctx.author.id, amount)
        await ctx.send(
            inflector.inflect(
                "Removed {0:,} plural('charge', {0})! "
                "You now have {1:,} plural('charge', {1}).".format(
                    amount, new_charges
                )
            )
        )





    @client_charges.command(name='number', aliases=('amount',))
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_charges_number(self, ctx, *, user=None):
        """Show the number of charges you or someone else has."""
        await ctx.channel.trigger_typing()

        try:
            user_obj = await commands.UserConverter().convert(ctx, user)
        except (TypeError, commands.UserNotFound):
            # TypeError raised when user is None
            user_obj = ctx.author

        try:
            charges = await self.db.get_charges(user_obj.id, add_user=False)
        except ValueError as e:
            # Prevents non-members of the guild from being added
            # to the database
            raise commands.UserNotFound(user) from e

        if user_obj == ctx.author:
            await ctx.send(inflector.inflect(
                "You have {0:,} plural('charge', {0}).".format(charges)
            ))
        else:
            await ctx.send(inflector.inflect(
                "{0} has {1:,} plural('charge', {1}).".format(
                    user_obj.display_name, charges)
            ))





    @client_charges.command(name='total')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    async def client_charges_guildtotal(self, ctx):
        """Show the squad's total charges."""
        await ctx.channel.trigger_typing()

        rows = await self.db.get_rows('Charges')

        total = sum(r['amount'] for r in rows)

        rows = sorted((r for r in rows if r['amount'] != 0),
                      key=lambda r: r['amount'], reverse=True)

        description = []
        for i, r in enumerate(rows, start=1):
            if i > self.CHARGE_LEADERBOARD_MAX:
                description.append('...')
                break

            user = self.bot.get_user(r['user_id'])
            mention = user.mention if user is not None else None

            description.append(f"{mention}: {r['amount']:,}")

        embed = None
        if description:
            embed = discord.Embed(
                color=utils.get_bot_color(),
                description='\n'.join(description)
            )

        await ctx.send(
            inflector.inflect(
                "The squad has a total of {0:,} plural('charge', {0}).".format(
                    total)
            ),
            embed=embed
        )





    @client_charges.command(name='reset')
    @commands.check_any(
        has_guild_permissions_dm_safe(manage_guild=True),
        checks.is_bot_owner()
    )
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def client_charges_reset(self, ctx):
        """Reset the number of charges everyone has.
This requires a confirmation."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            "Are you sure you want to reset Irish Squad's number of charges?")

        if confirmed:
            await self.db.delete_rows('Charges', where='1')

            await prompt.update('Completed charge wipe!',
                                prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled charge wipe.',
                                prompt.emoji_no.color)





    @client_charges.command(name='vacuum', aliases=('cleanup',))
    @checks.is_bot_owner()
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def client_irish_vacuum(self, ctx):
        """Clean up the database."""
        if not self.bot.intents.members:
            return await ctx.send('This is currently disabled as the bot '
                                  'cannot fetch member data at this time.')

        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            "Are you sure you want to vacuum the database?")

        if confirmed:
            guild = self.bot.get_guild(self.GUILD_ID)

            # Remove all IDs from the Users table if they are
            # not in the guild
            invalid_users = []
            async for row in self.db.yield_rows('Users'):
                user_id = row['id']
                member = guild.get_member(user_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(user_id)
                    except discord.NotFound:
                        member = None
                if member is None:
                    invalid_users.append(user_id)

            where = 'id IN ({})'.format(
                ', '.join([str(user_id) for user_id in invalid_users])
            )
            await self.db.delete_rows('Users', where=where)

            # Execute vacuum
            await self.db.vacuum()

            message = inflector.inflect(
                "Completed clean up!\n{0:,} plural('user', {0}) "
                "vacuumed.".format(len(invalid_users))
            )

            await prompt.update(message, prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled clean up.', prompt.emoji_no.color)










def setup(bot):
    bot.add_cog(IrishSquad(bot))
