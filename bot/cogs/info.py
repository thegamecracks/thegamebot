import collections
import datetime
import sys
import random
import time
from typing import Optional

from dateutil.relativedelta import relativedelta
import discord
from discord.ext import commands
from discord_slash.utils import manage_commands
from discord_slash import cog_ext as dslash_cog
from discord_slash import SlashContext
import discord_slash as dslash
import humanize
import psutil
import pytz

from bot import converters, utils


class Informative(commands.Cog):
    """Informative commands."""
    qualified_name = 'Informative'

    ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS = False
    # If True, members of any guild the bot is in can be looked up in DMs.
    # Note that this has no effect when the members intent is disabled.

    DATETIME_DIFFERENCE_PRECISION = {'minutes': False, 'seconds': False}

    CHANNELINFO_TYPE_NAMES = {
        discord.ChannelType.news: 'announcement'
    }

    COMMANDINFO_BUCKETTYPE_DESCRIPTIONS = {
        commands.BucketType.default:  'globally',
        commands.BucketType.user:     'per user',
        commands.BucketType.guild:    'per guild',
        commands.BucketType.channel:  'per text channel',
        commands.BucketType.member:   'per user',
        commands.BucketType.category: 'per channel category',
        commands.BucketType.role:     'per role'
    }

    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()

        if self.bot.help_command is not None:
            self.bot.help_command.cog = self

    def cog_unload(self):
        help_command = self.bot.help_command
        if help_command is not None:
            help_command.cog = None





    @commands.command(
        name='about', aliases=['info'])
    @commands.cooldown(3, 60, commands.BucketType.guild)
    @commands.max_concurrency(3, wait=True)
    async def client_aboutbot(self, ctx, *args):
        """An about page for this bot.
Optional settings:
    -S --system: show system-related information about the bot."""
        embed = discord.Embed(
            title='About',
            description=('I do random stuff, whatever <@153551102443257856> '
                         'adds to me'),
            color=utils.get_bot_color(ctx.bot)
        ).set_thumbnail(
            url=self.bot.user.avatar_url
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar_url
        )

        vp = sys.version_info
        version_python = f'{vp.major}.{vp.minor}.{vp.micro}'

        start_time = datetime.datetime.fromtimestamp(
            self.process.create_time()).astimezone().astimezone(pytz.utc)

        await ctx.trigger_typing()

        field_statistics = [
            f"Bot started at: {start_time.strftime('%Y/%m/%d %a %X UTC')}"
        ]

        if self.bot.intents.members:
            member_count = sum(not u.bot for u in self.bot.users)
            s_member_count = f'{member_count:,}'
        else:
            member_count = sum(g.member_count for g in self.bot.guilds)
            s_member_count = f'~{member_count:,}'

        commands_processed = sum(
            self.bot.info_processed_commands.values()) + 1

        field_statistics.extend((
            f'# Members: {s_member_count}',
            f'# Servers: {len(self.bot.guilds):,}',
            f'# Commands: {len(self.bot.commands):,}',
            f'# Commands processed: {commands_processed:,}',
            f'Python version: {version_python}',
            f'D.py version: {discord.__version__}'
        ))

        if utils.iterable_has(args, '-S', '--system'):
            # Add system information
            p = self.process
            with p.oneshot():
                mem_usage = p.memory_full_info().uss
                num_threads = p.num_threads()
                num_handles = p.num_handles()
                cpu = p.cpu_percent(interval=0.1)
                if cpu <= 5:
                    # Fake CPU reading :)
                    cpu = min(
                        random.uniform(20, 60),
                        max(1, cpu / 2) * random.uniform(5, 30)
                    )

            field_statistics.extend((
                f'> Bootup time: {self.bot.info_bootup_time:.3g} seconds',
                f'> CPU usage: {cpu:.3g}%',
                f'> Memory usage: {humanize.naturalsize(mem_usage)}',
                f'> Threads: {num_threads}',
                f'> Handles: {num_handles}'
            ))

        embed.add_field(
            name='Statistics',
            value='\n'.join(field_statistics)
        )

        await ctx.send(embed=embed)





    @commands.command(name='channelinfo')
    @commands.cooldown(3, 15, commands.BucketType.channel)
    @commands.guild_only()
    async def client_channelinfo(self, ctx):
        """Count the different types of channels in the server.

This only counts channels that both you and the bot can see."""
        def visible_channels():
            for c in ctx.guild.channels:
                perms_author = c.permissions_for(ctx.author)
                perms_me = c.permissions_for(ctx.me)
                if perms_author.view_channel and perms_me.view_channel:
                    yield c

        counter = collections.Counter(c.type for c in visible_channels())

        s = ['```yaml']
        count_length = max(len(str(v)) for v in counter.values())
        for c, count in counter.most_common():
            name = self.CHANNELINFO_TYPE_NAMES.get(c, str(c)).capitalize()
            s.append(f'{count:>{count_length}} : {name}')
        s.append('```')
        s = '\n'.join(s)

        embed = discord.Embed(
            description=s,
            color=utils.get_bot_color(ctx.bot)
        ).set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)





    @commands.command(name='commandinfo', aliases=('cinfo',))
    @commands.cooldown(3, 15, commands.BucketType.user)
    async def client_commandinfo(self, ctx, *, command):
        """Get statistics about a command."""
        def get_group_uses(stats, cmd):
            """Recursively count the uses of a command group."""
            uses = 0
            for sub in cmd.commands:
                if isinstance(sub, commands.Group):
                    uses += get_group_uses(stats, sub)
                uses += stats[sub.qualified_name]
            return uses

        # Search for the command
        try:
            command = await converters.CommandConverter().convert(ctx, command)
        except commands.BadArgument:
            return await ctx.send("That command doesn't exist.")

        # Create a response
        embed = discord.Embed(
            title=command.qualified_name,
            color=utils.get_bot_color(ctx.bot)
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar_url
        )

        stats = self.bot.info_processed_commands

        is_group = isinstance(command, commands.Group)
        enabled = ('\N{WHITE HEAVY CHECK MARK}' if command.enabled
                   else '\N{NO ENTRY}')

        # Write description
        description = []

        # Insert cog
        if command.cog is not None:
            description.append(
                f'Categorized under: __{command.cog.qualified_name}__')

        # Insert aliases
        if len(command.aliases) == 1:
            description.append(f"Alias: {command.aliases[0]}")
        elif len(command.aliases) > 1:
            description.append(f"Aliases: {', '.join(command.aliases)}")

        # Insert parent
        if command.parent is not None:
            description.append(f'Parent command: {command.parent.name}')

        # Insert enabled status
        description.append(f"Is enabled: {enabled}")

        # Insert hidden status
        if command.hidden:
            description.append('Is hidden: \N{WHITE HEAVY CHECK MARK}')

        # Insert cooldown
        cooldown: commands.Cooldown = command._buckets._cooldown
        if cooldown is not None:
            cooldown_type = self.COMMANDINFO_BUCKETTYPE_DESCRIPTIONS.get(
                cooldown.type, '')
            description.append(
                'Cooldown settings: '
                f'{cooldown.rate}/{cooldown.per:.2g}s {cooldown_type}'
            )

        # Insert concurrency limit
        concurrency: commands.MaxConcurrency = command._max_concurrency
        if concurrency is not None:
            concurrency_type = self.COMMANDINFO_BUCKETTYPE_DESCRIPTIONS.get(
                concurrency.per, '')
            concurrency_wait = '(has queue)' if concurrency.wait else ''
            description.append(
                'Concurrency settings: '
                f'{concurrency.number} {concurrency_type} {concurrency_wait}'
            )

        # Insert uses
        uses = stats[command.qualified_name]
        if is_group:
            # Include total count of subcommands
            uses += get_group_uses(stats, command)

        if command == ctx.command:
            # Command used on self
            uses += 1

        if is_group:
            description.extend((
                f'# subcommands: {len(command.commands):,}',
                f'# uses (including subcommands): {uses:,}'
            ))
        else:
            description.append(f'# uses: {uses:,}')

        # Finalize embed
        embed.description = '\n'.join(description)

        await ctx.send(embed=embed)





    @commands.command(name='messagecount')
    @commands.guild_only()
    @commands.cooldown(2, 10, commands.BucketType.channel)
    async def client_messagecount(self, ctx):
        """Get the number of messages sent in the server within one day.

This command only records the server ID and timestamps of messages,
and purges outdated messages daily. No user info or message content is stored."""
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

        cog = self.bot.get_cog('MessageTracker')
        if cog is None:
            return await ctx.send('Unfortunately the bot is not tracking '
                                  'message frequency at this time.')

        async with cog.connect() as conn:
            async with conn.execute(
                    'SELECT COUNT(*) AS total FROM Messages '
                    'WHERE guild_id = ? AND created_at > ?',
                    (ctx.guild.id, yesterday,)) as c:
                count = (await c.fetchone())['total']

        embed = discord.Embed(
            title='Server Message Count',
            description='{:,} {} have been sent in the last 24 hours.'.format(
                count, ctx.bot.inflector.plural('message', count)),
            colour=utils.get_bot_color(ctx.bot)
        ).set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)





    def get_invite_link(self, perms: Optional[discord.Permissions] = None,
                        slash_commands=True):
        if perms is None:
            perms = discord.Permissions(
                add_reactions=True,
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                external_emojis=True,
                change_nickname=True,
                connect=True,
                speak=True
            )

        link = discord.utils.oauth_url(self.bot.user.id, perms)

        if slash_commands:
            link = link.replace('scope=bot', 'scope=bot%20applications.commands')

        return link


    @commands.command(name='invite')
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def client_invite(self, ctx):
        """Get the bot's invite link."""
        link = self.get_invite_link()
        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot)
        ).set_author(
            name=f'—> Invitation link <—',
            url=link
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)


    @dslash_cog.cog_slash(name='invite')
    async def client_slash_invite(self, ctx: SlashContext):
        """Get the invite link for the bot."""
        link = self.get_invite_link()

        await ctx.send(content=f'[Invitation link]({link})', hidden=True)





    @commands.command(name='ping')
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def client_ping(self, ctx):
        """Get the bot's latency."""
        def round_ms(n):
            return round(n * 100_000) / 1000

        # Bot response time
        now = time.time()
        created_at = pytz.utc.localize(
            ctx.message.created_at
        ).astimezone().timestamp()
        latency_response_ms = round_ms(now - created_at)

        # Heartbeat
        latency_heartbeat_ms = round_ms(ctx.bot.latency)

        embed = discord.Embed(
            title='Pong!',
            color=utils.get_bot_color(ctx.bot)
        )

        # API typing time
        start = time.perf_counter()
        await ctx.trigger_typing()
        latency_typing_ms = round_ms(time.perf_counter() - start)

        # API message time
        start = time.perf_counter()
        message = await ctx.send(embed=embed)
        latency_message_ms = round_ms(time.perf_counter() - start)

        # Format embed
        stats = []
        if latency_response_ms >= 0:
            stats.append(f'\N{EYES} Bot: {latency_response_ms:g}ms')
        stats.extend((
            f'\N{TABLE TENNIS PADDLE AND BALL} API: {latency_message_ms:g}ms',
            f'\N{KEYBOARD} Typing: {latency_typing_ms:g}ms',
            f'\N{HEAVY BLACK HEART} Heartbeat: {latency_heartbeat_ms:g}ms'
        ))
        stats = '\n'.join(stats)
        embed.description = stats

        embed.set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.avatar_url
        )

        await message.edit(embed=embed)





    @commands.command(
        name='serverinfo')
    @commands.guild_only()
    @commands.cooldown(1, 15, commands.BucketType.channel)
    async def client_serverinfo(self, ctx, streamer_friendly: bool = True):
        """Get information about the server you are currently in.

streamer_friendly: If yes, hides the server ID and the owner's discriminator.

Format referenced from the Ayana bot."""
        guild = ctx.author.guild

        created = (
            utils.timedelta_string(
                relativedelta(
                    datetime.datetime.utcnow(),
                    guild.created_at
                ),
                **self.DATETIME_DIFFERENCE_PRECISION,
                inflector=ctx.bot.inflector
            ),
            guild.created_at.strftime('%Y/%m/%d %a %X UTC')
        )
        count_text_ch = len(guild.text_channels)
        count_voice_ch = len(guild.voice_channels)
        owner = guild.owner.name if streamer_friendly else str(guild.owner)
        roles = guild.roles

        embed = discord.Embed(
            color=utils.get_user_color(ctx.bot, ctx.author),
            timestamp=datetime.datetime.utcnow()
        )

        embed.set_author(name=guild.name)
        embed.set_thumbnail(url=guild.icon_url)
        if not streamer_friendly:
            embed.add_field(
                name='ID',
                value=guild.id
            )
        embed.add_field(
            name='Region',
            value=guild.region
        )
        embed.add_field(
            name='Members',
            value=guild.member_count
        )
        embed.add_field(
            name='Channels',
            value=f'{count_text_ch} text : {count_voice_ch} voice'
        )
        embed.add_field(
            name='Owner',
            value=owner
        )
        embed.add_field(
            name='Time of Server Creation',
            value=f'{created[0]} ago ({created[1]})',
            inline=False
        )
        embed.add_field(
            name=f"{len(roles):,} Role{'s' if len(roles) != 1 else ''}",
            value=', '.join([r.mention for r in roles]),
            inline=False
        )
        embed.set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)





    @commands.command(name='utctime', aliases=['utc'])
    @commands.cooldown(3, 15, commands.BucketType.member)
    async def client_timeutc(self, ctx):
        """Get the current date and time in UTC."""
        await ctx.send(time.asctime(time.gmtime()) + ' (UTC)')





    @commands.command(name='timezone', aliases=['tz'])
    @commands.cooldown(2, 5, commands.BucketType.member)
    async def client_timezone(self, ctx, *, timezone):
        """Get the current date and time in a given timezone.

This command uses the IANA timezone database."""
        # Resource: https://medium.com/swlh/making-sense-of-timezones-in-python-16d8ae210c1c
        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            return await ctx.send('Unknown timezone.')

        UTC = pytz.utc
        utcnow = UTC.localize(datetime.datetime.utcnow())
        tznow = utcnow.astimezone(tz)
        await ctx.send(tznow.strftime('%c %Z (%z)'))





    @commands.command(
        name='uptime')
    @commands.cooldown(2, 20, commands.BucketType.user)
    async def client_uptime(self, ctx):
        """Get the uptime of the bot."""
        # Calculate time diff (subtracting downtime)
        diff = relativedelta(
            datetime.datetime.now().astimezone(),
            self.bot.uptime_last_connect_adjusted
        )
        diff_string = utils.timedelta_string(diff, inflector=ctx.bot.inflector)

        utc = self.bot.uptime_last_connect.astimezone(datetime.timezone.utc)
        date_string = utc.strftime('%Y/%m/%d %a %X UTC')

        await ctx.send(embed=discord.Embed(
            title='Uptime',
            description=f'{diff_string}\n({date_string})',
            color=utils.get_bot_color(ctx.bot)
        ))





    @commands.command(
        name='userinfo')
    @commands.cooldown(3, 20, commands.BucketType.user)
    async def client_userinfo(self, ctx,
                              streamer_friendly: Optional[bool] = True,
                              *, user=None):
        """Get information about a user by name or mention.

streamer_friendly: If yes, hides the user's discriminator.
user: Can be referenced by name, nickname, name#discrim, or by mention.

https://youtu.be/CppEzOOXJ8E used as reference.
Format referenced from the Ayana bot."""
        # NOTE: when members intent is enabled, members from guilds
        # the bot is in can be accessed in DMs.
        if user is None:
            user = ctx.author
        else:
            try:
                user = await commands.MemberConverter().convert(ctx, user)
            except commands.MemberNotFound as e:
                if (not self.ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS
                        and ctx.guild is None):
                    return await ctx.send('Cannot search for members in DMs.')
                # Else allow error handler to deal with it
                raise e
            else:
                # Successful search
                is_me = user.id == self.bot.user.id
                if isinstance(user, discord.Member):
                    if ctx.guild is None:
                        # Command invoked in DMs
                        if is_me:
                            # Convert to discord.User so guild-related
                            # information is not displayed
                            user = self.bot.get_user(user.id)
                        elif not self.ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS:
                            # Disallowed showing guild members in DMs
                            return await ctx.send('Cannot search for members in DMs.')

        # Extract attributes based on whether its a Member or User
        if isinstance(user, discord.Member):
            description = None
            activity = user.activity
            # If presences or members intent are disabled, d.py returns
            # None for activity
            guild = user.guild
            joined = (
                utils.timedelta_string(
                    relativedelta(
                        datetime.datetime.utcnow(),
                        user.created_at
                    ),
                    **self.DATETIME_DIFFERENCE_PRECISION,
                    inflector=ctx.bot.inflector
                ),
                user.joined_at.strftime('%Y/%m/%d %a %X UTC')
            )
            nickname = user.nick
            roles = user.roles
            if len(roles) > 1:
                # Has a role(s); remove @everyone
                roles = roles[:0:-1]
            status = None
            # Check required intents before obtaining status
            # (since d.py returns Status.offline instead of None)
            if self.bot.intents.members and self.bot.intents.presences:
                status = user.status
                if isinstance(status, discord.Status):
                    status = str(status).title()
                else:
                    # Status is unknown
                    status = None
                if status == 'Dnd':
                    status = 'Do Not Disturb'
        else:
            description = '*For more information, ' \
                          'use this command in a server.*'
            activity = None
            guild = None
            joined = None
            nickname = None
            roles = None
            status = None
        author = (f'{user} (Bot)' if user.bot
                  else f'{user.name}' if streamer_friendly
                  else str(user))
        created = (
            utils.timedelta_string(
                relativedelta(
                    datetime.datetime.utcnow(),
                    user.created_at
                ),
                **self.DATETIME_DIFFERENCE_PRECISION,
                inflector=ctx.bot.inflector
            ),
            user.created_at.strftime('%Y/%m/%d %a %X UTC')
        )

        embed = discord.Embed(
            color=utils.get_user_color(ctx.bot, user),
            description=description,
            timestamp=datetime.datetime.utcnow()
        )

        embed.set_author(name=author)  # icon_url=user.avatar_url
        embed.set_thumbnail(url=user.avatar_url)
        if not streamer_friendly:
            embed.add_field(
                name='ID',
                value=user.id,
                inline=False
            )
        embed.add_field(
            name='Mention',
            value=user.mention,
            inline=False
        )
        if nickname is not None:
            embed.add_field(
                name='Nickname',
                value=nickname,
                inline=False
            )
        if joined is not None:
            if guild != ctx.guild:
                # Queried in DMs (could also mean found member
                # in another guild but MemberConverter currently won't
                # search for members outside of the guild);
                # include guild name in join title
                joined_name = f'Time of joining {guild.name}'
            else:
                joined_name = 'Time of Server Join'
            embed.add_field(
                name=joined_name,
                value=f'{joined[0]} ago ({joined[1]})',
                inline=False
            )
        embed.add_field(
            name='Time of User Creation',
            value=f'{created[0]} ago ({created[1]})',
            inline=False
        )
        if status is not None:
            embed.add_field(
                name='Status',
                value=status
            )
        if activity is not None:
            if activity.type is discord.ActivityType.playing:
                embed.add_field(
                    name='Playing',
                    value=activity.name
                )
            elif activity.type is discord.ActivityType.streaming:
                embed.add_field(
                    name='Streaming',
                    value=activity.name
                )
            elif activity.type is discord.ActivityType.listening:
                embed.add_field(
                    name='Listening to',
                    value=activity.name
                )
            elif activity.type is discord.ActivityType.watching:
                embed.add_field(
                    name='Watching',
                    value=activity.name
                )
        if roles is not None:
            embed.add_field(
                name=f"{len(roles):,} Role{'s' if len(roles) != 1 else ''}",
                value=', '.join([r.mention for r in roles]),
                inline=False
            )
        embed.set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)










def setup(bot):
    info = Informative(bot)
    # Categorize help command in info
    bot.help_command.cog = info
    bot.add_cog(info)
