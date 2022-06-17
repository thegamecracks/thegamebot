#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import collections
import datetime
import re
import sys
import time
from typing import Optional, Literal

from dateutil.relativedelta import relativedelta
import discord
from discord.ext import commands
import humanize
import psutil

from bot import converters, utils
from main import Context, TheGameBot


def count_channel_types(
    guild: discord.Guild, member: discord.Member = None,
    *, simple=False
) -> collections.Counter[discord.ChannelType, int]:
    """Counts the different types of channels in a guild.

    :param guild: The guild to count channels in.
    :param member: A member to also consider in permission checking.
    :param simple: Aggregates different channel types into either text or voice.

    """
    counter = collections.Counter()

    for c in guild.channels:
        if not c.permissions_for(guild.me).view_channel:
            continue
        elif member is not None and not c.permissions_for(member).view_channel:
            continue
        elif not simple:
            counter[c.type] += 1
        elif isinstance(c, discord.TextChannel):
            counter[discord.ChannelType.text] += 1
        elif isinstance(c, discord.channel.VocalGuildChannel):
            counter[discord.ChannelType.voice] += 1

    return counter


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

    USERINFO_ACTIVITIES = {
        discord.ActivityType.playing: 'Playing',
        discord.ActivityType.listening: 'Listening to',
        discord.ActivityType.watching: 'Watching',
        discord.ActivityType.streaming: 'Streaming',
        discord.ActivityType.competing: 'Competing in'
    }

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.process = psutil.Process()

        if self.bot.help_command is not None:
            self.bot.help_command.cog = self

    def cog_unload(self):
        help_command = self.bot.help_command
        if help_command is not None:
            help_command.cog = None

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: Context):
        """Used for tracking processed commands."""
        self.bot.info_processed_commands[ctx.command.qualified_name] += 1

    @commands.command(aliases=('info',))
    @commands.cooldown(3, 60, commands.BucketType.guild)
    @commands.max_concurrency(3, wait=True)
    async def about(self, ctx: Context, *, options=''):
        """An about page for this bot.
Optional settings:
    -S --system: show system-related information about the bot."""
        embed = discord.Embed(
            title='About',
            description=(
                'I do whatever '
                '[**thegamecracks**](https://github.com/thegamecracks/thegamebot "This bot\'s GitHub repository") '
                'adds to me.'
            ),
            color=ctx.bot.get_bot_color()
        ).set_thumbnail(
            url=self.bot.user.display_avatar.url
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.display_avatar.url
        )

        vp = sys.version_info
        version_python = f'{vp.major}.{vp.minor}.{vp.micro}'

        start_time = datetime.datetime.fromtimestamp(self.process.create_time())
        start_time = discord.utils.format_dt(start_time)

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

        parser = utils.RaisingArgumentParser(add_help=False)
        parser.add_argument('--system', '-S', action='store_true')

        try:
            args = parser.split_and_parse(options)
        except (RuntimeError, ValueError):
            args = parser.parse_args([])

        if args.system:
            # Add system information
            p = self.process
            with p.oneshot():
                memory_info = p.memory_full_info()
                mem_phys = humanize.naturalsize(memory_info.uss)
                mem_virt = humanize.naturalsize(memory_info.vms)
                num_threads = p.num_threads()
                num_handles = p.num_handles()
                cpu = p.cpu_percent(interval=0.1)

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
    async def channel_info(self, ctx: Context):
        """Count the different types of channels in the server.

This only counts channels that both you and the bot can see."""
        counter = count_channel_types(ctx.guild, ctx.author)

        s = ['```yaml']
        count_length = max(len(str(v)) for v in counter.values())
        for c, count in counter.most_common():
            name = self.CHANNELINFO_TYPE_NAMES.get(c, str(c)).capitalize()
            s.append(f'{count:>{count_length}} : {name}')
        s.append('```')
        s = '\n'.join(s)

        embed = discord.Embed(
            description=s,
            color=ctx.bot.get_bot_color()
        ).set_footer(
            text=f'Requested by {ctx.author.display_name}',
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)





    @commands.command(name='commandinfo')
    @commands.cooldown(3, 15, commands.BucketType.user)
    async def command_info(self, ctx: Context, *, command: converters.CommandConverter):
        """Get statistics about a command."""
        def get_group_uses(stats, cmd):
            """Recursively count the uses of a command group."""
            uses = 0
            for sub in cmd.commands:
                if isinstance(sub, commands.Group):
                    uses += get_group_uses(stats, sub)
                uses += stats[sub.qualified_name]
            return uses

        command: commands.Command

        # Create a response
        embed = discord.Embed(
            title=command.qualified_name,
            color=ctx.bot.get_bot_color()
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.display_avatar.url
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
        mapping: commands.CooldownMapping = command._buckets
        if mapping._cooldown is not None:
            cooldown_type = self.COMMANDINFO_BUCKETTYPE_DESCRIPTIONS.get(
                mapping._type, '')
            description.append(
                'Cooldown settings: {}/{:.0f}s {}'.format(
                    mapping._cooldown.rate,
                    mapping._cooldown.per,
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

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def invite(self, ctx: Context):
        """Get the bot's invite link."""
        link = self.get_invite_link()
        embed = discord.Embed(
            description=link,
            color=ctx.bot.get_bot_color()
        ).set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def ping(self, ctx: Context):
        """Get the bot's latency."""
        def round_ms(n):
            return round(n * 100_000) / 1000

        async def time_ms(coro):
            start = time.perf_counter()
            await coro
            return round_ms(time.perf_counter() - start)

        async def poll_database():
            async with ctx.bot.db.connect() as conn:
                await conn.execute('SELECT 1')

        async def poll_message():
            nonlocal message
            message = await ctx.send(embed=embed)

        message: discord.Message
        embed = discord.Embed(
            title='Pong!',
            color=ctx.bot.get_bot_color()
        )

        task_database = asyncio.create_task(time_ms(poll_database()))
        task_message = asyncio.create_task(time_ms(poll_message()))
        task_typing = asyncio.create_task(time_ms(ctx.typing()))
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
            icon_url=ctx.author.display_avatar.url
        )

        await message.edit(embed=embed)

    @commands.command(name='serverinfo')
    @commands.guild_only()
    @commands.cooldown(1, 15, commands.BucketType.channel)
    async def server_info(self, ctx: Context, streamer_friendly: bool = True):
        """Get information about the server you are currently in.

streamer_friendly: If yes, hides the server ID and the owner's discriminator.

Format inspired by the bot Ayana."""
        guild = ctx.author.guild

        channel_count = count_channel_types(ctx.guild, ctx.author, simple=True)
        owner = guild.get_member(guild.owner_id) or await guild.fetch_member(guild.owner_id)
        roles = guild.roles

        embed = discord.Embed(
            color=ctx.bot.get_user_color(ctx.author),
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
            name='Members',
            value=guild.member_count
        )
        embed.add_field(
            name='Channels',
            value='{} text : {} voice'.format(
                channel_count[discord.ChannelType.text],
                channel_count[discord.ChannelType.voice]
            )
        )
        embed.add_field(
            name='Owner',
            value=owner.display_name if streamer_friendly else str(owner)
        )
        embed.add_field(
            name='Time of Server Creation',
            value=discord.utils.format_dt(guild.created_at, style='R'),
            inline=False
        )
        embed.add_field(
            name=f"{len(roles):,} Role{'s' if len(roles) != 1 else ''}",
            value=', '.join([r.mention for r in roles]),
            inline=False
        )
        embed.set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @commands.command(name='userinfo')
    @commands.cooldown(3, 20, commands.BucketType.user)
    async def user_info(
        self, ctx: Context,
        streamer_friendly: Optional[bool] = True,
        *, user=None
    ):
        """Get information about a user by name or mention.

streamer_friendly: If yes, hides the user's discriminator.
user: Can be referenced by name, nickname, name#discrim, or by mention.

https://youtu.be/CppEzOOXJ8E used as reference.
Format referenced from the Ayana bot."""
        # NOTE: when members intent is enabled, members from guilds
        # the bot is in can be accessed in DMs.
        if user is None:
            user = ctx.author
        elif ctx.guild is None:
            if not self.ALLOW_DISPLAYING_GUILD_MEMBERS_IN_DMS:
                return await ctx.send('Cannot search for members in DMs.')

            user = await commands.MemberConverter().convert(ctx, user)

            if user.id == self.bot.user.id:
                # Hide guild-related information
                user = self.bot.user

        # Extract attributes based on whether it's a Member or User
        author = (
            f'{user} (Bot)' if user.bot
            else f'{user.display_name}' if streamer_friendly
            else str(user)
        )
        description = '*For more information, use this command in a server.*'
        activity = None
        guild = None
        joined_at = None
        nickname = None
        roles = None
        status = None

        if isinstance(user, discord.Member):
            description = ''
            activity = user.activity  # None if members/presences intent is disabled
            guild = user.guild
            joined_at = user.joined_at
            nickname = user.nick
            roles = user.roles
            if len(roles) > 1:
                # Has a role(s); remove @everyone
                roles = roles[:0:-1]
            status = None
            # Check required intents before obtaining status
            # (since d.py returns Status.offline instead of None)
            if self.bot.intents.members and self.bot.intents.presences:
                if user.status == discord.Status.dnd:
                    status = 'Do Not Disturb'
                elif isinstance(user.status, discord.Status):
                    status = str(status).title()
                else:
                    # Status is unknown
                    status = None

        embed = discord.Embed(
            color=ctx.bot.get_user_color(user),
            description=description,
            timestamp=datetime.datetime.now()
        )

        embed.set_author(name=author)
        embed.set_thumbnail(url=user.display_avatar.url)
        if not streamer_friendly:
            embed.add_field(
                name='ID',
                value=user.id
            )
        embed.add_field(
            name='Mention',
            value=user.mention
        )
        if nickname is not None:
            embed.add_field(
                name='Nickname',
                value=nickname
            )
        if joined_at is not None:
            if guild != ctx.guild:
                # Queried in DMs; include guild name in join title
                joined_name = f'Time of joining {guild.name}'
            else:
                joined_name = 'Time of Server Join'

            embed.add_field(
                name=joined_name,
                value=discord.utils.format_dt(joined_at, style='R')
            )
        embed.add_field(
            name='Time of User Creation',
            value=discord.utils.format_dt(user.created_at, style='R')
        )
        if status is not None:
            embed.add_field(
                name='Status',
                value=status
            )
        if activity is not None:
            embed.add_field(
                name=self.USERINFO_ACTIVITIES.get(activity.type, 'Activity'),
                value=activity.name
            )
        if roles is not None:
            embed.add_field(
                name="{n:,} {roles}".format(
                    n=len(roles),
                    roles=ctx.bot.inflector.plural('Role', len(roles))
                ),
                value=', '.join([r.mention for r in roles]),
                inline=False
            )
        embed.set_footer(
            text=f'Requested by {ctx.author.name}',
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @commands.command(name='timestamp')
    @commands.cooldown(1, 2, commands.BucketType.member)
    async def format_timestamp(
        self, ctx: Context,
        style: Literal['t', 'T', 'd', 'D', 'f', 'F', 'R'] = None,
        *, date: converters.DatetimeConverter = None
    ):
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
        text = discord.utils.format_dt(date, style=style)

        # await ctx.send('{} ({})'.format(s, discord.utils.escape_markdown(s)))
        await ctx.send('{normal} {escaped}'.format(
            normal=text,
            escaped=re.sub(r'[<:>]', r'\\\g<0>', text)
        ))

    @commands.command()
    @commands.cooldown(2, 20, commands.BucketType.user)
    async def uptime(self, ctx: Context):
        """Get the uptime of the bot."""
        # Calculate time diff (subtracting downtime)
        diff = relativedelta(
            datetime.datetime.now().astimezone(),
            self.bot.uptime_last_connect_adjusted
        )

        timestamp = discord.utils.format_dt(ctx.bot.uptime_last_connect, style='F')
        diff_string = utils.timedelta_string(diff, inflector=ctx.bot.inflector)

        embed = discord.Embed(
            title=f'Uptime: {timestamp}',
            description=f'{diff_string}',
            color=ctx.bot.get_bot_color()
        )

        await ctx.send(embed=embed)


async def setup(bot: TheGameBot):
    await bot.add_cog(Informative(bot))
