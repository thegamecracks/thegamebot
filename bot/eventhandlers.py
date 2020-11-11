import time

import discord
from discord.ext import commands
import inflect

handlers = [
    'on_command_error',
    'on_connect',
    'on_disconnect',
    'on_ready',
    'on_resumed',
]

inflector = inflect.engine()

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
    'send_messages': 'Send Messages',
    'send_tts_messages': 'Send TTS Messages',
    'speak': 'Speak',
    'stream': 'Stream',
    'use_external_emojis': 'External Emojis',
    'use_voice_activation': 'Voice Activation',
    'view_audit_log': 'View Audit Log',
    'view_channel': 'Read Messages',
    'view_guild_insights': 'View Guild Insights'
}


def convert_perms_to_english(perms):
    """Run through a list of permissions and convert them into
    user-friendly representations.
    """
    new_perms = []

    for p in perms:
        eng = PERMS_TO_ENGLISH.get(p)
        if eng is not None:
            new_perms.append(eng)

    return new_perms


async def on_connect():
    print(time.strftime(
        'Connection: Connected to Discord, %c',
        time.localtime()))


async def on_disconnect():
    print(time.strftime(
        'Connection: Lost connection to Discord, %c',
        time.localtime()))


async def on_ready():
    s = time.strftime(
        'Bot is ready, %c',
        time.localtime()
    )
    line = '-' * len(s)
    print(s, line, sep='\n')


async def on_resumed():
    print(time.strftime(
        'Connection: Reconnected to Discord, %c',
        time.localtime()))


async def on_command_error(ctx, error):
    # Print error
    if ctx.guild is not None:
        # Command invoked in server
        print(
            'Command error ({}:{}:{}:"{}")\n  {}: {}'.format(
                ctx.guild,
                ctx.channel,
                ctx.author,
                ctx.invoked_with,
                type(error).__name__,
                error
        ))
    else:
        # Command invoked in DMs
        print(
            'Command error (<DM>:{}:"{}")\n  {}: {}'.format(
                ctx.author, ctx.invoked_with,
                type(error).__name__, error
        ))

    # Error message functions
    def convert_roles(missing_perms):
        "Convert IDs in one or more roles into strings."
        def convert(p):
            if isinstance(p, int):
                r = ctx.bot.get_role(p)
                return str(r) if r is not None else p
            return p

        if isinstance(missing_perms, list):
            return [convert(p) for p in missing_perms]

        return (convert(missing_perms),)

    def get_command_signature():
        prefix = ctx.prefix
        name_signature = ctx.invoked_with
        arguments = ctx.command.signature

        return f'{prefix}{name_signature} {arguments}'

    def missing_x_to_run(x, missing_perms):
        count = len(missing_perms)
        if count == 1:
            return (f'missing the {missing_perms[0]} {x} '
                    'to run this command.')

        return 'missing {:,} {} to run this command: {}'.format(
            count, inflector.plural(x), inflector.join(missing_perms)
        )

    # Send an error message
    if isinstance(error, commands.BadBoolArgument):
        await ctx.send('Expected a boolean answer for a parameter.')
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
        await ctx.send('I am {}'.format(
            missing_x_to_run('role', convert_roles(error.missing_perms))
        ))
    elif isinstance(error, commands.CommandNotFound):
        # Command "x" is not found
        await ctx.send('Unknown command: {}'.format(
                error.args[0].split()[1].strip('"')
        ))
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send('I cannot find the given channel.')
    elif isinstance(error, commands.ChannelNotReadable):
        await ctx.send('I cannot read messages in the channel.')
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            inflector.inflect(
                'This command is on cooldown; '
                'try again after {0:.1f} plural("second", {0}).'.format(
                    error.retry_after
        )))
    elif isinstance(error, commands.EmojiNotFound):
        await ctx.send(f'I cannot find the given emoji "{error.argument}"')
    elif isinstance(error, commands.ExpectedClosingQuoteError):
        await ctx.send('Expected a closing quotation mark.')
    elif isinstance(error, commands.InvalidEndOfQuotedStringError):
        await ctx.send('Expected a space after a closing quotation mark.')
    elif isinstance(error, commands.MaxConcurrencyReached):
        await ctx.send('Too many people are using this command!')
    elif isinstance(error, commands.MessageNotFound):
        await ctx.send('I cannot find the given message.')
    elif isinstance(error, commands.MissingRequiredArgument):
        # error.param is instance of inspect.Parameter
        await ctx.send(f'Missing argument "{error.param.name}"')
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(
            'You are {}'.format(
                missing_x_to_run(
                    'permission',
                    convert_perms_to_english(error.missing_perms)
                )
            )
        )
    elif isinstance(error, (
            commands.MissingRole,
            commands.MissingAnyRole)):
        await ctx.send('You are {}'.format(
            missing_x_to_run('role', convert_roles(error.missing_perms))
        ))
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send('You must be in a server to use this command.')
    elif isinstance(error, commands.NotOwner):
        await ctx.send('This command is for the bot owner only.')
    elif isinstance(error, commands.NSFWChannelRequired):
        await ctx.send('The given channel must be marked as NSFW.')
    elif isinstance(error, commands.UnexpectedQuoteError):
        await ctx.send('Did not expect a quotation mark.')
    elif isinstance(error, (
            commands.UserNotFound,
            commands.MemberNotFound)):
        await ctx.send('I cannot find the given user.')
    elif isinstance(error, commands.UserInputError):
        # NOTE: This is a superclass of several other errors
        await ctx.send('Failed to parse your parameters.\n'
                       f'Usage: `{get_command_signature()}`')
    else:
        raise error


def setup(bot):
    for handler in handlers:
        bot.event(globals()[handler])