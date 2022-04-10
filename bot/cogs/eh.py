#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
import random
import sys
import textwrap
import time
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot import errors
from main import Context, TheGameBot

COOLDOWN_DESCRIPTIONS = {
    commands.BucketType.default: (
        'Too many people have used this command globally. '
        'The limit is {times}.'
    ),
    commands.BucketType.user: (
        'You have used this command too many times. '
        'The personal limit is {times}.'
    ),
    commands.BucketType.guild: (
        'Too many people have used this command {here}. '
        'The limit is {times}.'
    ),
    commands.BucketType.channel: (
        'Too many people have used this command {here}. '
        'The limit is {times}.'
    ),
    commands.BucketType.member: (
        'You have used this command too many times {here}. '
        'The personal limit is {times}.'
    ),
    commands.BucketType.category: (
        'Too many people have used this command in this server category. '
        'The limit is {times}.'
    ),
    commands.BucketType.role: (
        'Too many people with the same role have used this command. '
        'The limit is {times}.'
    )
}

MAX_CONCURRENCY_DESCRIPTIONS = {
    commands.BucketType.default: (
        'This command has globally reached the maximum concurrent usage of {n}.'
    ),
    commands.BucketType.user: (
        "You have reached this command's maximum concurrent usage of {n}."
    ),
    commands.BucketType.guild: (
        'This command has reached the maximum concurrent usage of {n} {here}.'
    ),
    commands.BucketType.channel: (
        'This command has reached the maximum concurrent usage of {n} {here}.'
    ),
    commands.BucketType.member: (
        "You have reached this command's maximum concurrent usage of {n} {here}."
    ),
    commands.BucketType.category: (
        'This command has reached the maximum concurrent usage of {n} '
        'in this channel category.'
    ),
    commands.BucketType.role: (
        'This command has reached the maximum concurrent usage of {n} '
        'for your top role.'
    )
}


def generate_error_code():
    """Generate an error code for a command error."""
    return ''.join(random.choices('0123456789ABCDEF', k=4))


def get_command_signature(ctx: Context):
    invoked_with = ctx.invoked_with
    if ctx.command.parent:
        invoked_with = ' '.join([ctx.command.full_parent_name, invoked_with])

    return '{}{} {}'.format(
        ctx.prefix, invoked_with,
        ctx.command.signature
    )


def humanize_permissions(perms: list[str]):
    # same code that MissingPermissions uses in its constructor
    return [
        p.replace('_', ' ').replace('guild', 'server').title()
        for p in perms
    ]


def resolve_role(ctx: Context | discord.Interaction, role: str | int) -> str:
    if isinstance(role, int):
        return f'<@&{role}>'
    elif resolved := discord.utils.get(ctx.guild.roles, name=role):
        return resolved.mention
    return role


logger = logging.getLogger('discord')


def get_ratelimit_description(
    ctx: Context | discord.Interaction,
    error: commands.CommandOnCooldown | commands.MaxConcurrencyReached
        | app_commands.CommandOnCooldown
):
    """Returns an embed describing a given cooldown/max concurrency error."""
    def get_cooldown_here():
        if bucket is None:
            return 'here'
        elif ctx.guild:
            if bucket == commands.BucketType.guild:
                return 'on this server'
            return 'in this channel'
        else:
            return 'in this DM'

    def light_round(n: int | float):
        if isinstance(n, int):
            return str(n)
        elif n.is_integer():
            return str(int(n))
        return str(round(n, 1))

    if isinstance(ctx, commands.Context):
        bot = ctx.bot
    else:
        bot = cast(TheGameBot, ctx.client)

    # Initial variables to determine
    description = 'This command is on cooldown.'
    bucket = None
    rate = 0
    per = 0
    retry_after = 0.0
    append_retry_after = False

    guild_dm_types = (commands.BucketType.channel, commands.BucketType.guild)
    if isinstance(error, app_commands.CommandOnCooldown):
        # this error has no type attribute,
        # so we can't tell what bucket it falls under
        description = 'This command is on cooldown and can be retried in {retry_after}.'
        retry_after = error.retry_after

    elif isinstance(error, commands.CommandOnCooldown):
        bucket = error.type
        rate = error.cooldown.rate
        per = error.cooldown.per
        retry_after = error.retry_after
        append_retry_after = True

        if not ctx.guild and error.type in guild_dm_types:
            # Ran in DMs so the member message is more appropriate
            description = COOLDOWN_DESCRIPTIONS[commands.BucketType.member]
        else:
            description = COOLDOWN_DESCRIPTIONS[error.type]

    elif isinstance(error, commands.MaxConcurrencyReached):
        bucket = error.per
        rate = error.number

        if not ctx.guild and error.per in guild_dm_types:
            description = MAX_CONCURRENCY_DESCRIPTIONS[commands.BucketType.member]
        else:
            description = MAX_CONCURRENCY_DESCRIPTIONS[error.per]

    # Create description
    times = '{{rate}} {{times}} every {}'.format(
        # if per == 1 then simply write "every second"
        '{per} {seconds}' if per != 1 else '{seconds}'
    ).format(
        rate=rate,
        times=bot.inflector.plural('time', rate),
        per=per,
        seconds=bot.inflector.plural('second', per)
    )

    retry_after_text = ' '.join([
        light_round(retry_after),
        bot.inflector.plural('second', retry_after)
    ])

    description = description.format(
        here=get_cooldown_here(),
        n=rate,
        times=times,
        retry_after=retry_after_text
    )

    if append_retry_after:
        description += '\nYou can retry this command in {}.'.format(retry_after_text)

    return description


async def send(
    ctx: Context | discord.Interaction,
    *args, ephemeral=True, **kwargs
):
    """A shorthand function for sending a message using
    either a message context or a discord interaction.

    Allowed mentions will always be none, and for interactions
    the response will always be ephemeral.

    """
    kwargs['allowed_mentions'] = discord.AllowedMentions.none()
    try:
        if isinstance(ctx, commands.Context):
            await ctx.send(*args, **kwargs)
        elif ctx.response.is_done() and not ctx.is_expired():
            await ctx.followup.send(*args, ephemeral=ephemeral, **kwargs)
        else:
            await ctx.response.send_message(*args, ephemeral=ephemeral, **kwargs)
    except discord.HTTPException:
        # probably okay to not worry about it
        pass


class EventHandlers(commands.Cog):
    """Event handlers for the bot."""
    qualified_name = 'Event Handlers'

    EVENTS = (
        'on_command_error',
        'on_connect',
        'on_disconnect',
        'on_ready',
        'on_resumed',
    )

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.line_wrapper = textwrap.TextWrapper(max_lines=1, placeholder='...')

        self._old_events = {}
        self.setup_events()

    def cog_unload(self):
        self.teardown_events()

    def setup_events(self):
        """Add the cog's custom event handlers to the bot."""
        for name in self.EVENTS:
            coro = getattr(self, name)
            old = getattr(self.bot, name, None)
            self.bot.event(coro)
            if old is not None:
                self._old_events[name] = old

        self._old_events['on_slash_error'] = self.bot.tree.on_error
        self.bot.tree.error(self.on_slash_error)

    def teardown_events(self):
        """Restore the bot's original event handlers."""
        for name, coro in self._old_events.items():
            setattr(self.bot, name, coro)

        self.bot.tree.error(self._old_events['on_slash_error'])

    # Events
    async def on_connect(self):
        s = time.strftime(
            'Connection: Connected to Discord, %c',
            time.localtime()
        )
        print(s)

    async def on_disconnect(self):
        s = time.strftime(
            'Connection: Lost connection to Discord, %c',
            time.localtime()
        )
        print(s)

    async def on_ready(self):
        s = time.strftime(
            'Bot is ready, %c',
            time.localtime()
        )
        line = '-' * len(s)
        print(s, line, sep='\n')

    async def on_resumed(self):
        s = time.strftime(
            'Connection: Reconnected to Discord, %c',
            time.localtime()
        )
        print(s)

    def truncate(self, message: str, *, width=30):
        self.line_wrapper.width = width
        return self.line_wrapper.fill(message)

    def create_error_embed(
        self, ctx: Context | discord.Interaction,
        error: Exception, error_code: str,
        *, message='An error occurred while trying to run your command:'
    ):
        description = '{} ```py\n{}: {}``` Error code: **{}**'.format(
            message,
            type(error).__name__,
            str(error),
            error_code
        )

        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        embed = discord.Embed(
            color=self.bot.get_bot_color(),
            description=description
        ).set_author(
            name=author.display_name,
            icon_url=author.display_avatar.url
        )

        return embed

    async def handle_command_invoke_error(
        self, ctx: Context | discord.Interaction,
        error: commands.CommandInvokeError | app_commands.CommandInvokeError,
        error_code: str
    ):
        """Handles a CommandInvokeError from either message commands
        or application commands.

        :returns: A boolean indicating if the exception is one that is expected.
            Unknown exceptions should be logged.

        """
        original = error.original
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        if isinstance(original, discord.Forbidden) and original.code == 50007:
            content = '{} I tried DMing you but you have your messages disabled for this server.'
            content = content.format(author.mention)
            await send(ctx, content)
            return True
        elif isinstance(original, errors.SettingsNotFound):
            content = '{} Fatal error: Settings could not be loaded.'
            content = content.format(author.mention)
            await send(ctx, content)
            return True
        else:
            embed = self.create_error_embed(ctx, error, error_code)
            await send(ctx, embed=embed)
            return False

    async def handle_conversion_error(
        self, ctx: Context | discord.Interaction,
        error: commands.ConversionError | app_commands.TransformerError,
        error_code: str
    ):
        """Handles an unknown conversion or transform error.

        :returns: A boolean indicating if the exception is one that is expected.
            Unknown exceptions should be logged.

        """
        original = error.__cause__ or error
        embed = self.create_error_embed(
            ctx, original, error_code,
            message='An error occurred while trying to parse your parameters:'
        )
        await send(ctx, embed=embed)
        return False

    async def on_command_error(self, ctx: Context, error: commands.CommandError):
        if getattr(ctx, 'handled', False):
            # a local or cog error handler has managed this
            return
        elif isinstance(error, commands.CommandNotFound):
            # too noisy to handle this error
            return

        # Handle the first error in check_any or union converters
        if isinstance(error, (commands.CheckAnyFailure, commands.BadUnionArgument)):
            error = error.errors[0]

        error_code = generate_error_code()
        include_traceback = False

        # Argument quantity errors
        if isinstance(error, commands.MissingRequiredArgument):
            content = '{} I am missing the required parameter `{}`.\nUsage: {}'.format(
                ctx.author.mention,
                error.param.name, get_command_signature(ctx)
            )
            await send(ctx, content)
        elif isinstance(error, commands.TooManyArguments):
            content = '{} Too many parameters were given.\nUsage: {}'
            content = content.format(ctx.author.mention, get_command_signature(ctx))
            await send(ctx, content)
        # Flag errors
        elif isinstance(error, commands.BadFlagArgument):
            content = '{} Could not parse your input for the `{}` flag.'
            content = content.format(ctx.author.mention, error.flag.name)
            await send(ctx, content)
        elif isinstance(error, commands.MissingFlagArgument):
            content = '{} A value for the `{}` flag must be provided.'
            content = content.format(ctx.author.mention, error.flag.name)
            await send(ctx, content)
        elif isinstance(error, commands.TooManyFlags):
            content = '{} Too many values were provided for the `{}` flag (max: {}).'.format(
                ctx.author.mention,
                error.flag.name, error.flag.max_args
            )
            await send(ctx, content)
        elif isinstance(error, commands.MissingRequiredFlag):
            content = '{} The `{}` flag must be provided.'
            content = content.format(ctx.author.mention, error.flag.name)
            await send(ctx, content)
        # Converter errors
        elif isinstance(error, commands.MessageNotFound):
            content = '{} I could not find the message "{}".'.format(
                ctx.author.mention, self.truncate(error.argument)
            )
            await send(ctx, content)
        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            content = '{} I could not find the user "{}".'.format(
                ctx.author.mention, self.truncate(error.argument)
            )
            await send(ctx, content)
        elif isinstance(error, commands.GuildNotFound):
            content = '{} I could not find the guild "{}".'.format(
                ctx.author.mention, self.truncate(error.argument)
            )
            await send(ctx, content)
        elif isinstance(error, commands.ChannelNotFound):
            content = '{} I could not find the channel "{}".'.format(
                ctx.author.mention, self.truncate(error.argument)
            )
            await send(ctx, content)
        elif isinstance(error, commands.ChannelNotReadable):
            content = '{} I cannot read messages in the {} channel.'.format(
                ctx.author.mention, error.argument.mention
            )
            await send(ctx, content)
        elif isinstance(error, commands.BadColorArgument):
            content = '{} I could not understand the color "{}".'.format(
                ctx.author.mention, self.truncate(error.argument, width=20)
            )
            await send(ctx, content)
        elif isinstance(error, commands.RoleNotFound):
            content = '{} I could not find the role "{}".'.format(
                ctx.author.mention, self.truncate(error.argument)
            )
            await send(ctx, content)
        elif isinstance(error, commands.BadInviteArgument):
            content = '{} Your given invite has either expired or is invalid.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, commands.EmojiNotFound):
            content = '{} I could not find the custom emoji "{}".'.format(
                ctx.author.mention, self.truncate(error.argument, width=57)
            )
            await send(ctx, content)
        elif isinstance(error, commands.GuildStickerNotFound):
            content = '{} I could not find the sticker "{}".'.format(
                ctx.author.mention, self.truncate(error.argument, width=30)
            )
            await send(ctx, content)
        elif isinstance(error, commands.ScheduledEventNotFound):
            content = '{} I could not find the given event.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, commands.PartialEmojiConversionFailure):
            content = '{} I could not understand the custom emoji "{}".'.format(
                ctx.author.mention, self.truncate(error.argument, width=57)
            )
            await send(ctx, content)
        elif isinstance(error, commands.BadBoolArgument):
            content = '{} Expected a "true" or "false" answer instead of "{}".'.format(
                ctx.author.mention, self.truncate(error.argument, width=10)
            )
            await send(ctx, content)
        elif isinstance(error, commands.ThreadNotFound):
            content = '{} I could not find the thread "{}".'.format(
                ctx.author.mention, self.truncate(error.argument)
            )
            await send(ctx, content)
        elif isinstance(error, commands.BadLiteralArgument):
            values = '{}{}'.format(
                'one of: ' * (len(error.literals) > 1),
                ctx.bot.inflector.join(
                    [f'**{v}**' for v in error.literals],
                    conj='or'
                )
            )
            content = '{} The `{}` parameter must be {}.'.format(
                ctx.author.mention, error.param.name, values
            )
            await send(ctx, content)
        elif isinstance(error, commands.BadArgument):
            content = ' '.join([ctx.author.mention, str(error)])
            await send(ctx, content)
        # Other parsing errors
        elif isinstance(error, commands.UnexpectedQuoteError):
            content = '{} I could not understand your message due to an unexpected quote `{}`.'
            content = content.format(ctx.author.mention, error.quote)
            await send(ctx, content)
        elif isinstance(error, (commands.InvalidEndOfQuotedStringError,
                                commands.ExpectedClosingQuoteError)):
            content = '{} I could not determine the end of your quoted argument.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, commands.UserInputError):
            content = '{} Failed to parse your parameters.\nUsage: `{}`'
            content = content.format(ctx.author.mention, get_command_signature(ctx))
            await send(ctx, content)
        # Check errors
        elif isinstance(error, commands.PrivateMessageOnly):
            content = '{} This command can only be used in DMs.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, commands.NoPrivateMessage):
            content = '{} This command must be used in a server.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, commands.NotOwner):
            content = '{} This command is limited to the owner of the bot.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, (commands.MissingPermissions, commands.BotMissingPermissions)):
            content = '{} {} missing the {} {} needed to run this command.'.format(
                ctx.author.mention,
                'You are' if isinstance(error, commands.MissingPermissions) else 'I am',
                ctx.bot.inflector.join(humanize_permissions(error.missing_permissions)),
                ctx.bot.inflector.plural('permission', len(error.missing_permissions))
            )
            await send(ctx, content)
        elif isinstance(error, (commands.MissingRole, commands.BotMissingRole)):
            content = '{} {} missing the {} role needed to run this command.'.format(
                ctx.author.mention,
                'You are' if isinstance(error, commands.MissingRole) else 'I am',
                resolve_role(ctx, error.missing_role)
            )
            await send(ctx, content)
        elif isinstance(error, (commands.MissingAnyRole, commands.BotMissingAnyRole)):
            roles = [resolve_role(ctx, role) for role in error.missing_roles]
            content = '{} {} missing {} needed to run this command.'.format(
                ctx.author.mention,
                'You are' if isinstance(error, commands.MissingAnyRole) else 'I am',
                'one of the roles {}' if len(roles) > 1 else 'the {} role'
            ).format(
                ctx.bot.inflector.join(roles, conj='or')
            )
            await send(ctx, content)
        elif isinstance(error, commands.NSFWChannelRequired):
            content = '{} This command can only be used in an NSFW channel.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        elif isinstance(error, commands.DisabledCommand):
            content = '{} This command is currently disabled.'
            content = content.format(ctx.author.mention)
            await send(ctx, content)
        # Ratelimiting errors
        elif isinstance(error, (commands.CommandOnCooldown, commands.MaxConcurrencyReached)):
            content = ' '.join([
                ctx.author.mention,
                get_ratelimit_description(ctx, error)
            ])
            delete_after = None
            if getattr(error, 'retry_after', sys.maxsize) <= 20:
                delete_after = error.retry_after
            await send(
                ctx, content,
                delete_after=delete_after
            )
        # Other errors
        elif isinstance(error, commands.CommandInvokeError):
            handled = await self.handle_command_invoke_error(ctx, error, error_code)
            if not handled:
                include_traceback = True
        elif isinstance(error, commands.ConversionError):
            handled = await self.handle_conversion_error(ctx, error, error_code)
            if not handled:
                include_traceback = True
        elif not isinstance(error, commands.CheckFailure):
            # Any subclass of CheckFailure is probably fine to ignore
            include_traceback = True

        # Log error message if necessary
        simple_message = 'Command error {} ({}:{}:"{}")\n  {}: {}'.format(
            error_code, f'{ctx.guild}:{ctx.channel}' if ctx.guild else '<DM>',
            ctx.author, ctx.invoked_with, type(error).__name__, error
        )
        if include_traceback:
            logger.exception(simple_message, exc_info=error)
        elif not isinstance(error, (
            commands.BadArgument,
            commands.CheckFailure,
            commands.CommandOnCooldown,
            commands.DisabledCommand,
            commands.MaxConcurrencyReached,
            commands.UserInputError
        )):
            logger.debug(simple_message)

    async def on_slash_error(
        self, interaction: discord.Interaction,
        command: app_commands.Command | app_commands.ContextMenu | None,
        error: app_commands.AppCommandError
    ):
        if getattr(error, 'handled', False):
            # a local error handler has managed this
            return

        error_code = generate_error_code()
        include_traceback = False

        # Check errors
        if isinstance(error, app_commands.NoPrivateMessage):
            content = 'This command must be used in a server.'
            await send(interaction, content)
        elif isinstance(error, app_commands.MissingRole):
            content = 'You are missing the {} role needed to run this command.'.format(
                resolve_role(interaction, error.missing_role)
            )
            await send(interaction, content)
        elif isinstance(error, app_commands.MissingAnyRole):
            roles = [resolve_role(interaction, role) for role in error.missing_roles]
            content = 'You are missing {} needed to run this command.'.format(
                'one of the roles {}' if len(roles) > 1 else 'the {} role'
            ).format(
                self.bot.inflector.join(roles, conj='or')
            )
            await send(interaction, content)
        elif isinstance(error, (app_commands.MissingPermissions, app_commands.BotMissingPermissions)):
            content = '{} missing the {} {} needed to run this command.'.format(
                'You are' if isinstance(error, app_commands.MissingPermissions) else 'I am',
                self.bot.inflector.join(humanize_permissions(error.missing_permissions)),
                self.bot.inflector.plural('permission', len(error.missing_permissions))
            )
            await send(interaction, content)
        elif isinstance(error, app_commands.CommandOnCooldown):
            content = get_ratelimit_description(interaction, error)
            await send(interaction, content)
        # Other errors
        elif isinstance(error, app_commands.CommandNotFound):
            # Unlike on_command_error this one usually means
            # we forgot to sync, so we should know about it
            content = (
                'This command is currently unrecognized by the bot; '
                'an alert has been issued to the developer to fix this problem.'
            )
            logger.warning(
                'Application command %r (%s) not found',
                error.name,
                error.type.name  # type: ignore # this enum does have a name attribute
            )
            await send(interaction, content)
        elif isinstance(error, app_commands.CommandInvokeError):
            handled = await self.handle_command_invoke_error(interaction, error, error_code)
            if not handled:
                include_traceback = True
        elif isinstance(error, app_commands.TransformerError):
            handled = await self.handle_conversion_error(interaction, error, error_code)
            if not handled:
                include_traceback = True
        elif isinstance(error, app_commands.AppCommandError):
            # Our transformers use this exception to distinguish from
            # unexpected bugs wrapped by TransformerError
            await send(interaction, str(error))
        elif not isinstance(error, app_commands.CheckFailure):
            include_traceback = True

        simple_message = 'Application command error {} ({}:{})\n  {}: {}'.format(
            error_code,
            f'{interaction.guild}:{interaction.channel}'
            if interaction.guild else '<DM>',
            interaction.user, type(error).__name__, error
        )
        if include_traceback:
            logger.exception(simple_message, exc_info=error)
        elif not isinstance(error, (app_commands.CheckFailure, app_commands.CommandOnCooldown)):
            logger.debug(simple_message)


async def setup(bot: TheGameBot):
    await bot.add_cog(EventHandlers(bot))
