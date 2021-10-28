#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import re
from typing import Literal, Optional, Union

import dateparser
from dateutil.relativedelta import relativedelta
import discord
from discord.ext import commands, tasks
import pytz

from bot import errors, utils
from bot.database.reminderdatabase import PartialReminderEntry, ReminderEntry
from bot.other import discordlogger


class IndexConverter(commands.Converter):
    """Parse an integer (1) or range (1-4)."""

    async def convert(self, ctx, arg) -> range:
        error = errors.ErrorHandlerResponse(f'Could not understand "{arg}".')
        values = []
        for n in arg.split('-')[:3]:
            try:
                values.append(int(n))
            except ValueError:
                raise error

        length = len(values)
        if length == 1:
            return range(values[0], values[0] + 1)
        elif length == 2:
            return range(values[0], values[1] + 1)
        raise error


class Reminders(commands.Cog):
    """Commands for setting up reminders."""
    qualified_name = 'Reminders'

    ESCAPED_ROLE_MENTION = re.compile(r'\\<@&(\d+)>')
    EVERYONE_ROLE_USER_MENTION = re.compile(r'@everyone|@here|<@[!&]?\d+>')
    EVERYONE_ROLE_MENTION = re.compile(r'@everyone|@here|<@&(?P<id>\d+)>')

    MAXIMUM_REMINDERS = 10
    MAXIMUM_REMINDER_CONTENT = 250
    MAXIMUM_ANNOUNCEMENT_CONTENT = 1000
    MINIMUM_REMINDER_TIME = 30

    DATEPARSER_SETTINGS = {
        'PREFER_DATES_FROM': 'future',
        'RETURN_AS_TIMEZONE_AWARE': True,
        'TIMEZONE': 'UTC',
    }

    send_reminders_near_due = datetime.timedelta(minutes=11)
    # NOTE: should be just a bit longer than task loop

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}  # user_id: reminders
        self.send_reminders_tasks = {}  # reminder_id: Task
        self.send_reminders.start()

    def cog_unload(self):
        self.send_reminders.cancel()
        for task in self.send_reminders_tasks.values():
            task.cancel()





    async def add_reminder(self, **entry: PartialReminderEntry):
        """Adds a reminder and invalidates the user's cache.
        Kwargs are passed through to dbreminders.add_reminder.
        """
        reminder_id = await self.bot.dbreminders.add_reminder(**entry)
        self.cache.pop(entry['user_id'], None)

        self.check_to_create_reminder(reminder_id=reminder_id, **entry)

    async def delete_reminder_by_id(self, reminder_id, pop=False):
        """Remove a reminder by reminder_id and update the caches."""
        deleted = await self.bot.dbreminders.delete_reminder_by_id(
            reminder_id, pop=True)

        updated_ids = frozenset(reminder['user_id'] for reminder in deleted)
        updated_reminders = [reminder['reminder_id'] for reminder in deleted]

        for user_id in updated_ids:
            user = self.cache.pop(user_id, None)
            if user is not None:
                discordlogger.get_logger().info(
                    f'Reminders: Invalidated user cache, ID {user_id}')
        for reminder_id in updated_reminders:
            task = self.send_reminders_tasks.pop(reminder_id, None)
            if task is not None:
                discordlogger.get_logger().info(
                    f'Reminders: Removed reminder task, ID {reminder_id}')

        if pop:
            return deleted

    async def get_reminders(self, user_id):
        reminders = self.cache.get(user_id)

        if reminders is None:
            # Uncached user; add them to cache
            reminders = await self.bot.dbreminders.get_reminders(user_id)
            self.cache[user_id] = reminders

        return reminders

    def is_announcement(self, content: str):
        """Determine if a reminder's content is an announcement
        (whether a user/role mention exists on the first line of the message).

        When adding reminders in DMs, a newline can be prepended to the content
        to prevent the reminder from being interpreted as an announcement.

        """
        return bool(self.EVERYONE_ROLE_USER_MENTION.search(content.split('\n', 1)[0]))

    async def parse_datetime(self, ctx, date_string: str) -> datetime.datetime:
        """Parse a string as a timezone-aware datetime."""
        # Determine timezone
        # Check string for timezone, then look in database, and fallback to UTC
        date_string, tz = dateparser.timezone_parser.pop_tz_offset_from_string(date_string)
        if not tz:
            user_row = await ctx.bot.dbusers.get_user(ctx.author.id)
            tz = await ctx.bot.dbusers.convert_timezone(user_row) or pytz.UTC
        tz: datetime.tzinfo

        # Make times relative to the timezone
        settings = self.DATEPARSER_SETTINGS.copy()
        now = datetime.datetime.now(datetime.timezone.utc).astimezone(tz)
        settings['RELATIVE_BASE'] = now
        settings['TIMEZONE'] = now.tzname()

        # Parse
        dt = dateparser.parse(date_string, settings=settings)

        return dt





    @commands.group(
        name='reminder', aliases=('reminders',),
        invoke_without_command=True
    )
    @commands.cooldown(2, 6, commands.BucketType.user)
    async def client_reminders(self, ctx, index: int = None):
        """See your reminders."""
        reminder_list = await self.get_reminders(ctx.author.id)

        if not reminder_list:
            return await ctx.send("You don't have any reminders.")

        if index is None:
            lines = [
                '{}. <#{}> {}: {}'.format(
                    i,
                    reminder['channel_id'],
                    discord.utils.format_dt(
                        reminder['due'].replace(
                            tzinfo=datetime.timezone.utc
                        ), 'R'
                    ),
                    utils.truncate_message(reminder['content'].lstrip(), 40, max_lines=1)
                ) for i, reminder in enumerate(reminder_list, start=1)
            ]

            embed = discord.Embed(
                color=utils.get_user_color(ctx.bot, ctx.author),
                description='\n'.join(lines)
            ).set_author(
                name=ctx.author.display_name,
                icon_url=ctx.author.display_avatar.url
            )
            return await ctx.send(embed=embed)
        elif not 0 < index <= len(reminder_list):
            return await ctx.send('That index does not exist.')

        reminder = reminder_list[index - 1]
        utcdue = reminder['due'].replace(tzinfo=datetime.timezone.utc)
        embed = discord.Embed(
            title=f'Reminder #{index:,}',
            description=reminder['content'].lstrip(),
            color=utils.get_user_color(ctx.bot, ctx.author)
        ).add_field(
            name='Sends to',
            value='<#{}>'.format(reminder['channel_id'])
        ).add_field(
            name='Due in',
            value='{}\n({})'.format(
                utils.timedelta_string(
                    relativedelta(
                        utcdue,
                        discord.utils.utcnow()
                    ),
                    inflector=ctx.bot.inflector
                ),
                discord.utils.format_dt(utcdue, style='F')
            )
        )
        await ctx.send(embed=embed)


    @client_reminders.command(name='remove', aliases=('delete',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_reminders_remove(
        self, ctx, *indices: Union[Literal['all'], IndexConverter]
    ):
        """Remove one or multiple reminders.

Examples:
    <prefix>reminder remove 1
    <prefix>reminder remove 1-4
    <prefix>reminder remove 1 3 5-7
    <prefix>reminder remove all"""
        if not indices:
            return await ctx.send_help(ctx.command)

        reminder_list = await self.get_reminders(ctx.author.id)

        if not reminder_list:
            return await ctx.send("You already have no reminders.")

        if 'all' in indices:
            valid = range(len(reminder_list))
        else:
            valid = {n - 1 for r in indices for n in r
                     if 0 < n <= len(reminder_list)}

        if not valid:
            return await ctx.send('No valid indices were provided.')

        for n in valid:
            reminder = reminder_list[n]
            await self.delete_reminder_by_id(reminder['reminder_id'])

        await ctx.send(
            '{} {} successfully deleted!'.format(
                len(valid),
                ctx.bot.inflector.plural('reminder', len(valid))
            )
        )


    @client_reminders.command(name='add')
    async def client_reminders_add(
            self, ctx, channel: Optional[discord.TextChannel],
            *, time_and_reminder):
        """Create a reminder in the given or current channel.

Usage:
    remind at 10pm EST to <x>
    remind in 30 sec/min/h/days to <x>
    remind #announcements on wednesday to <x>
Note that the time and your reminder message have to be separated with "to".
If you have not explicitly said a timezone in the command but you have
provided the bot your timezone before with "timezone set", that timezone will
be used instead of UTC.

The channel parameter only allows channels where you can both send messages and mention everyone in.

User mentions will be escaped except in DMs or where you are permitted to mention everyone.
If you can mention, this command can be used to create scheduled server announcements with these steps:
1. hide the "@you time" header by mentioning your members in the first line of your reminder
2. use @all and @now in place of @\u200beveryone and @\u200bhere to avoid pinging people with your command
3. prefix role mentions with a backslash \\ to avoid pinging roles
The announcement can only be scheduled if the bot has sufficient permissions to ping each included mention."""
        if channel is not None:
            # Given channel must be in same guild and have enough permissions
            if channel.guild != ctx.guild:
                return await ctx.message.add_reaction('\N{CROSS MARK}')

            user_perms = channel.permissions_for(ctx.author)
            if not user_perms.send_messages or not user_perms.mention_everyone:
                return await ctx.message.add_reaction('\N{CROSS MARK}')
        else:
            channel = ctx.channel
            user_perms = channel.permissions_for(ctx.author)

        me_perms = channel.permissions_for(ctx.me)
        if not me_perms.send_messages:
            return await ctx.message.add_reaction('\N{FACE WITHOUT MOUTH}')

        total_reminders = len(await self.get_reminders(ctx.author.id))
        if total_reminders >= self.MAXIMUM_REMINDERS:
            return await ctx.send(
                'You have reached the maximum limit of '
                f'{self.MAXIMUM_REMINDERS} reminders.'
            )

        # Get current time in UTC without microseconds
        utcnow = discord.utils.utcnow().replace(microsecond=0)
        try:
            # Separate time and reminder,
            # also making sure that content is provided
            due, content = [s.strip() for s in re.split(
                'to', time_and_reminder, maxsplit=1, flags=re.IGNORECASE
            )]
            async with ctx.typing():
                due = await self.parse_datetime(ctx, due)
            if due is None:
                return await ctx.send(
                    'Could not understand your given time.')
        except (ValueError, AttributeError):
            return await ctx.send(
                'Could not understand your reminder request. Check this '
                "command's help page for allowed syntax."
            )

        td = due - utcnow
        seconds_until = td.total_seconds()
        if seconds_until < 0:
            return await ctx.send(
                'You cannot create a reminder for the past.')
        elif seconds_until < self.MINIMUM_REMINDER_TIME:
            return await ctx.send(
                'You must set a reminder lasting for at '
                f'least {self.MINIMUM_REMINDER_TIME} seconds.'
            )
        elif not content:
            return await ctx.send('You must have a message with your reminder.')

        # Fix/clean mentions
        if user_perms.mention_everyone:
            max_content_size = self.MAXIMUM_ANNOUNCEMENT_CONTENT
            content = content.replace('@all', '@everyone').replace('@now', '@here')
            content = self.ESCAPED_ROLE_MENTION.sub(r'<@&\1>', content)

            if isinstance(channel, discord.DMChannel):
                # Prepend a newline so the message is not
                # considered an announcement (yes, this is stupid)
                content = '\n' + content
            elif not me_perms.mention_everyone:
                # Prevent creating the announcement if there's a mention
                # the bot cannot do properly
                for m in self.EVERYONE_ROLE_MENTION.finditer(content):
                    if m.group() in ('@everyone', '@here'):
                        return await ctx.send(
                            f'I am missing permissions to '
                            f'ping everyone in {channel.mention}.'
                        )
                    role = channel.guild.get_role(int(m.group('id')))
                    if role is not None and not role.mentionable:
                        return await ctx.send(
                            f'I am missing permissions to '
                            f'properly ping the {role.mention} role.'
                        )
        else:
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

        await self.add_reminder(
            user_id=ctx.author.id,
            channel_id=channel.id,
            due=due,
            content=content
        )

        await ctx.send(
            'Added your {} {} for {} in {}.'.format(
                ctx.bot.inflector.ordinal(total_reminders + 1),
                'announcement' if self.is_announcement(content) else 'reminder',
                discord.utils.format_dt(due, style='F'),
                'this channel' if channel == ctx.channel else channel.mention
            )
        )


    @commands.command(
        name='remind', aliases=('remindme', 'announce'),
        brief='Shorthand for reminder add.',
        help=client_reminders_add.callback.__doc__
    )
    async def client_remind(
            self, ctx, channel: Optional[discord.TextChannel],
            *, time_and_reminder):
        await self.client_reminders_add(ctx, channel, time_and_reminder=time_and_reminder)





    def check_to_create_reminder(self, *, now=None, **entry: ReminderEntry):
        """Create a reminder task if needed.

        This does not store the reminder in the database.

        Returns:
            bool: Indicates whether the task was created or not.

        """
        if entry['reminder_id'] in self.send_reminders_tasks:
            # Task already exists; skip
            return False
        elif now is None:
            now = discord.utils.utcnow()

        td = entry['due'] - now
        is_soon = td < self.send_reminders_near_due
        if is_soon:
            self.create_reminder_task(td, entry)

        return is_soon

    def create_reminder_task(self, td, entry: ReminderEntry):
        """Adds a reminder task to the bot loop and logs it."""
        task = self.bot.loop.create_task(self.reminder_coro(entry))
        self.send_reminders_tasks[entry['reminder_id']] = task

        discordlogger.get_logger().info(
            'Reminders: created reminder task {} '
            'for {}, due in {}'.format(
                entry['reminder_id'], entry['user_id'], td
            )
        )

        return task

    async def reminder_coro(self, entry: ReminderEntry):
        """Schedules a reminder to be sent to the user."""
        async def remove_entry():
            await self.delete_reminder_by_id(reminder_id)

        def remove_task():
            self.send_reminders_tasks.pop(reminder_id, None)

        reminder_id = entry['reminder_id']
        seconds = (entry['due'] - discord.utils.utcnow()).total_seconds()
        await asyncio.sleep(seconds)

        logger = discordlogger.get_logger()
        db = self.bot.dbreminders
        row = await db.get_one(
            db.TABLE_NAME, 'reminder_id',
            where={'reminder_id': reminder_id}
        )
        if row is None:
            # Reminder was deleted during wait; don't send
            return logger.debug(
                'Reminders: failed to send reminder, '
                f'ID {reminder_id}: reminder was deleted during wait'
            )

        description = []
        # Include mention and time if message is not an announcement
        if not self.is_announcement(entry['content']):
            description.append(
                '<@{}> **{}'.format(
                    entry['user_id'],
                    discord.utils.format_dt(entry['due'], style='F')
                )
            )
            if seconds < 0:
                description.append(' (overdue)')
            description.append('**\n')
        description.append(entry['content'].lstrip())

        channel = self.bot.get_partial_messageable(entry['channel_id'])
        try:
            await channel.send(''.join(description))
        except discord.Forbidden as e:
            logger.debug(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'was forbidden from sending: {e}'
            )
        except discord.HTTPException as e:
            logger.warning(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'HTTPException occurred: {e}'
            )
        else:
            # Successful; remove reminder task and database entry
            logger.debug(
                f'Reminders: successfully sent reminder, ID {reminder_id}')
            await remove_entry()
        finally:
            remove_task()

    @tasks.loop(minutes=10)
    async def send_reminders(self):
        """Periodically queries the database for reminders and
        spins up reminder tasks as needed.
        """
        db = self.bot.dbreminders
        now = discord.utils.utcnow()

        async for entry in db.yield_rows(db.TABLE_NAME):
            due = entry['due'].replace(tzinfo=datetime.timezone.utc)
            self.check_to_create_reminder(
                now=now,
                reminder_id=entry['reminder_id'],
                user_id=entry['user_id'],
                channel_id=entry['channel_id'],
                due=due,
                content=entry['content']
            )

    @send_reminders.before_loop
    async def before_send_reminders(self):
        await self.bot.wait_until_ready()










def setup(bot):
    bot.add_cog(Reminders(bot))
