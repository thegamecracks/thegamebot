import asyncio
import random
import time

import discord
from discord.ext import commands, tasks

from bot import checks
from bot import settings
from bot import utils


# Since the settings file is used as an argument to decorators which are
# evaluated at runtime, the file must be set up
class BackgroundTasks(commands.Cog):
    qualified_name = 'Threads'
    description = 'Background tasks.'

    def __init__(self, bot):
        self.bot = bot

        self.list_guilds.start()
        if settings.get_setting('bgtask_RandomPresenceOnStartup'):
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





    @tasks.loop(seconds=settings.get_setting('bgtask_ListGuildsDelay'))
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





    @tasks.loop()
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

            if status == discord.Status.online:
                message.append(', status: online')
            elif status == discord.Status.idle:
                message.append(', status: idle')
            elif status == discord.Status.dnd:
                message.append(', status: dnd')
            elif status == discord.Status.invisible:
                message.append(', status: invisible')

            print(''.join(message))

        while not self.bot.is_closed():
            try:
                pres = random.choice(
                    settings.get_setting('bgtask_RandomPresences')
                ).copy()
                # NOTE: .copy() is a fix to a bug occurring after
                # settings caching was added where it mutates the status
                # attribute and on second pass, it attempts reconverting
                # the enumeration
            except IndexError:
                print('No random presences in settings; '
                      'ending random presence task')
                return

            # Parse status, otherwise use online/randomly pick one
            if 'status' in pres:
                pres['status'] = utils.parse_status(pres['status'])
            elif random.randint(1, 100) <= settings.get_setting(
                    'bgtask_RandomPresenceRandomStatusChance'):
                pres['status'] = random.choice(
                    (discord.Status.idle, discord.Status.dnd)
                )
            else:
                pres['status'] = discord.Status.online

            # Parse activity
            activity = pres.get('activity')
            if activity == 'listening':
                activity = discord.Activity(
                    name=pres['title'], type=discord.ActivityType.listening)
            elif activity == 'playing':
                activity = discord.Game(name=pres['title'])
            elif activity == 'streaming':
                if 'url' not in pres:
                    pres['url'] = settings.get_setting('default_StreamingURL')
                activity = discord.Streaming(
                    name=pres['title'], url=pres['url'])
            elif activity == 'watching':
                activity = discord.Activity(
                    name=pres['title'], type=discord.ActivityType.watching)

            # Change presence
            print(self.timestamp())
            print_presence(pres)
            await self.bot.change_presence(
                activity=activity, status=pres['status'])

            # Sleep
            min_delay = settings.get_setting('bgtask_RandomPresenceMinDelay')
            max_delay = settings.get_setting('bgtask_RandomPresenceMaxDelay')
            await asyncio.sleep(random.randint(
                min_delay, max_delay))

    @random_presence.before_loop
    async def before_random_presence(self):
        await self.bot.wait_until_ready()

    @commands.command(
        name='randompresence',
        brief='Toggles random presence changes.',
        aliases=('randpres', 'randpresence'))
    @checks.is_bot_admin()
    async def random_presence_toggle(self, ctx, toggle: bool):
        if toggle:
            try:
                self.random_presence.start()
            except RuntimeError:
                return await ctx.send('The task is already running.')

            min_delay = settings.get_setting('bgtask_RandomPresenceMinDelay')
            max_delay = settings.get_setting('bgtask_RandomPresenceMaxDelay')
            print('Enabled random presence')
            await ctx.send(
                'Now randomly changing presence '
                'every {}-{} seconds.'.format(
                    min_delay,
                    max_delay
                )
            )
        else:
            self.random_presence.cancel()
            print('Disabled random presence')
            await ctx.send('Turning off random presence changes.')










def setup(bot):
    bot.add_cog(BackgroundTasks(bot))
