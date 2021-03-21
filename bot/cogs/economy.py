import decimal
from typing import Optional

import discord
from discord.ext import commands

from bot.classes.confirmation import AdaptiveConfirmation
from bot import utils


class DollarConverter(commands.Converter):
    async def convert(self, ctx, argument):
        return Economy.parse_dollars(argument)


class Economy(commands.Cog):
    """Manage your economics."""
    qualified_name = 'Economy'

    def __init__(self, bot):
        self.bot = bot

    @classmethod
    def format_cents(cls, cents: int):
        return cls.format_dollars(cents / 100)

    @classmethod
    def format_dollars(cls, dollars):
        dollars = cls.round_dollars(dollars)
        sign = '-' if dollars < 0 else ''
        dollar_part = abs(int(dollars))
        cent_part = abs(int(dollars % 1 * 100))
        return '{}${}.{:02d}'.format(sign, dollar_part, cent_part)

    @classmethod
    def parse_dollars(cls, s: str, round_to_cent=True) -> decimal.Decimal:
        """Parse a string into a Decimal.

        Raises:
            ValueError: The string could not be parsed.

        """
        s = s.replace('$', '', 1)
        try:
            d = decimal.Decimal(s)
        except decimal.InvalidOperation as e:
            raise ValueError('Could not parse cents') from e
        return cls.round_dollars(d) if round_to_cent else d

    @staticmethod
    def round_dollars(d) -> decimal.Decimal:
        """Round a number-like object to the nearest cent."""
        cent = decimal.Decimal('0.01')
        return decimal.Decimal(d).quantize(cent, rounding=decimal.ROUND_HALF_UP)





    @commands.group(name='money', invoke_without_command=True)
    @commands.cooldown(3, 15, commands.BucketType.user)
    @commands.guild_only()
    async def client_money(self, ctx, *, user: discord.Member = None):
        """Inspect you or someone else's money."""
        user = user or ctx.author

        cents = await ctx.bot.dbcurrency.get_cents(ctx.guild.id, user.id)

        embed = discord.Embed(
            description=self.format_cents(cents),
            color=utils.get_user_color(ctx.bot, user)
        ).set_author(
            name=user.display_name,
            icon_url=user.avatar_url
        )

        await ctx.send(embed=embed)


    @client_money.command(name='adjust')
    @commands.check_any(
        commands.has_guild_permissions(manage_guild=True),
        commands.is_owner()
    )
    async def client_money_adjust(self, ctx, user: Optional[discord.Member],
                                  dollars: DollarConverter):
        """Add or take away money from a user."""
        if dollars == 0:
            return await ctx.send('Please provide a non-zero quantity.')

        user = user or ctx.author

        cents = await ctx.bot.dbcurrency.change_cents(
            ctx.guild.id, user.id, dollars * 100, keep_positive=True)

        embed = discord.Embed(
            color=utils.get_user_color(ctx.bot, user)
        )
        verb = 'Added {} to' if dollars > 0 else 'Removed {} from'
        if user == ctx.author:
            embed.description = '{} your balance. You now have {}.'.format(
                verb, self.format_cents(cents)
            ).format(self.format_dollars(dollars))
        else:
            embed.description = "{} {}'s balance. They now have {}.".format(
                verb, user.mention, self.format_cents(cents)
            ).format(self.format_dollars(dollars))

        await ctx.send(embed=embed)





    @client_money.command(name='reset')
    @commands.check_any(
        commands.has_guild_permissions(manage_guild=True),
        commands.is_owner()
    )
    @commands.cooldown(1, 60)
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
