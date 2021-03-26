"""
Note: This requires members intent to be enabled in order to send reminders."""
import asyncio
import datetime
import re

import dateparser
import discord
from discord.ext import commands, tasks
import pytz

from bot import utils
from bot.other import discordlogger


class Reminders(commands.Cog):
    """Commands for setting up reminders."""
    qualified_name = 'Reminders'

    MINIMUM_REMINDER_TIME = 30

    DATEPARSER_SETTINGS = {
        'PREFER_DATES_FROM': 'future',
        'RETURN_AS_TIMEZONE_AWARE': False,
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
        if self.bot.intents.members:
            # Only send reminders when members intent is enabled
            self.send_reminders_tasks = {}  # reminder_id: Task
            self.send_reminders.start()
        else:
            self.description += ('\n**NOTE**: The bot currently '
                                 'cannot send reminders at this time.')

    def cog_unload(self):
        self.send_reminders.cancel()





    async def add_reminder(self, user_id, utcdue, content):
        """Adds a reminder and invalidates the user's cache."""
        reminder_id = await self.bot.dbreminders.add_reminder(
            user_id, utcdue, content)
        self.cache.pop(user_id, None)

        self.check_to_create_reminder(reminder_id, user_id, content, utcdue)

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

    async def send_with_disclaimer(
            self, messageable, content=None, *args, **kwargs):
        if content is not None and not self.bot.intents.members:
            content += ('\nNote: the bot currently cannot send '
                        'reminders at this time.')

        return await messageable.send(content, *args, **kwargs)





    def parse_datetime(self, date_string):
        # Determine timezone
        date_string, tz = dateparser.timezone_parser.pop_tz_offset_from_string(date_string)

        if tz is not None:
            # Make times relative to the given timezone instead of UTC
            settings = self.DATEPARSER_SETTINGS.copy()
            settings['RELATIVE_BASE'] = pytz.UTC.localize(
                datetime.datetime.utcnow()).astimezone(tz)
        else:
            settings = self.DATEPARSER_SETTINGS

        dt = dateparser.parse(date_string, settings=settings)

        if tz is not None:
            # Offset back to UTC and make it timezone-naive
            dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)

        return dt


    @commands.command(
        name='addreminder',
        aliases=['remindme'])
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def client_addreminder(self, ctx, *, time_and_reminder):
        """Add a reminder.
Usage:

    <command> at 10pm EST to <x>
    <command> in 30 sec/min/h/days to <x>
    <command> on wednesday to <x> (checks the current day in UTC)

Reminders will appear in your DMs.
Time is rounded down to the minute if seconds are not specified.
You can have a maximum of 5 reminders."""
        await ctx.channel.trigger_typing()

        total_reminders = len(await self.get_reminders(ctx.author.id))

        if total_reminders < 5:
            # Get current time in UTC without microseconds
            utcnow = datetime.datetime.utcnow().replace(microsecond=0)
            try:
                # Separate time and reminder,
                # also making sure that content is provided
                when, content = re.split(' to ', time_and_reminder, flags=re.IGNORECASE)
                when = self.parse_datetime(when)
            except (ValueError, AttributeError):
                return await self.send_with_disclaimer(
                    ctx,
                    'Could not understand your reminder request. Check this '
                    "command's help page for allowed syntax."
                )

            td = when - utcnow
            seconds_until = td.total_seconds()

            if seconds_until < 0:
                return await self.send_with_disclaimer(
                    ctx, 'You cannot create a reminder for the past.')
            elif seconds_until < self.MINIMUM_REMINDER_TIME:
                return await self.send_with_disclaimer(
                    ctx, 'You must set a reminder lasting for at '
                    f'least {self.MINIMUM_REMINDER_TIME} seconds.'
                )
            elif not content:
                return await self.send_with_disclaimer(
                    ctx, 'You must have a message with your reminder.')

            # Round seconds down if td does not specify seconds
            if td.seconds % 60 == 0:
                utcnow = utcnow.replace(second=0)

            utcdue = utcnow + td

            await self.add_reminder(ctx.author.id, utcdue, content)

            await self.send_with_disclaimer(
                ctx, 'Your {} reminder has been added!'.format(
                    ctx.bot.inflector.ordinal(total_reminders + 1)
                ),
                embed=discord.Embed(
                    color=utils.get_user_color(ctx.bot, ctx.author),
                    timestamp=utcdue
                )
            )
        else:
            await self.send_with_disclaimer(
                ctx, 'Sorry, but you have reached your maximum limit '
                'of 5 reminders.'
            )




    @commands.command(name='removereminder')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_removereminder(self, ctx, index: int):
        """Remove a reminder.

To see a list of your reminders and their indices, use the showreminders command.
To remove several reminders, use the removereminders command."""
        await ctx.channel.trigger_typing()

        reminder_list = await self.get_reminders(ctx.author.id)

        if len(reminder_list) == 0:
            return await self.send_with_disclaimer(
                ctx, "You already don't have any reminders.")

        try:
            reminder = reminder_list[index - 1]
        except IndexError:
            await self.send_with_disclaimer(
                ctx, 'That reminder index does not exist.')
        else:
            await self.delete_reminder_by_id(reminder['reminder_id'])
            await self.send_with_disclaimer(
                ctx, 'Reminder successfully deleted!')





    @commands.command(name='removereminders')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def client_removereminders(self, ctx, indices):
        """Remove multiple reminders.

You can remove "all" of your reminders or remove only a section of it by specifying the start and end indices ("1-4").
To remove only one reminder, use the removereminder command."""
        await ctx.channel.trigger_typing()

        reminder_list = await self.get_reminders(ctx.author.id)

        if len(reminder_list) == 0:
            return await self.send_with_disclaimer(
                ctx, "You already don't have any reminders.")

        if indices.lower() == 'all':
            for reminder in reminder_list:
                await self.delete_reminder_by_id(reminder['reminder_id'])
            await self.send_with_disclaimer(
                ctx, 'Reminders successfully deleted!')

        else:
            start, end = [int(n) for n in indices.split('-')]
            start -= 1
            if start < 0:
                return await self.send_with_disclaimer(
                    ctx, 'Start must be 1 or greater.')
            elif end > len(reminder_list):
                return await self.send_with_disclaimer(
                    ctx, f'End must only go up to {len(reminder_list)}.')

            for i in range(start, end):
                reminder = reminder_list[i]
                await self.delete_reminder_by_id(reminder['reminder_id'])
            await self.send_with_disclaimer(
                ctx, 'Reminders successfully deleted!')





    @commands.command(name='showreminder')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_showreminder(self, ctx, index: int):
        """Show one of your reminders."""
        await ctx.channel.trigger_typing()

        reminder_list = await self.get_reminders(ctx.author.id)

        if len(reminder_list) == 0:
            return await self.send_with_disclaimer(
                ctx, "You don't have any reminders.")

        if index < 1:
            return await self.send_with_disclaimer(
                ctx, 'Index must be 1 or greater.')

        try:
            reminder = reminder_list[index - 1]
        except IndexError:
            await self.send_with_disclaimer(
                ctx, 'That index does not exist.')
        else:
            utcdue = datetime.datetime.fromisoformat(reminder['due'])
            embed = discord.Embed(
                title=f'Reminder #{index:,}',
                description=reminder['content'],
                color=utils.get_user_color(ctx.bot, ctx.author),
                timestamp=utcdue
            ).add_field(
                name='Due in',
                value=utils.timedelta_string(
                    utils.datetime_difference(
                        utcdue,
                        datetime.datetime.utcnow()
                    ),
                    inflector=ctx.bot.inflector
                )
            ).set_footer(text='Due date')
            await self.send_with_disclaimer(ctx, embed=embed)





    @commands.command(name='showreminders')
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_showreminders(self, ctx):
        """Show all of your reminders."""
        await ctx.channel.trigger_typing()

        reminder_list = await self.get_reminders(ctx.author.id)

        if len(reminder_list) == 0:
            return await self.send_with_disclaimer(
                ctx, "You don't have any reminders.")

        # Create fields for each reminder, limiting them
        # to 140 characters/5 lines
        fields = [
            utils.truncate_message(reminder['content'], 140, max_lines=5)
            for reminder in reminder_list
        ]
        color = utils.get_user_color(ctx.bot, ctx.author)

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Reminders",
            color=color,
            timestamp=datetime.datetime.now().astimezone()
        )

        for i, content in enumerate(fields, start=1):
            embed.add_field(name=f'Reminder {i:,}', value=content)

        await self.send_with_disclaimer(ctx, embed=embed)





    def check_to_create_reminder(
            self, reminder_id, user_id, content, utcwhen, utcnow=None):
        """Create a reminder task if needed.

        This does not store the reminder in the database.

        Returns:
            bool: Indicates whether the task was created or not.

        """
        if not self.bot.intents.members:
            # Prevents creating reminder tasks without members intent
            # as get_user() doesn't work, meaning it's basically
            # impossible to send DMs
            return False

        if utcnow is None:
            utcnow = datetime.datetime.utcnow()

        td = utcwhen - utcnow
        zero_td = datetime.timedelta()

        if reminder_id in self.send_reminders_tasks:
            # Task already exists; skip
            return False

        if td < zero_td:
            # Overdue; send message immediately
            self.create_reminder_task(
                reminder_id, user_id, utcwhen, zero_td, content)
            return True
        elif td < self.send_reminders_near_due:
            # Close to due date; spin up task
            self.create_reminder_task(
                reminder_id, user_id, utcwhen, td, content)
            return True

    def create_reminder_task(self, reminder_id, user_id, utcwhen, td, content):
        """Adds a reminder task to the bot loop and logs it."""
        task = self.bot.loop.create_task(
            self.reminder_coro(reminder_id, user_id, utcwhen, content)
        )
        self.send_reminders_tasks[reminder_id] = task

        discordlogger.get_logger().info(
            f'Reminders: created reminder task for {user_id}, due in {td}')

        return task

    async def reminder_coro(self, reminder_id, user_id, utcwhen, content):
        """Schedules a reminder to be sent to the user."""
        async def remove_entry():
            await self.delete_reminder_by_id(reminder_id)

        def remove_task():
            self.send_reminders_tasks.pop(reminder_id, None)

        def log_and_print(message):
            discordlogger.get_logger().info(message)
            print(message)

        db = self.bot.dbreminders

        utcnow = datetime.datetime.utcnow()
        seconds = (utcwhen - utcnow).total_seconds()

        await asyncio.sleep(seconds)

        if await db.get_one(db.TABLE_NAME, 'reminder_id',
                            where={'reminder_id': reminder_id}) is None:
            # Reminder was deleted during wait; don't send
            return

        user = self.bot.get_user(user_id)

        if user is None:
            # Could not find user; remove database entry
            log_and_print(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'could not find user: {user_id}'
            )
            await remove_entry()
            remove_task()
            return

        if seconds == 0:
            title = f'Late reminder for {utcwhen.strftime("%c UTC")}'
        else:
            title = f'Reminder for {utcwhen.strftime("%c UTC")}'
        embed = discord.Embed(
            title=title,
            description=content,
            color=utils.get_user_color(self.bot, user),
            timestamp=datetime.datetime.now().astimezone()
        )

        try:
            await user.send(embed=embed)
        except discord.Forbidden as e:
            log_and_print(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'was forbidden from sending: {e}'
            )
        except discord.HTTPException as e:
            log_and_print(
                f'Reminders: failed to send reminder, ID {reminder_id}: '
                f'HTTPException occurred: {e}'
            )
        else:
            # Successful; remove reminder task and database entry
            discordlogger.get_logger().info(
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
        utcnow = datetime.datetime.utcnow()

        async for entry in db.yield_rows(db.TABLE_NAME):
            utcwhen = datetime.datetime.fromisoformat(entry['due'])

            self.check_to_create_reminder(
                entry['reminder_id'], entry['user_id'],
                entry['content'], utcwhen, utcnow
            )

    @send_reminders.before_loop
    async def before_send_reminders(self):
        await self.bot.wait_until_ready()










def setup(bot):
    bot.add_cog(Reminders(bot))