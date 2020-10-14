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
            'Command error from server {}, channel {}, by {}, '
            'which raised {}: {}'.format(
                ctx.guild,
                ctx.channel,
                ctx.author,
                type(error).__name__,
                error
        ))
    else:
        # Command invoked in DMs
        print(
            'Command error in DMs by {} which raised {}: {}'.format(
                ctx.author, type(error).__name__, error
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
        await ctx.send(
            'Expected a boolean answer for an argument.'
        )
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send('I am {}'.format(
            missing_x_to_run('permission', error.missing_perms)
        ))
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
        await ctx.send(f'Missing argument "{error.param}"')
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send('You are {}'.format(
            missing_x_to_run('permission', error.missing_perms)
        ))
    elif isinstance(error, (
            commands.MissingRole,
            commands.MissingAnyRole)):
        await ctx.send('You are {}'.format(
            missing_x_to_run('role', convert_roles(error.missing_perms))
        ))
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


def setup(bot):
    for handler in handlers:
        bot.event(globals()[handler])
