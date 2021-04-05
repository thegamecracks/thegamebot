import datetime

import discord
from discord.ext import commands, tasks
import pytz

from bot.converters import TimezoneConverter
from bot import utils


class Timezones(commands.Cog):
    """Stores the database for tracking message timestamps."""

    def __init__(self, bot):
        self.bot = bot

    # @commands.Cog.listener()
    # async def on_message(self, m):
    #     """Detect times sent in messages."""





    @commands.group(name='timezone', aliases=['tz'], invoke_without_command=True)
    @commands.cooldown(2, 5, commands.BucketType.member)
    async def client_timezone(self, ctx, *, timezone: TimezoneConverter = None):
        """Get the current date and time in a given timezone.
This command uses the IANA timezone database.
You can find the timezone names using this [Time Zone Map](https://kevinnovak.github.io/Time-Zone-Picker/)."""
        # Resource: https://medium.com/swlh/making-sense-of-timezones-in-python-16d8ae210c1c
        timezone = timezone or await ctx.bot.dbusers.get_timezone(ctx.author.id)
        if timezone is None:
            return await ctx.send(
                'You do not have a timezone set. Please specify a timezone or '
                'set your own timezone using "timezone set".'
            )
        timezone: pytz.BaseTzInfo

        UTC = pytz.utc
        utcnow = UTC.localize(datetime.datetime.utcnow())
        tznow = utcnow.astimezone(timezone)
        await ctx.send(tznow.strftime('%c %Z (%z)'))


    @client_timezone.command(name='set')
    @commands.cooldown(2, 60, commands.BucketType.user)
    async def client_timezone_set(self, ctx, *, timezone: TimezoneConverter):
        """Set your timezone.
You can find the timezone names using this [Time Zone Map](https://kevinnovak.github.io/Time-Zone-Picker/)."""
        timezone: pytz.BaseTzInfo

        # Try adding user entry
        db = ctx.bot.dbusers
        rowid = await db.add_user(
            ctx.author.id,
            timezone=timezone.zone
        )

        if rowid is None:
            # Update user entry
            await db.update_rows(
                db.TABLE_NAME,
                {'timezone': timezone.zone},
                where={'id': ctx.author.id}
            )

        embed = discord.Embed(
            description=f'Updated your timezone to {timezone.zone}.',
            color=utils.get_bot_color(ctx.bot)
        )
        await ctx.send(embed=embed)










def setup(bot):
    bot.add_cog(Timezones(bot))
