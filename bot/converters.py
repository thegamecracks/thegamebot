#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import re
from typing import Optional, cast

import dateparser
import discord
from discord import app_commands
from discord.ext import commands

from main import Context, TheGameBot


class CodeBlock:
    REGEX = re.compile(
        r'```(?:(?P<language>\w*)\n)?\s*(?P<code>.*?)\s*```',
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, language: str | None, code: str):
        self.language = language or None
        self.code = code

    @classmethod
    def from_search(cls, s: str) -> Optional['CodeBlock']:
        match = cls.REGEX.search(s)
        return None if match is None else cls(**match.groupdict())

    @classmethod
    async def convert(cls, ctx: Context, arg, required=False):
        """Converts a code block with an optional language name
        and strips whitespace from the following block.

        If `required`, the :class:`commands.BadArgument` exception
        will be raised when the argument is not a code block.

        """
        match = cls.REGEX.match(arg)
        if match is None:
            if required:
                raise commands.BadArgument('Argument must be a code block.')
            return cls(language=None, code=arg)
        return cls(**match.groupdict())


class CommandConverter(commands.Converter):
    """Converts to a Command.

    Args:
        run_checks (bool): If True, checks if the bot can run with the
            given command and context. Otherwise, returns the command
            regardless if the user is able to run it.

    """
    def __init__(self, run_checks=True):
        self.run_checks = run_checks

    async def can_run(self, ctx: Context, command: commands.Command, *, call_once=False):
        """A variant of Command.can_run() that doesn't check if
        the command is disabled."""
        if not self.run_checks:
            return True

        original = ctx.command
        ctx.command = self

        try:
            if not await ctx.bot.can_run(ctx):
                return False

            cog = command.cog
            if cog is not None:
                local_check = commands.Cog._get_overridden_method(cog.cog_check)
                if local_check is not None:
                    ret = await discord.utils.maybe_coroutine(local_check, ctx)
                    if not ret:
                        return False

            predicates = command.checks
            if not predicates:
                return True

            return await discord.utils.async_all(predicate(ctx) for predicate in predicates)  # type: ignore
        finally:
            ctx.command = original

    async def convert(self, ctx, argument) -> commands.Command:
        c: Optional[commands.Command] = ctx.bot.get_command(argument)
        try:
            if c is None or c.hidden:
                raise commands.BadArgument(f'Could not find the given command.')
            elif not await self.can_run(ctx, c):
                raise commands.BadArgument(f'You cannot use "{c.qualified_name}".')
        except commands.CheckFailure as e:
            raise commands.BadArgument(str(e)) from e
        return c


class DatetimeConverter(commands.Converter):
    """Parse a datetime."""
    DEFAULT_SETTINGS = {
        'PREFER_DATES_FROM': 'current_period'
        # 'current_period', 'future', 'past'
    }

    def __init__(self, *, settings: dict = None, stored_tz=True):
        self.settings = settings or self.DEFAULT_SETTINGS
        self.stored_tz = stored_tz

    async def parse_datetime(self, bot: TheGameBot, user_id: int, arg: str):
        dt = await asyncio.to_thread(dateparser.parse, arg, settings=self.settings)

        if dt is None:
            raise commands.BadArgument('Could not parse your date.')
        elif dt.tzinfo is None:
            if self.stored_tz:
                # Use the user's timezone if they supplied one before
                dt = await bot.localize_datetime(user_id, dt)
            else:
                dt = dt.replace(tzinfo=datetime.timezone.utc)

        return dt

    async def convert(self, ctx: Context, arg: str) -> datetime.datetime:
        return await self.parse_datetime(ctx.bot, ctx.author.id, arg)


class DatetimeTransformer(app_commands.Transformer):
    """A transformer variant of the DatetimeConverter."""
    AUTOCOMPLETE_CURRENT_TIME = True

    async def parse_datetime(
        self, bot: TheGameBot, user_id: int,
        now: datetime.datetime, value: str,
        *args, **kwargs
    ) -> datetime.datetime:
        """Converts the given value to a datetime.

        Normally the DatetimeConverter class is used to handle
        parsing the value, but subclasses may override this to
        change the behaviour.

        :raises commands.BadArgument: The given input could not be parsed.

        """
        return await DatetimeConverter(
            *args, **kwargs
        ).parse_datetime(bot, user_id, value)

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> list[app_commands.Choice[str]]:
        bot = cast(TheGameBot, interaction.client)
        now = interaction.created_at.replace(microsecond=0)
        # microsecond is removed for simpler ISO output

        choices = []

        try:
            dt = await self.parse_datetime(bot, interaction.user.id, now, value)
        except commands.BadArgument:
            pass
        else:
            choices.append(app_commands.Choice(
                name=dt.strftime(f'%A, {dt.day} %B %Y, %H:%M (%Z)'), value=value
            ))

        if self.AUTOCOMPLETE_CURRENT_TIME:
            choices.append(app_commands.Choice(name='Current time', value='now'))

        return choices

    async def transform(self, interaction: discord.Interaction, value: str):
        bot = cast(TheGameBot, interaction.client)
        now = interaction.created_at.replace(microsecond=0)
        try:
            return await self.parse_datetime(bot, interaction.user.id, now, value)
        except commands.BadArgument as e:
            raise app_commands.AppCommandError(*e.args) from None


DatetimeTransform = app_commands.Transform[datetime.datetime, DatetimeTransformer]


class FutureDatetimeTransformer(DatetimeTransformer):
    AUTOCOMPLETE_CURRENT_TIME = False
    AUTOCOMPLETE_DEFAULTS = [
        'in 1 minute',
        'in 10 minutes',
        'in 30 minutes',
        'in 1 hour'
    ]

    DEFAULT_SETTINGS: dict = {
        'PREFER_DATES_FROM': 'future',
        'RETURN_AS_TIMEZONE_AWARE': True,
        'TIMEZONE': 'UTC',
    }

    async def parse_datetime(
        self, bot: TheGameBot, user_id: int, now: datetime.datetime, value: str,
        *args, **kwargs
    ):
        """Converts a value to a datetime, requiring that the datetime
        is in the future.

        :raises commands.BadArgument: The given input could not be parsed.
        :raises app_commands.AppCommandError:
            The given date must be in the future.

        """
        # NOTE: This parsing logic may be movable to DatetimeConverter

        # A timezone is needed so we first check the string for one.
        # If no TZ is provided then the user's timezone is used.
        tz: datetime.tzinfo
        value, tz = dateparser.timezone_parser.pop_tz_offset_from_string(value)
        if not tz:
            dt = await bot.localize_datetime(user_id, now)
            tz = dt.tzinfo

        # Parse the user's string relative to the timezone
        settings = self.DEFAULT_SETTINGS.copy()
        tz_now = now.astimezone(tz)
        settings['RELATIVE_BASE'] = tz_now
        settings['TIMEZONE'] = tz_now.tzname()

        dt = await super().parse_datetime(
            bot, user_id, now, value,
            *args, settings=settings, **kwargs
        )

        delta = dt - now
        if delta.total_seconds() <= 0:
            raise app_commands.AppCommandError('A date in the future must be selected!')

        return dt

    async def autocomplete(self, interaction: discord.Interaction, value: str):
        choices = await super().autocomplete(interaction, value)

        choices.extend(
            app_commands.Choice(name=choice.capitalize(), value=choice)
            for choice in self.AUTOCOMPLETE_DEFAULTS
        )

        return choices


FutureDatetimeTransform = app_commands.Transform[
    datetime.datetime, FutureDatetimeTransformer
]


class IndexConverter(commands.Converter[list[int]]):
    """Convert an argument to a list of indices or a range.

    Formats supported:
        1        # [0]
        1, 9, 4  # [0, 4, 8]; indices are sorted
        1-3      # [0, 1, 2]

    Parameters
    ----------
    max_digits: int
        The max number of digits an index can have.

    """
    FORMAT_REGEX = re.compile(r'(?P<start>\d+)(?:-(?P<end>\d+))?')

    def __init__(self, *, max_digits: int = 3):
        self.max_length = max_digits

    async def convert(self, ctx: Context, argument) -> list[int]:
        indices = set()

        for m in self.FORMAT_REGEX.finditer(argument):
            # ignore unreasonably high indices
            if len(m['start']) > self.max_length or m['end'] and len(m['end']) > self.max_length:
                continue

            start = int(m['start'])
            end = int(m['end'] or start)

            if start < 1:
                raise commands.BadArgument('Your starting index cannot be 0.')
            elif end < start:
                raise commands.BadArgument(
                    f'The end index cannot be lower '
                    f'than the start index (`{start}-{end}`).'
                )

            for i in range(start - 1, end):
                indices.add(i)

        if not indices:
            raise commands.BadArgument('No indices were specified.')

        return sorted(indices)
