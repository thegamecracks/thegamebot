import asyncio
import random
import time

import discord
from discord.ext import commands, tasks

from bot import checks, utils


# Since the settings file is used as an argument to decorators which are
# evaluated at runtime, the file must be set up
class Tasks(commands.Cog):
    """Commands for controlling background tasks."""
    qualified_name = 'Tasks'

    def __init__(self, bot):
        self.bot = bot

        settings = self.bot.get_cog('Settings')

        self.list_guilds.change_interval(
            seconds=settings.get('bgtask_ListGuildsDelay'))
        self.list_guilds.start()

        if settings.get('bgtask_RandomPresenceOnStartup'):
            self.random_presence.start()

    def cog_unload(self):
        self.list_guilds.cancel()
        self.random_presence.cancel()

    @staticmethod
    def timestamp():
        """Show the current time."""
        return time.strftime(
            'Timestamp: %c',
            time.localtime()
        )





    @tasks.loop()
    async def list_guilds(self):
        """Periodically lists all guilds the bot is in."""
        print(self.timestamp())
        print('Current guilds:')
        for guild in self.bot.guilds:
            print(guild.name)
        print()

    @list_guilds.before_loop
    async def before_list_guilds(self):
        await self.bot.wait_until_ready()





    @tasks.loop(minutes=5)
    async def random_presence(self):
        """Periodically change current presence.

        Format:
            {
                'status':   'online',
                'activity': 'playing',
                'title':    'something',
                'url':      'DEFAULT_STREAMING_URL'  # only-when-streaming
            }

        """
        def print_presence(pres):
            activity = pres.get('activity')
            title = pres.get('title')
            url = pres.get('url')
            status = pres.get('status')
            message = ['Random Presence: ']
            if activity is None:
                message.append('cleared activity')
            elif activity == 'listening':
                message.append(f'listening to {title}')
            elif activity == 'playing':
                message.append(f'playing {title}')
            elif activity == 'streaming':
                message.append(f'streaming {title} to {url}')
            elif activity == 'watching':
                message.append(f'watching {title}')
            elif activity == 'competing':
                message.append(f'competing in {title}')

            if status == discord.Status.online:
                message.append(', status: online')
            elif status == discord.Status.idle:
                message.append(', status: idle')
            elif status == discord.Status.dnd:
                message.append(', status: dnd')
            elif status == discord.Status.invisible:
                message.append(', status: invisible')

            print(''.join(message))

        settings = self.bot.get_cog('Settings')

        pres = random.choice(settings.get('bgtask_RandomPresences'))

        # Parse status, otherwise use online/randomly pick one
        status = pres.get('status')
        if status is not None:
            status = utils.parse_status(status)
        elif random.randint(1, 100) <= settings.get(
                'bgtask_RandomPresenceRandomStatusChance'):
            status = random.choice(
                (discord.Status.idle, discord.Status.dnd)
            )
        else:
            status = discord.Status.online

        # Parse activity
        activity = pres.get('activity')
        if activity == 'listening':
            activity = discord.Activity(
                name=pres['title'], type=discord.ActivityType.listening)
        elif activity == 'playing':
            activity = discord.Game(name=pres['title'])
        elif activity == 'streaming':
            url = pres.get('url') or settings.get('default_StreamingURL')
            activity = discord.Streaming(name=pres['title'], url=url)
        elif activity == 'watching':
            activity = discord.Activity(
                name=pres['title'], type=discord.ActivityType.watching)
        elif activity == 'competing':
            activity = discord.Activity(
                name=pres['title'], type=discord.ActivityType.competing)

        # Change presence
        print(self.timestamp())
        print_presence(pres)
        await self.bot.change_presence(activity=activity, status=status)

        # Sleep
        min_delay = settings.get('bgtask_RandomPresenceMinDelay')
        max_delay = settings.get('bgtask_RandomPresenceMaxDelay')
        self.random_presence.change_interval(
            seconds=random.randint(min_delay, max_delay))

    @random_presence.before_loop
    async def before_random_presence(self):
        await self.bot.wait_until_ready()

    @commands.command(
        name='randompresence',
        brief='Toggles random presence changes.',
        aliases=('randpres', 'randpresence'))
    @commands.is_owner()
    async def random_presence_toggle(self, ctx, toggle: bool):
        if toggle:
            if not self.random_presence.is_running():
                self.random_presence.start()
            else:
                return await ctx.send('The task is already running.')

            settings = ctx.bot.get_cog('Settings')

            min_delay = settings.get('bgtask_RandomPresenceMinDelay')
            max_delay = settings.get('bgtask_RandomPresenceMaxDelay')
            print('Enabled random presence')
            await ctx.send(
                'Now randomly changing presence '
                'every {}-{} seconds.'.format(
                    min_delay,
                    max_delay
                )
            )
        elif self.random_presence.is_running():
            self.random_presence.cancel()
            print('Disabled random presence')
            await ctx.send('Turned off random presence changes.')
        else:
            await ctx.send('The task is not running.')










def setup(bot):
    bot.add_cog(Tasks(bot))
