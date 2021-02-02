"""
The "execute" command is in part from RoboDanny which is released under MPL-2.0.
See https://www.mozilla.org/en-US/MPL/2.0/ for full license details.
"""
import contextlib
import io
import textwrap
import time
from typing import Optional

import discord
from discord.ext import commands
import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from bot.classes.confirmation import AdaptiveConfirmation
from bot.other import discordlogger
from bot import checks, converters, settings, utils


def get_user_for_log(ctx):
    return f'{ctx.author} ({ctx.author.id})'


def send_restart_signal():
    """Create a file named RESTART that the batch file running the script
    loop should detect and recognize to rerun the bot again."""
    open('RESTART', 'w').close()


class BucketTypeConverter(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            # Convert by number
            return commands.BucketType(argument)
        except ValueError:
            try:
                # Convert by enum name
                return getattr(commands.BucketType, argument)
            except AttributeError:
                raise commands.BadArgument(f'{argument!r} is not a valid BucketType')


class Administrative(commands.Cog):
    """Administrative commands available for owners/admins."""
    qualified_name = 'Administrative'

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





    @commands.group(name='cooldown', invoke_without_command=True)
    @checks.is_bot_admin()
    async def client_cooldown(self, ctx):
        """Modify a command's cooldown."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.',
                       delete_after=6)


    @client_cooldown.command(name='update')
    async def client_cooldown_update(
            self, ctx,
            command: converters.CommandConverter,
            rate: Optional[int] = None,
            per: Optional[float] = None,
            type: BucketTypeConverter = None):
        """Update a command's cooldown."""
        type: commands.BucketType
        command: commands.Command

        # Fill missing arguments
        old_cool: commands.CooldownMapping = command._buckets
        if old_cool.valid:
            rate = old_cool._cooldown.rate if rate is None else rate
            per = old_cool._cooldown.per if per is None else per
            type = old_cool._cooldown.type if type is None else type

        # Default arguments
        if type is None:
            type = commands.BucketType.default

        # Check arguments
        if rate is None:
            return await ctx.send(
                'There is no cooldown; `rate` must be specified.',
                delete_after=10
            )
        elif rate < 1:
            return await ctx.send('`rate` cannot be below 1.', delete_after=10)
        elif per is None:
            return await ctx.send(
                'There is no cooldown; `per` must be specified.',
                delete_after=10
            )
        elif per < 0:
            return await ctx.send('`per` cannot be negative.', delete_after=10)

        buckets = commands.CooldownMapping(commands.Cooldown(rate, per, type))
        command._buckets = buckets

        await ctx.send(f'Updated cooldown for {command.name}.')


    @client_cooldown.command(name='reset')
    async def client_cooldown_reset(self, ctx,
                                    everyone: Optional[bool] = False,
                                    *, command: converters.CommandConverter):
        """Reset a command's cooldown.

everyone: If true, this will reset everyone's cooldown. Otherwise it only
resets your cooldown.
command: The name of the command to reset."""
        command: commands.Command

        if not command._buckets.valid:
            return await ctx.send('This command does not have a cooldown.',
                                  delete_after=10)

        if everyone:
            buckets = command._buckets
            buckets._cache.clear()
        else:
            command.reset_cooldown(ctx)

        await ctx.send(f'Resetted cooldown for {command.name}.')


    @client_cooldown.command(name='remove')
    async def client_cooldown_remove(
            self, ctx, *, command: converters.CommandConverter):
        """Remove a command's cooldown."""
        command: commands.Command

        if not command._buckets.valid:
            return await ctx.send('This command does not have a cooldown.',
                                  delete_after=10)

        buckets = commands.CooldownMapping(None)
        command._buckets = buckets

        await ctx.send(f'Removed cooldown for {command.name}.')





    @commands.group(name='concurrency', invoke_without_command=True)
    @checks.is_bot_admin()
    async def client_concurrency(self, ctx):
        """Modify a command's max concurrency."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.',
                       delete_after=6)


    @client_concurrency.command(name='update')
    async def client_concurrency_update(
            self, ctx,
            command: converters.CommandConverter,
            number: Optional[int] = None,
            per: Optional[BucketTypeConverter] = None,
            wait: bool = None):
        """Update a command's concurrency limit."""
        command: commands.Command

        # Fill missing arguments
        old_con: commands.MaxConcurrency = command._max_concurrency
        if old_con is not None:
            number = old_con.number if number is None else number
            per = old_con.per if per is None else number
            wait = old_con.wait if wait is None else wait

        # Default arguments
        if per is None:
            per = commands.BucketType.default
        if wait is None:
            wait = False

        # Check arguments
        if number is None:
            return await ctx.send(
                'There is no concurrency limit; `number` must be specified.',
                delete_after=10
            )
        elif number < 1:
            return await ctx.send('`number` cannot be below 1.', delete_after=10)

        con = commands.MaxConcurrency(number, per=per, wait=wait)
        command._max_concurrency = con
        # NOTE: no need to worry about race conditions since MaxConcurrency.release()
        # excepts KeyError if the bucket does not exist

        await ctx.send(f'Updated concurrency limits for {command.name}.')


    @client_concurrency.command(name='remove')
    async def client_concurrency_remove(self, ctx, *,
                                        command: converters.CommandConverter):
        """Remove a command's max concurrency limit."""
        command: commands.Command

        if command._max_concurrency is None:
            return await ctx.send(
                'This command does not have a max concurrency limit.',
                delete_after=10
            )

        command._max_concurrency = None
        await ctx.send(f'Removed concurrency limits for {command.name}.')





    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code.

        Based off of RoboDanny/rewrite/cogs/admin.py.

        """
        # remove ```py\n``` or ```py```
        if content.startswith('```') and content.endswith('```'):
            return content.lstrip('```py').strip('```').strip()
        return content


    @commands.command(name='execute')
    @checks.is_bot_owner()
    async def client_execute(
            self, ctx, sendIOtoDM: Optional[bool] = False, *, x: str):
        """Run python code in an async condition.
Graphs can be generated if a Figure is returned.

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
            'discord': discord,
            'commands': commands,
            'bot': self.bot,
            'ctx': ctx,
            'matplotlib': matplotlib,
            'plt': plt,
            'np': np,
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

        # If matplotlib figure was returned, generate an image from it
        image = None
        if isinstance(result, matplotlib.figure.Figure):
            image = io.BytesIO()
            result.savefig(
                image, format='png', bbox_inches='tight', pad_inches=0)
            plt.close(result)
            image.seek(0)
            image = discord.File(image, 'Graph.png')
            result = None

        # Get output and truncate it, and display result if its not None
        out = f.getvalue() + f'{result}' * (result is not None)
        out = utils.truncate_message(out, 1991)  # -9 to add code blocks

        # Return output
        if out:
            await send(f'```py\n{out}```', file=image)
        elif image is not None:
            await send(file=image)





    @commands.command(name='clearsettingscache')
    @checks.is_bot_owner()
    async def client_clearsettingscache(self, ctx):
        """Clear the settings cache."""
        settings.clear_cache()
        await ctx.send('Cleared cache.', delete_after=10)





    @commands.group(name='presence', invoke_without_command=True)
    @checks.is_bot_admin()
    @commands.cooldown(2, 40, commands.BucketType.default)
    async def client_presence(self, ctx):
        """Commands to change the bot's presence. Restricted to admins."""
        await ctx.send(f'Unknown {ctx.command.name} subcommand given.',
                       delete_after=6)


    @client_presence.command(name='competing')
    async def client_competing(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the competing message.
status: The status to set for the bot.
title: The title to show."""
        if title is None:
            return await self.bot.change_presence(activity=None)

        activity = discord.Activity(
            name=title, type=discord.ActivityType.competing)

        await self.bot.change_presence(
            activity=activity, status=status)


    @client_competing.error
    async def client_competing_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.', delete_after=8)


    @client_presence.command(
        name='playing')
    async def client_playing(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the playing message.
status: The status to set for the bot.
title: The title to show."""
        if title is None:
            return await self.bot.change_presence(activity=None)

        game = discord.Game(name=title)

        await self.bot.change_presence(
            activity=game, status=status)


    @client_playing.error
    async def client_playing_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.', delete_after=8)


    @client_presence.command(
        name='streaming')
    async def client_streaming(self, ctx,
        status: utils.parse_status = 'online',
        title=None,
            url='https://www.twitch.tv/thegamecracks'):
        """Sets the streaming message.
status: The status to set for the bot.
title: The title to show. Use "quotations" to specify the title.
url: The url to link to when streaming. Defaults to \
https://www.twitch.tv/thegamecracks ."""
        if title is None:
            return await self.bot.change_presence(activity=None)

        game = discord.Streaming(name=title, url=url)

        await self.bot.change_presence(
            activity=game, status=status)


    @client_streaming.error
    async def client_streaming_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.', delete_after=8)


    @client_presence.command(name='listening')
    async def client_listening(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the listening message.
status: The status to set for the bot.
title: The title to show."""
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
                await ctx.send('Unknown status given.', delete_after=8)


    @client_presence.command(
        name='watching')
    async def client_watching(self, ctx,
            status: utils.parse_status = 'online', *, title=None):
        """Sets the watching message.
status: The status to set for the bot.
title: The title to show."""
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
                await ctx.send('Unknown status given.', delete_after=8)


    @client_presence.command(
        name='status',
        aliases=('state',))
    @commands.cooldown(2, 40, commands.BucketType.default)
    async def client_status(self, ctx, status: utils.parse_status = 'online'):
        """Sets the current status.
Options:
    online, on
    idle, away
    dnd
    invisible, offline, off
This removes any activity the bot currently has."""
        await self.bot.change_presence(status=status)


    @client_status.error
    async def client_status_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, commands.BadArgument):
            if 'parse_status' in str(error):
                await ctx.send('Unknown status given.', delete_after=8)





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
            except (ModuleNotFoundError, commands.errors.ExtensionNotFound):
                return 'Could not find the extension.'
            except commands.errors.NoEntryPointError:
                return 'This extension is missing a setup.'
            except commands.errors.CommandInvokeError:
                return 'This extension failed to be reloaded.'

        if extension == 'all':
            logger.info('Attempting to reload all extensions '
                        f'by {get_user_for_log(ctx)}')
            await ctx.trigger_typing()
            # NOTE: must cast dict into list as extensions is mutated
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
            await ctx.trigger_typing()
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
        if isinstance(error, AttributeError):
            if "'NoneType' object has no attribute" in str(error):
                await ctx.send('I cannot find the given channel.', delete_after=8)
        elif isinstance(error, discord.Forbidden):
            await ctx.send('I cannot access this given channel.', delete_after=8)





    @commands.command(name='restart')
    @checks.is_bot_owner()
    async def client_restart(self, ctx):
        """Restarts the bot."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            'Are you sure you want to RESTART the bot?')

        if confirmed:
            await prompt.update('Restarting.', prompt.emoji_yes.color)
            send_restart_signal()
            print(f'Initiating restart by {get_user_for_log(ctx)}')
            await self.bot.logout()
        else:
            await prompt.update('Cancelled restart.', prompt.emoji_no.color)





    @commands.command(
        name='shutdown',
        aliases=('close', 'exit', 'quit', 'stop'))
    @checks.is_bot_owner()
    async def client_shutdown(self, ctx):
        """Shutdown the bot."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            'Are you sure you want to SHUTDOWN the bot?')

        if confirmed:
            await prompt.update('Shutting down.', prompt.emoji_yes.color)
            print(f'Initiating shutdown by {get_user_for_log(ctx)}')
            await self.bot.logout()
        else:
            await prompt.update('Cancelled shutdown.', prompt.emoji_no.color)










def setup(bot):
    bot.add_cog(Administrative(bot))
