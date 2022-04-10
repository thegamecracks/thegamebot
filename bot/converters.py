#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import datetime
import re
from typing import Optional

import dateparser
import discord
from discord.ext import commands

from main import Context


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
        self.run_checks = True

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
    PREFER_DATES_FROM = {
        None: 'current_period',
        True: 'future',
        False: 'past'
    }

    def __init__(self, *, prefer_future=None, stored_tz=True):
        self.prefer_future = prefer_future
        self.stored_tz = stored_tz

    async def convert(self, ctx: Context, arg: str) -> datetime.datetime:
        dt = await asyncio.to_thread(
            dateparser.parse,
            arg,
            settings={
                'PREFER_DATES_FROM': self.PREFER_DATES_FROM[self.prefer_future]
            }
        )

        if dt is None:
            raise commands.BadArgument('Could not parse your date.')
        elif dt.tzinfo is None:
            if self.stored_tz:
                # Since the datetime was user inputted, if it's naive
                # it's probably in their timezone so don't assume it's UTC
                dt = await ctx.bot.localize_datetime(ctx.author.id, dt)
            else:
                dt = dt.replace(tzinfo=datetime.timezone.utc)

        return dt
