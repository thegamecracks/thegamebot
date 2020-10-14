import contextlib
import io
import random

import discord
from discord.ext import commands

from bot import checks
from bot import settings
from bot import utils
from bot.other import discordlogger


def get_denied_message():
    return random.choice(settings.get_setting('deniedmessages'))


def get_user_for_log(ctx):
    return f'{ctx.author} ({ctx.author.mention})'


class Administrative(commands.Cog):
    qualified_name = 'Administrative'
    description = 'Administrative commands available for owners/admins.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='shutdown',
        brief='Shutdown the bot.',
        aliases=('close', 'exit', 'quit', 'stop'))
    @checks.is_bot_owner()
    async def client_shutdown(self, ctx):
        """Shuts down the bot."""
        print('Shutting down')
        await ctx.send('Shutting down.')
        await self.bot.logout()


    @client_shutdown.error
    async def client_shutdown_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotOwner):
            await ctx.send(get_denied_message())
            return





    @commands.command(
        name='execute',
        description='https://repl.it/@AllAwesome497/ASB-DEV-again '
                    'used as reference.')
    @checks.is_bot_owner()
    async def client_execute(self, ctx, sendIOtoDM: bool, *, x: str):
        log = f'Executing code by {get_user_for_log(ctx)}:\n {x}'
        discordlogger.get_logger().warning(log)
        print(log)
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            exec(x, globals(), locals())
        out = f.getvalue().strip()
        if len(out) > 2000:
            out = '{}...'.format(out[:1997])
        if out:
            if sendIOtoDM:
                await ctx.author.send(out)
            else:
                await ctx.send(out)


    @client_execute.error
    async def client_execute_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotOwner):
            await ctx.send(get_denied_message())
            return





    @commands.group(
        name='presence')
    @checks.is_bot_admin()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def client_presence(self, ctx):
        """Commands to change the bot's presence. Restricted to admins."""
        if ctx.invoked_subcommand is None:
            raise commands.CommandNotFound(
                f'Unknown {ctx.command.name} subcommand given.')


    @client_presence.error
    async def client_presence_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotAdmin):
            await ctx.send(get_denied_message())
            return
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send(str(error))
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
            return


    @client_presence.command(
        name='playing')
    async def client_playing(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the playing message.
status - The status to set for the bot.
title - The title to show."""
        if title is None:
            await self.bot.change_presence(activity=None)
            return

        game = discord.Game(name=title)

        await self.bot.change_presence(
            activity=game, status=status)


    @client_playing.error
    async def client_playing_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.')
                return


    @client_presence.command(
        name='streaming')
    async def client_streaming(self, ctx,
        status: utils.parse_status = 'online',
        title=None,
            url='https://www.twitch.tv/thegamecracks'):
        """Sets the streaming message.
status - The status to set for the bot.
title - The title to show. Use "quotations" to specify the title.
url - The url to link to when streaming. Defaults to \
https://www.twitch.tv/thegamecracks ."""
        if title is None:
            await self.bot.change_presence(activity=None)
            return

        game = discord.Streaming(name=title, url=url)

        await self.bot.change_presence(
            activity=game, status=status)


    @client_streaming.error
    async def client_streaming_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.')
                return


    @client_presence.command(name='listening')
    async def client_listening(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the listening message.
status - The status to set for the bot.
title - The title to show."""
        if title is None:
            await self.bot.change_presence(activity=None)
            return

        activity = discord.Activity(
            name=title, type=discord.ActivityType.listening)

        await self.bot.change_presence(
            activity=activity, status=status)


    @client_listening.error
    async def client_listening_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.')
                return


    @client_presence.command(
        name='watching')
    async def client_watching(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the watching message.
status - The status to set for the bot.
title - The title to show."""
        if title is None:
            await self.bot.change_presence(activity=None)
            return

        activity = discord.Activity(
            name=title, type=discord.ActivityType.watching)

        await self.bot.change_presence(
            activity=activity, status=status)


    @client_watching.error
    async def client_watching_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.')
                return


    @client_presence.command(
        name='status',
        aliases=('state',))
    async def client_status(self, ctx, status: utils.parse_status = 'online'):
        """Sets the current status.
Options:
    online, on
    idle, away
    dnd
    invisible, offline, off
Will remove any activity the bot currently has."""
        await self.bot.change_presence(status=status)


    @client_status.error
    async def client_status_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.')
                return





    @commands.command(
        name='send')
    @checks.is_bot_admin()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def client_sendmessage(self, ctx, channelID, *, message):
        """Sends a message to a given channel. Restricted to admins.

BUG (2020/06/21): An uneven amount of colons will prevent
    custom emoji from being detected."""

        def convert_emojis_in_message(message, guild):

            def partition_emoji(s, start=0):
                """Find a substring encapsulated in colons
                and partition it, stripping the colons."""
                left = s.find(':', start)
                right = s.find(':', left + 1)
                if left == -1 or right == -1:
                    return None
                return s[:left], s[left + 1:right], s[right + 1:]

            # NOTE: While not very memory efficient to create a dictionary
            # of emojis, the send command is sparsely used
            emojis = {e.name: e for e in guild.emojis}

            # BUG: Emojis not separated from other words by spaces don't
            # get seen
##            word_list = message.split(' ')
##
##            for i, word in enumerate(word_list):
##                if word.startswith(':') and word.endswith(':'):
##                    word = word[1:-1]
##
##                    e = emojis.get(word, None)
##
##                    if e is not None:
##                        # Emoji found; replace word with converted text
##                        word_list[i] = '<:{}:{}>'.format(word, e.id)
##
##            return ' '.join(word_list)

            # BUG: this revision breaks when there are an odd number of colons
            # NOTE: After this, `message` will no longer contain
            # the original message
            parts = []
            while message:
                search = partition_emoji(message)
                if search is None:
                    parts.append(message)
                    break
                left, e, message = search
                parts.append(left)
                parts.append(e)

            # Iterate through the emojis found in the message
            # NOTE: `parts` should always have an odd length
            # (1 for no emoji, then 2 * [# of emoji] + 1)
            for i in range(1, len(parts), 2):
                name = parts[i]
                # Search for custom emoji with matching names
                e = emojis.get(name)

                if e is not None:
                    # Emoji found; replace word with converted text
                    parts[i] = f'<:{name}:{e.id}>'

            return ''.join(parts)

        if channelID == 'here':
            channel = ctx.channel
        else:
            channel = self.bot.get_channel(int(channelID))
        message = convert_emojis_in_message(message, channel.guild)
        # NOTE: Emoji conversion could result in an oversized message.
        await channel.send(message)


    @client_sendmessage.error
    async def client_sendmessage_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotAdmin):
            await ctx.send(get_denied_message())
            return
        elif isinstance(error, AttributeError):
            if "'NoneType' object has no attribute" in str(error):
                await ctx.send('I cannot find the given channel.')
        elif isinstance(error, discord.Forbidden):
            await ctx.send('I cannot access this given channel.')





    @commands.command(
        name='reload')
    @checks.is_bot_owner()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def client_ext_reload(self, ctx, extension):
        """Reload an extension.
https://repl.it/@AllAwesome497/ASB-DEV-again used as reference."""
        logger = discordlogger.get_logger()

        def reload(ext):
            # Unload extension if possible then load extension
            try:
                self.bot.unload_extension(ext)
            except commands.errors.ExtensionNotFound:
                return 'Could not find the extension.'
            except commands.errors.NoEntryPointError:
                return 'This extension is missing a setup.'
            except commands.errors.ExtensionNotLoaded:
                pass
            try:
                self.bot.load_extension(ext)
            except commands.errors.ExtensionNotFound:
                return 'Could not find the extension.'
            except commands.errors.NoEntryPointError:
                return 'This extension is missing a setup.'
            except commands.errors.CommandInvokeError:
                return 'This extension failed to be reloaded.'

        if extension == 'all':
            # Note: must convert dict into list as extensions is mutated
            # during reloading
            for ext in list(self.bot.extensions):
                result = reload(ext)
                if result is not None:
                    await ctx.send(result)
                    break
            else:
                logger.info(
                    f'All extensions reloaded by {get_user_for_log(ctx)}')
                await ctx.send('Extensions have been reloaded.')
        else:
            logger.info(f'Attempting to reload {extension} extension '
                        f'by {get_user_for_log(ctx)}')
            result = reload(extension)
            if result is not None:
                await ctx.send(result)
            else:
                await ctx.send('Extension has been reloaded.')





    @commands.command(
        name='test')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_test(self, ctx):
        await ctx.send(
            'This command is designated for administrative validative \
analysis via manual connection deriving out of the primary specialist.')





    @commands.command(
        name='dmtest')
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def client_dmtest(self, ctx):
        await ctx.author.send(
            'This command is designated for administrative validative \
analysis via manual connection deriving out of the primary specialist.')










def setup(bot):
    bot.add_cog(Administrative(bot))
