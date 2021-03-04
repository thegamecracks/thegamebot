from typing import Optional

import discord
from discord.ext import commands
import inflect

from bot.classes.confirmation import ReactionConfirmation
from bot import checks
from bot import utils

inflector = inflect.engine()


class IrishSquad(commands.Cog):
    """Commands for Irish Squad."""
    qualified_name = 'Irish Squad'

    GUILD_ID = 153553830670368769

    CHARGE_LEADERBOARD_MAX = 10

    def __init__(self, bot):
        self.bot = bot

        if not self.bot.intents.members:
            self.description += ('\n**NOTE**: This category will not be '
                                 'available in DMs at this time.')


    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.GUILD_ID)


    def cog_check(self, ctx):
        if isinstance(ctx.author, discord.Member):
            return ctx.author.guild.id == self.GUILD_ID

        # In DMs; check if user is part of the guild
        # NOTE: this requires members intent
        guild = self.guild
        if guild is None:
            # RIP
            return False
        return guild.get_member(ctx.author.id) is not None





    @commands.group(name='charges', aliases=('charge',),
                    invoke_without_command=True)
    async def client_charges(self, ctx):
        """Commands for tracking the amount of charges in the squad."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.',
                       delete_after=6)


    @client_charges.command(name='add')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_addcharges(self, ctx, *, number: int):
        """Add to the number of charges you have."""
        if number < 1:
            return await ctx.send('You must add at least one charge.',
                                  delete_after=6)

        db = self.bot.dbirish.charges

        await ctx.channel.trigger_typing()

        await db.change_charges(ctx.author.id, number)
        new_charges = await db.get_charges(ctx.author.id)

        await ctx.send(
            inflector.inflect(
                "Added {0:,} plural('charge', {0})! "
                "You now have {1:,} plural('charge', {1}).".format(
                    number, new_charges
                )
            )
        )





    @client_charges.command(name='remove')
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_removecharges(self, ctx, number: int):
        """Subtract from the number of charges you have."""
        if number < 1:
            return await ctx.send('You must remove at least one charge.',
                                  delete_after=6)

        db = self.bot.dbirish.charges

        await ctx.channel.trigger_typing()

        charges = await db.get_charges(ctx.author.id)
        new_charges = charges - number

        if new_charges < 0:
            return await ctx.send(inflector.inflect(
                "Cannot remove {0:,} plural('charge', {0}); "
                "you only have {1:,} plural('charge', {1}).".format(
                    number, charges)
            ))

        await db.change_charges(ctx.author.id, -number)
        await ctx.send(
            inflector.inflect(
                "Removed {0:,} plural('charge', {0})! "
                "You now have {1:,} plural('charge', {1}).".format(
                    number, new_charges
                )
            )
        )





    @client_charges.command(name='number', aliases=('amount',))
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def client_charges_number(self, ctx, *, user: discord.User = None):
        """Show the number of charges you or someone else has."""
        db = self.bot.dbirish.charges
        await ctx.channel.trigger_typing()

        if user is None:
            user = ctx.author

        try:
            charges = await db.get_charges(user.id, add_user=False)
        except ValueError as e:
            # Prevents non-members of the guild from being added
            # to the database
            raise commands.UserNotFound(user) from e

        if user == ctx.author:
            await ctx.send(inflector.inflect(
                "You have {0:,} plural('charge', {0}).".format(charges)
            ))
        else:
            await ctx.send(inflector.inflect(
                "{0} has {1:,} plural('charge', {1}).".format(
                    user.display_name, charges)
            ))





    @client_charges.command(name='total')
    @commands.cooldown(2, 10, commands.BucketType.channel)
    async def client_charges_guildtotal(self, ctx):
        """Show the squad's total charges."""
        db = self.bot.dbirish.charges
        await ctx.channel.trigger_typing()

        async with db.connect() as conn:
            async with await conn.execute(
                    f'SELECT SUM(amount) AS total FROM {db.TABLE_NAME}') as c:
                total = (await c.fetchone())['total']

            async with await conn.execute(
                    f'SELECT user_id, amount FROM {db.TABLE_NAME} '
                    'WHERE amount != 0 ORDER BY amount DESC '
                    f'LIMIT {self.CHARGE_LEADERBOARD_MAX:d}') as c:
                rows = await c.fetchall()

        description = []
        for i, r in enumerate(rows, start=1):
            mention = f"<@{r['user_id']}>"
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
        commands.has_guild_permissions(manage_guild=True),
        checks.is_bot_owner()
    )
    @commands.cooldown(1, 60)
    async def client_charges_reset(self, ctx):
        """Reset the number of charges everyone has.
This requires a confirmation."""
        prompt = ReactionConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            "Are you sure you want to reset Irish Squad's number of charges?")

        if confirmed:
            await self.bot.dbirish.charges.delete_rows('Charges', where='1')

            await prompt.update('Completed charge wipe!',
                                prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled charge wipe.',
                                prompt.emoji_no.color)





    @client_charges.command(name='vacuum', aliases=('cleanup',))
    @checks.is_bot_owner()
    @commands.cooldown(1, 60)
    async def client_irish_vacuum(self, ctx):
        """Clean up the database."""
        if not self.bot.intents.members:
            return await ctx.send('This is currently disabled as the bot '
                                  'cannot fetch member data at this time.')

        prompt = ReactionConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            "Are you sure you want to vacuum the database?")

        if not confirmed:
            return await prompt.update('Cancelled clean up.', prompt.emoji_no.color)

        db = self.bot.dbirish.users
        guild = self.guild

        invalid_users = []

        async with db.connect() as conn:
            async with await conn.execute('SELECT id FROM Users') as c:
                # Remove all IDs from the Users table if they are
                # not in the guild
                async for row in c:
                    user_id = row['id']
                    member = guild.get_member(user_id)
                    if member is None:
                        try:
                            member = await guild.fetch_member(user_id)
                        except discord.NotFound:
                            pass
                    if member is None:
                        invalid_users.append(user_id)

            if invalid_users:
                query = 'DELETE FROM Users WHERE id IN ({})'.format(
                    ', '.join([str(user_id) for user_id in invalid_users])
                )
                await conn.execute(query)
                await conn.commit()

        # Execute vacuum
        await db.vacuum()

        message = inflector.inflect(
            "Completed clean up!\n{0:,} plural('user', {0}) "
            "vacuumed.".format(len(invalid_users))
        )

        await prompt.update(message, prompt.emoji_yes.color)










def setup(bot):
    bot.add_cog(IrishSquad(bot))
