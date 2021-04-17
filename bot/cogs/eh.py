import random
import time

import discord
from discord.ext import commands

from bot import checks, errors, utils


class CommandErrorCooldown:
    """Maps cooldowns to specific errors.

    Args:
        errors_to_cooldowns (Dictionary[commands.CommandError, Optional[Tuple[int, int, commands.BucketType]]]):
            A mapping of errors to CooldownMapping arguments.
            the value can be None to use default parameters.

    """

    __slots__ = ('error_mapping',)

    DEFAULT_COOLDOWN = (1, 10, commands.BucketType.user)

    def __init__(self, errors_to_cooldowns):
        from_cooldown = commands.CooldownMapping.from_cooldown
        self.error_mapping = {
            err: from_cooldown(*args) if args is not None
                 else from_cooldown(*self.DEFAULT_COOLDOWN)
            for err, args in errors_to_cooldowns.items()
        }

    def check_user(self, ctx, error):
        """Check if a user is ratelimited for an exception.
        Returns True if they are ratelimited."""
        mapping = self.error_mapping.get(type(error))
        if mapping is None:
            return False
        return mapping.update_rate_limit(ctx.message)


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

    COMMAND_ERROR_IGNORE_EXCEPTIONS = (commands.CommandNotFound,)
    # Prevents errors from being processed in this set of exceptions
    COMMAND_ERROR_IGNORE_EXCEPTIONS_AFTER = (commands.CheckFailure,)
    # Same as above except this prevents raising the error if the exception
    # was not matched. Helpful for ignoring superclasses of exceptions.

    COOLDOWN_DESCRIPTIONS = {
        commands.BucketType.default: 'Too many people have used this command '
                                     'globally. The limit is {times}.',

        commands.BucketType.user: 'You have used this command too many times. '
                                  'The personal limit is {times}.',

        commands.BucketType.guild: 'Too many people have used this command '
                                   '{here}. The limit is {times}.',

        commands.BucketType.channel: 'Too many people have used this command '
                                     '{here}. The limit is {times}.',

        commands.BucketType.member: 'You have used this command too many times '
                                    '{here}. The personal limit is {times}.',

        commands.BucketType.category: 'Too many people have used this command in '
                                      'this server category. The limit is {times}.',

        commands.BucketType.role: 'Too many people with the same role have used '
                                  'this command. The limit is {times}.'
    }

    MAX_CONCURRENCY_DESCRIPTIONS = {
        commands.BucketType.default: 'Too many people are currently using this '
                                     'command globally. The limit is '
                                     '{times} concurrently.',

        commands.BucketType.user: 'You are using this command too many times. '
                                  'The personal limit is {times} concurrently.',

        commands.BucketType.guild: 'Too many people are currently using this '
                                   'command {here}. The limit is '
                                   '{times} concurrently.',

        commands.BucketType.channel: 'Too many people are currently using this '
                                     'command {here}. The limit is '
                                     '{times} concurrently.',

        commands.BucketType.member: 'You are using this command too many times '
                                    '{here}. The personal limit is '
                                    '{times} concurrently.',

        commands.BucketType.category: 'Too many people are currently using this '
                                      'command in this server category. '
                                      'The limit is {times} concurrently.',

        commands.BucketType.role: 'Too many people with the same role are using '
                                  'this command. The limit is '
                                  '{times} concurrently.'
    }

    PERMS_TO_ENGLISH = {
        'add_reactions': 'Add Reactions',
        'administrator': 'Administrator',
        'attach_files': 'Attach Files',
        'ban_members': 'Ban Members',
        'change_nickname': 'Change Nickname',
        'connect': 'Connect',
        'deafen_members': 'Deafen Members',
        'embed_links': 'Embed Links',
        'external_emojis': 'External Emojis',
        'kick_members': 'Kick Members',
        'manage_channels': 'Manage Channels',
        'manage_emojis': 'Manage Emojis',
        'manage_guild': 'Manage Guild',
        'manage_messages': 'Manage Messages',
        'manage_nicknames': 'Manage Nicknames',
        'manage_permissions': 'Manage Roles',
        'manage_roles': 'Manage Roles',
        'manage_webhooks': 'Manage ',
        'mention_everyone': 'Mention Everyone',
        'move_members': 'Move Members',
        'mute_members': 'Mute Members',
        'priority_speaker': 'Priority Speaker',
        'read_message_history': 'Read Message History',
        'read_messages': 'Read Messages',
        'request_to_speak': 'Request to Speak',
        'send_messages': 'Send Messages',
        'send_tts_messages': 'Send TTS Messages',
        'speak': 'Speak',
        'stream': 'Stream',
        'use_external_emojis': 'External Emojis',
        'use_slash_commands': 'Use Slash Commands',
        'use_voice_activation': 'Use Voice Activity',
        'view_audit_log': 'View Audit Log',
        'view_channel': 'Read Messages',
        'view_guild_insights': 'View Guild Insights'
    }

    ERRORS_TO_LIMIT_COOLDOWN_MAPPING = {
        commands.BotMissingPermissions: None,
        commands.BotMissingAnyRole: None,
        commands.BotMissingRole: None,
        commands.CommandOnCooldown: None,
        commands.DisabledCommand: None,
        commands.MaxConcurrencyReached: None,
        commands.MissingAnyRole: None,
        commands.MissingPermissions: None,
        commands.MissingRole: None,
        commands.NoPrivateMessage: None,
        commands.PrivateMessageOnly: None,
        commands.NotOwner: None,
        commands.UserInputError: (1, 5, commands.BucketType.user),
        checks.UserOnCooldown: (1, 5, commands.BucketType.user),
        discord.Forbidden: (1, 5, commands.BucketType.user),
    }
    ERRORS_TO_LIMIT = tuple(ERRORS_TO_LIMIT_COOLDOWN_MAPPING)

    def __init__(self, bot):
        self.bot = bot
        self.command_error_limiter = CommandErrorCooldown(
            self.ERRORS_TO_LIMIT_COOLDOWN_MAPPING)

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

    def teardown_events(self):
        """Restore the bot's original event handlers."""
        for name, coro in self._old_events.items():
            setattr(self.bot, name, coro)

    # Events
    async def on_connect(self):
        print(time.strftime(
            'Connection: Connected to Discord, %c',
            time.localtime()))

    async def on_disconnect(self):
        print(time.strftime(
            'Connection: Lost connection to Discord, %c',
            time.localtime()))

    async def on_ready(self):
        s = time.strftime(
            'Bot is ready, %c',
            time.localtime()
        )
        line = '-' * len(s)
        print(s, line, sep='\n')

    async def on_resumed(self):
        print(time.strftime(
            'Connection: Reconnected to Discord, %c',
            time.localtime()))

    async def on_command_error(self, ctx, error):
        error_unpacked = getattr(error, 'original', error)
        if isinstance(error, self.COMMAND_ERROR_IGNORE_EXCEPTIONS):
            return
        elif isinstance(error_unpacked, self.ERRORS_TO_LIMIT):
            if self.command_error_limiter.check_user(ctx, error_unpacked):
                # user is rate limited on receiving a particular error
                return

        # Print error
        print(
            'Command error ({}:{}:"{}")\n  {}: {}'.format(
                f'{ctx.guild}:{ctx.channel}' if ctx.guild else '<DM>',
                ctx.author, ctx.invoked_with, type(error).__name__, error
            )
        )

        # Error message functions
        def convert_perms_to_english(perms):
            """Run through a list of permissions and convert them into
            user-friendly representations.
            """
            new_perms = []

            for p in perms:
                eng = self.PERMS_TO_ENGLISH.get(p)
                if eng is not None:
                    new_perms.append(eng)

            return new_perms

        def convert_roles(missing_perms):
            """Convert IDs in one or more roles into strings."""
            def convert(p):
                if isinstance(p, int):
                    r = ctx.bot.get_role(p)
                    return str(r) if r is not None else p
                return p

            if isinstance(missing_perms, list):
                return [convert(p) for p in missing_perms]

            return convert(missing_perms),

        def get_command_signature():
            prefix = ctx.prefix
            name_signature = ctx.invoked_with
            arguments = ctx.command.signature

            return f'{prefix}{name_signature} {arguments}'

        def get_concurrency_description():
            if not ctx.guild and error.per == commands.BucketType.channel:
                # Use message for member bucket when in DMs
                description = self.MAX_CONCURRENCY_DESCRIPTIONS.get(
                    commands.BucketType.member,
                    'This command has currently reached max concurrency.'
                )
            else:
                description = self.MAX_CONCURRENCY_DESCRIPTIONS.get(
                    error.per,
                    'This command has currently reached max concurrency.'
                )

            return description.format(
                here=get_cooldown_here(error.per),
                times=ctx.bot.inflector.inflect(
                    '{0} plural("time", {0})'.format(
                        error.number
                    )
                )
            )

        def get_cooldown_description():
            if (not ctx.guild
                and error.cooldown.type in (
                    commands.BucketType.channel,
                    commands.BucketType.guild)):
                # in DMs; use member in place of channel/guild bucket
                description = self.COOLDOWN_DESCRIPTIONS.get(
                    commands.BucketType.member, 'This command is on cooldown.'
                )
            else:
                description = self.COOLDOWN_DESCRIPTIONS.get(
                    error.cooldown.type, 'This command is on cooldown.'
                )

            return description.format(
                here=get_cooldown_here(error.cooldown.type),
                times=ctx.bot.inflector.inflect(
                    '{0} plural("time", {0}) '
                    'every {1} plural("second", {1})'.format(
                        error.cooldown.rate,
                        utils.num(error.cooldown.per)
                    )
                )
            )

        def get_cooldown_here(bucket):
            if ctx.guild:
                if bucket == commands.BucketType.guild:
                    return 'on this server'
                return 'in this channel'
            else:
                return 'in this DM'

        def get_denied_message():
            return random.choice(ctx.bot.get_cog('Settings').get('deniedmessages'))

        def missing_x_to_run(x, missing_perms):
            count = len(missing_perms)
            if count == 1:
                return (f'missing the {missing_perms[0]} {x} '
                        'to run this command.')

            return 'missing {:,} {} to run this command: {}'.format(
                count, ctx.bot.inflector.plural(x), ctx.bot.inflector.join(missing_perms)
            )

        # Send an error message
        if isinstance(error, commands.BadBoolArgument):
            # error.param is instance of inspect.Parameter
            await ctx.send('Expected a boolean answer for parameter '
                           f'"{error.param.name}".\n'
                           f'Usage: `{get_command_signature()}`')
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(
                'I am {}'.format(
                    missing_x_to_run(
                        'permission',
                        convert_perms_to_english(error.missing_perms)
                    )
                )
            )
        elif isinstance(error, (
                commands.BotMissingRole,
                commands.BotMissingAnyRole)):
            await ctx.send(
                'I am {}'.format(
                    missing_x_to_run('role', convert_roles(error.missing_roles))
                )
            )
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send(f'I cannot find the given channel "{error.argument}".')
        elif isinstance(error, commands.ChannelNotReadable):
            await ctx.send('I cannot read messages in the channel '
                           f'{error.argument.mention}.')
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                color=utils.get_bot_color(ctx.bot)
            ).set_footer(
                text=ctx.bot.inflector.inflect(
                    'You can retry in {0} plural("second", {0}).'.format(
                        round(error.retry_after * 10) / 10
                    )
                ),
                icon_url=ctx.author.avatar_url
            )

            embed.description = get_cooldown_description()

            await ctx.send(embed=embed, delete_after=min(error.retry_after, 20))
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send('This command is currently disabled.')
        elif isinstance(error, errors.DollarInputError):
            await ctx.send(str(error))
        elif isinstance(error, commands.EmojiNotFound):
            await ctx.send(f'I cannot find the given emoji "{error.argument}"')
        elif isinstance(error, commands.ExpectedClosingQuoteError):
            await ctx.send('Expected a closing quotation mark.')
        elif isinstance(error, errors.IndexOutOfBoundsError):
            await ctx.send(str(error))
        elif isinstance(error, commands.InvalidEndOfQuotedStringError):
            await ctx.send('Expected a space after a closing quotation mark.')
        elif isinstance(error, commands.MaxConcurrencyReached):
            embed = discord.Embed(
                color=utils.get_bot_color(ctx.bot)
            ).set_footer(
                text=get_concurrency_description(),
                icon_url=ctx.author.avatar_url
            )

            await ctx.send(embed=embed)
        elif isinstance(error, commands.MessageNotFound):
            await ctx.send('I cannot find the given message.')
        elif isinstance(error, commands.MissingRequiredArgument):
            # error.param is instance of inspect.Parameter
            await ctx.send(f'Missing argument "{error.param.name}"\n'
                           f'Usage: `{get_command_signature()}`')
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(
                'You are {}'.format(
                    missing_x_to_run(
                        'permission',
                        convert_perms_to_english(error.missing_perms)
                    )
                )
            )
        elif isinstance(error, (commands.MissingRole,
                                commands.MissingAnyRole)):
            await ctx.send(
                'You are {}'.format(
                    missing_x_to_run('role', convert_roles(error.missing_roles))
                )
            )
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send('You must be in a server to use this command.')
        elif isinstance(error, commands.NotOwner):
            await ctx.send(get_denied_message(), delete_after=6)
        elif isinstance(error, commands.NSFWChannelRequired):
            await ctx.send('The channel must be NSFW.')
        elif isinstance(error, commands.PrivateMessageOnly):
            await ctx.send('You must be in DMs to use this command.')
        elif isinstance(error, commands.UnexpectedQuoteError):
            await ctx.send('Did not expect a quotation mark.')
        elif isinstance(error, errors.UnknownTimezoneError):
            embed = discord.Embed(
                description='Unknown timezone given. See the [Time Zone Map]'
                            '(https://kevinnovak.github.io/Time-Zone-Picker/) '
                            'for the names of timezones supported.',
                color=utils.get_bot_color(ctx.bot)
            )
            await ctx.send(embed=embed)
        elif isinstance(error, (commands.UserNotFound,
                                commands.MemberNotFound)):
            await ctx.send('I cannot find the given user.')
        elif isinstance(error, commands.UserInputError):
            # NOTE: This is a superclass of several other errors
            await ctx.send('Failed to parse your parameters.\n'
                           f'Usage: `{get_command_signature()}`')
        elif isinstance(error, commands.ConversionError):
            await ctx.send('An error occurred while trying to parse your parameters.')
        elif isinstance(error, checks.UserOnCooldown):
            # User has invoked too many commands
            embed = discord.Embed(
                color=utils.get_bot_color(ctx.bot)
            ).set_footer(
                text=ctx.bot.inflector.inflect(
                    'You are using commands too frequently. '
                    'You can retry in {0} plural("second", {0}).'.format(
                        round(error.retry_after * 10) / 10)
                ),
                icon_url=ctx.author.avatar_url
            )

            await ctx.send(embed=embed, delete_after=min(error.retry_after, 20))
        elif (isinstance(error_unpacked, discord.Forbidden)
              and error_unpacked.code == 50007):
            # Cannot send messages to this user
            await ctx.send('I tried DMing you but you have your DMs '
                           'disabled for this server.')
        elif isinstance(error_unpacked, errors.SettingsNotFound):
            await ctx.send('Fatal error: settings could not be loaded.')
        elif not isinstance(error, self.COMMAND_ERROR_IGNORE_EXCEPTIONS_AFTER):
            raise error










def setup(bot):
    bot.add_cog(EventHandlers(bot))
