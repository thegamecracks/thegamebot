import discord
from discord.ext import commands
import emoji

from bot import errors, utils

__all__ = ('CommandConverter', 'DollarConverter', 'UnicodeEmojiConverter')


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

    async def convert(self, ctx, argument):
        """
        Args:
            ctx (commands.Context)
            argument (str)

        Returns:
            commands.Command

        Raises:
            BadArgument

        """
        c = ctx.bot.get_command(argument)
        try:
            if c is None:
                raise commands.BadArgument(
                    f'Could not convert "{argument}" into a command.')
            elif not await self.can_run(ctx, c):
                raise commands.BadArgument(f'The user cannot use "{argument}".')
        except commands.CheckFailure as e:
            raise commands.BadArgument(str(e)) from e
        return c


class DollarConverter(commands.Converter):
    def __init__(self, negative=True, zero=True, positive=True):
        self.negative = negative
        self.zero = zero
        self.positive = positive

    async def convert(self, ctx, argument):
        dollars = utils.parse_dollars(argument)

        if not self.negative and dollars < 0:
            raise errors.DollarInputError(
                'Negative dollar values are not allowed.')
        if not self.zero and dollars == 0:
            raise errors.DollarInputError('Zero dollars is not allowed.')
        if not self.positive and dollars > 0:
            raise errors.DollarInputError(
                'Positive dollar values are not allowed.')

        return dollars


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
