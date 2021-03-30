import decimal
import random
from typing import Optional

import discord
from discord.ext import commands

from bot.classes.confirmation import AdaptiveConfirmation
from bot.converters import DollarConverter
from bot.utils import format_cents, format_dollars
from bot import utils


class Economy(commands.Cog):
    """Manage your economics."""
    qualified_name = 'Economy'

    LEADERBOARD_MAX_DISPLAYED = 10

    def __init__(self, bot):
        self.bot = bot
        self.chat_cooldown = commands.CooldownMapping.from_cooldown(
            1, 60, commands.BucketType.member)

    @commands.Cog.listener('on_message')
    async def chat_reward(self, message):
        """Reward money for chatting."""
        if message.author.bot:
            return
        elif message.guild is None:
            return
        elif not self.chat_cooldown.update_rate_limit(message):
            cents = random.randint(1, 12) * 100 + random.randint(-10, 10)
            cents = max(0, cents)  # future proofing
            await self.bot.dbcurrency.change_cents(
                message.guild.id, message.author.id, cents)





    @commands.group(name='money', invoke_without_command=True)
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.guild_only()
    async def client_money(self, ctx, *, user: discord.Member = None):
        """Inspect you or someone else's money."""
        user = user or ctx.author

        cents = await ctx.bot.dbcurrency.get_cents(ctx.guild.id, user.id)

        embed = discord.Embed(
            description=format_cents(cents),
            color=utils.get_user_color(ctx.bot, user)
        ).set_author(
            name=user.display_name,
            icon_url=user.avatar_url
        )

        await ctx.send(embed=embed)





    @client_money.command(name='adjust')
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.guild_only()
    @commands.check_any(
        commands.has_guild_permissions(manage_guild=True),
        commands.is_owner()
    )
    async def client_money_adjust(self, ctx, user: Optional[discord.Member],
                                  dollars: DollarConverter(zero=False)):
        """Add or take away money from a user."""
        user = user or ctx.author

        cents = await ctx.bot.dbcurrency.change_cents(
            ctx.guild.id, user.id, dollars * 100, keep_positive=True)

        embed = discord.Embed(
            color=utils.get_user_color(ctx.bot, user)
        )
        verb = 'Added {} to' if dollars > 0 else 'Removed {} from'
        if user == ctx.author:
            embed.description = '{} your balance. You now have {}.'.format(
                verb, format_cents(cents)
            ).format(format_dollars(dollars))
        else:
            embed.description = "{} {}'s balance. They now have {}.".format(
                verb, user.mention, format_cents(cents)
            ).format(format_dollars(dollars))

        await ctx.send(embed=embed)





    @client_money.command(name='give', aliases=('gift', 'send',))
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.guild_only()
    async def client_money_send(
            self, ctx, dollars: DollarConverter(negative=False, zero=False),
            user: discord.Member):
        """Send money to another member."""
        if user.bot:
            return await ctx.send('You cannot send money to bots.')

        db = ctx.bot.dbcurrency
        cents_author = await db.get_cents(ctx.guild.id, ctx.author.id)
        dollars_author = decimal.Decimal(cents_author) / 100

        if dollars > dollars_author:
            return await ctx.send(f'You only have {format_cents(cents_author)}.')
        elif user != ctx.author:
            # If the user tries giving themselves money, do not make a query
            await db.send_cents(ctx.guild.id, ctx.author.id, user.id, dollars * 100)
            dollars_author -= dollars

        embed = discord.Embed(
            description=f'{ctx.author.mention} has sent {user.mention} '
                        f'{format_dollars(dollars)}!\n'
                        f'You have {format_dollars(dollars_author)} left.',
            color=utils.get_user_color(ctx.bot, ctx.author)
        )

        await ctx.send(embed=embed)





    @client_money.command(
        name='leaderboard',
        aliases=('leaderboards', 'scoreboard',))
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.guild_only()
    async def client_money_leaderboard(self, ctx):
        """Show the most wealthy members in the economy."""

        db = ctx.bot.dbcurrency

        async with db.connect() as conn:
            async with await conn.execute(
                    f'SELECT SUM(cents) AS total FROM {db.TABLE_NAME} '
                    'WHERE guild_id = ?', (ctx.guild.id,)) as c:
                total = (await c.fetchone())['total'] or 0

            async with await conn.execute(
                    f'SELECT user_id, cents FROM {db.TABLE_NAME} '
                    'WHERE guild_id = ? AND cents != 0 ORDER BY cents DESC '
                    f'LIMIT {self.LEADERBOARD_MAX_DISPLAYED:d}',
                    (ctx.guild.id,)) as c:
                description = []
                i = 1
                async for row in c:
                    mention = f"<@{row['user_id']}>"
                    dollars = format_cents(row['cents'])
                    description.append(f'{mention}: {dollars}')

        embed = None
        if description:
            embed = discord.Embed(
                color=utils.get_bot_color(ctx.bot),
                description='\n'.join(description)
            )

        await ctx.send(
            f"The server's economy has a total of {format_cents(total)}.",
            embed=embed
        )





    @client_money.command(name='reset')
    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.guild_only()
    @commands.check_any(
        commands.has_guild_permissions(manage_guild=True),
        commands.is_owner()
    )
    async def client_money_reset(self, ctx):
        """Reset the economy for the server.
This requires a confirmation."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color(ctx.bot))

        confirmed = await prompt.confirm(
            "Are you sure you want to reset the server's economy?")

        if confirmed:
            await self.bot.dbcurrency.wipe(ctx.guild.id)
            await prompt.update('Completed economy wipe!', prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled economy wipe.', prompt.emoji_no.color)










def setup(bot):
    bot.add_cog(Economy(bot))
