import contextlib
import io
import random
import textwrap
import time

import discord
from discord.ext import commands

from bot import checks
from bot import settings
from bot import utils
from bot.other import discordlogger


def get_denied_message():
    return random.choice(settings.get_setting('deniedmessages'))


def get_user_for_log(ctx):
    return f'{ctx.author} ({ctx.author.id})'


class Administrative(commands.Cog):
    qualified_name = 'Administrative'
    description = 'Administrative commands available for owners/admins.'

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None  # Used in execute command





    @commands.command(name='block')
    @checks.is_bot_owner()
    async def client_block(self, ctx, x: int = 20):
        """Block the operation of the bot."""
        await ctx.send(f'Blocking for {x} seconds.')
        time.sleep(x)
        await ctx.send('Finished blocking.')


    @client_block.error
    async def client_block_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotOwner):
            await ctx.send(get_denied_message())





    @commands.command(name='cooldown')
    @checks.is_bot_admin()
    async def client_cooldown(self, ctx, *, command):
        """Reset your cooldown for a command.

Will reset cooldowns for all subcommands in a group."""
        com = self.bot.get_command(command)

        if com is None:
            await ctx.send('Unknown command.')

        com.reset_cooldown(ctx)

        await ctx.send('Cooldown reset.')


    @client_cooldown.error
    async def client_cooldown_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotOwner):
            await ctx.send(get_denied_message())





    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code.

        Based off of RoboDanny/rewrite/cogs/admin.py.

        """
        # remove ```py\n``` or ```py```
        if content.startswith('```') and content.endswith('```'):
            # return '\n'.join(content.split('\n')[1:-1])
            return content.lstrip('```py').rstrip('```').strip()
        return content


    @commands.command(name='execute')
    @checks.is_bot_owner()
    async def client_execute(self, ctx, sendIOtoDM: bool, *, x: str):
        """Run python code in an async condition.

Based off of https://repl.it/@AllAwesome497/ASB-DEV-again and RoboDanny."""
        async def send(*args, **kwargs):
            # Send to either DM or channel based on sendIOtoDM
            if sendIOtoDM:
                return await ctx.author.send(*args, **kwargs)
            await ctx.send(*args, **kwargs)

        # Remove code blocks
        x = self.cleanup_code(x)

        # Compile the code as an async function
        # See RoboDanny admin.py cog
        to_compile = f'async def func():\n{textwrap.indent(x, "  ")}'

        environment = {
            'author': ctx.author,
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'discord': discord,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self._last_result
        }

        # Log before compilation
        log = f'Executing code by {get_user_for_log(ctx)}:\n {to_compile}'
        discordlogger.get_logger().warning(log)
        print(log)

        try:
            exec(to_compile, environment)
        except Exception as e:
            return await ctx.send(
                'Failed during compilation:\n`{}`'.format(
                    discord.utils.escape_markdown(
                        f'{e.__class__.__name__}: {e}'
                    )
                )
            )

        # Run code and store output
        f = io.StringIO()
        try:
            with contextlib.redirect_stdout(f):
                result = await environment['func']()
        except Exception:
            error_message = utils.exception_message()
            return await ctx.send(f'```py\n{error_message}```')

        # Get output and truncate it, and display result if its not None
        out = f.getvalue() + f'{result}' * (result is not None)
        out = utils.truncate_message(out, 1991)  # -9 to add code blocks

        # Return output
        if out:
            await send(f'```py\n{out}```')


    @client_execute.error
    async def client_execute_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotOwner):
            await ctx.send(get_denied_message())





    @commands.command(name='clearsettingscache')
    @checks.is_bot_owner()
    async def client_clearsettingscache(self, ctx):
        """Clear the settings cache."""
        settings.clear_cache()
        await ctx.send('Cleared cache.')


    @client_clearsettingscache.error
    async def client_clearsettingscache_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotOwner):
            await ctx.send(get_denied_message())





    @commands.group(name='presence', invoke_without_command=True)
    @checks.is_bot_admin()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def client_presence(self, ctx):
        """Commands to change the bot's presence. Restricted to admins."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.')


    @client_presence.error
    async def client_presence_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, checks.InvalidBotAdmin):
            await ctx.send(get_denied_message())


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


    @client_presence.command(name='listening')
    async def client_listening(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the listening message.
status - The status to set for the bot.
title - The title to show."""
        if title is None:
            return await self.bot.change_presence(activity=None)

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
            return await self.bot.change_presence(activity=None)

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
                    return await ctx.send(result)
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
        elif isinstance(error, AttributeError):
            if "'NoneType' object has no attribute" in str(error):
                await ctx.send('I cannot find the given channel.')
        elif isinstance(error, discord.Forbidden):
            await ctx.send('I cannot access this given channel.')





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










def setup(bot):
    bot.add_cog(Administrative(bot))
