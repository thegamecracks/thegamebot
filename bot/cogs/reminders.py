#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import re
from typing import Literal, Union

import dateparser
from dateutil.relativedelta import relativedelta
import discord
from discord.ext import commands, tasks
import pytz

from bot import errors, utils
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

    MAXIMUM_REMINDERS = 10
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
        # NOTE: this bot is small so this isn't required but if the bot
        # never restarts frequently, the cache could grow forever,
        # so this could use an LRU cache implementation
        self.send_reminders_tasks = {}  # reminder_id: Task
        self.send_reminders.start()

    def cog_unload(self):
        self.send_reminders.cancel()





    async def add_reminder(self, user_id, due, content):
        """Adds a reminder and invalidates the user's cache."""
        reminder_id = await self.bot.dbreminders.add_reminder(
            user_id, due, content)
        self.cache.pop(user_id, None)

        self.check_to_create_reminder(reminder_id, user_id, content, due)

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
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_reminders(self, ctx, index: int = None):
        """See your reminders."""
        reminder_list = await self.get_reminders(ctx.author.id)

        if not reminder_list:
            return await ctx.send("You don't have any reminders.")

        if index is None:
            lines = [
                '{}. {}: {}'.format(
                    i,
                    discord.utils.format_dt(
                        reminder['due'].replace(
                            tzinfo=datetime.timezone.utc
                        ), 'R'
                    ),
                    utils.truncate_message(reminder['content'], 40, max_lines=1)
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
            description=reminder['content'],
            color=utils.get_user_color(ctx.bot, ctx.author)
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
    async def client_reminders_add(self, ctx, *, time_and_reminder):
        """Add a reminder to be sent in your DMs.

Usage:
    <command> at 10pm EST to <x>
    <command> in 30 sec/min/h/days to <x>
    <command> on wednesday to <x>
Note that the time and your reminder message have to be separated with "to".
If you have not explicitly said a timezone in the command but you have
provided the bot your timezone before with "timezone set", that timezone will
be used instead of UTC.

Time is rounded down to the minute if seconds are not specified.
You can have a maximum of 5 reminders."""
        total_reminders = len(await self.get_reminders(ctx.author.id))

        if total_reminders < self.MAXIMUM_REMINDERS:
            # Get current time in UTC without microseconds
            utcnow = discord.utils.utcnow().replace(microsecond=0)
            try:
                # Separate time and reminder,
                # also making sure that content is provided
                when, content = [s.strip() for s in re.split(
                    'to', time_and_reminder, maxsplit=1, flags=re.IGNORECASE
                )]
                async with ctx.typing():
                    when = await self.parse_datetime(ctx, when)
                if when is None:
                    return await ctx.send(
                        'Could not understand your given time.')
            except (ValueError, AttributeError):
                return await ctx.send(
                    'Could not understand your reminder request. Check this '
                    "command's help page for allowed syntax."
                )

            td = when - utcnow
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
                return await ctx.send(
                    'You must have a message with your reminder.')

            await self.add_reminder(ctx.author.id, when, content)

            await ctx.send(
                'Your {} reminder has been added for: {}'.format(
                    ctx.bot.inflector.ordinal(total_reminders + 1),
                    discord.utils.format_dt(when, style='F')
                )
            )
        else:
            await ctx.send(
                'You have reached the maximum limit of '
                f'{self.MAXIMUM_REMINDERS} reminders.'
            )


    @commands.command(
        name='remind', aliases=('remindme',),
        brief='Shorthand for reminder add.',
        help=client_reminders_add.callback.__doc__
    )
    async def client_remind(self, ctx, *, time_and_reminder):
        await self.client_reminders_add(ctx, time_and_reminder=time_and_reminder)





    def check_to_create_reminder(
            self, reminder_id, user_id, content, when, now=None):
        """Create a reminder task if needed.

        This does not store the reminder in the database.

        Returns:
            bool: Indicates whether the task was created or not.

        """
        if reminder_id in self.send_reminders_tasks:
            # Task already exists; skip
            return False

        if now is None:
            now = discord.utils.utcnow()
        td = when - now

        is_soon = td < self.send_reminders_near_due
        if is_soon:
            self.create_reminder_task(reminder_id, user_id, when, td, content)
        return is_soon

    def create_reminder_task(self, reminder_id, user_id, when, td, content):
        """Adds a reminder task to the bot loop and logs it."""
        task = self.bot.loop.create_task(
            self.reminder_coro(reminder_id, user_id, when, content)
        )
        self.send_reminders_tasks[reminder_id] = task

        discordlogger.get_logger().info(
            f'Reminders: created reminder task {reminder_id} '
            f'for {user_id}, due in {td}')

        return task

    async def reminder_coro(self, reminder_id, user_id, when, content):
        """Schedules a reminder to be sent to the user."""
        async def remove_entry():
            await self.delete_reminder_by_id(reminder_id)

        def remove_task():
            self.send_reminders_tasks.pop(reminder_id, None)

        logger = discordlogger.get_logger()

        db = self.bot.dbreminders

        now = discord.utils.utcnow()
        seconds = (when - now).total_seconds()

        await asyncio.sleep(seconds)

        if await db.get_one(db.TABLE_NAME, 'reminder_id',
                            where={'reminder_id': reminder_id}) is None:
            # Reminder was deleted during wait; don't send
            logger.info(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                'reminder was deleted during wait'
            )

        user = await self.bot.try_user(user_id)

        if user is None:
            # Could not find user; remove database entry
            logger.info(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'could not find user: {user_id}'
            )
            await remove_entry()
            remove_task()
            return

        when_str = await self.bot.strftime_user(user.id, when, aware='%c %Z')

        if seconds == 0:
            title = f'Late reminder for {when_str}'
        else:
            title = f'Reminder for {when_str}'
        embed = discord.Embed(
            title=title,
            description=content,
            color=utils.get_user_color(self.bot, user),
            timestamp=now
        )

        try:
            await user.send(embed=embed)
        except discord.Forbidden as e:
            logger.info(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'was forbidden from sending: {e}'
            )
        except discord.HTTPException as e:
            logger.info(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'HTTPException occurred: {e}'
            )
        else:
            # Successful; remove reminder task and database entry
            logger.info('Reminders: successfully sent reminder, '
                        f'ID {reminder_id}')
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
                entry['reminder_id'], entry['user_id'],
                entry['content'], due, now
            )

    @send_reminders.before_loop
    async def before_send_reminders(self):
        await self.bot.wait_until_ready()










def setup(bot):
    bot.add_cog(Reminders(bot))
