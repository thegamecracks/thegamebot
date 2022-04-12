#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import functools
import logging
import re
from typing import Literal, TypedDict, cast

import asqlite
import dateparser
from dateutil.relativedelta import relativedelta
import discord
from discord.ext import commands, tasks

from bot import converters, utils
from main import Context, TheGameBot

logger = logging.getLogger('discord')


class Reminder:
    DATEPARSER_SETTINGS: dict = {
        'PREFER_DATES_FROM': 'future',
        'RETURN_AS_TIMEZONE_AWARE': True,
        'TIMEZONE': 'UTC',
    }

    FAIL_TEXT = (
        "Could not understand your time/reminder. Check this "
        "command's help page for the supported syntax."
    )

    MINIMUM_REMINDER_TIME = 30

    TO_PATTERN = re.compile(r'to', re.IGNORECASE)

    def __init__(self, due: datetime.datetime, content: str):
        self.due = due
        self.content = content

    @classmethod
    def split_time_and_reminder(cls, argument: str):
        return cls.TO_PATTERN.split(argument, maxsplit=1)

    @classmethod
    async def convert(cls, ctx: Context, argument: str):
        # Skip microsecond for simpler timedelta
        now = discord.utils.utcnow().replace(microsecond=0)

        parts = cls.split_time_and_reminder(argument)
        if len(parts) != 2:
            raise commands.BadArgument(cls.FAIL_TEXT)

        due_str, content = parts
        content = content.lstrip()

        # Check string for timezone, then look in database, and fallback to UTC
        tz: datetime.tzinfo
        due_str, tz = dateparser.timezone_parser.pop_tz_offset_from_string(due_str)
        if not tz:
            dt = await ctx.bot.localize_datetime(ctx.author.id, now)
            tz = dt.tzinfo

        # Make times relative to the timezone
        settings = cls.DATEPARSER_SETTINGS.copy()
        tz_now = now.astimezone(tz)
        settings['RELATIVE_BASE'] = tz_now
        settings['TIMEZONE'] = tz_now.tzname()

        async with ctx.typing():
            converter = converters.DatetimeConverter(settings=settings)
            due = await converter.convert(ctx, due_str)

        td = due - now
        seconds_until = td.total_seconds()
        if seconds_until < 0:
            raise commands.BadArgument('You cannot create a reminder for the past.')
        elif seconds_until < cls.MINIMUM_REMINDER_TIME:
            raise commands.BadArgument(
                'You must set a reminder lasting for at '
                f'least {cls.MINIMUM_REMINDER_TIME} seconds.'
            )
        elif not content:
            raise commands.BadArgument('You must have a message with your reminder.')

        return cls(due, content)


class PartialReminderEntry(TypedDict):
    user_id: int
    channel_id: int
    due: datetime.datetime
    content: str


class ReminderEntry(PartialReminderEntry):
    reminder_id: int


async def query_reminder_count(conn: asqlite.Connection, user_id: int) -> int:
    # NOTE: because guild_id can be None, the query has
    # to use "IS" to correctly match nulls
    query = 'SELECT COUNT(*) AS length FROM reminder WHERE user_id = ?'
    async with conn.execute(query, user_id) as c:
        row = await c.fetchone()
        return row['length']


class Reminders(commands.Cog):
    """Commands for setting up reminders."""
    qualified_name = 'Reminders'

    MAXIMUM_REMINDERS = 10
    MAXIMUM_REMINDER_CONTENT = 250

    NEAR_DUE = datetime.timedelta(minutes=11)
    # NOTE: should be just a bit longer than task loop

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.reminder_tasks = {}  # reminder_id: Task
        self.send_reminders.start()

    def cog_unload(self):
        self.send_reminders.cancel()
        for task in self.reminder_tasks.values():
            task.cancel()

    async def add_reminder(self, entry: PartialReminderEntry):
        row = entry.copy()
        # NOTE: due to a bug with sqlite3.dbapi2.convert_timestamp,
        # timezones cannot be included when the microsecond
        # is omitted by isoformat()
        row['due'] = row['due'].astimezone(datetime.timezone.utc).replace(tzinfo=None)

        # SQLite rowid is aliased as reminder_id, so we don't need an extra query
        reminder_id = await self.bot.db.add_row('reminder', row)

        entry = cast(ReminderEntry, entry)
        entry['reminder_id'] = reminder_id

        return self.check_reminder(entry)

    @commands.group(aliases=('reminder',), invoke_without_command=True)
    @commands.cooldown(2, 6, commands.BucketType.user)
    async def reminders(self, ctx: Context, index: int = None):
        """See a list of your reminders.

index: If provided, shows more details about the given reminder."""
        async with ctx.bot.db.connect() as conn:
            count = await query_reminder_count(conn, ctx.author.id)

            if count == 0:
                return await ctx.send("You don't have any reminders.")
            elif index is None:
                # Show a list of existing reminders
                query = 'SELECT * FROM reminder WHERE user_id = ?'
                async with conn.execute(query, ctx.author.id) as c:
                    lines = []
                    i = 1
                    while row := await c.fetchone():
                        due = row['due'].replace(tzinfo=datetime.timezone.utc)
                        lines.append('{}. <#{}> {}: {}'.format(
                            i, row['channel_id'],
                            discord.utils.format_dt(due, 'R'),
                            utils.truncate_message(row['content'], 40, max_lines=1)
                        ))
                        i += 1

                embed = discord.Embed(
                    color=ctx.bot.get_user_color(ctx.author),
                    description='\n'.join(lines)
                ).set_author(
                    name=ctx.author.display_name,
                    icon_url=ctx.author.display_avatar.url
                )

                return await ctx.send(embed=embed)
            elif not 1 <= index <= count:
                return await ctx.send('That index does not exist.')

            # NOTE: maybe refactor this to support same syntax as notes
            query = 'SELECT * FROM reminder WHERE user_id = ? LIMIT 1 OFFSET ?'
            async with conn.execute(query, ctx.author.id, index - 1) as c:
                row = await c.fetchone()

            due = row['due'].replace(tzinfo=datetime.timezone.utc)
            embed = discord.Embed(
                title=f'Reminder #{index:,d}',
                description=row['content'],
                color=ctx.bot.get_user_color(ctx.author)
            ).add_field(
                name='Sends to',
                value='<#{}>'.format(row['channel_id'])
            ).add_field(
                name='Due in',
                value='{}\n({})'.format(
                    utils.timedelta_string(
                        relativedelta(due, discord.utils.utcnow()),
                        inflector=ctx.bot.inflector
                    ),
                    discord.utils.format_dt(due, style='F')
                )
            )
            await ctx.send(embed=embed)

    @reminders.command(name='remove', aliases=('delete',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def reminders_remove(
        self, ctx: Context, *,
        indices: list[int] | Literal['all'] = commands.parameter(
            converter=converters.IndexConverter | Literal['all']
        )
    ):
        """Remove one or multiple reminders.

Examples:
    <prefix>reminder remove 1
    <prefix>reminder remove 1-4
    <prefix>reminder remove 1 3 5-7
    <prefix>reminder remove all"""
        async with ctx.bot.db.connect() as conn:
            count = await query_reminder_count(conn, ctx.author.id)

        if count == 0:
            return await ctx.send('You already have no reminders.')
        elif indices == 'all':
            await ctx.bot.db.delete_rows('reminder', where={'user_id': ctx.author.id})
        else:
            indices = [n for n in indices if 1 <= n <= count]
            rows = await ctx.bot.db.get_rows(
                'reminder', 'reminder_id', where={'user_id': ctx.author.id}
            )
            to_delete = [(rows[i]['reminder_id'],) for i in indices]
            count = len(to_delete)

            async with ctx.bot.db.connect(writing=True) as conn:
                query = 'DELETE FROM reminder WHERE reminder_id = ?'
                await conn.executemany(query, to_delete)

        await ctx.send(
            '{} {} successfully deleted!'.format(
                count, ctx.bot.inflector.plural('reminder', count)
            )
        )


    @reminders.command(name='add')
    async def reminders_add(self, ctx: Context, *, time_and_reminder: Reminder):
        """Create a reminder in the given or current channel.

Usage:
    remind at 10pm EST to <x>
    remind in 30 sec/min/h/days to <x>
    remind #bot-commands on wednesday to <x>
Note that the time and your reminder message have to be separated with "to".
If you have not explicitly included a timezone in the command, but you have
provided the bot your timezone before with "/timezone set", that timezone will
be used instead of UTC.

User mentions will otherwise be escaped except in DMs."""
        me_perms = ctx.channel.permissions_for(ctx.me)
        if not me_perms.send_messages:
            return await ctx.message.add_reaction('\N{FACE WITHOUT MOUTH}')

        # Check maximum reminders
        async with ctx.bot.db.connect() as conn:
            count = await query_reminder_count(conn, ctx.author.id)

        if count >= self.MAXIMUM_REMINDERS:
            return await ctx.send(
                'You have reached the maximum limit of '
                f'{self.MAXIMUM_REMINDERS} reminders.'
            )

        due, content = time_and_reminder.due, time_and_reminder.content

        max_content_size = self.MAXIMUM_REMINDER_CONTENT
        content = await commands.clean_content().convert(ctx, content)

        diff = len(content) - max_content_size
        if diff > 0:
            return await ctx.send(
                'Please provide a message under {:,d} {} (-{:,d}).'.format(
                    max_content_size,
                    ctx.bot.inflector.plural('character', max_content_size),
                    diff
                )
            )

        await self.add_reminder({
            'user_id': ctx.author.id,
            'channel_id': ctx.channel.id,
            'due': due,
            'content': content
        })

        await ctx.send(
            'Added your {} reminder for {} in this channel!'.format(
                ctx.bot.inflector.ordinal(count + 1),
                discord.utils.format_dt(due, style='F')
            )
        )


    @reminders.group(name='clear', aliases=('wipe',), invoke_without_command=True)
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def reminders_clear(self, ctx: Context, channel: discord.TextChannel = None):
        """Clear all your reminders in the given channel."""
        channel = channel or ctx.channel

        entries = await ctx.bot.db.delete_rows(
            'reminder', {'user_id': ctx.author.id, 'channel_id': channel.id},
            pop=True
        )

        count = len(entries)
        channel_reference = 'this channel' if channel == ctx.channel else channel.mention

        if count == 0:
            return await ctx.send(f'You have no reminders in {channel_reference}!')

        await ctx.send(
            'Cleared your {} {} in {}!'.format(
                count,
                ctx.bot.inflector.plural('reminder', count),
                channel_reference
            )
        )


    @reminders_clear.command(name='everyone')
    @commands.guild_only()
    async def reminders_clear_everyone(self, ctx: Context, channel: discord.TextChannel = None):
        """Clear everyone's reminders in the given channel.

This requires the Manage Messages permission in the given channel."""
        channel = channel or ctx.channel

        if not channel.permissions_for(ctx.author).manage_messages:
            return await ctx.send(
                'You must have the Manage Messages permission '
                "to clear everyone's reminders!"
            )

        entries = await ctx.bot.db.delete_rows(
            'reminder', {'channel_id': channel.id}, pop=True
        )

        count = len(entries)
        channel_reference = 'this channel' if channel == ctx.channel else channel.mention

        if count == 0:
            return await ctx.send(f'There are no reminders in {channel_reference}!')

        await ctx.send(
            'Cleared {} {} in {}!'.format(
                count,
                ctx.bot.inflector.plural('reminder', count),
                channel_reference
            )
        )


    @commands.command(
        name='remind', aliases=('remindme',),
        brief='Shorthand for reminder add.',
        help=reminders_add.callback.__doc__
    )
    async def remind(self, ctx: Context, *, time_and_reminder: Reminder):
        await self.reminders_add(ctx, time_and_reminder=time_and_reminder)

    def check_reminder(self, entry: ReminderEntry, *, now=None):
        """Starts an :class:`asyncio.Task` to handle sending a reminder
        if the given reminder is nearing due.

        :returns bool: Indicates whether the task was created or not.

        """
        if entry['reminder_id'] in self.reminder_tasks:
            # Task already exists; skip
            return False
        elif now is None:
            now = discord.utils.utcnow()

        td = entry['due'] - now
        is_soon = td < self.NEAR_DUE
        if is_soon:
            self.create_reminder_task(td, entry)

        return is_soon

    def create_reminder_task(self, td, entry: ReminderEntry):
        """Adds a reminder task to the bot loop and logs it."""
        reminder_id = entry['reminder_id']
        task = self.bot.loop.create_task(self.reminder_coro(entry))
        self.reminder_tasks[reminder_id] = task
        task.add_done_callback(functools.partial(
            self.reminder_coro_remove_task, reminder_id
        ))

        logger.debug(
            'Reminders: created reminder task {} '
            'for {}, due in {}'.format(
                reminder_id, entry['user_id'], td
            )
        )

        return task

    def reminder_coro_remove_task(self, reminder_id: int, task: asyncio.Task):
        self.reminder_tasks.pop(reminder_id, None)

    async def reminder_coro(self, entry: ReminderEntry):
        """Schedules a reminder to be sent to the user."""
        async def remove_entry(log: str):
            logger.debug(log)
            await self.bot.db.delete_rows(
                'reminder',
                where={'reminder_id': reminder_id}
            )

        # Wait until the reminder is due
        reminder_id = entry['reminder_id']
        seconds = (entry['due'] - discord.utils.utcnow()).total_seconds()
        await asyncio.sleep(seconds)

        # Do some last-second checks before sending reminder
        row = await self.bot.db.get_one(
            'reminder', 'reminder_id',
            where={'reminder_id': reminder_id}
        )

        if row is None:
            return await remove_entry(
                f'Reminders: canceled reminder {reminder_id}: '
                'reminder was deleted during wait'
            )

        channel = self.bot.get_channel(entry['channel_id'])
        if channel is None:
            # Might be a deleted channel but could also be a DM channel,
            # the latter being resolvable with fetch_channel()
            try:
                channel = await self.bot.fetch_channel(entry['channel_id'])
            except (discord.NotFound, discord.Forbidden):
                return await remove_entry(
                    f'Reminders: canceled reminder {reminder_id}: '
                    'channel no longer exists'
                )

        if getattr(channel, 'guild', None) is not None:
            # Check if member is still in the guild
            member = await utils.getch_member(channel.guild, entry['user_id'])
            if member is None:
                return await remove_entry(
                    f'Reminders: canceled reminder {reminder_id}: '
                    'member is no longer in the guild'
                )

        # NOTE: multiple API calls could be made above if
        # member/user left several reminders

        description = '<@{mention}> **{due}{is_overdue}**\n{content}'.format(
            mention=entry['user_id'],
            due=discord.utils.format_dt(entry['due'], style='F'),
            is_overdue=' (overdue)' * (seconds < 0),
            content=entry['content']
        )

        # Now we can try to send the reminder
        try:
            await channel.send(description)
        except discord.Forbidden as e:
            await remove_entry(
                f'Reminders: failed to send reminder {reminder_id}: '
                f'was forbidden from sending: {e}'
            )
        except discord.HTTPException as e:
            # This may be a fault on server end, log this with higher
            # severity and allow the send_reminders loop to retry
            logger.warning(
                f'Reminders: failed to send reminder {reminder_id}: '
                f'HTTPException occurred: {e}'
            )
        else:
            await remove_entry(f'Reminders: successfully sent reminder {reminder_id}')

    @tasks.loop(minutes=10)
    async def send_reminders(self):
        """Periodically queries the database for reminders and
        spins up reminder tasks as needed.
        """
        now = discord.utils.utcnow()

        async for entry in self.bot.db.yield_rows('reminder'):
            entry = cast(ReminderEntry, dict(entry))
            entry['due'] = entry['due'].replace(tzinfo=datetime.timezone.utc)
            self.check_reminder(entry, now=now)

    @send_reminders.before_loop
    async def before_send_reminders(self):
        await self.bot.wait_until_ready()


async def setup(bot: TheGameBot):
    await bot.add_cog(Reminders(bot))
