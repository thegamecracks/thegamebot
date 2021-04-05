import asyncio
import datetime
import re
from typing import List, Tuple, Union

# import dateparser.search
import discord
from discord.ext import commands, tasks
import pytz

from bot.converters import TimezoneConverter
from bot import utils


class MockMessage:
    """A mock message object sufficient for most cooldown BucketTypes.

    BucketTypes supported:
        default (technically you don't need a message at all for this)
        user
        guild (guild parameter is still optional)
        channel (channel required)
        member (guild optional)
        category (channel required)
        role (author must be Member if channel is not DM)
        """
    def __init__(self, author, *, channel: discord.TextChannel = None,
                 guild: discord.Guild = None):
        self.author = author
        self.channel = channel
        self.guild = guild


class Timezones(commands.Cog):
    """Stores the database for tracking message timestamps."""

    # regex_twelve = re.compile(r'(?P<hour>\d{1,2})(:(?P<minute>\d{2}))?[ap]m', re.I)
    # regex_twenty = re.compile(r'(?P<hour>\d{2}):(?P<minute>\d{2})(?![ap]m)', re.I)
    regex_12_24 = re.compile(r'(?P<hour>\d{1,2})(:(?P<minute>\d{2}))?(?P<noon>[ap]m)?', re.I)

    clock_emoji = 828494826155802624

    def __init__(self, bot):
        self.bot = bot
        self.translate_timezone_cooldown = commands.CooldownMapping.from_cooldown(
            1, 15, commands.BucketType.user)

    @classmethod
    def find_times(cls, s, tz, limit=5) -> List[Tuple[str, datetime.datetime, str]]:
        """Find times in a string with a given timezone."""
        matches = []
        for i, m in enumerate(cls.regex_12_24.finditer(s), start=1):
            hour, minute, noon = int(m['hour']), m['minute'], m['noon']

            if noon is not None:
                hour += 12 * (noon.lower() == 'pm')
            elif minute is None:
                # single/double digit number (4, 20)
                continue

            if not 1 <= hour < 24:
                continue
            t = datetime.time(hour=hour)

            if minute is not None:
                minute = int(minute)
                if not 0 <= minute < 60:
                    continue
                t = t.replace(minute=minute)
            # else hour and noon (8am, 3pm)

            dt = datetime.datetime.combine(datetime.date.today(), t)
            dt = tz.localize(dt)
            form = '{}{}{}'.format(
                '%I' if noon else '%H',
                ':%M' * (minute is not None),
                '%p' * (noon is not None)
            )
            matches.append((m.string[slice(*m.span())], dt, form))

            if i == limit:
                break

        return matches
        # return [m[1] for m in dateparser.search.search_dates(s, languages=['en'])]

    async def set_user_timezone(self, user_id: int, timezone: pytz.BaseTzInfo):
        """Add a timezone for a user."""
        user_id = int(user_id)

        # Try adding user entry
        db = self.bot.dbusers
        rowid = await db.add_user(user_id, timezone=timezone.zone)

        if rowid is None:
            # Update user entry
            await db.update_rows(
                db.TABLE_NAME,
                {'timezone': timezone.zone},
                where={'id': user_id}
            )

    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        """Detect times sent in messages."""
        if m.guild is None:
            return

        perms = m.channel.permissions_for(m.guild.me)
        if not (perms.add_reactions and perms.send_messages):
            return

        tz = await self.bot.dbusers.get_timezone(m.author.id)
        if tz is None:
            return

        times = self.find_times(m.content, tz)
        if times:
            await m.add_reaction(self.bot.get_emoji(self.clock_emoji))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Respond to someone that wants a timezone translated."""
        if payload.emoji.id != self.clock_emoji:
            return
        elif payload.user_id == self.bot.user.id:
            return
        elif payload.user_id in self.bot.timezones_users_inputting:
            return

        c = self.bot.get_channel(payload.channel_id)
        m = await c.fetch_message(payload.message_id)

        if payload.user_id == m.author.id:
            return

        r = discord.utils.get(m.reactions, emoji__id=payload.emoji.id)
        if not r.me:
            return

        tz_in = await self.bot.dbusers.get_timezone(m.author.id)
        if tz_in is None:
            return

        times = self.find_times(m.content, tz_in)
        if not times:
            return

        tz_out = await self.bot.dbusers.get_timezone(payload.user_id)
        user = await self.bot.try_user(payload.user_id)

        if not self.translate_timezone_cooldown.update_rate_limit(
                MockMessage(user, channel=c, guild=c.guild)):
            # not rate limited; start translation
            await self.translate_timezone(user, m, times, tz_out)

    async def translate_timezone(
            self, user: discord.User, message: discord.Message,
            times: List[Tuple[str, datetime.datetime, str]],
            tz_out: pytz.BaseTzInfo):
        """Start translating a timezone for a user."""
        async def input_timezone():
            nonlocal channel

            # Decide whether to get input in DMs or same channel
            form = (
                'I do not know what timezone you are in! '
                "Let's do that now; please __type in your timezone__.\n"
                'If you do not know what timezone name you are in, '
                'please use this Time Zone Map to find out: '
                'https://kevinnovak.github.io/Time-Zone-Picker/\n'
                'You have **3 minutes** to complete this form.'
            )
            try:
                await user.send(form)
            except discord.HTTPException:
                await channel.send(form)
            else:
                channel = user.dm_channel

            # Wait for response
            def check(m):
                return m.channel == channel and m.author == user

            due = datetime.datetime.utcnow() + datetime.timedelta(minutes=3)
            self.bot.timezones_users_inputting.add(user.id)
            while (timeout := (due - datetime.datetime.utcnow()).total_seconds()) > 0:
                try:
                    m = await self.bot.wait_for('message', check=check, timeout=timeout)
                except asyncio.TimeoutError:
                    continue  # go into while-else

                try:
                    tz = pytz.timezone(m.content)
                except pytz.UnknownTimeZoneError:
                    pass
                else:
                    # Success
                    await m.add_reaction('\N{WHITE HEAVY CHECK MARK}')
                    await self.set_user_timezone(user.id, tz)
                    self.bot.timezones_users_inputting.remove(user.id)
                    return tz
            else:
                # Timeout
                self.bot.timezones_users_inputting.remove(user.id)
                return await channel.send(
                    'You have ran out of time to input your timezone.')

        channel: Union[discord.TextChannel, discord.User] = message.channel

        tz_in = times[0][1].tzinfo
        tz_out = tz_out or await input_timezone()
        if tz_out is None:
            return

        embed = discord.Embed(
            color=utils.get_bot_color(self.bot)
        ).set_author(
            name=f'Requested by {user.display_name}',
            icon_url=user.avatar_url
        ).set_footer(
            text='Feature inspired by the Friend Time Bot'
        )

        if tz_in == tz_out:
            embed.description = 'You are both in the same timezone!'
            return await channel.send(embed=embed)

        description = [
            f'{message.author.mention} in {message.channel.mention} sent these times:',
            f'{tz_in} -> **{tz_out}**'
        ]

        for s, dt, form in times:
            dt_out = dt.astimezone(tz_out).strftime(form)
            description.append(f'{s} -> **{dt_out}**')

        embed.description = '\n'.join(description)
        kwargs = {'embed': embed, 'reference': message, 'mention_author': False}

        try:
            await channel.send(**kwargs)
        except discord.HTTPException:
            if channel != user:
                await user.send(**kwargs)





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

        if ctx.author.id in ctx.bot.timezones_users_inputting:
            return await ctx.send('You are already being asked to input a timezone.')

        await self.set_user_timezone(ctx.author.id, timezone)

        embed = discord.Embed(
            description=f'Updated your timezone to {timezone.zone}.',
            color=utils.get_bot_color(ctx.bot)
        )
        await ctx.send(embed=embed)










def setup(bot):
    bot.add_cog(Timezones(bot))
