#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import re
from typing import List, Optional, Tuple, Union

import dateparser
import discord
from discord.ext import commands
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
    regex_12_24 = re.compile(r'(?<!\w)(?P<hour>\d{1,2})(:(?P<minute>\d{2}))?(?P<noon>[ap]m)?(?P<tz>\W[a-zA-Z/]+)?', re.I)

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
                pm, is_twelve = noon.lower() == 'pm', hour == 12
                # 12am and 12pm are special cases
                if pm and not is_twelve:
                    hour += 12
                elif not pm and is_twelve:
                    hour = 0
            elif minute is None:
                # just a single/double digit number (4, 20)
                continue

            if not 0 <= hour < 24:
                continue
            t = datetime.time(hour=hour)

            if minute is not None:
                minute = int(minute)
                if not 0 <= minute < 60:
                    continue
                t = t.replace(minute=minute)
            # else hour and noon (8am, 3pm)

            dt = datetime.datetime.combine(datetime.date.today(), t)

            # Try parsing timezone if string has one
            given_tz = None
            if m['tz']:
                _, given_tz = dateparser.timezone_parser.pop_tz_offset_from_string(m[0])
                if not given_tz:
                    try:
                        given_tz = pytz.timezone(m['tz'].lstrip())
                    except pytz.UnknownTimeZoneError:
                        pass

            dt = (given_tz or tz).localize(dt)
            form = '{}{}{}'.format(
                '%I' if noon else '%H',
                ':%M' * (minute is not None),
                '%p' * (noon is not None)
            )
            # Include timezone in string only if it was parsed correctly
            s = m[0] if given_tz else m[0][:m.start('tz')] if m['tz'] else m[0]
            matches.append((s, dt, form))

            if i == limit:
                break

        return matches
        # return [m[1] for m in dateparser.search.search_dates(s, languages=['en'])]

    async def set_user_timezone(
            self, user_id: int, timezone: pytz.BaseTzInfo = None):
        """Add a timezone for a user."""
        user_id, timezone = int(user_id), getattr(timezone, 'zone', timezone)

        # Try adding user entry
        db = self.bot.dbusers
        success = await db.add_user(user_id, timezone=timezone)

        if not success:
            # Update user entry
            await db.update_rows(
                db.TABLE_NAME,
                {'timezone': timezone},
                where={'id': user_id}
            )

    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        """Detect times sent in messages."""
        if m.guild is None:
            return

        perms = m.channel.permissions_for(m.guild.me)
        if not perms.add_reactions:
            return

        author_row = await self.bot.dbusers.get_user(m.author.id)
        tz = await self.bot.dbusers.convert_timezone(author_row)
        if tz is None:
            return

        if self.find_times(m.content, tz):
            await m.add_reaction(self.bot.get_emoji(self.clock_emoji))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Respond to someone that wants a timezone translated."""
        if (    payload.emoji.id != self.clock_emoji
                or payload.user_id == self.bot.user.id
                or payload.user_id in self.bot.timezones_users_inputting):
            return

        c = self.bot.get_channel(payload.channel_id)
        m = await c.fetch_message(payload.message_id)

        # Prevent author from translating their own timezone
        if payload.user_id == m.author.id:
            return

        # Bot must have its own reaction on it too
        r = discord.utils.get(m.reactions, emoji__id=payload.emoji.id)
        if not r.me:
            return

        # Check the author's timezone
        user_in_row = await self.bot.dbusers.get_user(m.author.id)
        tz_in = await self.bot.dbusers.convert_timezone(user_in_row)
        if tz_in is None:
            return

        times = self.find_times(m.content, tz_in)
        if not times:
            return

        user_out_row = await self.bot.dbusers.get_user(payload.user_id)
        tz_out = await self.bot.dbusers.convert_timezone(user_out_row)
        user = await self.bot.try_user(payload.user_id)

        if not self.translate_timezone_cooldown.update_rate_limit(
                MockMessage(user, channel=c, guild=c.guild)):
            # not rate limited; start translation
            await self.translate_timezone(
                user, m, times,
                tz_in, user_in_row,
                tz_out, user_out_row
            )

    async def translate_timezone(
            self, user: discord.User, message: discord.Message,
            times: List[Tuple[str, datetime.datetime, str]],
            tz_in: pytz.BaseTzInfo, user_in_row,
            tz_out: pytz.BaseTzInfo, user_out_row):
        """Start translating a timezone for a user."""
        def get_bot_permissions(c):
            if isinstance(c, (discord.User, discord.DMChannel)):
                return discord.Permissions.text()
            return c.permissions_for(c.guild.me)

        async def send_backup(first, second=True, send_func=None, *args, **kwargs):
            """Send a message to the first messageable,
            and if it fails then use the second as a backup.

            Once it tests a messageable, it memoizes it so it will not need
            to catch exceptions for it again.

            Returns the Messageable and Message that successfully worked,
            or (None, None) if both first and second channels fail.

            send_func is an optional callable that takes the messageable
            and a variable amount of positional and keyword arguments.
            This should do the actual message sending and return a Message.

            """
            async def default_send_func(c, *args, **kwargs):
                return await c.send(*args, **kwargs)

            if first is None:
                raise ValueError('no channel passed')
            elif first in failed_channels:
                if second is None:
                    return
                return await send_backup(second, None, send_func, *args, **kwargs)

            send_func = send_func or default_send_func

            can_send = get_bot_permissions(first).send_messages
            if can_send:
                try:
                    return first, await send_func(first, *args, **kwargs)
                except discord.HTTPException:
                    can_send = False

            if not can_send:
                failed_channels.append(first)
                if second is True:  # Pick an alternative
                    second = user if first != user else message.channel
                elif second is None:
                    return
                return await send_backup(second, None, send_func, *args, **kwargs)

        async def send_func_reference(c, *args, embed, **kwargs):
            if c == message.channel:
                return await c.send(
                    *args, embed=embed, reference=message,
                    mention_author=False, **kwargs
                )
            jump_embed = embed.copy()
            jump_embed.description += jump_to
            return await c.send(*args, embed=jump_embed, **kwargs)

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
            channel, m = await send_backup(user, channel, None, form)

            # Wait for response
            def check(m):
                return m.author == user and m.channel in (channel, user.dm_channel)

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
                await send_backup(
                    channel, None, None,
                    'You have ran out of time to input your timezone.'
                )
                return

        channel: Union[discord.TextChannel, discord.User] = message.channel
        failed_channels = []

        # Ask user for timezone if needed
        asked_timezone = tz_out is None
        if asked_timezone:
            tz_out = await input_timezone()
        if tz_out is None:
            return

        embed = discord.Embed(
            color=utils.get_bot_color(self.bot)
        ).set_author(
            name=f'Requested by {user.display_name}',
            icon_url=user.avatar_url
        )
        jump_to = f'\n[Jump to message]({message.jump_url})'
        if tz_in == tz_out:
            embed.description = f'You are both in the same timezone!'
            c, m = await send_backup(
                user, message.channel, send_func_reference,
                embed=embed
            )
            if c != user:
                await m.delete(delay=10)
            return

        embed.set_footer(
            text='Feature inspired by the Friend Time Bot'
        )

        # Convert times
        tz_in_str = str(tz_in) if user_in_row['timezone_public'] else 'Hidden'
        tz_out_str = str(tz_out) if user_out_row['timezone_public'] else 'Hidden'
        description = [
            f'{message.author.mention} in {message.channel.mention} sent these times:',
            f'{tz_in_str} -> **{tz_out_str}**'
        ]
        for s, dt, form in times:
            dt_out = dt.astimezone(tz_out).strftime(form).lstrip('0')
            description.append(f'{s} -> **{dt_out}**')

        # Send message with reference/jump url
        embed.description = '\n'.join(description)
        await send_backup(channel, True, send_func_reference, embed=embed)





    @commands.group(name='timezone', aliases=['tz'], invoke_without_command=True)
    @commands.cooldown(2, 5, commands.BucketType.member)
    async def client_timezone(self, ctx, *, timezone: TimezoneConverter = None):
        """Get the current date and time in a given timezone.
This command uses the IANA timezone database.
You can find the timezone names using this [Time Zone Map](https://kevinnovak.github.io/Time-Zone-Picker/)."""
        # Resource: https://medium.com/swlh/making-sense-of-timezones-in-python-16d8ae210c1c
        utcnow = datetime.datetime.utcnow()

        if timezone is None:
            row = await ctx.bot.dbusers.get_user(ctx.author.id)
            if row['timezone'] is None:
                return await ctx.send(
                    'You do not have a timezone set. Please specify a timezone '
                    'or set your own timezone using "timezone set".'
                )
            s = await ctx.bot.strftime_user(
                row, utcnow, respect_settings=bool(ctx.guild))
        else:
            timezone: pytz.BaseTzInfo
            tznow = utcnow.astimezone(timezone)
            s = utils.strftime_zone(tznow)

        await ctx.send(s)


    @client_timezone.command(name='set')
    @commands.cooldown(2, 60, commands.BucketType.user)
    async def client_timezone_set(self, ctx, *, timezone: TimezoneConverter = None):
        """Set your timezone.
You can find the timezone names using this [Time Zone Map](https://kevinnovak.github.io/Time-Zone-Picker/).
If you want to remove your timezone, use this command with no arguments."""
        timezone: Optional[pytz.BaseTzInfo]

        if ctx.author.id in ctx.bot.timezones_users_inputting:
            return await ctx.send('You are already being asked to input a timezone.')

        author_row = await ctx.bot.dbusers.get_user(ctx.author.id)
        curr_timezone = await ctx.bot.dbusers.convert_timezone(author_row)
        if not timezone and not curr_timezone:
            return await ctx.send('You already have no timezone set.')

        await self.set_user_timezone(ctx.author.id, timezone)

        description = 'Removed your timezone!'
        if timezone:
            if author_row['timezone_public']:
                description = f'Updated your timezone to {timezone.zone}!'
            else:
                description = 'Updated your timezone!'
                await ctx.message.delete(delay=0)
        embed = discord.Embed(
            description=description,
            color=utils.get_bot_color(ctx.bot)
        )
        await ctx.send(embed=embed)


    @client_timezone.command(name='visibility', aliases=('visible', 'show'))
    @commands.cooldown(2, 60, commands.BucketType.user)
    async def client_timezone_visibility(self, ctx, mode: bool):
        """Set your timezone visibility on or off.
This hides the name and abbreviation of your timezone whenever it needs to be shown.
By default, your timezone is hidden."""
        row = await ctx.bot.dbusers.get_user(ctx.author.id)
        curr_visibility = row['timezone_public']

        if mode and curr_visibility:
            return await ctx.send('Your timezone visibility is already set to on!')
        elif not mode and not curr_visibility:
            return await ctx.send('Your timezone visibility is already set to off!')

        await ctx.bot.dbusers.update_rows(
            ctx.bot.dbusers.TABLE_NAME,
            {'timezone_public': mode},
            where={'id': ctx.author.id}
        )

        await ctx.send('Updated your timezone visibility!')










def setup(bot):
    bot.add_cog(Timezones(bot))
