#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import collections
import datetime
import io
import itertools
import math
import random
import re
import sys
import time
from typing import Optional, Literal

from dateutil.relativedelta import relativedelta
import discord
from discord.ext import commands
import humanize
import matplotlib
from matplotlib import colors
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import psutil

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

    MESSAGECOUNT_BINS_PER_HOUR = 3
    MESSAGECOUNT_DOWNTIME_BINS_PER_HOUR = 6
    MESSAGECOUNT_IGNORE_ALLOWED_DOWNTIMES = True
    # If true, uses the uptime cog to filter downtimes
    # shorter than UPTIME_ALLOWED_DOWNTIME

    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()

        if self.bot.help_command is not None:
            self.bot.help_command.cog = self

    def cog_unload(self):
        help_command = self.bot.help_command
        if help_command is not None:
            help_command.cog = None





    @commands.command(name='about', aliases=('info',))
    @commands.cooldown(3, 60, commands.BucketType.guild)
    @commands.max_concurrency(3, wait=True)
    async def client_aboutbot(self, ctx, *args):
        """An about page for this bot.
Optional settings:
    -S --system: show system-related information about the bot."""
        embed = discord.Embed(
            title='About',
            description=(
                'I do random stuff, whatever '
                '[**thegamecracks**](https://github.com/thegamecracks/thegamebot "This bot\'s GitHub repository") '
                'adds to me.'
            ),
            color=utils.get_bot_color(ctx.bot)
        ).set_thumbnail(
            url=self.bot.user.avatar.url
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar.url
        )

        vp = sys.version_info
        version_python = f'{vp.major}.{vp.minor}.{vp.micro}'

        start_time = datetime.datetime.fromtimestamp(
            self.process.create_time()).astimezone()
        start_time = await ctx.bot.strftime_user(ctx.author.id, start_time)

        field_statistics = [
            f"Bot started at: {start_time}"
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
                memory_info = p.memory_full_info()
                mem_phys = humanize.naturalsize(memory_info.uss)
                mem_virt = humanize.naturalsize(memory_info.vms)
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
                f'> Memory usage: {mem_phys} (virtual: {mem_virt})',
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
            icon_url=ctx.author.avatar.url
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
            command: commands.Command = \
                await converters.CommandConverter().convert(ctx, command)
        except commands.BadArgument:
            return await ctx.send("That command doesn't exist.")

        # Create a response
        embed = discord.Embed(
            title=command.qualified_name,
            color=utils.get_bot_color(ctx.bot)
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar.url
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
        cooldown: commands.CooldownMapping = command._buckets
        if cooldown is not None:
            cooldown_type = self.COMMANDINFO_BUCKETTYPE_DESCRIPTIONS.get(
                cooldown._type, '')
            description.append(
                'Cooldown settings: {}/{:.0f}s {}'.format(
                    cooldown._cooldown.rate,
                    cooldown._cooldown.per,
                    cooldown_type
                )
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
            command: commands.Group
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





    def message_count_graph(
            self, graphing_cog, uptime_cog, messages, now, cumulative=False):
        """Generate a histogram of when messages were sent.
        Assumes all messages were sent in the last day.

        Args:
            graphing_cog (commands.Cog): The Graphing cog.
            uptime_cog (Optional[commands.Cog]): The Uptime cog.
                Only required if intermittent downtimes should be filtered.
            messages (List[float]): A list of times in seconds since now
                for each message that was sent.
            now (datetime.datetime): A timezone-aware datetime of now.
            cumulative (bool): Accumulate message counts in the histogram.

        """
        def downtime_to_seconds(downtimes):
            """Convert a list of downtimes into a set of seconds denoting
            which hours have been affected by the downtime.
            """
            n_bins = 24 * downtime_bins_per_hour
            seconds_per_bin = day // n_bins
            minimum_downtime = getattr(
                uptime_cog, 'UPTIME_ALLOWED_DOWNTIME', None)

            affected_bins = set()
            for period in downtimes:
                end = (now - period.end).total_seconds()
                if end > day:
                    continue
                elif (  minimum_downtime is not None
                        and period.total_seconds() <= minimum_downtime):
                    # Ignore intermittent downtime periods
                    continue

                start = min(day, (now - period.start).total_seconds())

                # Round the start and end to the nearest bin
                start = math.ceil(start / seconds_per_bin)
                end = int(end // seconds_per_bin)

                # Add the bins inbetween the start and end
                for b in range(end, start):
                    affected_bins.add(b * seconds_per_bin)

            return range(0, day + 1, seconds_per_bin), affected_bins

        def format_hours(seconds, pos):
            return seconds // hour

        # Constants
        bot_color = '#' + hex(utils.get_bot_color(self.bot))[2:]
        day, hour = 86400, 3600
        bins_per_hour = self.MESSAGECOUNT_BINS_PER_HOUR
        downtime_bins_per_hour = self.MESSAGECOUNT_DOWNTIME_BINS_PER_HOUR
        n_bins = 24 * bins_per_hour
        seconds_per_bin = day // n_bins
        bin_edges = range(0, day + 1, seconds_per_bin)
        downtime_edges, downtime_bins = downtime_to_seconds(
            self.bot.uptime_downtimes)

        fig, ax = plt.subplots()

        # Plot messages
        N, bins, patches = ax.hist(
            messages, bins=bin_edges, cumulative=-cumulative)

        # Color each bar
        colors = plt.cm.hsv([0.4 - 0.15 * i / 23 for i in range(24)])
        patches_grouped = (patches[i:i + bins_per_hour]
                           for i in range(0, len(patches), bins_per_hour))
        for c, bars in zip(colors, patches_grouped):
            for p in bars:
                p.set_facecolor(c)

        if downtime_bins:
            # Plot downtime and include legend
            downtime_data = np.repeat(np.array(list(downtime_bins)), max(N))
            dtN, dtbins, dtpatches = ax.hist(
                downtime_data, bins=downtime_edges, hatch='//',
                facecolor='#00000000', edgecolor='#00000000'
            )
            # Workaround to color just the hatches since
            # no public interface is provided
            for patch in dtpatches:
                patch._hatch_color = matplotlib.colors.to_rgba('#ff0000a0')
            ax.legend([dtpatches[0]], ['Downtime'], labelcolor=bot_color)

        # Add labels
        ax.set_title('Message Count Graph')
        ax.set_xlabel('# hours ago')
        ax.set_ylabel('# messages')

        # Set ticks and formatting
        ax.set_xticks(range(0, day + 1, hour * 6))
        # ax.set_xticks(range(0, hour_span * hour + 1, hour * math.ceil(hour_span / 4)))
        # NOTE: looks better to always use 6 hour tick increments
        # instead of dynamically changing the ticks based on the hour span
        ax.xaxis.set_major_formatter(format_hours)
        ax.invert_xaxis()

        # Force yaxis integer ticks
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        # Add grid 
        ax.set_axisbelow(True)
        ax.grid(color='#707070', alpha=0.4)

        # Set label colors
        for item in itertools.chain(
                (ax.title, ax.xaxis.label, ax.yaxis.label),
                ax.get_xticklabels(), ax.get_yticklabels()):
            item.set_color(bot_color)

        # Color the spines and ticks
        for spine in ax.spines.values():
            spine.set_color(bot_color)
        ax.tick_params(colors=bot_color)

        # Make background fully transparent
        fig.patch.set_facecolor('#00000000')

        graphing_cog.set_axes_aspect(ax, 9 / 16, 'box')

        f = io.BytesIO()
        fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
        # bbox_inches, pad_inches: removes padding around the graph
        f.seek(0)

        plt.close(fig)
        return f


    @commands.command(name='messagecount')
    @commands.guild_only()
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_messagecount(self, ctx, cumulative: bool = False):
        """Get the number of messages sent in the server within one day.

This command only records the server ID and timestamps of messages,
and purges outdated messages daily. No user info or message content is stored.
A time series graph is generated along with this.

cumulative: If true, makes the number of messages cumulative when graphing."""
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

        cog = self.bot.get_cog('MessageTracker')
        if cog is None:
            return await ctx.send(
                'The bot is currently not tracking message frequency.')

        utcnow_timestamp = datetime.datetime.utcnow().timestamp()
        now = datetime.datetime.now().astimezone()
        start_time = datetime.datetime.fromtimestamp(
            self.process.create_time()).astimezone()
        start_hour = math.ceil((now - start_time).total_seconds() / 3600)
        hour_span = min(24, start_hour)
        plural = ctx.bot.inflector.plural

        with ctx.typing():
            messages = []
            async with cog.connect() as conn:
                async with conn.execute(
                        'SELECT created_at FROM Messages '
                        'WHERE guild_id = ? AND created_at > ?',
                        ctx.guild.id, yesterday) as c:
                    while m := await c.fetchone():
                        dt = m['created_at']
                        td = max(0, utcnow_timestamp - dt.timestamp())
                        messages.append(td)
            count = len(messages)

            embed = discord.Embed(
                title='Server Message Count',
                description='{:,} {} {} been sent in the last {}.'.format(
                    count, plural('message', count), plural('has', count),
                    'hour' if hour_span == 1 else f'{hour_span} hours'
                ),
                colour=utils.get_bot_color(ctx.bot)
            ).set_footer(
                text=f'Requested by {ctx.author.display_name}',
                icon_url=ctx.author.avatar.url
            )

            graph = None
            require_uptime_cog = self.MESSAGECOUNT_IGNORE_ALLOWED_DOWNTIMES
            graphing_cog = ctx.bot.get_cog('Graphing')
            uptime_cog = ctx.bot.get_cog('Uptime') if require_uptime_cog else None
            if count and graphing_cog and (uptime_cog or not require_uptime_cog):
                # Generate graph
                f = await asyncio.to_thread(
                    self.message_count_graph,
                    graphing_cog, uptime_cog, messages, now, cumulative
                )
                graph = discord.File(f, filename='graph.png')
                embed.set_image(url='attachment://graph.png')

        await ctx.send(file=graph, embed=embed)





    def get_invite_link(self, perms: Optional[discord.Permissions] = None):
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

        return discord.utils.oauth_url(
            self.bot.user.id, permissions=perms,
            scopes=('bot', 'applications.commands')
        )


    @commands.command(name='invite')
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def client_invite(self, ctx):
        """Get the bot's invite link."""
        link = self.get_invite_link()
        embed = discord.Embed(
            description=link,
            color=utils.get_bot_color(ctx.bot)
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar.url
        )

        await ctx.send(embed=embed)





    @commands.command(name='ping')
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def client_ping(self, ctx):
        """Get the bot's latency."""
        def round_ms(n):
            return round(n * 100_000) / 1000

        async def time_ms(coro):
            start = time.perf_counter()
            await coro
            return round_ms(time.perf_counter() - start)

        async def poll_database():
            async with await ctx.bot.dbusers.connect() as conn:
                await conn.execute('SELECT 1')

        async def poll_message():
            nonlocal message
            message = await ctx.send(embed=embed)

        message: discord.Message
        embed = discord.Embed(
            title='Pong!',
            color=utils.get_bot_color(ctx.bot)
        )

        task_database = asyncio.create_task(time_ms(poll_database()))
        task_message = asyncio.create_task(time_ms(poll_message()))
        task_typing = asyncio.create_task(time_ms(ctx.trigger_typing()))
        await asyncio.wait((task_typing, task_message, task_database))

        latency_database_ms = task_database.result()
        latency_heartbeat_ms = round_ms(ctx.bot.latency)
        latency_message_ms = task_message.result()
        latency_typing_ms = task_typing.result()

        # Format embed
        stats = []
        stats.extend((
            f'\N{TABLE TENNIS PADDLE AND BALL} API: {latency_message_ms:g}ms',
            f'\N{KEYBOARD} Typing: {latency_typing_ms:g}ms',
            f'\N{HEAVY BLACK HEART} Heartbeat: {latency_heartbeat_ms:g}ms',
            f'\N{FILE CABINET} Database: {latency_database_ms:g}ms'
        ))
        stats = '\n'.join(stats)
        embed.description = stats

        embed.set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.avatar.url
        )

        await message.edit(embed=embed)





    @commands.command(name='serverinfo')
    @commands.guild_only()
    @commands.cooldown(1, 15, commands.BucketType.channel)
    async def client_serverinfo(self, ctx, streamer_friendly: bool = True):
        """Get information about the server you are currently in.

streamer_friendly: If yes, hides the server ID and the owner's discriminator.

Format referenced from the Ayana bot."""
        guild = ctx.author.guild

        created = utils.timedelta_string(
            relativedelta(
                datetime.datetime.now(datetime.timezone.utc),
                guild.created_at
            ),
            **self.DATETIME_DIFFERENCE_PRECISION,
            inflector=ctx.bot.inflector
        )
        count_text_ch = len(guild.text_channels)
        count_voice_ch = len(guild.voice_channels)
        owner = guild.owner or await guild.fetch_member(guild.owner_id)
        roles = guild.roles

        embed = discord.Embed(
            color=utils.get_user_color(ctx.bot, ctx.author),
            timestamp=datetime.datetime.now()
        )

        embed.set_author(name=guild.name)
        embed.set_thumbnail(url=guild.icon.url)
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
            value=owner.display_name if streamer_friendly else str(owner)
        )
        embed.add_field(
            name='Time of Server Creation',
            value='{} ago\n({})'.format(
                created, discord.utils.format_dt(guild.created_at, style='F')
            ),
            inline=False
        )
        embed.add_field(
            name=f"{len(roles):,} Role{'s' if len(roles) != 1 else ''}",
            value=', '.join([r.mention for r in roles]),
            inline=False
        )
        embed.set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.avatar.url
        )

        await ctx.send(embed=embed)





    @commands.command(name='timestamp')
    @commands.cooldown(1, 2, commands.BucketType.member)
    async def client_format_timestamp(
            self, ctx, style: Literal['t', 'T', 'd', 'D', 'f', 'F', 'R'],
            *, date: converters.DatetimeConverter = None):
        """Send a message with the special <t:0:f> timestamp format.
If no date is given, uses the current date.

Available styles:
    t: Short time (22:57)
    T: Long time (22:57:58)
    d: Short date (17/05/2016)
    D: Long date (17 May 2016)
    f: Short date-time (17 May 2016 22:57)
    F: Long date-time (Tuesday, 17 May 2016 22:57)
    R: Relative time (5 years ago)
The exact format of each style depends on your locale settings."""
        date = date or datetime.datetime.now()
        s = discord.utils.format_dt(date, style=style)
        # await ctx.send('{} ({})'.format(s, discord.utils.escape_markdown(s)))
        await ctx.send(
            '{} ({})'.format(
                re.sub(r'[<:>]', r'\\\g<0>', s), s
            )
        )


    @client_format_timestamp.error
    async def client_format_timestamp_error(self, ctx, error):
        handled = isinstance(error, commands.BadArgument)
        if handled:
            await ctx.send(error)
        ctx.handled = handled





    @commands.command(name='utctime', aliases=['utc'])
    @commands.cooldown(3, 15, commands.BucketType.member)
    async def client_timeutc(self, ctx):
        """Get the current date and time in UTC."""
        await ctx.send(time.asctime(time.gmtime()) + ' (UTC)')





    @commands.command(name='uptime')
    @commands.cooldown(2, 20, commands.BucketType.user)
    async def client_uptime(self, ctx):
        """Get the uptime of the bot."""
        # Calculate time diff (subtracting downtime)
        diff = relativedelta(
            datetime.datetime.now().astimezone(),
            self.bot.uptime_last_connect_adjusted
        )
        diff_string = utils.timedelta_string(diff, inflector=ctx.bot.inflector)

        timestamp = discord.utils.format_dt(
            ctx.bot.uptime_last_connect, style='F')

        embed = discord.Embed(
            title=f'Uptime: {timestamp}',
            description=f'{diff_string}',
            color=utils.get_bot_color(ctx.bot)
        )

        await ctx.send(embed=embed)





    @commands.command(name='userinfo')
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
            description = ''
            activity = user.activity
            # If presences or members intent are disabled, d.py returns
            # None for activity
            guild = user.guild
            joined = utils.timedelta_string(
                relativedelta(
                    datetime.datetime.now(datetime.timezone.utc),
                    user.joined_at
                ),
                **self.DATETIME_DIFFERENCE_PRECISION,
                inflector=ctx.bot.inflector
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
            description = '*For more information, use this command in a server.*'
            activity = None
            guild = None
            joined = None
            nickname = None
            roles = None
            status = None
        author = (f'{user} (Bot)' if user.bot
                  else f'{user.name}' if streamer_friendly
                  else str(user))
        created = utils.timedelta_string(
            relativedelta(
                datetime.datetime.now(datetime.timezone.utc),
                user.created_at
            ),
            **self.DATETIME_DIFFERENCE_PRECISION,
            inflector=ctx.bot.inflector
        )

        embed = discord.Embed(
            color=utils.get_user_color(ctx.bot, user),
            description=description,
            timestamp=datetime.datetime.now()
        )

        embed.set_author(name=author)  # icon_url=user.avatar.url
        embed.set_thumbnail(url=user.avatar.url)
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
                value='{} ago\n({})'.format(
                    joined, discord.utils.format_dt(user.joined_at, style='F')
                ),
                inline=False
            )
        embed.add_field(
            name='Time of User Creation',
            value='{} ago\n({})'.format(
                created, discord.utils.format_dt(user.created_at, style='F')
            ),
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
            icon_url=ctx.author.avatar.url
        )

        await ctx.send(embed=embed)










def setup(bot):
    bot.add_cog(Informative(bot))
