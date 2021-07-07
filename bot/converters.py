#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import functools
import re
from typing import Optional

import dateparser
import discord
from discord.ext import commands
import emoji
import pytz

from bot import errors, utils

__all__ = (
    'CodeBlock', 'CommandConverter', 'DatetimeConverter',
    'DollarConverter', 'TimezoneConverter',
    'UnicodeEmojiConverter'
)


class CodeBlock:
    REGEX = re.compile(
        r'```(?:(?P<language>\w*)(?:\n))?\s*(?P<code>.*?)\s*```',
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, language, code):
        self.language = language or None
        self.code = code

    @classmethod
    def from_search(cls, s: str) -> Optional['CodeBlock']:
        match = cls.REGEX.search(s)
        return None if match is None else cls(**match.groupdict())

    @classmethod
    async def convert(cls, ctx, arg, required=False):
        """Converts a code block with an optional language name
        and strips whitespace from the following block.

        If `required`, commands.UserInputError is raised when the argument
        is not a code block.

        """
        match = cls.REGEX.match(arg)
        if match is None:
            if required:
                raise commands.UserInputError('Argument must be a code block.')
            return cls(language=None, code=arg)
        return cls(**match.groupdict())


class CommandConverter(commands.Converter):
    """Converts to a Command.

    Args:
        run_checks (bool): If True, checks if the bot can run with the
            given command and context. Otherwise returns the command
            regardless if the user is able to run it.

    """
    def __init__(self, run_checks=True):
        self.run_checks = True

    async def can_run(self, ctx, command, *, call_once=False):
        """A variant of Command.can_run() that doesn't check if
        the command is disabled."""
        if not self.run_checks:
            return True

        original = ctx.command
        ctx.command = command

        try:
            if not await ctx.bot.can_run(ctx, call_once=call_once):
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
                # since we have no checks, then we just return True.
                return True

            return await discord.utils.async_all(
                predicate(ctx) for predicate in predicates)
        finally:
            ctx.command = original

    async def convert(self, ctx, argument) -> commands.Command:
        """
        Args:
            ctx (commands.Context)
            argument (str)

        Returns:
            commands.Command

        Raises:
            BadArgument

        """
        c: Optional[commands.Command] = ctx.bot.get_command(argument)
        try:
            if c is None:
                raise commands.BadArgument(
                    f'Could not convert "{argument}" into a command.')
            elif not await self.can_run(ctx, c):
                raise commands.BadArgument(f'The user cannot use "{argument}".')
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

    async def convert(self, ctx, arg) -> datetime.datetime:
        dt = await ctx.bot.loop.run_in_executor(
            None,
            functools.partial(
                dateparser.parse,
                arg,
                settings={
                    'PREFER_DATES_FROM': self.PREFER_DATES_FROM[self.prefer_future]
                }
            )
        )

        if dt is None:
            raise commands.BadArgument('Could not parse your date.')
        elif dt.tzinfo is None:
            if self.stored_tz:
                # Since the datetime was user inputted, if it's naive
                # it's probably in their timezone so don't assume it's UTC
                dt = await ctx.bot.localize_datetime(
                    ctx.author.id, dt, assume_utc=False, return_row=False)
            else:
                dt = dt.replace(tzinfo=datetime.timezone.utc)

        return dt


class DollarConverter(commands.Converter):
    def __init__(self, negative=True, zero=True, positive=True):
        self.negative = negative
        self.zero = zero
        self.positive = positive

    async def convert(self, ctx, argument):
        dollars = utils.parse_dollars(argument)

        if not self.negative and dollars < 0:
            raise errors.DollarInputError(
                'Negative dollar values are not allowed.', argument)
        if not self.zero and dollars == 0:
            raise errors.DollarInputError(
                'Zero dollars is not allowed.', argument)
        if not self.positive and dollars > 0:
            raise errors.DollarInputError(
                'Positive dollar values are not allowed.', argument)

        return dollars


class TimezoneConverter(commands.Converter):
    """Converts to a timezone using pytz.timezone()."""
    async def convert(self, ctx, argument):
        try:
            return pytz.timezone(argument)
        except pytz.UnknownTimeZoneError as e:
            raise errors.UnknownTimezoneError(argument) from e


class UnicodeEmojiConverter(commands.Converter):
    """Converts to a string unicode emoji.

    This merely just uses a lookup table to verify if the argument
    is a unicode emoji; no other conversion is done.

    Args:
        partial_emoji (bool): If True, returns a discord.PartialEmoji
            instead of just the emoji as a string.

    Returns:
        PartialEmoji
        str

    """
    def __init__(self, partial_emoji=False):
        self.partial_emoji = partial_emoji

    async def convert(self, ctx, argument):
        if argument in emoji.UNICODE_EMOJI_ALIAS_ENGLISH:
            if self.partial_emoji:
                return discord.PartialEmoji(name=argument)
            return argument

        raise commands.BadArgument(
            f'Could not convert "{argument}" into a unicode emoji.')
